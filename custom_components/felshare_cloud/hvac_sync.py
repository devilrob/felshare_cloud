from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time as dtime, timedelta
import logging
from typing import Callable, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers.event import async_call_later, async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    CONF_HVAC_SYNC_ENABLED,
    CONF_HVAC_SYNC_CLIMATE_ENTITY,
    CONF_HVAC_SYNC_ON_DELAY_SECONDS,
    CONF_HVAC_SYNC_OFF_DELAY_SECONDS,
    CONF_HVAC_SYNC_AIRFLOW_MODE,
    HVAC_SYNC_FORCED_WORK_RUN_S,
    HVAC_SYNC_FORCED_WORK_STOP_S,
    DEFAULT_HVAC_SYNC_ENABLED,
    DEFAULT_HVAC_SYNC_ON_DELAY_SECONDS,
    DEFAULT_HVAC_SYNC_OFF_DELAY_SECONDS,
    DEFAULT_HVAC_SYNC_AIRFLOW_MODE,
)


# Days mask bits (device convention): Sun=1, Mon=2, Tue=4, Wed=8, Thu=16, Fri=32, Sat=64
_WEEKDAY_TO_BIT = [0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x01]  # Mon..Sun


def _parse_hhmm(value: str | None, default: str = "00:00") -> dtime:
    s = (value or default or "00:00").strip()
    try:
        hh, mm = s.split(":", 1)
        return dtime(hour=int(hh), minute=int(mm))
    except Exception:
        # Fallback to midnight
        return dtime(hour=0, minute=0)


def _now_local(hass: HomeAssistant) -> datetime:
    # dt_util.now() is timezone-aware and uses HA's configured TZ.
    return dt_util.now()


def _in_schedule(now: datetime, *, days_mask: int, start: dtime, end: dtime) -> bool:
    # Day check
    bit = _WEEKDAY_TO_BIT[now.weekday()]
    if not (days_mask & bit):
        return False

    # Time window check
    t = now.timetz().replace(tzinfo=None)
    if start == end:
        # Treat as always-on for that day
        return True
    if start < end:
        return start <= t < end
    # Overnight window (e.g., 22:00–06:00)
    return t >= start or t < end


def _hvac_action(state: State | None) -> str | None:
    """Return best-effort hvac_action/current_operation string."""
    if state is None:
        return None
    if state.state in ("unknown", "unavailable", None):
        return None
    action = state.attributes.get("hvac_action")
    if action is None:
        action = state.attributes.get("current_operation")
    if action is None:
        return None
    try:
        s = str(action).strip().lower()
        return s or None
    except Exception:
        return None


def _is_airflow_active(state: State | None, mode: str) -> bool:
    """Decide if the HVAC is "running air" based on hvac_action.

    We intentionally use hvac_action (runtime state) vs hvac_mode (setpoint mode).
    """
    # Safety: if the thermostat is explicitly OFF, treat airflow as inactive even if
    # some integrations briefly keep a stale hvac_action.
    if state is not None:
        try:
            if str(state.state).strip().lower() == "off":
                return False
        except Exception:
            pass

    act = _hvac_action(state)
    if act is None:
        return False

    mode = (mode or "").strip().lower()

    if mode in ("cooling_only", "cool_only", "cooling"):
        return act == "cooling"

    if mode in ("heat_cool", "heat+cool", "heat_cool_only", "heat_and_cool"):
        return act in ("cooling", "heating")

    # "Any airflow" tries to catch fan-only patterns across integrations.
    if mode in ("any_airflow", "any", "airflow", "heat_cool_fan"):
        return act in ("cooling", "heating", "fan", "fan_only", "fan-only")

    # Unknown -> default to cooling-only
    return act == "cooling"


@dataclass
class HvacSyncStatus:
    enabled: bool = False
    climate_entity: str | None = None
    airflow_mode: str | None = None
    in_window: bool = False
    cooling: bool = False
    desired_power: bool = False
    last_reason: str | None = None
    last_action_ts: float | None = None
    pending_until_ts: float | None = None


class FelshareHvacSyncController:
    """Optionally sync the diffuser Work schedule with a HA climate entity.

    Goals:
    - Simple UX: HVAC Sync reuses the diffuser's own Work schedule (days + start/end)
      so the user doesn't have to configure two separate schedules.
    - Safe behavior: avoid rapid toggles via on/off delays and rely on MQTT rate limiting.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, coordinator) -> None:
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        self.logger = logging.getLogger(__name__)

        # Persist the last known manual settings so we can restore them when HVAC Sync is turned off.
        # Stored per config entry (and survives HA restarts).
        self._manual_store: Store = Store(hass, 1, f"{DOMAIN}.manual_snapshot_{entry.entry_id}")
        self._manual_snapshot: dict | None = None
        self._restore_pending: bool = False
        self._sync_params_pending: bool = False
        self._prev_enabled: bool | None = None

        # If the device is offline when HVAC Sync is enabled, we may need to
        # apply the forced Work run/stop values later.
        self._forced_work_pending: bool = False

        self.status = HvacSyncStatus()
        self._unsub_state: Optional[Callable[[], None]] = None
        self._unsub_timer: Optional[Callable[[], None]] = None
        self._unsub_pending: Optional[Callable[[], None]] = None
        self._subscribed_entity: str | None = None

        self._last_desired: bool | None = None
        self._pending_target: bool | None = None
        self._pending_until: float | None = None

        # NOTE: manual controls are locked while HVAC Sync is ON (Option 2).

    def _cancel_pending_timer(self) -> None:
        if self._unsub_pending:
            try:
                self._unsub_pending()
            except Exception:
                pass
            self._unsub_pending = None

    def _arm_pending_timer(self, delay_s: float) -> None:
        """Ensure we wake up when a pending on/off delay expires."""
        self._cancel_pending_timer()

        # Never schedule negative; also avoid 0 which would call immediately and can recurse.
        delay_s = max(0.01, float(delay_s))

        @callback
        def _due(_now) -> None:
            # Clear the handle first to avoid stale cancels.
            self._unsub_pending = None
            # Force evaluation so we don't re-arm the same delay again.
            self.hass.async_create_task(self.async_evaluate(force=True))

        self._unsub_pending = async_call_later(self.hass, delay_s, _due)

    async def async_start(self) -> None:
        # Load last manual snapshot (if any)
        try:
            data = await self._manual_store.async_load()
            if isinstance(data, dict) and data.get("device_id"):
                self._manual_snapshot = data
        except Exception:
            self._manual_snapshot = None

        # Remember initial enabled state so first user toggle is treated as a transition.
        self._prev_enabled = bool(self._opts().get(CONF_HVAC_SYNC_ENABLED, DEFAULT_HVAC_SYNC_ENABLED))

        # Periodic enforcement for schedule boundaries (and in case climate doesn't emit updates)
        self._unsub_timer = async_track_time_interval(self.hass, self._handle_tick, timedelta(seconds=60))
        await self._ensure_subscription()
        await self.async_evaluate(force=True)

    async def _async_save_manual_snapshot(self, snap: dict) -> None:
        self._manual_snapshot = snap
        try:
            await self._manual_store.async_save(snap)
        except Exception:
            # Best-effort persistence; continue anyway
            pass

    async def _async_capture_manual_snapshot(self) -> None:
        """Capture the current diffuser settings as the "manual" baseline.

        Called when HVAC Sync transitions from OFF -> ON.
        """
        d = self.coordinator.data
        snap = {
            "device_id": getattr(d, "device_id", None),
            "captured_ts": _now_local(self.hass).timestamp(),
            "power_on": d.power_on,
            "fan_on": d.fan_on,
            "oil_name": d.oil_name,
            "work": {
                "start": d.work_start,
                "end": d.work_end,
                "run_s": d.work_run_s,
                "stop_s": d.work_stop_s,
                "enabled": d.work_enabled,
                "days_mask": d.work_days_mask,
            },
        }
        await self._async_save_manual_snapshot(snap)

    async def _async_apply_forced_work_params(self) -> None:
        """Force Work run/stop cadence while HVAC Sync is enabled.

        This is a safety/UX feature requested for setups where the diffuser is
        expected to follow HVAC runtime, but the device itself caps run/stop at
        0..999 seconds. We keep Work mode armed and use Power ON/OFF for gating.
        """

        # If disconnected, postpone until we see a connected state again.
        if not getattr(self.coordinator.data, "connected", False):
            self._sync_params_pending = True
            return

        self._sync_params_pending = False

        def _apply_blocking() -> None:
            hub = self.coordinator.hub
            # Only update run/stop (and keep work mode enabled while sync is active).
            hub.publish_work_schedule(
                run_s=int(HVAC_SYNC_FORCED_WORK_RUN_S),
                stop_s=int(HVAC_SYNC_FORCED_WORK_STOP_S),
                enabled=True,
            )

        try:
            await self.hass.async_add_executor_job(_apply_blocking)
        except Exception as e:
            self.status.last_reason = f"sync_params_error: {e}"
            self.logger.warning("HVACSync could not apply forced work run/stop: %s", e)

    async def _async_restore_manual_snapshot(self) -> None:
        """Restore the last saved manual settings back to the device."""
        snap = self._manual_snapshot
        if not isinstance(snap, dict):
            # Try load on-demand
            try:
                data = await self._manual_store.async_load()
                if isinstance(data, dict):
                    snap = data
                    self._manual_snapshot = data
            except Exception:
                snap = None

        if not isinstance(snap, dict):
            return

        # If disconnected, postpone restore until we see a connected state again.
        if not getattr(self.coordinator.data, "connected", False):
            self._restore_pending = True
            return

        self._restore_pending = False

        work = snap.get("work") if isinstance(snap.get("work"), dict) else {}
        power_on = snap.get("power_on")
        fan_on = snap.get("fan_on")
        oil_name = snap.get("oil_name")

        def _restore_blocking() -> None:
            hub = self.coordinator.hub

            # Restore schedule settings in a single WorkTime publish (avoids multiple MQTT writes).
            hub.publish_work_schedule(
                start=work.get("start"),
                end=work.get("end"),
                run_s=work.get("run_s"),
                stop_s=work.get("stop_s"),
                enabled=work.get("enabled"),
                days_mask=work.get("days_mask"),
            )

            if oil_name is not None:
                hub.publish_oil_name(str(oil_name))
            if fan_on is not None:
                hub.publish_fan(bool(fan_on))
            if power_on is not None:
                hub.publish_power(bool(power_on))

        try:
            await self.hass.async_add_executor_job(_restore_blocking)
        except Exception as e:
            self.status.last_reason = f"restore_error: {e}"
            self.logger.warning("HVACSync restore failed: %s", e)

    async def async_stop(self) -> None:
        if self._unsub_state:
            self._unsub_state()
            self._unsub_state = None
        if self._unsub_timer:
            self._unsub_timer()
            self._unsub_timer = None
        self._cancel_pending_timer()

    def _opts(self):
        return self.entry.options

    async def _ensure_subscription(self) -> None:
        entity = self._opts().get(CONF_HVAC_SYNC_CLIMATE_ENTITY) or None
        if entity == self._subscribed_entity:
            return

        # Unsubscribe old
        if self._unsub_state:
            self._unsub_state()
            self._unsub_state = None

        self._subscribed_entity = entity
        if not entity:
            return

        self._unsub_state = async_track_state_change_event(
            self.hass,
            [entity],
            self._handle_climate_event,
        )

    @callback
    def _handle_climate_event(self, event) -> None:
        # Evaluate ASAP when climate changes
        self.hass.async_create_task(self.async_evaluate())

    @callback
    def _handle_tick(self, now) -> None:
        self.hass.async_create_task(self.async_evaluate())

    async def async_evaluate(self, *, force: bool = False) -> None:
        await self._ensure_subscription()

        opts = self._opts()
        enabled = bool(opts.get(CONF_HVAC_SYNC_ENABLED, DEFAULT_HVAC_SYNC_ENABLED))
        climate_entity = (opts.get(CONF_HVAC_SYNC_CLIMATE_ENTITY) or "").strip() or None
        airflow_mode = (opts.get(CONF_HVAC_SYNC_AIRFLOW_MODE) or DEFAULT_HVAC_SYNC_AIRFLOW_MODE).strip() or DEFAULT_HVAC_SYNC_AIRFLOW_MODE

        # Track transitions to support:
        #  - OFF -> ON : capture a manual snapshot (persistent)
        #  - ON -> OFF : restore the last manual snapshot
        if self._prev_enabled is None:
            self._prev_enabled = enabled
        elif enabled and not self._prev_enabled:
            # Capture baseline BEFORE HVAC Sync starts changing the device schedule.
            await self._async_capture_manual_snapshot()
            # Force Work run/stop cadence while HVAC Sync is active.
            await self._async_apply_forced_work_params()
        elif (not enabled) and self._prev_enabled:
            # Restore manual state when HVAC Sync is turned off.
            await self._async_restore_manual_snapshot()

        # If HVAC Sync is disabled but we previously couldn't restore (device offline),
        # attempt restore once the device comes back online.
        if (not enabled) and self._restore_pending and getattr(self.coordinator.data, "connected", False):
            await self._async_restore_manual_snapshot()

        # If HVAC Sync is enabled but we couldn't apply forced run/stop earlier (device offline),
        # retry once the device comes back online.
        if enabled and self._sync_params_pending and getattr(self.coordinator.data, "connected", False):
            await self._async_apply_forced_work_params()

        self._prev_enabled = enabled
        # HVAC Sync schedule window is taken from the diffuser's own Work schedule.
        d = self.coordinator.data
        days_mask = int(d.work_days_mask or 0) & 0x7F
        start_s = (d.work_start or "").strip() or None
        end_s = (d.work_end or "").strip() or None
        start = _parse_hhmm(start_s)
        end = _parse_hhmm(end_s)

        on_delay = int(opts.get(CONF_HVAC_SYNC_ON_DELAY_SECONDS, DEFAULT_HVAC_SYNC_ON_DELAY_SECONDS) or 0)
        off_delay = int(opts.get(CONF_HVAC_SYNC_OFF_DELAY_SECONDS, DEFAULT_HVAC_SYNC_OFF_DELAY_SECONDS) or 0)

        now = _now_local(self.hass)
        now_ts = now.timestamp()

        st = self.hass.states.get(climate_entity) if climate_entity else None
        airflow_active = _is_airflow_active(st, airflow_mode)

        schedule_ok = bool(start_s and end_s and days_mask)

        # Enforce forced run/stop values while HVAC Sync is enabled. This covers
        # cases where the user changes settings from the phone app while Sync is ON.
        if enabled and schedule_ok and getattr(self.coordinator.data, "connected", False):
            cur_run = getattr(d, "work_run_s", None)
            cur_stop = getattr(d, "work_stop_s", None)
            if cur_run is not None and cur_stop is not None:
                if int(cur_run) != int(HVAC_SYNC_FORCED_WORK_RUN_S) or int(cur_stop) != int(HVAC_SYNC_FORCED_WORK_STOP_S):
                    await self._async_apply_forced_work_params()
        in_window = _in_schedule(now, days_mask=days_mask, start=start, end=end) if (enabled and schedule_ok) else False

        self.logger.debug(
            "HVACSync eval: enabled=%s climate=%s hvac_action=%s airflow_mode=%s airflow_active=%s in_window=%s work_start=%s work_end=%s days_mask=0x%02X on_delay=%ss off_delay=%ss",
            enabled,
            climate_entity,
            (st.attributes.get("hvac_action") if st else None),
            airflow_mode,
            airflow_active,
            in_window,
            (start_s or ""),
            (end_s or ""),
            days_mask,
            on_delay,
            off_delay,
        )

        # Decide desired power
        if not enabled:
            # When HVAC Sync is disabled, do not override the diffuser schedule.
            desired = False
            reason = "disabled"
        elif not climate_entity:
            desired = False
            reason = "no_thermostat_selected"
        elif not schedule_ok:
            desired = False
            reason = "work_schedule_not_configured"
        elif not in_window:
            desired = False
            reason = "out_of_schedule"
        elif not airflow_active:
            desired = False
            reason = "hvac_airflow_inactive"
        else:
            desired = True
            reason = "airflow_active_in_schedule"

        self.status.enabled = enabled
        self.status.climate_entity = climate_entity
        self.status.airflow_mode = airflow_mode
        # Keep attribute name "cooling" for backwards compatibility in diagnostics;
        # value means "airflow active" per airflow_mode.
        self.status.cooling = airflow_active
        self.status.in_window = in_window
        self.status.desired_power = desired
        self.status.last_reason = reason

        # If disabled, clear pending and stop enforcing.
        if not enabled:
            self._last_desired = None
            self._pending_target = None
            self._pending_until = None
            self.status.pending_until_ts = None
            self._cancel_pending_timer()
            return

        # Track the instantaneous decision separately from a delayed/pending decision.
        desired_now = bool(desired)
        applied_from_pending = False

        # If we have a pending change, keep waiting unless it's due OR the desired state changed.
        if self._pending_target is not None and self._pending_until is not None:
            if now_ts < self._pending_until:
                if desired_now != bool(self._pending_target):
                    # Desired changed while we were waiting -> restart the delay from *now*.
                    delay = on_delay if desired_now else off_delay
                    if delay <= 0:
                        self._pending_target = None
                        self._pending_until = None
                        self.status.pending_until_ts = None
                        self._cancel_pending_timer()
                    else:
                        self._pending_target = desired_now
                        self._pending_until = now_ts + float(delay)
                        self.status.pending_until_ts = self._pending_until
                        self._arm_pending_timer(self._pending_until - now_ts)
                        self.logger.debug(
                            "HVACSync pending retargeted: target=%s apply_in=%.1fs reason=%s",
                            self._pending_target,
                            self._pending_until - now_ts,
                            reason,
                        )
                        return
                else:
                    self.status.pending_until_ts = self._pending_until
                    self.logger.debug(
                        "HVACSync pending: target=%s apply_in=%.1fs reason=%s",
                        self._pending_target,
                        self._pending_until - now_ts,
                        reason,
                    )
                    return

            # Pending time reached.
            if desired_now == bool(self._pending_target):
                desired_now = bool(self._pending_target)
                applied_from_pending = True
            # Either way, clear pending.
            self._pending_target = None
            self._pending_until = None
            self.status.pending_until_ts = None
            self._cancel_pending_timer()

        # When desired flips, apply delay (unless forced OR we're applying a delay that already elapsed).
        if (
            (not force)
            and (not applied_from_pending)
            and (self._last_desired is not None)
            and (desired_now != bool(self._last_desired))
        ):
            delay = on_delay if desired_now else off_delay
            if delay > 0:
                self._pending_target = desired_now
                self._pending_until = now_ts + float(delay)
                self.status.pending_until_ts = self._pending_until
                self._arm_pending_timer(self._pending_until - now_ts)
                self.logger.debug(
                    "HVACSync delayed: desired=%s delay=%ss reason=%s",
                    desired_now,
                    delay,
                    reason,
                )
                return

        desired = desired_now
        self._last_desired = desired

        # Don't act if diffuser is disconnected
        if not getattr(self.coordinator.data, "connected", False):
            return

        # IMPORTANT: Some Felshare models require Work schedule (work mode) to stay enabled,
        # otherwise a Power ON command has no effect.
        #
        # Therefore HVAC Sync **never disables work mode**. We "gate" diffusion by toggling
        # the main Power switch instead.

        current_work = getattr(self.coordinator.data, "work_enabled", None)
        current_power = getattr(self.coordinator.data, "power_on", None)
        if current_power is None:
            # If unknown, avoid toggling aggressively.
            return

        # When Sync is enabled and schedule is configured, ensure Work mode is ON (armed).
        # We only ever set it to True here; restoration happens when Sync is turned off.
        if schedule_ok and current_work is False:
            try:
                self.logger.info("HVACSync precondition: enabling Work schedule (required for Power control)")
                await self.hass.async_add_executor_job(self.coordinator.hub.publish_work_enabled, True)
            except Exception as e:
                self.status.last_reason = f"error: {e}"
                self.logger.warning("HVACSync could not enable Work schedule: %s", e)
                # If we can't arm work mode, don't spam power toggles.
                return

        if bool(current_power) == bool(desired):
            return

        # Apply action (Power gate)
        try:
            self.logger.info(
                "HVACSync action: set_power=%s (current=%s) reason=%s",
                desired,
                current_power,
                reason,
            )
            await self.hass.async_add_executor_job(self.coordinator.hub.publish_power, bool(desired))
            self.status.last_action_ts = now_ts
        except Exception as e:
            self.status.last_reason = f"error: {e}"
            self.logger.warning("HVACSync publish_power failed: %s", e)
