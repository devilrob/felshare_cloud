from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, CONF_HVAC_SYNC_CLIMATE_ENTITY
from .coordinator import FelshareCoordinator
from .entity import FelshareEntity


_NONE = "(none)"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: FelshareCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    dev = coordinator.data.device_id
    async_add_entities([FelshareHvacThermostatSelect(coordinator, entry, dev)])


class FelshareHvacThermostatSelect(FelshareEntity, SelectEntity):
    """Select which climate entity to follow for HVAC Sync."""

    _attr_has_entity_name = True
    _attr_name = "HVAC sync thermostat"
    _attr_entity_category = None
    _attr_icon = "mdi:thermostat"
    _attr_suggested_object_id = "90_hvac_sync_thermostat"

    def __init__(self, coordinator: FelshareCoordinator, entry: ConfigEntry, dev: str) -> None:
        super().__init__(coordinator, entry, dev)
        self._attr_unique_id = f"{self._entry_id}_{dev}_hvac_sync_thermostat"

    @property
    def options(self) -> list[str]:
        # List all climate entities currently in HA. This is dynamic so the user doesn't
        # need to restart HA when adding a thermostat integration.
        entities = sorted(self.hass.states.async_entity_ids("climate"))
        return [_NONE, *entities]

    @property
    def current_option(self) -> str | None:
        sel = (self._entry.options.get(CONF_HVAC_SYNC_CLIMATE_ENTITY) or "").strip()
        return sel if sel else _NONE

    async def async_select_option(self, option: str) -> None:
        new_opts = dict(self._entry.options)
        new_opts[CONF_HVAC_SYNC_CLIMATE_ENTITY] = "" if option == _NONE else option
        self.hass.config_entries.async_update_entry(self._entry, options=new_opts)

        # Poke controller for immediate effect
        ctl = self.hass.data.get(DOMAIN, {}).get(self._entry.entry_id, {}).get("hvac_sync")
        if ctl is not None:
            await ctl.async_evaluate(force=True)

        self.async_write_ha_state()
