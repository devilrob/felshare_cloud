from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.button import ButtonEntity
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .coordinator import FelshareCoordinator
from .entity import FelshareEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: FelshareCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    dev = coordinator.data.device_id

    async_add_entities([FelshareRefreshButton(coordinator, entry, dev)])


class FelshareRefreshButton(FelshareEntity, ButtonEntity):
    """Manual refresh helper.

    Useful when the cloud doesn't push state changes until the mobile app is opened.
    """

    _attr_has_entity_name = True
    _attr_name = "Refresh status"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator: FelshareCoordinator, entry: ConfigEntry, dev: str) -> None:
        super().__init__(coordinator, entry, dev)
        self._attr_unique_id = f"{self._entry_id}_{dev}_refresh"

    async def async_press(self) -> None:
        try:
            await self.hass.async_add_executor_job(self.coordinator.hub.request_status)
        except Exception as e:
            raise HomeAssistantError(str(e))
