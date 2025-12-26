from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.exceptions import HomeAssistantError

from .const import (
    DOMAIN,
    FRONT_URL,
    OFFLINE_AFTER_MINUTES,
    CONF_DEVICE_NAME,
    CONF_DEVICE_MODEL,
    CONF_HVAC_SYNC_ENABLED,
    DEFAULT_HVAC_SYNC_ENABLED,
)
from .coordinator import FelshareCoordinator


class FelshareEntity(CoordinatorEntity[FelshareCoordinator]):
    """Common base for all Felshare entities.

    - Provides consistent Device Info (name/model/config URL)
    - Implements a safer availability policy (offline after N minutes without updates)
    """

    def __init__(self, coordinator: FelshareCoordinator, entry: ConfigEntry, dev: str) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._entry_id = entry.entry_id
        self._dev = dev

    @property
    def device_info(self) -> DeviceInfo:
        name = self._entry.data.get(CONF_DEVICE_NAME) or f"Felshare {self._dev}"
        model = self._entry.data.get(CONF_DEVICE_MODEL) or "Smart Diffuser"
        return DeviceInfo(
            identifiers={(DOMAIN, self._dev)},
            name=name,
            manufacturer="Felshare",
            model=model,
            configuration_url=FRONT_URL,
        )

    @property
    def available(self) -> bool:
        data = self.coordinator.data
        if data.connected:
            return True
        if not data.last_seen:
            return False
        try:
            return (datetime.utcnow() - data.last_seen) < timedelta(minutes=OFFLINE_AFTER_MINUTES)
        except Exception:
            # If something goes weird with timestamps, prefer not to flip entities to unavailable.
            return True

    # ---------------- UX helpers ----------------
    def _hvac_sync_enabled(self) -> bool:
        """Return True when HVAC Sync mode is enabled for this config entry."""
        try:
            return bool(self._entry.options.get(CONF_HVAC_SYNC_ENABLED, DEFAULT_HVAC_SYNC_ENABLED))
        except Exception:
            return False

    def _raise_if_hvac_sync_locked(self) -> None:
        """Block manual edits while HVAC Sync is enabled (Option 2)."""
        if self._hvac_sync_enabled():
            raise HomeAssistantError(
                "HVAC Sync is enabled: manual diffuser controls are locked. Disable 'HVAC sync' to edit settings."
            )
