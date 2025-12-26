from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import EntityCategory
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_registry import RegistryEntryDisabler, RegistryEntryHider

from datetime import timedelta

from .const import (
    DOMAIN,
    PLATFORMS,
    CONF_POLL_INTERVAL_MINUTES,
    DEFAULT_POLL_INTERVAL_MINUTES,
)
from .coordinator import FelshareCoordinator
from .hub import FelshareHub
from .hvac_sync import FelshareHvacSyncController


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

    # Optional HVAC Sync controller (runs entirely locally inside HA)
    hvac_sync = FelshareHvacSyncController(hass, entry, coordinator)
    await hvac_sync.async_start()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "hub": hub,
        "coordinator": coordinator,
        "hvac_sync": hvac_sync,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # UI polish: older versions stored many entities as EntityCategory.CONFIG in the entity registry.
    # That makes the device page show almost everything under "Configuration". We clear only those
    # sticky registry values so entities fall back to normal Controls/Sensors grouping.
    ent_reg = er.async_get(hass)
    # Cache device_id for migration checks
    dev_id = coordinator.data.device_id
    for ent in list(ent_reg.entities.values()):
        if ent.config_entry_id != entry.entry_id:
            continue
        if ent.platform != DOMAIN:
            continue
        if ent.entity_category == EntityCategory.CONFIG:
            ent_reg.async_update_entity(ent.entity_id, entity_category=None)

        # Deprecation: HVAC Sync now reuses Work schedule, so we disable legacy HVAC Sync
        # day/time entities to reduce duplicates and confusion.
        uid = ent.unique_id or ""
        legacy_prefix = f"{entry.entry_id}_{dev_id}_hvac_sync_day_"
        if uid.startswith(legacy_prefix) or uid in (
            f"{entry.entry_id}_{dev_id}_hvac_sync_start",
            f"{entry.entry_id}_{dev_id}_hvac_sync_end",
        ):
            ent_reg.async_update_entity(
                ent.entity_id,
                disabled_by=RegistryEntryDisabler.INTEGRATION,
                hidden_by=RegistryEntryHider.INTEGRATION,
            )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if data:
        coordinator: FelshareCoordinator = data["coordinator"]
        hvac_sync = data.get("hvac_sync")
        if hvac_sync is not None:
            await hvac_sync.async_stop()
        await coordinator.async_stop()
    return unload_ok
