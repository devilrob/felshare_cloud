from __future__ import annotations

from typing import Any

import asyncio
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, CONF_EMAIL, CONF_PASSWORD, CONF_DEVICE_ID, API_BASE


async def _login_and_devices(hass: HomeAssistant, email: str, password: str) -> list[dict]:
    """Login and fetch device list using HA's aiohttp session (no external deps)."""
    session = async_get_clientsession(hass)

    # Login
    try:
        async with asyncio.timeout(20):
            resp = await session.post(
                f"{API_BASE}/login",
                json={"username": email, "password": password},
                headers={"Content-Type": "application/json"},
            )
            data = await resp.json(content_type=None)
    except Exception as err:
        raise ConnectionError(f"Login error: {err}") from err

    token = None
    if isinstance(data, dict):
        token = (data.get("data") or {}).get("token")
    if not token:
        raise ConnectionError("Login failed")

    # Devices
    try:
        async with asyncio.timeout(20):
            resp = await session.get(f"{API_BASE}/device", headers={"token": token})
            dd = await resp.json(content_type=None)
    except Exception as err:
        raise ConnectionError(f"Device list error: {err}") from err

    devs = dd.get("data") if isinstance(dd, dict) else None
    if not isinstance(devs, list):
        raise ConnectionError("Device list failed")
    return devs


class FelshareConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._email: str | None = None
        self._password: str | None = None
        self._device_options: dict[str, str] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            email = user_input[CONF_EMAIL]
            password = user_input[CONF_PASSWORD]
            try:
                devices = await _login_and_devices(self.hass, email, password)

                options: dict[str, str] = {}
                for d in devices:
                    if not isinstance(d, dict):
                        continue
                    device_id = d.get("device_id") or d.get("name")
                    if device_id:
                        label = f"{device_id} (state={d.get('state')})"
                        options[str(device_id)] = label

                if not options:
                    raise ConnectionError("No devices")

                self._email = email
                self._password = password
                self._device_options = options
                return await self.async_step_device()
            except Exception:
                errors["base"] = "cannot_connect"

        schema = vol.Schema(
            {
                vol.Required(CONF_EMAIL): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_device(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            device_id = str(user_input[CONF_DEVICE_ID])
            await self.async_set_unique_id(f"{DOMAIN}_{device_id}")
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"Felshare {device_id}",
                data={
                    CONF_EMAIL: self._email,
                    CONF_PASSWORD: self._password,
                    CONF_DEVICE_ID: device_id,
                },
            )

        schema = vol.Schema({vol.Required(CONF_DEVICE_ID): vol.In(self._device_options)})
        return self.async_show_form(step_id="device", data_schema=schema, errors=errors)
