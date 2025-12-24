from __future__ import annotations

from datetime import time as dtime

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    CONF_HVAC_SYNC_START,
    CONF_HVAC_SYNC_END,
    DEFAULT_HVAC_SYNC_START,
    DEFAULT_HVAC_SYNC_END,
)
from .coordinator import FelshareCoordinator
from .entity import FelshareEntity


def _parse(value: str | None, default: str) -> dtime:
    s = (value or default or "00:00").strip()
    try:
        hh, mm = s.split(":", 1)
        return dtime(hour=int(hh), minute=int(mm))
    except Exception:
        return dtime(hour=0, minute=0)


def _fmt(t: dtime) -> str:
    return f"{t.hour:02d}:{t.minute:02d}"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: FelshareCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    dev = coordinator.data.device_id
    async_add_entities(
        [
            FelshareHvacSyncStartTime(coordinator, entry, dev),
            FelshareHvacSyncEndTime(coordinator, entry, dev),
        ]
    )


class _BaseHvacTime(FelshareEntity, TimeEntity):
    _attr_entity_category = None
    _attr_icon = "mdi:clock-outline"

    _key: str
    _default: str

    @property
    def native_value(self) -> dtime | None:
        v = (self._entry.options.get(self._key) or "").strip()
        return _parse(v, self._default)

    async def async_set_value(self, value: dtime) -> None:
        new_opts = dict(self._entry.options)
        new_opts[self._key] = _fmt(value)
        self.hass.config_entries.async_update_entry(self._entry, options=new_opts)

        ctl = self.hass.data.get(DOMAIN, {}).get(self._entry.entry_id, {}).get("hvac_sync")
        if ctl is not None:
            await ctl.async_evaluate(force=True)

        self.async_write_ha_state()


class FelshareHvacSyncStartTime(_BaseHvacTime):
    _attr_has_entity_name = True
    _attr_name = "HVAC sync start"
    _attr_suggested_object_id = "91_hvac_sync_start"

    _key = CONF_HVAC_SYNC_START
    _default = DEFAULT_HVAC_SYNC_START

    def __init__(self, coordinator: FelshareCoordinator, entry: ConfigEntry, dev: str) -> None:
        super().__init__(coordinator, entry, dev)
        self._attr_unique_id = f"{self._entry_id}_{dev}_hvac_sync_start"


class FelshareHvacSyncEndTime(_BaseHvacTime):
    _attr_has_entity_name = True
    _attr_name = "HVAC sync end"
    _attr_suggested_object_id = "92_hvac_sync_end"

    _key = CONF_HVAC_SYNC_END
    _default = DEFAULT_HVAC_SYNC_END

    def __init__(self, coordinator: FelshareCoordinator, entry: ConfigEntry, dev: str) -> None:
        super().__init__(coordinator, entry, dev)
        self._attr_unique_id = f"{self._entry_id}_{dev}_hvac_sync_end"
