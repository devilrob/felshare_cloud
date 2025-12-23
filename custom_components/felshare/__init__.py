from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .coordinator import FelshareCoordinator
from .hub import FelshareHub


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hub = FelshareHub(hass, entry)
    coordinator = FelshareCoordinator(hass, hub)

    await coordinator.async_start()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "hub": hub,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if data:
        coordinator: FelshareCoordinator = data["coordinator"]
        await coordinator.async_stop()
    return unload_ok
