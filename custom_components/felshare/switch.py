from __future__ import annotations

import functools

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.switch import SwitchEntity
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .coordinator import FelshareCoordinator
from .entity import FelshareEntity

# Work days bitmask (device): Sun=1, Mon=2, Tue=4, Wed=8, Thu=16, Fri=32, Sat=64
_DAYS = [
    ("mon", "Monday", 0x02),
    ("tue", "Tuesday", 0x04),
    ("wed", "Wednesday", 0x08),
    ("thu", "Thursday", 0x10),
    ("fri", "Friday", 0x20),
    ("sat", "Saturday", 0x40),
    ("sun", "Sunday", 0x01),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: FelshareCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    dev = coordinator.data.device_id

    entities: list[SwitchEntity] = [
        FelsharePowerSwitch(coordinator, entry, dev),
        FelshareFanSwitch(coordinator, entry, dev),
        # Work schedule controls (config)
        FelshareWorkEnabledSwitch(coordinator, entry, dev),
    ]

    # Add 7 day toggles
    for key, label, bit in _DAYS:
        entities.append(
            FelshareWorkDaySwitch(
                coordinator,
                entry,
                dev,
                key=key,
                label=label,
                bit=bit,
            )
        )

    async_add_entities(entities)


class FelsharePowerSwitch(FelshareEntity, SwitchEntity):
    _attr_has_entity_name = True
    _attr_name = "Power"
    _attr_suggested_object_id = "power"
    _attr_icon = "mdi:power"

    def __init__(self, coordinator: FelshareCoordinator, entry: ConfigEntry, dev: str) -> None:
        super().__init__(coordinator, entry, dev)
        self._attr_unique_id = f"{self._entry_id}_{dev}_power"

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.power_on

    async def async_turn_on(self, **kwargs) -> None:
        try:
            await self.hass.async_add_executor_job(self.coordinator.hub.publish_power, True)
        except Exception as e:
            raise HomeAssistantError(str(e))

    async def async_turn_off(self, **kwargs) -> None:
        try:
            await self.hass.async_add_executor_job(self.coordinator.hub.publish_power, False)
        except Exception as e:
            raise HomeAssistantError(str(e))


class FelshareFanSwitch(FelshareEntity, SwitchEntity):
    _attr_has_entity_name = True
    _attr_name = "Fan"
    _attr_suggested_object_id = "fan"
    _attr_icon = "mdi:fan"

    def __init__(self, coordinator: FelshareCoordinator, entry: ConfigEntry, dev: str) -> None:
        super().__init__(coordinator, entry, dev)
        self._attr_unique_id = f"{self._entry_id}_{dev}_fan"

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.fan_on

    async def async_turn_on(self, **kwargs) -> None:
        try:
            await self.hass.async_add_executor_job(self.coordinator.hub.publish_fan, True)
        except Exception as e:
            raise HomeAssistantError(str(e))

    async def async_turn_off(self, **kwargs) -> None:
        try:
            await self.hass.async_add_executor_job(self.coordinator.hub.publish_fan, False)
        except Exception as e:
            raise HomeAssistantError(str(e))


class FelshareWorkEnabledSwitch(FelshareEntity, SwitchEntity):
    """Enable/disable the programmed WorkTime schedule."""

    _attr_has_entity_name = True
    _attr_name = "Work schedule"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_suggested_object_id = "00_work_schedule"
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: FelshareCoordinator, entry: ConfigEntry, dev: str) -> None:
        super().__init__(coordinator, entry, dev)
        self._attr_unique_id = f"{self._entry_id}_{dev}_work_enabled"

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.work_enabled

    async def async_turn_on(self, **kwargs) -> None:
        try:
            await self.hass.async_add_executor_job(self.coordinator.hub.publish_work_enabled, True)
        except Exception as e:
            raise HomeAssistantError(str(e))

    async def async_turn_off(self, **kwargs) -> None:
        try:
            await self.hass.async_add_executor_job(self.coordinator.hub.publish_work_enabled, False)
        except Exception as e:
            raise HomeAssistantError(str(e))


class FelshareWorkDaySwitch(FelshareEntity, SwitchEntity):
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:calendar-week"

    def __init__(
        self,
        coordinator: FelshareCoordinator,
        entry: ConfigEntry,
        dev: str,
        *,
        key: str,
        label: str,
        bit: int,
    ) -> None:
        super().__init__(coordinator, entry, dev)
        self._key = key
        self._bit = bit
        self._attr_name = f"Work day {label}"
        self._attr_unique_id = f"{self._entry_id}_{dev}_work_day_{key}"
        # Keep your sorting scheme
        self._attr_suggested_object_id = f"05_work_day_{key}"

    @property
    def is_on(self) -> bool | None:
        mask = self.coordinator.data.work_days_mask
        if mask is None:
            return None
        return bool(mask & self._bit)

    async def async_turn_on(self, **kwargs) -> None:
        await self._async_set_day(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._async_set_day(False)

    async def _async_set_day(self, on: bool) -> None:
        d = self.coordinator.data
        mask = d.work_days_mask if d.work_days_mask is not None else 0x7F
        if on:
            mask |= self._bit
        else:
            mask &= ~self._bit

        try:
            await self.hass.async_add_executor_job(
                functools.partial(self.coordinator.hub.publish_work_schedule, days_mask=mask)
            )
        except Exception as e:
            raise HomeAssistantError(str(e))
