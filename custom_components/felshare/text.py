from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.text import TextEntity, TextMode
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .coordinator import FelshareCoordinator
from .entity import FelshareEntity

_HHMM_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: FelshareCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    dev = coordinator.data.device_id

    async_add_entities(
        [
            FelshareOilNameText(coordinator, entry, dev),
            FelshareWorkStartText(coordinator, entry, dev),
            FelshareWorkEndText(coordinator, entry, dev),
        ]
    )


class FelshareOilNameText(FelshareEntity, TextEntity):
    _attr_has_entity_name = True
    _attr_name = "Oil name"
    _attr_entity_category = None
    _attr_suggested_object_id = "oil_name"
    _attr_icon = "mdi:flower"
    _attr_mode = TextMode.TEXT
    _attr_native_min = 0
    _attr_native_max = 32

    def __init__(self, coordinator: FelshareCoordinator, entry: ConfigEntry, dev: str) -> None:
        super().__init__(coordinator, entry, dev)
        self._attr_unique_id = f"{self._entry_id}_{dev}_oil_name"

    @property
    def native_value(self):
        return self.coordinator.data.oil_name

    async def async_set_value(self, value: str) -> None:
        self._raise_if_hvac_sync_locked()
        try:
            await self.hass.async_add_executor_job(self.coordinator.hub.publish_oil_name, value)
        except Exception as e:
            raise HomeAssistantError(str(e))


class FelshareWorkStartText(FelshareEntity, TextEntity):
    _attr_has_entity_name = True
    _attr_name = "Work start (HH:MM)"
    _attr_entity_category = None
    _attr_suggested_object_id = "01_work_start"
    _attr_icon = "mdi:clock-start"
    _attr_mode = TextMode.TEXT
    _attr_pattern = _HHMM_PATTERN
    _attr_native_min = 5
    _attr_native_max = 5

    def __init__(self, coordinator: FelshareCoordinator, entry: ConfigEntry, dev: str) -> None:
        super().__init__(coordinator, entry, dev)
        self._attr_unique_id = f"{self._entry_id}_{dev}_work_start"

    @property
    def native_value(self):
        return self.coordinator.data.work_start

    async def async_set_value(self, value: str) -> None:
        self._raise_if_hvac_sync_locked()
        try:
            await self.hass.async_add_executor_job(self.coordinator.hub.publish_work_start, value)
            ctl = self.hass.data.get(DOMAIN, {}).get(self._entry.entry_id, {}).get("hvac_sync")
            if ctl is not None:
                await ctl.async_evaluate(force=True)
        except Exception as e:
            raise HomeAssistantError(str(e))


class FelshareWorkEndText(FelshareEntity, TextEntity):
    _attr_has_entity_name = True
    _attr_name = "Work end (HH:MM)"
    _attr_entity_category = None
    _attr_suggested_object_id = "02_work_end"
    _attr_icon = "mdi:clock-end"
    _attr_mode = TextMode.TEXT
    _attr_pattern = _HHMM_PATTERN
    _attr_native_min = 5
    _attr_native_max = 5

    def __init__(self, coordinator: FelshareCoordinator, entry: ConfigEntry, dev: str) -> None:
        super().__init__(coordinator, entry, dev)
        self._attr_unique_id = f"{self._entry_id}_{dev}_work_end"

    @property
    def native_value(self):
        return self.coordinator.data.work_end

    async def async_set_value(self, value: str) -> None:
        self._raise_if_hvac_sync_locked()
        try:
            await self.hass.async_add_executor_job(self.coordinator.hub.publish_work_end, value)
            ctl = self.hass.data.get(DOMAIN, {}).get(self._entry.entry_id, {}).get("hvac_sync")
            if ctl is not None:
                await ctl.async_evaluate(force=True)
        except Exception as e:
            raise HomeAssistantError(str(e))
