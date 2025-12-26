from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .models import FelshareState
from .hub import FelshareHub


class FelshareCoordinator(DataUpdateCoordinator[FelshareState]):
    """Push-based coordinator (MQTT thread -> HA loop)."""

    def __init__(self, hass: HomeAssistant, hub: FelshareHub, poll_interval: timedelta | None) -> None:
        super().__init__(
            hass,
            logger=hub.logger,
            name="felshare",
            update_interval=poll_interval,  # poll fallback (optional)
        )
        self.hub = hub
        self.data = hub.state

    async def async_start(self) -> None:
        # Start hub (login + mqtt)
        await self.hub.async_start(self._on_state)

    async def async_stop(self) -> None:
        await self.hub.async_stop()

    def _on_state(self, state: FelshareState) -> None:
        """Called from hub thread; marshal back to HA event loop."""
        self.hass.loop.call_soon_threadsafe(self._async_set_state, state)

    @callback
    def _async_set_state(self, state: FelshareState) -> None:
        self.async_set_updated_data(state)

    async def _async_update_data(self) -> FelshareState:
        # Best-effort polling: request status periodically so HA can refresh even if the phone app is closed.
        # If polling is disabled (update_interval=None), HA won't call this.
        try:
            self.hub.request_status()
        except Exception:
            pass
        return self.hub.state