from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.sensor import SensorEntity

from .const import DOMAIN
from .coordinator import FelshareCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: FelshareCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    dev = coordinator.data.device_id

    async_add_entities(
        [
            FelshareLiquidLevelSensor(coordinator, entry.entry_id, dev),
            FelshareMqttStatusSensor(coordinator, entry.entry_id, dev),
            FelshareWorkScheduleSensor(coordinator, entry.entry_id, dev),
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
        # If we have ever seen data OR MQTT is connected, keep entity available.
        data = self.coordinator.data
        return bool(data.connected or data.last_seen)


class FelshareLiquidLevelSensor(_Base, SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Liquid level"
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, coordinator: FelshareCoordinator, entry_id: str, dev: str) -> None:
        super().__init__(coordinator, entry_id, dev)
        self._attr_unique_id = f"{entry_id}_{dev}_liquid_level"

    @property
    def native_value(self):
        return self.coordinator.data.liquid_level


class FelshareMqttStatusSensor(_Base, SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "MQTT status"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: FelshareCoordinator, entry_id: str, dev: str) -> None:
        super().__init__(coordinator, entry_id, dev)
        self._attr_unique_id = f"{entry_id}_{dev}_mqtt_status"

    @property
    def native_value(self):
        return "connected" if self.coordinator.data.connected else "disconnected"

    @property
    def extra_state_attributes(self):
        d = self.coordinator.data
        return {
            "last_seen": d.last_seen.isoformat() if d.last_seen else None,
            "last_topic": d.last_topic,
            "last_payload_hex": d.last_payload_hex,
        }


class FelshareWorkScheduleSensor(_Base, SensorEntity):
    """Human-friendly summary of the programmed WorkTime schedule."""

    _attr_has_entity_name = True
    _attr_name = "Work schedule info"
    _attr_suggested_object_id = "99_work_schedule_info"
    # Home Assistant does not allow EntityCategory.CONFIG for SensorEntity.
    # This is informational, so expose it as diagnostic instead.
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: FelshareCoordinator, entry_id: str, dev: str) -> None:
        super().__init__(coordinator, entry_id, dev)
        self._attr_unique_id = f"{entry_id}_{dev}_work_schedule"

    @property
    def native_value(self):
        d = self.coordinator.data
        if not d.work_start or not d.work_end:
            return None
        enabled = "enabled" if d.work_enabled else "disabled"
        days = d.work_days or "-"
        run_stop = ""
        if d.work_run_s is not None and d.work_stop_s is not None:
            run_stop = f" run={d.work_run_s}s stop={d.work_stop_s}s"
        return f"{d.work_start}–{d.work_end} ({days}) {enabled}{run_stop}".strip()

    @property
    def extra_state_attributes(self):
        d = self.coordinator.data
        return {
            "work_enabled": d.work_enabled,
            "work_days_mask": d.work_days_mask,
            "work_flag_raw": d.work_flag_raw,
            "work_start": d.work_start,
            "work_end": d.work_end,
            "work_run_s": d.work_run_s,
            "work_stop_s": d.work_stop_s,
        }
