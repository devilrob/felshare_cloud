from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.exceptions import HomeAssistantError

from .const import (
    DOMAIN,
    CONF_HVAC_SYNC_ON_DELAY_SECONDS,
    CONF_HVAC_SYNC_OFF_DELAY_SECONDS,
    DEFAULT_HVAC_SYNC_ON_DELAY_SECONDS,
    DEFAULT_HVAC_SYNC_OFF_DELAY_SECONDS,
)
from .coordinator import FelshareCoordinator
from .entity import FelshareEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: FelshareCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    dev = coordinator.data.device_id

    async_add_entities(
        [
            FelshareConsumptionNumber(coordinator, entry, dev),
            FelshareCapacityNumber(coordinator, entry, dev),
            FelshareRemainOilNumber(coordinator, entry, dev),
            FelshareWorkRunSecondsNumber(coordinator, entry, dev),
            FelshareWorkStopSecondsNumber(coordinator, entry, dev),
            FelshareHvacSyncOnDelaySecondsNumber(coordinator, entry, dev),
            FelshareHvacSyncOffDelaySecondsNumber(coordinator, entry, dev),
        ]
    )


class _BaseHvacSyncDelayNumber(FelshareEntity, NumberEntity):
    # Intentionally not EntityCategory.CONFIG so HA doesn't group everything under
    # the device "Configuration" section.
    _attr_entity_category = None
    _attr_native_unit_of_measurement = "s"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_max_value = 900
    _attr_native_step = 1

    _key: str
    _default: int

    @property
    def native_value(self):
        try:
            return int(self._entry.options.get(self._key, self._default) or 0)
        except Exception:
            return int(self._default)

    async def async_set_native_value(self, value: float) -> None:
        new_opts = dict(self._entry.options)
        new_opts[self._key] = int(value)
        self.hass.config_entries.async_update_entry(self._entry, options=new_opts)

        ctl = self.hass.data.get(DOMAIN, {}).get(self._entry.entry_id, {}).get("hvac_sync")
        if ctl is not None:
            await ctl.async_evaluate(force=True)
        self.async_write_ha_state()


class FelshareHvacSyncOnDelaySecondsNumber(_BaseHvacSyncDelayNumber):
    _attr_has_entity_name = True
    _attr_name = "HVAC sync on delay (seconds)"
    _attr_suggested_object_id = "94_hvac_sync_on_delay_s"
    _attr_icon = "mdi:timer-play-outline"

    _key = CONF_HVAC_SYNC_ON_DELAY_SECONDS
    _default = DEFAULT_HVAC_SYNC_ON_DELAY_SECONDS

    def __init__(self, coordinator: FelshareCoordinator, entry: ConfigEntry, dev: str) -> None:
        super().__init__(coordinator, entry, dev)
        self._attr_unique_id = f"{self._entry_id}_{dev}_hvac_sync_on_delay_s"


class FelshareHvacSyncOffDelaySecondsNumber(_BaseHvacSyncDelayNumber):
    _attr_has_entity_name = True
    _attr_name = "HVAC sync off delay (seconds)"
    _attr_suggested_object_id = "95_hvac_sync_off_delay_s"
    _attr_icon = "mdi:timer-stop-outline"

    _key = CONF_HVAC_SYNC_OFF_DELAY_SECONDS
    _default = DEFAULT_HVAC_SYNC_OFF_DELAY_SECONDS

    def __init__(self, coordinator: FelshareCoordinator, entry: ConfigEntry, dev: str) -> None:
        super().__init__(coordinator, entry, dev)
        self._attr_unique_id = f"{self._entry_id}_{dev}_hvac_sync_off_delay_s"


class FelshareConsumptionNumber(FelshareEntity, NumberEntity):
    _attr_has_entity_name = True
    _attr_name = "Consumption"
    _attr_entity_category = None
    _attr_suggested_object_id = "consumption"
    _attr_native_unit_of_measurement = "ml/h"
    _attr_icon = "mdi:water"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0.0
    _attr_native_max_value = 200.0
    _attr_native_step = 0.1

    def __init__(self, coordinator: FelshareCoordinator, entry: ConfigEntry, dev: str) -> None:
        super().__init__(coordinator, entry, dev)
        self._attr_unique_id = f"{self._entry_id}_{dev}_consumption"

    @property
    def native_value(self):
        return self.coordinator.data.consumption

    async def async_set_native_value(self, value: float) -> None:
        try:
            await self.hass.async_add_executor_job(self.coordinator.hub.publish_consumption, float(value))
        except Exception as e:
            raise HomeAssistantError(str(e))


class FelshareCapacityNumber(FelshareEntity, NumberEntity):
    _attr_has_entity_name = True
    _attr_name = "Oil capacity"
    _attr_entity_category = None
    _attr_suggested_object_id = "capacity"
    _attr_native_unit_of_measurement = "ml"
    _attr_icon = "mdi:cup-water"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_max_value = 5000
    _attr_native_step = 1

    def __init__(self, coordinator: FelshareCoordinator, entry: ConfigEntry, dev: str) -> None:
        super().__init__(coordinator, entry, dev)
        self._attr_unique_id = f"{self._entry_id}_{dev}_capacity"

    @property
    def native_value(self):
        return self.coordinator.data.capacity

    async def async_set_native_value(self, value: float) -> None:
        try:
            await self.hass.async_add_executor_job(self.coordinator.hub.publish_capacity, int(value))
        except Exception as e:
            raise HomeAssistantError(str(e))


class FelshareRemainOilNumber(FelshareEntity, NumberEntity):
    _attr_has_entity_name = True
    _attr_name = "Remaining oil"
    _attr_entity_category = None
    _attr_suggested_object_id = "remain_oil"
    _attr_native_unit_of_measurement = "ml"
    _attr_icon = "mdi:cup-water"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_max_value = 5000
    _attr_native_step = 1

    def __init__(self, coordinator: FelshareCoordinator, entry: ConfigEntry, dev: str) -> None:
        super().__init__(coordinator, entry, dev)
        self._attr_unique_id = f"{self._entry_id}_{dev}_remain_oil"

    @property
    def native_value(self):
        return self.coordinator.data.remain_oil

    async def async_set_native_value(self, value: float) -> None:
        try:
            await self.hass.async_add_executor_job(self.coordinator.hub.publish_remain_oil, int(value))
        except Exception as e:
            raise HomeAssistantError(str(e))


class FelshareWorkRunSecondsNumber(FelshareEntity, NumberEntity):
    _attr_has_entity_name = True
    _attr_name = "Work run (seconds)"
    _attr_entity_category = None
    _attr_suggested_object_id = "03_work_run_s"
    _attr_native_unit_of_measurement = "s"
    _attr_icon = "mdi:timer-outline"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    # Device limitation: 0..999 seconds
    _attr_native_max_value = 999
    _attr_native_step = 1

    def __init__(self, coordinator: FelshareCoordinator, entry: ConfigEntry, dev: str) -> None:
        super().__init__(coordinator, entry, dev)
        self._attr_unique_id = f"{self._entry_id}_{dev}_work_run_s"

    @property
    def native_value(self):
        return self.coordinator.data.work_run_s

    async def async_set_native_value(self, value: float) -> None:
        try:
            await self.hass.async_add_executor_job(self.coordinator.hub.publish_work_run_s, int(value))
        except Exception as e:
            raise HomeAssistantError(str(e))


class FelshareWorkStopSecondsNumber(FelshareEntity, NumberEntity):
    _attr_has_entity_name = True
    _attr_name = "Work stop (seconds)"
    _attr_entity_category = None
    _attr_suggested_object_id = "04_work_stop_s"
    _attr_native_unit_of_measurement = "s"
    _attr_icon = "mdi:timer-off-outline"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    # Device limitation: 0..999 seconds
    _attr_native_max_value = 999
    _attr_native_step = 1

    def __init__(self, coordinator: FelshareCoordinator, entry: ConfigEntry, dev: str) -> None:
        super().__init__(coordinator, entry, dev)
        self._attr_unique_id = f"{self._entry_id}_{dev}_work_stop_s"

    @property
    def native_value(self):
        return self.coordinator.data.work_stop_s

    async def async_set_native_value(self, value: float) -> None:
        try:
            await self.hass.async_add_executor_job(self.coordinator.hub.publish_work_stop_s, int(value))
        except Exception as e:
            raise HomeAssistantError(str(e))
