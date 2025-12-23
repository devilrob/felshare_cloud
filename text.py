from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.text import TextEntity
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .coordinator import FelshareCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: FelshareCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    dev = coordinator.data.device_id

    async_add_entities(
        [
            FelshareOilNameText(coordinator, entry.entry_id, dev),
            FelshareWorkStartText(coordinator, entry.entry_id, dev),
            FelshareWorkEndText(coordinator, entry.entry_id, dev),        ]
    )


class _Base(CoordinatorEntity[FelshareCoordinator]):
    def __init__(self, coordinator: FelshareCoordinator, entry_id: str, dev: str) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._dev = dev

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._dev)},
            "name": f"Felshare {self._dev}",
            "manufacturer": "Felshare",
            "model": "Cloud MQTT Device",
        }

    @property
    def available(self) -> bool:
        data = self.coordinator.data
        return bool(data and (data.connected or data.last_seen))


class FelshareOilNameText(_Base, TextEntity):
    _attr_has_entity_name = True
    _attr_name = "Oil name"
    _attr_native_min = 0
    _attr_native_max = 10

    def __init__(self, coordinator: FelshareCoordinator, entry_id: str, dev: str) -> None:
        super().__init__(coordinator, entry_id, dev)
        self._attr_unique_id = f"{entry_id}_{dev}_oil_name"

    @property
    def native_value(self):
        return self.coordinator.data.oil_name

    async def async_set_value(self, value: str) -> None:
        await self.hass.async_add_executor_job(self.coordinator.hub.publish_oil_name, value)


class FelshareWorkStartText(_Base, TextEntity):
    _attr_has_entity_name = True
    _attr_name = "Work start (HH:MM)"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_suggested_object_id = "01_work_start"
    _attr_native_min = 0
    _attr_native_max = 5

    def __init__(self, coordinator: FelshareCoordinator, entry_id: str, dev: str) -> None:
        super().__init__(coordinator, entry_id, dev)
        self._attr_unique_id = f"{entry_id}_{dev}_work_start"

    @property
    def native_value(self):
        return self.coordinator.data.work_start

    async def async_set_value(self, value: str) -> None:
        try:
            await self.hass.async_add_executor_job(self.coordinator.hub.publish_work_start, value)
        except Exception as e:
            raise HomeAssistantError(str(e))


class FelshareWorkEndText(_Base, TextEntity):
    _attr_has_entity_name = True
    _attr_name = "Work end (HH:MM)"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_suggested_object_id = "02_work_end"
    _attr_native_min = 0
    _attr_native_max = 5

    def __init__(self, coordinator: FelshareCoordinator, entry_id: str, dev: str) -> None:
        super().__init__(coordinator, entry_id, dev)
        self._attr_unique_id = f"{entry_id}_{dev}_work_end"

    @property
    def native_value(self):
        return self.coordinator.data.work_end

    async def async_set_value(self, value: str) -> None:
        try:
            await self.hass.async_add_executor_job(self.coordinator.hub.publish_work_end, value)
        except Exception as e:
            raise HomeAssistantError(str(e))
