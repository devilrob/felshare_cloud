from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.sensor import SensorEntity

from .const import DOMAIN
from .coordinator import FelshareCoordinator
from .entity import FelshareEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: FelshareCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    dev = coordinator.data.device_id

    async_add_entities(
        [
            FelshareLiquidLevelSensor(coordinator, entry, dev),
            FelshareMqttStatusSensor(coordinator, entry, dev),
            FelshareWorkScheduleSensor(coordinator, entry, dev),
        ]
    )


class FelshareLiquidLevelSensor(FelshareEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Liquid level"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_icon = "mdi:gauge"

    def __init__(self, coordinator: FelshareCoordinator, entry: ConfigEntry, dev: str) -> None:
        super().__init__(coordinator, entry, dev)
        self._attr_unique_id = f"{self._entry_id}_{dev}_liquid_level"

    @property
    def native_value(self):
        return self.coordinator.data.liquid_level


class FelshareMqttStatusSensor(FelshareEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "MQTT status"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:cloud-check"

    def __init__(self, coordinator: FelshareCoordinator, entry: ConfigEntry, dev: str) -> None:
        super().__init__(coordinator, entry, dev)
        self._attr_unique_id = f"{self._entry_id}_{dev}_mqtt_status"

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


class FelshareWorkScheduleSensor(FelshareEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Work schedule info"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: FelshareCoordinator, entry: ConfigEntry, dev: str) -> None:
        super().__init__(coordinator, entry, dev)
        self._attr_unique_id = f"{self._entry_id}_{dev}_work_schedule"

    @property
    def native_value(self):
        d = self.coordinator.data
        if not d.work_start or not d.work_end:
            return None

        days = (d.work_days or "-").replace(",", " ")
        enabled = "ON" if d.work_enabled else "OFF"

        parts = [f"{d.work_start}–{d.work_end}", days, enabled]
        if d.work_run_s is not None and d.work_stop_s is not None:
            parts.append(f"run {d.work_run_s}s / stop {d.work_stop_s}s")
        return " | ".join(parts)

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
