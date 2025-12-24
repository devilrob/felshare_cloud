from __future__ import annotations

DOMAIN = "felshare"

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

DEFAULT_POLL_INTERVAL_MINUTES = 15
DEFAULT_ENABLE_TXD_LEARNING = False
DEFAULT_MAX_BACKOFF_SECONDS = 900

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
PLATFORMS: list[str] = ["sensor", "switch", "number", "text", "button"]
