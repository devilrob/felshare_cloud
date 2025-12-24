from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from datetime import timedelta

from .const import (
    DOMAIN,
    PLATFORMS,
    CONF_POLL_INTERVAL_MINUTES,
    DEFAULT_POLL_INTERVAL_MINUTES,
)
from .coordinator import FelshareCoordinator
from .hub import FelshareHub


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hub = FelshareHub(hass, entry)
    poll_minutes = entry.options.get(CONF_POLL_INTERVAL_MINUTES, DEFAULT_POLL_INTERVAL_MINUTES)
    try:
        poll_minutes = int(poll_minutes)
    except Exception:
        poll_minutes = DEFAULT_POLL_INTERVAL_MINUTES

    poll_interval = None if poll_minutes <= 0 else timedelta(minutes=poll_minutes)
    coordinator = FelshareCoordinator(hass, hub, poll_interval)

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
