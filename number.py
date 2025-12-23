from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.number import NumberEntity, NumberMode

from .const import DOMAIN
from .coordinator import FelshareCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: FelshareCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    dev = coordinator.data.device_id

    async_add_entities(
        [
            FelshareConsumptionNumber(coordinator, entry.entry_id, dev),
            FelshareCapacityNumber(coordinator, entry.entry_id, dev),
            FelshareRemainOilNumber(coordinator, entry.entry_id, dev),
            FelshareWorkRunSecondsNumber(coordinator, entry.entry_id, dev),
            FelshareWorkStopSecondsNumber(coordinator, entry.entry_id, dev),
        ]
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


class FelshareConsumptionNumber(_Base, NumberEntity):
    _attr_has_entity_name = True
    _attr_name = "Consumption"
    _attr_native_unit_of_measurement = "ml/h"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0.0
    _attr_native_max_value = 200.0
    _attr_native_step = 0.1

    def __init__(self, coordinator: FelshareCoordinator, entry_id: str, dev: str) -> None:
        super().__init__(coordinator, entry_id, dev)
        self._attr_unique_id = f"{entry_id}_{dev}_consumption"

    @property
    def native_value(self):
        return self.coordinator.data.consumption

    async def async_set_native_value(self, value: float) -> None:
        await self.hass.async_add_executor_job(self.coordinator.hub.publish_consumption, float(value))


class FelshareCapacityNumber(_Base, NumberEntity):
    _attr_has_entity_name = True
    _attr_name = "Oil capacity"
    _attr_native_unit_of_measurement = "ml"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_max_value = 5000
    _attr_native_step = 1

    def __init__(self, coordinator: FelshareCoordinator, entry_id: str, dev: str) -> None:
        super().__init__(coordinator, entry_id, dev)
        self._attr_unique_id = f"{entry_id}_{dev}_capacity"

    @property
    def native_value(self):
        return self.coordinator.data.capacity

    async def async_set_native_value(self, value: float) -> None:
        await self.hass.async_add_executor_job(self.coordinator.hub.publish_capacity, int(value))


class FelshareRemainOilNumber(_Base, NumberEntity):
    _attr_has_entity_name = True
    _attr_name = "Remain oil"
    _attr_native_unit_of_measurement = "ml"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_max_value = 5000
    _attr_native_step = 1

    def __init__(self, coordinator: FelshareCoordinator, entry_id: str, dev: str) -> None:
        super().__init__(coordinator, entry_id, dev)
        self._attr_unique_id = f"{entry_id}_{dev}_remain_oil"

    @property
    def native_value(self):
        return self.coordinator.data.remain_oil

    async def async_set_native_value(self, value: float) -> None:
        await self.hass.async_add_executor_job(self.coordinator.hub.publish_remain_oil, int(value))


class FelshareWorkRunSecondsNumber(_Base, NumberEntity):
    _attr_has_entity_name = True
    _attr_name = "Work run (seconds)"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_suggested_object_id = "03_work_run_s"
    _attr_native_unit_of_measurement = "s"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_max_value = 3600
    _attr_native_step = 1

    def __init__(self, coordinator: FelshareCoordinator, entry_id: str, dev: str) -> None:
        super().__init__(coordinator, entry_id, dev)
        self._attr_unique_id = f"{entry_id}_{dev}_work_run_s"

    @property
    def native_value(self):
        return self.coordinator.data.work_run_s

    async def async_set_native_value(self, value: float) -> None:
        await self.hass.async_add_executor_job(self.coordinator.hub.publish_work_run_s, int(value))


class FelshareWorkStopSecondsNumber(_Base, NumberEntity):
    _attr_has_entity_name = True
    _attr_name = "Work stop (seconds)"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_suggested_object_id = "04_work_stop_s"
    _attr_native_unit_of_measurement = "s"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_max_value = 3600
    _attr_native_step = 1

    def __init__(self, coordinator: FelshareCoordinator, entry_id: str, dev: str) -> None:
        super().__init__(coordinator, entry_id, dev)
        self._attr_unique_id = f"{entry_id}_{dev}_work_stop_s"

    @property
    def native_value(self):
        return self.coordinator.data.work_stop_s

    async def async_set_native_value(self, value: float) -> None:
        await self.hass.async_add_executor_job(self.coordinator.hub.publish_work_stop_s, int(value))


