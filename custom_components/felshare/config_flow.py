from __future__ import annotations

from typing import Any

import async_timeout
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN,
    VERSION,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_MODEL,
    CONF_DEVICE_STATE,
    CONF_POLL_INTERVAL_MINUTES,
    CONF_ENABLE_TXD_LEARNING,
    CONF_MAX_BACKOFF_SECONDS,
    CONF_MIN_PUBLISH_INTERVAL_SECONDS,
    CONF_MAX_BURST_MESSAGES,
    CONF_STATUS_MIN_INTERVAL_SECONDS,
    CONF_BULK_MIN_INTERVAL_HOURS,
    CONF_STARTUP_STALE_MINUTES,
    DEFAULT_POLL_INTERVAL_MINUTES,
    DEFAULT_ENABLE_TXD_LEARNING,
    DEFAULT_MAX_BACKOFF_SECONDS,
    DEFAULT_MIN_PUBLISH_INTERVAL_SECONDS,
    DEFAULT_MAX_BURST_MESSAGES,
    DEFAULT_STATUS_MIN_INTERVAL_SECONDS,
    DEFAULT_BULK_MIN_INTERVAL_HOURS,
    DEFAULT_STARTUP_STALE_MINUTES,
    API_BASE,
)


async def _login_and_devices(hass: HomeAssistant, email: str, password: str) -> list[dict]:
    """Login and fetch device list using HA's aiohttp session (no external deps)."""
    session = async_get_clientsession(hass)

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": f"HomeAssistant-Felshare/{VERSION}",
    }

    # Login
    try:
        async with async_timeout.timeout(20):
            resp = await session.post(
                f"{API_BASE}/login",
                json={"username": email, "password": password},
                headers=headers,
            )
            if resp.status in (401, 403):
                raise ConnectionError("Login rejected")
            if resp.status == 429:
                raise ConnectionError("Login rate-limited")
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
        async with async_timeout.timeout(20):
            resp = await session.get(
                f"{API_BASE}/device",
                headers={"token": token, "Accept": "application/json", "User-Agent": f"HomeAssistant-Felshare/{VERSION}"},
            )
            if resp.status == 429:
                raise ConnectionError("Device list rate-limited")
            dd = await resp.json(content_type=None)
    except Exception as err:
        raise ConnectionError(f"Device list error: {err}") from err

    devs = dd.get("data") if isinstance(dd, dict) else None
    if not isinstance(devs, list):
        raise ConnectionError("Device list failed")
    return devs


def _pick(d: dict, *keys: str) -> Any | None:
    for k in keys:
        v = d.get(k)
        if v is not None and v != "":
            return v
    return None


class FelshareConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        return FelshareOptionsFlowHandler(config_entry)

    def __init__(self) -> None:
        self._email: str | None = None
        self._password: str | None = None

        # device_id -> label
        self._device_options: dict[str, str] = {}
        # device_id -> raw device dict
        self._device_map: dict[str, dict] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            email = user_input[CONF_EMAIL]
            password = user_input[CONF_PASSWORD]
            try:
                devices = await _login_and_devices(self.hass, email, password)

                options: dict[str, str] = {}
                devmap: dict[str, dict] = {}

                for d in devices:
                    if not isinstance(d, dict):
                        continue

                    device_id = _pick(d, "device_id", "deviceId", "devId", "id", "name")
                    if not device_id:
                        continue
                    device_id = str(device_id)

                    device_name = _pick(d, "device_name", "deviceName", "alias", "nickName", "name")
                    if device_name:
                        device_name = str(device_name).strip()
                    model = _pick(d, "model", "product", "productName", "product_name", "type")
                    state = _pick(d, "state", "online", "isOnline", "device_state")

                    # label shown in selector
                    label = device_id
                    if device_name and device_name != device_id:
                        label = f"{device_name} — {device_id}"
                    if state is not None:
                        label = f"{label} (state={state})"

                    options[device_id] = label
                    devmap[device_id] = d

                if not options:
                    raise ConnectionError("No devices")

                self._email = str(email)
                self._password = str(password)
                self._device_options = options
                self._device_map = devmap

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

            raw = self._device_map.get(device_id, {})
            device_name = _pick(raw, "device_name", "deviceName", "alias", "nickName", "name")
            device_model = _pick(raw, "model", "product", "productName", "product_name", "type")
            device_state = _pick(raw, "state", "online", "isOnline", "device_state")

            title = str(device_name).strip() if device_name else f"Felshare {device_id}"

            return self.async_create_entry(
                title=title,
                data={
                    CONF_EMAIL: self._email,
                    CONF_PASSWORD: self._password,
                    CONF_DEVICE_ID: device_id,
                    CONF_DEVICE_NAME: str(device_name).strip() if device_name else title,
                    CONF_DEVICE_MODEL: str(device_model).strip() if device_model else "Smart Diffuser",
                    CONF_DEVICE_STATE: str(device_state) if device_state is not None else None,
                },
            )

        schema = vol.Schema({vol.Required(CONF_DEVICE_ID): vol.In(self._device_options)})
        return self.async_show_form(step_id="device", data_schema=schema, errors=errors)


class FelshareOptionsFlowHandler(config_entries.OptionsFlow):
    """Options for the Felshare integration."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Existing
        poll_minutes = self._entry.options.get(CONF_POLL_INTERVAL_MINUTES, DEFAULT_POLL_INTERVAL_MINUTES)
        enable_txd = self._entry.options.get(CONF_ENABLE_TXD_LEARNING, DEFAULT_ENABLE_TXD_LEARNING)
        max_backoff = self._entry.options.get(CONF_MAX_BACKOFF_SECONDS, DEFAULT_MAX_BACKOFF_SECONDS)

        # Hardened
        min_pub = self._entry.options.get(CONF_MIN_PUBLISH_INTERVAL_SECONDS, DEFAULT_MIN_PUBLISH_INTERVAL_SECONDS)
        burst = self._entry.options.get(CONF_MAX_BURST_MESSAGES, DEFAULT_MAX_BURST_MESSAGES)
        status_min = self._entry.options.get(CONF_STATUS_MIN_INTERVAL_SECONDS, DEFAULT_STATUS_MIN_INTERVAL_SECONDS)
        bulk_hours = self._entry.options.get(CONF_BULK_MIN_INTERVAL_HOURS, DEFAULT_BULK_MIN_INTERVAL_HOURS)
        startup_stale = self._entry.options.get(CONF_STARTUP_STALE_MINUTES, DEFAULT_STARTUP_STALE_MINUTES)

        schema = vol.Schema(
            {
                # Recommended: 30–60 minutes, or 0 if MQTT is stable
                vol.Required(CONF_POLL_INTERVAL_MINUTES, default=poll_minutes): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=240)
                ),

                # Outbound MQTT rate limiting
                vol.Required(CONF_MIN_PUBLISH_INTERVAL_SECONDS, default=min_pub): vol.All(
                    vol.Coerce(float), vol.Range(min=0.2, max=10.0)
                ),
                vol.Required(CONF_MAX_BURST_MESSAGES, default=burst): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=20)
                ),

                # Status + bulk request throttles
                vol.Required(CONF_STATUS_MIN_INTERVAL_SECONDS, default=status_min): vol.All(
                    vol.Coerce(int), vol.Range(min=10, max=3600)
                ),
                vol.Required(CONF_BULK_MIN_INTERVAL_HOURS, default=bulk_hours): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=72)
                ),
                vol.Required(CONF_STARTUP_STALE_MINUTES, default=startup_stale): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=1440)
                ),

                # Misc
                vol.Required(CONF_ENABLE_TXD_LEARNING, default=enable_txd): bool,
                vol.Required(CONF_MAX_BACKOFF_SECONDS, default=max_backoff): vol.All(
                    vol.Coerce(int), vol.Range(min=30, max=3600)
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
