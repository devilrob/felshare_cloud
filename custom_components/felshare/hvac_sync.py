from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time as dtime, timedelta
import logging
from typing import Callable, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    CONF_HVAC_SYNC_ENABLED,
    CONF_HVAC_SYNC_CLIMATE_ENTITY,
    CONF_HVAC_SYNC_ON_DELAY_SECONDS,
    CONF_HVAC_SYNC_OFF_DELAY_SECONDS,
    DEFAULT_HVAC_SYNC_ENABLED,
    DEFAULT_HVAC_SYNC_ON_DELAY_SECONDS,
    DEFAULT_HVAC_SYNC_OFF_DELAY_SECONDS,
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


def _is_cooling(state: State | None) -> bool:
    if state is None:
        return False
    if state.state in ("unknown", "unavailable", None):
        return False

    # Preferred attribute for "actively cooling"
    action = state.attributes.get("hvac_action")
    if action is None:
        # Some climate integrations use current_operation
        action = state.attributes.get("current_operation")
    if action is not None:
        return str(action).lower() == "cooling"

    # Fallbacks
    return str(state.state).lower() == "cooling"


@dataclass
class HvacSyncStatus:
    enabled: bool = False
    climate_entity: str | None = None
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

        self.status = HvacSyncStatus()
        self._unsub_state: Optional[Callable[[], None]] = None
        self._unsub_timer: Optional[Callable[[], None]] = None
        self._subscribed_entity: str | None = None

        self._last_desired: bool | None = None
        self._pending_target: bool | None = None
        self._pending_until: float | None = None

    async def async_start(self) -> None:
        # Periodic enforcement for schedule boundaries (and in case climate doesn't emit updates)
        self._unsub_timer = async_track_time_interval(self.hass, self._handle_tick, timedelta(seconds=60))
        await self._ensure_subscription()
        await self.async_evaluate(force=True)

    async def async_stop(self) -> None:
        if self._unsub_state:
            self._unsub_state()
            self._unsub_state = None
        if self._unsub_timer:
            self._unsub_timer()
            self._unsub_timer = None

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
        cooling = _is_cooling(st)

        schedule_ok = bool(start_s and end_s and days_mask)
        in_window = _in_schedule(now, days_mask=days_mask, start=start, end=end) if (enabled and schedule_ok) else False

        self.logger.debug(
            "HVACSync eval: enabled=%s climate=%s hvac_action=%s in_window=%s work_start=%s work_end=%s days_mask=0x%02X on_delay=%ss off_delay=%ss",
            enabled,
            climate_entity,
            (st.attributes.get("hvac_action") if st else None),
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
        elif not cooling:
            desired = False
            reason = "hvac_not_cooling"
        else:
            desired = True
            reason = "cooling_in_schedule"

        self.status.enabled = enabled
        self.status.climate_entity = climate_entity
        self.status.cooling = cooling
        self.status.in_window = in_window
        self.status.desired_power = desired
        self.status.last_reason = reason

        # If disabled, clear pending and stop enforcing.
        if not enabled:
            self._last_desired = None
            self._pending_target = None
            self._pending_until = None
            self.status.pending_until_ts = None
            return

        # If we have a pending change, wait until its due.
        if self._pending_target is not None and self._pending_until is not None:
            if now_ts < self._pending_until:
                self.status.pending_until_ts = self._pending_until
                self.logger.debug(
                    "HVACSync pending: target=%s apply_in=%.1fs reason=%s",
                    self._pending_target,
                    self._pending_until - now_ts,
                    reason,
                )
                return
            # Pending time reached, apply
            desired = self._pending_target
            self._pending_target = None
            self._pending_until = None
            self.status.pending_until_ts = None

        # When desired flips, apply delay (unless forced)
        if not force and self._last_desired is not None and desired != self._last_desired:
            delay = on_delay if desired else off_delay
            if delay > 0:
                self._pending_target = desired
                self._pending_until = now_ts + float(delay)
                self.status.pending_until_ts = self._pending_until
                self.logger.debug(
                    "HVACSync delayed: desired=%s delay=%ss reason=%s",
                    desired,
                    delay,
                    reason,
                )
                return

        self._last_desired = desired

        # Don't act if diffuser is disconnected
        if not getattr(self.coordinator.data, "connected", False):
            return

        current_work = getattr(self.coordinator.data, "work_enabled", None)
        if current_work is None:
            # If unknown, avoid toggling aggressively.
            return

        if current_work == desired:
            return

        # Apply action
        try:
            self.logger.info(
                "HVACSync action: set_work_schedule=%s (current=%s) reason=%s",
                desired,
                current_work,
                reason,
            )
            await self.hass.async_add_executor_job(self.coordinator.hub.publish_work_enabled, desired)
            self.status.last_action_ts = now_ts
        except Exception as e:
            self.status.last_reason = f"error: {e}"
            self.logger.warning("HVACSync publish_work_enabled failed: %s", e)
