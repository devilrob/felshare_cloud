from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.switch import SwitchEntity
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .coordinator import FelshareCoordinator


# Work days bitmask: Mon=1, Tue=2, Wed=4, Thu=8, Fri=16, Sat=32, Sun=64
_DAYS = [
    ("mon", "Monday", 0x01),
    ("tue", "Tuesday", 0x02),
    ("wed", "Wednesday", 0x04),
    ("thu", "Thursday", 0x08),
    ("fri", "Friday", 0x10),
    ("sat", "Saturday", 0x20),
    ("sun", "Sunday", 0x40),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: FelshareCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    dev = coordinator.data.device_id

    entities: list[SwitchEntity] = [
        FelsharePowerSwitch(coordinator, entry.entry_id, dev),
        FelshareFanSwitch(coordinator, entry.entry_id, dev),
        # Work schedule controls (config)
        FelshareWorkEnabledSwitch(coordinator, entry.entry_id, dev),
    ]

    # Add 7 day toggles
    for key, label, bit in _DAYS:
        entities.append(
            FelshareWorkDaySwitch(
                coordinator,
                entry.entry_id,
                dev,
                key=key,
                label=label,
                bit=bit,
            )
        )

    async_add_entities(entities)


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


class FelsharePowerSwitch(_Base, SwitchEntity):
    _attr_has_entity_name = True
    _attr_name = "Power"

    def __init__(self, coordinator: FelshareCoordinator, entry_id: str, dev: str) -> None:
        super().__init__(coordinator, entry_id, dev)
        self._attr_unique_id = f"{entry_id}_{dev}_power"

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.power_on

    async def async_turn_on(self, **kwargs) -> None:
        await self.hass.async_add_executor_job(self.coordinator.hub.publish_power, True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.hass.async_add_executor_job(self.coordinator.hub.publish_power, False)


class FelshareFanSwitch(_Base, SwitchEntity):
    _attr_has_entity_name = True
    _attr_name = "Fan"

    def __init__(self, coordinator: FelshareCoordinator, entry_id: str, dev: str) -> None:
        super().__init__(coordinator, entry_id, dev)
        self._attr_unique_id = f"{entry_id}_{dev}_fan"

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.fan_on

    async def async_turn_on(self, **kwargs) -> None:
        await self.hass.async_add_executor_job(self.coordinator.hub.publish_fan, True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.hass.async_add_executor_job(self.coordinator.hub.publish_fan, False)


class FelshareWorkEnabledSwitch(_Base, SwitchEntity):
    """Enable/disable the programmed WorkTime schedule."""

    _attr_has_entity_name = True
    _attr_name = "Work schedule"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_suggested_object_id = "00_work_schedule"

    def __init__(self, coordinator: FelshareCoordinator, entry_id: str, dev: str) -> None:
        super().__init__(coordinator, entry_id, dev)
        self._attr_unique_id = f"{entry_id}_{dev}_work_enabled"

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.work_enabled

    async def async_turn_on(self, **kwargs) -> None:
        await self.hass.async_add_executor_job(self.coordinator.hub.publish_work_enabled, True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.hass.async_add_executor_job(self.coordinator.hub.publish_work_enabled, False)


class FelshareWorkDaySwitch(_Base, SwitchEntity):
    """One toggle per weekday (stored as a bitmask in WorkTime flag low 7 bits)."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: FelshareCoordinator,
        entry_id: str,
        dev: str,
        *,
        key: str,
        label: str,
        bit: int,
    ) -> None:
        super().__init__(coordinator, entry_id, dev)
        self._key = key
        self._label = label
        self._bit = bit & 0x7F

        self._attr_name = f"Work day {label}"
        self._attr_unique_id = f"{entry_id}_{dev}_work_day_{key}"
        # Only affects entity_id ordering (name stays clean)
        self._attr_suggested_object_id = f"05_work_day_{key}"

    @property
    def is_on(self) -> bool | None:
        mask = self.coordinator.data.work_days_mask
        if mask is None:
            return None
        return bool(int(mask) & self._bit)

    async def async_turn_on(self, **kwargs) -> None:
        await self._set_day(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set_day(False)

    async def _set_day(self, enabled: bool) -> None:
        try:
            cur = self.coordinator.data.work_days_mask
            cur_mask = int(cur) if cur is not None else 0

            if enabled:
                new_mask = cur_mask | self._bit
            else:
                new_mask = cur_mask & (~self._bit & 0x7F)

            await self.hass.async_add_executor_job(self.coordinator.hub.publish_work_schedule, days_mask=new_mask)
        except Exception as e:
            raise HomeAssistantError(str(e))
