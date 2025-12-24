from __future__ import annotations

DOMAIN = "felshare"

# Integration version (kept in code to build polite UA strings and diagnostics)
VERSION = "0.1.6.10"

CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_DEVICE_ID = "device_id"
CONF_DEVICE_NAME = "device_name"
CONF_DEVICE_MODEL = "device_model"
CONF_DEVICE_STATE = "device_state"

# Options
CONF_POLL_INTERVAL_MINUTES = "poll_interval_minutes"
CONF_ENABLE_TXD_LEARNING = "enable_txd_learning"
CONF_MAX_BACKOFF_SECONDS = "max_backoff_seconds"

# Hardening / stability options
CONF_MIN_PUBLISH_INTERVAL_SECONDS = "min_publish_interval_seconds"
CONF_MAX_BURST_MESSAGES = "max_burst_messages"
CONF_STATUS_MIN_INTERVAL_SECONDS = "status_min_interval_seconds"
CONF_BULK_MIN_INTERVAL_HOURS = "bulk_status_interval_hours"
CONF_STARTUP_STALE_MINUTES = "startup_request_stale_minutes"

# Safer defaults (less noisy)
DEFAULT_POLL_INTERVAL_MINUTES = 30
DEFAULT_ENABLE_TXD_LEARNING = False
DEFAULT_MAX_BACKOFF_SECONDS = 900

DEFAULT_MIN_PUBLISH_INTERVAL_SECONDS = 1.0
DEFAULT_MAX_BURST_MESSAGES = 3
DEFAULT_STATUS_MIN_INTERVAL_SECONDS = 60
DEFAULT_BULK_MIN_INTERVAL_HOURS = 6
DEFAULT_STARTUP_STALE_MINUTES = 30

# HVAC Sync (optional): follow a Home Assistant climate entity and only run the diffuser
# when HVAC is actively cooling. The schedule window is taken from the diffuser's
# own Work schedule (days + start/end), to avoid duplicated day/time entities.
CONF_HVAC_SYNC_ENABLED = "hvac_sync_enabled"
CONF_HVAC_SYNC_CLIMATE_ENTITY = "hvac_sync_climate_entity"
# Deprecated (kept for backwards compatibility): previously HVAC Sync had its own
# independent schedule. As of 0.1.6.10, HVAC Sync uses the diffuser Work schedule.
CONF_HVAC_SYNC_DAYS_MASK = "hvac_sync_days_mask"
CONF_HVAC_SYNC_START = "hvac_sync_start"
CONF_HVAC_SYNC_END = "hvac_sync_end"
CONF_HVAC_SYNC_ON_DELAY_SECONDS = "hvac_sync_on_delay_seconds"
CONF_HVAC_SYNC_OFF_DELAY_SECONDS = "hvac_sync_off_delay_seconds"

DEFAULT_HVAC_SYNC_ENABLED = False
DEFAULT_HVAC_SYNC_DAYS_MASK = 0x7F  # Sun..Sat
DEFAULT_HVAC_SYNC_START = "00:00"
DEFAULT_HVAC_SYNC_END = "23:59"
DEFAULT_HVAC_SYNC_ON_DELAY_SECONDS = 60
DEFAULT_HVAC_SYNC_OFF_DELAY_SECONDS = 60

# Mark entities unavailable after this many minutes without RXD updates
OFFLINE_AFTER_MINUTES = 15

MQTT_USERNAME = "jtdevice"
MQTT_PASSWORD = "jiutiankeji"
CLIENT_ID_SUFFIX = "40"

API_BASE = "http://app.felsharegroup.com:7001"
FRONT_URL = "https://app.felsharegroup.com"

MQTT_HOST = "app.felsharegroup.com"
MQTT_PORT = 443
MQTT_WS_PATH = "/mqtt"

# We only forward the platforms we actually implement in this package.
# NOTE: the "time" platform was removed in 0.1.6.10 because HVAC Sync no longer
# exposes separate start/end time entities (it reuses Work schedule).
PLATFORMS: list[str] = ["sensor", "switch", "number", "text", "button", "select"]
