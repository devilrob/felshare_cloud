from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    CONF_HVAC_SYNC_CLIMATE_ENTITY,
    CONF_HVAC_SYNC_AIRFLOW_MODE,
    DEFAULT_HVAC_SYNC_AIRFLOW_MODE,
)
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
    async_add_entities(
        [
            FelshareHvacThermostatSelect(coordinator, entry, dev),
            FelshareHvacAirflowModeSelect(coordinator, entry, dev),
        ]
    )


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


class FelshareHvacAirflowModeSelect(FelshareEntity, SelectEntity):
    """Select what "air running" means for HVAC Sync.

    We use hvac_action (runtime) and allow the user to choose whether to
    follow only cooling, heating+cooling, or any airflow (incl fan-only).
    """

    _attr_has_entity_name = True
    _attr_name = "HVAC sync airflow"
    _attr_entity_category = None
    _attr_icon = "mdi:fan-auto"
    _attr_suggested_object_id = "88_hvac_sync_airflow"

    _LABEL_TO_MODE = {
        "Cooling only": "cooling_only",
        "Heat + Cool": "heat_cool",
        "Any airflow (Heat/Cool/Fan)": "any_airflow",
    }
    _MODE_TO_LABEL = {v: k for k, v in _LABEL_TO_MODE.items()}

    def __init__(self, coordinator: FelshareCoordinator, entry: ConfigEntry, dev: str) -> None:
        super().__init__(coordinator, entry, dev)
        self._attr_unique_id = f"{self._entry_id}_{dev}_hvac_sync_airflow_mode"

    @property
    def options(self) -> list[str]:
        return list(self._LABEL_TO_MODE.keys())

    @property
    def current_option(self) -> str | None:
        mode = (self._entry.options.get(CONF_HVAC_SYNC_AIRFLOW_MODE) or DEFAULT_HVAC_SYNC_AIRFLOW_MODE).strip() or DEFAULT_HVAC_SYNC_AIRFLOW_MODE
        return self._MODE_TO_LABEL.get(mode, self._MODE_TO_LABEL.get(DEFAULT_HVAC_SYNC_AIRFLOW_MODE, "Cooling only"))

    async def async_select_option(self, option: str) -> None:
        mode = self._LABEL_TO_MODE.get(option, DEFAULT_HVAC_SYNC_AIRFLOW_MODE)
        new_opts = dict(self._entry.options)
        new_opts[CONF_HVAC_SYNC_AIRFLOW_MODE] = mode
        self.hass.config_entries.async_update_entry(self._entry, options=new_opts)

        ctl = self.hass.data.get(DOMAIN, {}).get(self._entry.entry_id, {}).get("hvac_sync")
        if ctl is not None:
            await ctl.async_evaluate(force=True)

        self.async_write_ha_state()
