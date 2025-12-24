from __future__ import annotations

import json
import logging
import random
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict, deque
from datetime import datetime
from typing import Callable, Optional

import paho.mqtt.client as mqtt
from paho.mqtt.client import CallbackAPIVersion

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    DOMAIN,
    VERSION,
    API_BASE,
    FRONT_URL,
    MQTT_HOST,
    MQTT_PORT,
    MQTT_USERNAME,
    MQTT_PASSWORD,
    MQTT_WS_PATH,
    CLIENT_ID_SUFFIX,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_DEVICE_ID,
    CONF_ENABLE_TXD_LEARNING,
    CONF_MAX_BACKOFF_SECONDS,
    DEFAULT_ENABLE_TXD_LEARNING,
    DEFAULT_MAX_BACKOFF_SECONDS,
    # Hardening options
    CONF_MIN_PUBLISH_INTERVAL_SECONDS,
    CONF_MAX_BURST_MESSAGES,
    CONF_STATUS_MIN_INTERVAL_SECONDS,
    CONF_BULK_MIN_INTERVAL_HOURS,
    CONF_STARTUP_STALE_MINUTES,
    DEFAULT_MIN_PUBLISH_INTERVAL_SECONDS,
    DEFAULT_MAX_BURST_MESSAGES,
    DEFAULT_STATUS_MIN_INTERVAL_SECONDS,
    DEFAULT_BULK_MIN_INTERVAL_HOURS,
    DEFAULT_STARTUP_STALE_MINUTES,
)
from .models import FelshareState


StateCallback = Callable[[FelshareState], None]


def _bytes_to_hex(b: bytes) -> str:
    return b.hex(" ", 1)


class FelshareHub:
    """Handles API login + MQTT in a background thread (paho-mqtt).

    Hardened goals:
    - Rate limit outbound MQTT (min interval + burst cap)
    - Coalesce duplicate / rapid-fire commands
    - Debounce status polling and bulk (0x0C)
    - Avoid "startup spam" on reconnect
    - Use polite HTTP headers and safer backoff
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.logger = logging.getLogger(__name__)

        self.email: str = entry.data[CONF_EMAIL]
        self.password: str = entry.data[CONF_PASSWORD]
        self.device_id: str = entry.data[CONF_DEVICE_ID]

        # Options (safe defaults)
        self._enable_txd_learning = bool(
            entry.options.get(CONF_ENABLE_TXD_LEARNING, DEFAULT_ENABLE_TXD_LEARNING)
        )
        self._max_backoff_seconds = self._as_int_option(
            CONF_MAX_BACKOFF_SECONDS, DEFAULT_MAX_BACKOFF_SECONDS, min_v=30, max_v=3600
        )

        # Hardening options
        self._min_publish_interval_s = self._as_float_option(
            CONF_MIN_PUBLISH_INTERVAL_SECONDS,
            DEFAULT_MIN_PUBLISH_INTERVAL_SECONDS,
            min_v=0.2,
            max_v=10.0,
        )
        self._max_burst = self._as_int_option(
            CONF_MAX_BURST_MESSAGES,
            DEFAULT_MAX_BURST_MESSAGES,
            min_v=1,
            max_v=20,
        )
        self._status_min_interval_s = self._as_int_option(
            CONF_STATUS_MIN_INTERVAL_SECONDS,
            DEFAULT_STATUS_MIN_INTERVAL_SECONDS,
            min_v=10,
            max_v=3600,
        )
        self._bulk_min_interval_s = 3600 * self._as_int_option(
            CONF_BULK_MIN_INTERVAL_HOURS,
            DEFAULT_BULK_MIN_INTERVAL_HOURS,
            min_v=1,
            max_v=72,
        )
        self._startup_stale_after_s = 60 * self._as_int_option(
            CONF_STARTUP_STALE_MINUTES,
            DEFAULT_STARTUP_STALE_MINUTES,
            min_v=1,
            max_v=24 * 60,
        )

        self.state = FelshareState(device_id=self.device_id)

        # Learn/persist the app's "status request" TXD payload so HA can request state on startup.
        self._store = Store(hass, 1, f"{DOMAIN}.sync_{entry.entry_id}")
        self._sync_payload: bytes | None = None
        self._last_txd_payload: bytes | None = None
        self._last_txd_ts: float = 0.0

        self._token: Optional[str] = None
        self._mqtt: Optional[mqtt.Client] = None
        # Keep a reference to the current paho client so we can stop its loop thread cleanly.
        self._client: Optional[mqtt.Client] = None
        self._last_connect_rc: int | None = None
        self._last_disconnect_rc: int | None = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._cb: Optional[StateCallback] = None

        self._lock = threading.Lock()

        # Outbound MQTT hardening
        self._outbox: "OrderedDict[str, bytes]" = OrderedDict()
        self._outbox_cv = threading.Condition()
        self._publish_history: deque[float] = deque(maxlen=200)

        # Login throttling (HTTP 401/403/429)
        self._login_blocked_until: float = 0.0

    # ---------------- lifecycle (HA loop) ----------------
    async def async_start(self, cb: StateCallback) -> None:
        self._cb = cb
        # Load saved sync payload (if any) so we can request state on startup.
        try:
            data = await self._store.async_load()
            if isinstance(data, dict) and data.get("payload_hex"):
                self._sync_payload = bytes.fromhex(str(data["payload_hex"]))
        except Exception:
            pass
        # Do blocking start in executor to avoid blocking HA loop.
        await self.hass.async_add_executor_job(self._start_blocking)

    async def async_stop(self) -> None:
        await self.hass.async_add_executor_job(self._stop_blocking)

    # ---------------- blocking section ----------------
    def _start_blocking(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="felshare_hub", daemon=True)
        self._thread.start()

    def _stop_blocking(self) -> None:
        self._stop.set()
        self._stop_mqtt_client()
        with self._outbox_cv:
            self._outbox.clear()
            self._outbox_cv.notify_all()

    def _emit(self) -> None:
        # Callback is expected to be thread-safe (coordinator marshals into HA loop).
        if self._cb:
            try:
                self._cb(self.state)
            except Exception:
                # Never let callback exceptions crash the MQTT thread.
                self.logger.debug("State callback raised", exc_info=True)

    def _persist_sync_payload(self, payload: bytes) -> None:
        try:
            from asyncio import run_coroutine_threadsafe

            run_coroutine_threadsafe(
                self._store.async_save({"payload_hex": payload.hex()}),
                self.hass.loop,
            )
        except Exception as e:
            self.logger.debug("Failed persisting sync payload: %s", e)

    def _rc_to_int(self, rc) -> int | None:
        if rc is None:
            return None
        try:
            return int(getattr(rc, "value", rc))
        except Exception:
            return None

    def _sleep_backoff(self, seconds: float) -> None:
        """Sleep with jitter, but return immediately when stop is set."""
        if seconds <= 0:
            return
        # +-20% jitter to avoid a perfectly periodic (bot-like) pattern.
        jitter = random.uniform(-0.2, 0.2) * seconds
        delay = max(1.0, seconds + jitter)
        self._stop.wait(delay)

    def _stop_mqtt_client(self) -> None:
        """Stop the current paho loop thread and drop client references."""
        with self._lock:
            c = self._client
            self._client = None
            self._mqtt = None
        if c:
            try:
                c.disconnect()
            except Exception:
                pass
            try:
                c.loop_stop()
            except Exception:
                pass
        with self._outbox_cv:
            self._outbox_cv.notify_all()

    # ---------------- hardening: status requests ----------------
    def request_status(self) -> None:
        """Ask the device to publish its current status.

        Debounced and bulk-throttled to reduce backend load.
        """
        now = time.time()

        # Debounce: avoid multiple status requests per minute (default).
        if self.state.last_status_request_ts and (now - self.state.last_status_request_ts) < self._status_min_interval_s:
            return

        # Status request (sync payload if learned; else 0x05)
        try:
            self.state.last_status_request_ts = now
            payload = self._sync_payload if self._sync_payload else b"\x05"
            self._publish(payload, key="status_request")
        except Exception as e:
            self.logger.debug("request_status status publish failed: %s", e)

        # Bulk request 0x0C (work schedule etc.)
        if self._should_request_bulk(now):
            try:
                self.state.last_bulk_request_ts = now
                self._publish(b"\x0C", key="bulk_request")
            except Exception as e:
                self.logger.debug("request_status bulk publish failed: %s", e)

        self._emit()

    def _should_request_bulk(self, now: float) -> bool:
        # Strict cap: at most once per configured interval, unless state appears stale.
        last = self.state.last_bulk_request_ts
        if last and (now - last) < self._bulk_min_interval_s:
            # Allow early refresh only if we don't have schedule fields yet.
            return self._bulk_state_is_stale()
        return True

    def _bulk_state_is_stale(self) -> bool:
        d = self.state
        # If any key work fields are missing, we consider bulk state stale.
        if not d.work_start or not d.work_end:
            return True
        if d.work_run_s is None or d.work_stop_s is None:
            return True
        if d.work_days_mask is None or d.work_enabled is None:
            return True
        return False

    # ---------------- login (HTTP) ----------------
    def _login(self) -> bool:
        """Login to Felshare cloud API and store session token.

        Uses stdlib urllib to avoid external deps.
        """
        try:
            url = f"{API_BASE}/login"
            payload = json.dumps({"username": self.email, "password": self.password}).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": f"HomeAssistant-Felshare/{VERSION}",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read()
            data = json.loads(raw.decode("utf-8", errors="ignore"))
            tok = data.get("data", {}).get("token") if isinstance(data, dict) else None
            if tok:
                self._token = tok
                return True
        except urllib.error.HTTPError as e:
            code = getattr(e, "code", None)
            # Read body (best-effort) for debugging.
            try:
                _ = e.read()
            except Exception:
                pass

            # Explicit handling to avoid aggressive retry loops.
            if code in (401, 403):
                self.logger.warning("Login rejected (HTTP %s). Pausing to avoid retry loops.", code)
                self._login_blocked_until = max(self._login_blocked_until, time.time() + min(3600, self._max_backoff_seconds))
            elif code == 429:
                retry_after = 0
                try:
                    ra = e.headers.get("Retry-After")
                    retry_after = int(ra) if ra else 0
                except Exception:
                    retry_after = 0
                cooldown = max(120, retry_after or 0)
                cooldown = min(max(cooldown, 120), max(300, self._max_backoff_seconds))
                self.logger.warning("Login rate-limited (HTTP 429). Backing off for ~%ss.", cooldown)
                self._login_blocked_until = max(self._login_blocked_until, time.time() + cooldown)
            else:
                self.logger.warning("Login HTTP error (HTTP %s): %s", code, e)

        except Exception as e:
            # Login can fail temporarily due to network issues.
            self.logger.warning("Login failed: %s", e)
            self.logger.debug("Login traceback", exc_info=True)

        self._token = None
        return False

    # ---------------- main background loop ----------------
    def _run(self) -> None:
        """Main background loop."""

        login_backoff = 5.0
        mqtt_backoff = 3.0
        mqtt_failures_with_token = 0

        while not self._stop.is_set():
            # Respect cooldowns from HTTP 401/403/429.
            if self._login_blocked_until and time.time() < self._login_blocked_until:
                self._set_connected(False)
                self._stop.wait(max(1.0, self._login_blocked_until - time.time()))
                continue

            if not self._token:
                ok = self._login()
                if not ok:
                    self._set_connected(False)
                    self._sleep_backoff(login_backoff)
                    login_backoff = min(login_backoff * 2.0, float(self._max_backoff_seconds))
                    continue
                # Login success
                login_backoff = 5.0
                mqtt_failures_with_token = 0
                mqtt_backoff = 3.0

            try:
                self._connect_mqtt()
                mqtt_backoff = 3.0
                mqtt_failures_with_token = 0

                # While connected: service outbox with rate limiting.
                self._service_outbox_until_disconnect()

                # Disconnected: stop paho loop thread cleanly before reconnecting.
                self._stop_mqtt_client()

            except PermissionError as e:
                # Likely invalid/expired token; relogin with backoff.
                self.logger.warning("MQTT authorization failed: %s", e)
                self._stop_mqtt_client()
                self._token = None
                mqtt_failures_with_token = 0

            except Exception as e:
                self.logger.error("MQTT error: %s", e)
                self._stop_mqtt_client()
                mqtt_failures_with_token += 1

            self._set_connected(False)
            if self._stop.is_set():
                break

            # Decide whether we need to force a relogin.
            rc = self._last_connect_rc if self._last_connect_rc not in (None, 0) else self._last_disconnect_rc
            if rc in (4, 5):
                self.logger.info("MQTT rc=%s (auth/permission). Forcing relogin.", rc)
                self._token = None
                mqtt_failures_with_token = 0
            elif mqtt_failures_with_token >= 3:
                self.logger.warning("Repeated MQTT failures; forcing relogin to refresh token.")
                self._token = None
                mqtt_failures_with_token = 0

            self._sleep_backoff(mqtt_backoff)
            mqtt_backoff = min(mqtt_backoff * 2.0, float(self._max_backoff_seconds))

    def _set_connected(self, connected: bool) -> None:
        self.state.connected = connected
        self._emit()

    # ---------------- MQTT connect + callbacks ----------------
    def _connect_mqtt(self) -> None:
        dev = self.device_id
        # Add entry_id to reduce the chance of session collisions with the mobile app.
        client_id = f"{dev}{CLIENT_ID_SUFFIX}ha_{self.entry.entry_id[:6]}"

        self._last_connect_rc = None
        self._last_disconnect_rc = None

        c = mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id=client_id,
            transport="websockets",
            protocol=mqtt.MQTTv311,
            clean_session=True,
        )
        with self._lock:
            self._client = c
        c.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

        ctx = ssl.create_default_context()
        c.tls_set_context(ctx)
        c.tls_insecure_set(False)

        ws_headers = {"Cookie": f"token={self._token}", "Origin": FRONT_URL}
        c.ws_set_options(path=MQTT_WS_PATH, headers=ws_headers)
        c.reconnect_delay_set(min_delay=1, max_delay=30)

        topic_rxd = f"/device/rxd/{dev}"
        topic_txd = f"/device/txd/{dev}"

        def on_connect(client, userdata, flags, reason_code, properties=None):
            rc_int = self._rc_to_int(reason_code)
            self._last_connect_rc = rc_int
            if rc_int == 0:
                with self._lock:
                    self._mqtt = client
                self._set_connected(True)
                self.logger.info("MQTT connected")
                client.subscribe(topic_rxd, qos=0)
                # Optional: subscribe to TXD only to "learn" the app's sync payload.
                if self._enable_txd_learning:
                    client.subscribe(topic_txd, qos=0)

                # Avoid startup spam on reconnection.
                try:
                    if self._should_request_on_connect():
                        self.request_status()
                except Exception as e:
                    self.logger.debug("Startup request suppressed/failed: %s", e)
            else:
                self.logger.error("MQTT connect failed (rc=%s)", rc_int)
                self._set_connected(False)

        def on_disconnect(client, userdata, disconnect_flags, reason_code, properties=None):
            self._last_disconnect_rc = self._rc_to_int(reason_code)
            with self._lock:
                if self._mqtt is client:
                    self._mqtt = None
            self.logger.warning("MQTT disconnected (rc=%s)", self._last_disconnect_rc)
            self._set_connected(False)
            with self._outbox_cv:
                self._outbox_cv.notify_all()

        def on_message(client, userdata, msg):
            payload: bytes = msg.payload or b""
            now_ts = time.time()
            self.state.last_seen = datetime.utcnow()
            self.state.last_seen_ts = now_ts
            self.state.last_topic = msg.topic
            self.state.last_payload_hex = _bytes_to_hex(payload)

            # Remember last TXD payload (optional "learning" mode only).
            if self._enable_txd_learning and msg.topic == topic_txd and payload:
                self._last_txd_payload = payload
                self._last_txd_ts = now_ts

            # Parse frames coming from the device (RXD only).
            if payload and msg.topic == topic_rxd:
                if payload[0] == 0x05:
                    # If we just saw a TXD packet and now we get a status frame, learn the TXD as "sync" request.
                    if (
                        self._enable_txd_learning
                        and self._last_txd_payload
                        and (now_ts - self._last_txd_ts) < 2.0
                    ):
                        op = self._last_txd_payload[0]
                        # Ignore our own "set" commands; we want the app's "status request".
                        if op not in (0x03, 0x04, 0x08, 0x0E, 0x0F, 0x10, 0x32):
                            if self._sync_payload != self._last_txd_payload:
                                self._sync_payload = self._last_txd_payload
                                self._persist_sync_payload(self._last_txd_payload)
                                self.logger.info(
                                    "Learned sync payload from app: %s",
                                    _bytes_to_hex(self._last_txd_payload),
                                )
                    self._parse_rxd_status(payload)
                elif payload[0] == 0x0C:
                    self._parse_bulk_settings(payload)
                elif payload[0] == 0x32:
                    self._parse_workmode_frame(payload)
                else:
                    self._parse_simple_frame(payload)

            self._emit()

        c.on_connect = on_connect
        c.on_disconnect = on_disconnect
        c.on_message = on_message

        try:
            c.connect(MQTT_HOST, MQTT_PORT, keepalive=20)
            c.loop_start()

            # wait for connect or stop
            t0 = time.time()
            while not self._stop.is_set():
                if self.state.connected:
                    return

                # If broker rejected the connection, fail fast.
                if self._last_connect_rc is not None and self._last_connect_rc != 0:
                    rc = self._last_connect_rc
                    if rc in (4, 5):
                        raise PermissionError(f"MQTT not authorized (rc={rc})")
                    raise RuntimeError(f"MQTT connect failed (rc={rc})")

                if time.time() - t0 > 15:
                    raise RuntimeError("MQTT connect timeout")
        except Exception:
            # Ensure we don't leak a paho thread when the connect attempt fails.
            with self._lock:
                if self._client is c:
                    self._client = None
                if self._mqtt is c:
                    self._mqtt = None
            try:
                c.disconnect()
            except Exception:
                pass
            try:
                c.loop_stop()
            except Exception:
                pass
            raise

    def _should_request_on_connect(self) -> bool:
        """Decide whether we should send status requests when MQTT connects.

        We avoid sending 0x05/0x0C on every reconnect; only if we have no prior state
        or the last_seen is considered stale.
        """
        now = time.time()

        # No state yet
        if self.state.last_seen_ts is None:
            return True

        # Key fields never populated (treat as no state)
        if self.state.power_on is None and self.state.fan_on is None and self.state.oil_name is None:
            return True

        # Stale
        if (now - self.state.last_seen_ts) >= self._startup_stale_after_s:
            return True

        return False

    # ---------------- outbound publish queue ----------------
    def _payload_key(self, payload: bytes) -> str:
        if payload == b"\x0C":
            return "bulk_request"
        if payload == b"\x05" or (payload and payload[0] == 0x05 and len(payload) == 1):
            return "status_request"
        if payload and payload[0] == 0x32:
            return "work_schedule"
        if payload and payload[0] == 0x08:
            return "oil_name"
        if payload and payload[0] == 0x03:
            return "power"
        if payload and payload[0] == 0x04:
            return "fan"
        if payload and payload[0] == 0x0E:
            return "consumption"
        if payload and payload[0] == 0x0F:
            return "capacity"
        if payload and payload[0] == 0x10:
            return "remain_oil"
        # Fallback: dedupe only exact payloads
        return f"raw:{payload.hex()}"

    def _rate_limiter_delay(self, now: float) -> float:
        # Enforce minimum spacing.
        delay = 0.0
        last_pub = self.state.last_publish_ts
        if last_pub is not None:
            dt = now - last_pub
            if dt < self._min_publish_interval_s:
                delay = max(delay, self._min_publish_interval_s - dt)

        # Enforce burst cap inside a sliding window.
        window = max(self._min_publish_interval_s * float(self._max_burst), self._min_publish_interval_s)
        while self._publish_history and (now - self._publish_history[0]) > window:
            self._publish_history.popleft()
        if len(self._publish_history) >= self._max_burst:
            oldest = self._publish_history[0]
            delay = max(delay, (oldest + window) - now)

        return max(0.0, delay)

    def _service_outbox_until_disconnect(self) -> None:
        """Runs in the hub thread while MQTT is connected."""
        while not self._stop.is_set():
            with self._lock:
                connected = self._mqtt is not None and self.state.connected
            if not connected:
                return

            key: str | None = None
            payload: bytes | None = None

            with self._outbox_cv:
                if not self._outbox:
                    self._outbox_cv.wait(timeout=0.5)
                    continue

                now = time.time()
                delay = self._rate_limiter_delay(now)
                if delay > 0:
                    # Wake early if new commands arrive.
                    self._outbox_cv.wait(timeout=min(delay, 2.0))
                    continue

                key, payload = self._outbox.popitem(last=False)

            if payload is None:
                continue

            try:
                self._publish_now(payload)
            except Exception as e:
                # If disconnected mid-flight, requeue and let reconnect logic handle it.
                self.logger.debug("Publish failed (%s): %s", key, e)
                with self._outbox_cv:
                    # Put it back at the front.
                    if key:
                        self._outbox[key] = payload
                        self._outbox.move_to_end(key, last=False)
                        self._outbox_cv.notify_all()
                return

    def _publish_now(self, payload: bytes) -> None:
        dev = self.device_id
        topic = f"/device/txd/{dev}"
        with self._lock:
            c = self._mqtt
        if not c or not self.state.connected:
            raise RuntimeError("MQTT not connected")

        c.publish(topic, payload, qos=0, retain=False)

        now = time.time()
        self.state.last_publish_ts = now
        self._publish_history.append(now)

    def _publish(self, payload: bytes, *, key: str | None = None) -> None:
        """Enqueue a payload for outbound publish (coalesced + rate-limited)."""
        with self._lock:
            c = self._mqtt
            connected = bool(c) and self.state.connected
        if not connected:
            raise RuntimeError("MQTT not connected")

        k = key or self._payload_key(payload)
        with self._outbox_cv:
            self._outbox[k] = payload
            # Ensure the newest request for the same key is sent last.
            self._outbox.move_to_end(k, last=True)
            self._outbox_cv.notify_all()

    # ---------------- parsing ----------------
    def _parse_rxd_status(self, p: bytes) -> None:
        # Empirical parsing from captures:
        # [0]=0x05, [1:]=datetime, then fields:
        # fan appears at index 10 (0/1)
        # power appears at index 9 (0/1)
        # consumption tenths (BE) at [11:13]
        # capacity ml (BE) at [13:15]
        # remain oil ml (BE) at [20:22]
        # oil name ASCII from [24:] until 0x00
        try:
            # switches
            if len(p) > 10:
                self.state.power_on = bool(p[9])
                self.state.fan_on = bool(p[10])

            if len(p) >= 15:
                cons_raw = int.from_bytes(p[11:13], "big", signed=False)  # e.g. 0x0023 -> 35
                cap = int.from_bytes(p[13:15], "big", signed=False)  # e.g. 0x00FA -> 250
                if 0 <= cons_raw <= 2000:
                    self.state.consumption = cons_raw / 10.0
                if 0 < cap <= 5000:
                    self.state.capacity = cap

            if len(p) >= 22:
                remain = int.from_bytes(p[20:22], "big", signed=False)
                if 0 <= remain <= 10000:
                    self.state.remain_oil = remain

            # oil name
            if len(p) >= 26:
                name_bytes = p[24:]
                if 0 in name_bytes:
                    name_bytes = name_bytes.split(b"\x00", 1)[0]
                try:
                    name = name_bytes.decode("utf-8", errors="ignore").strip()
                except Exception:
                    name = ""
                if name:
                    self.state.oil_name = name

            # derived liquid level %
            if self.state.capacity and self.state.remain_oil is not None and self.state.capacity > 0:
                self.state.liquid_level = int((self.state.remain_oil * 100) // self.state.capacity)

        except Exception as e:
            self.logger.debug("Failed parsing RXD payload: %s", e)

    def _decode_days_mask(self, mask: int) -> str:
        # Device mapping: Sun=1, Mon=2, Tue=4, Wed=8, Thu=16, Fri=32, Sat=64
        order = [
            ("Mon", 0x02),
            ("Tue", 0x04),
            ("Wed", 0x08),
            ("Thu", 0x10),
            ("Fri", 0x20),
            ("Sat", 0x40),
            ("Sun", 0x01),
        ]
        out = [name for name, bit in order if mask & bit]
        return ",".join(out) if out else "-"

    def _set_work_schedule(
        self,
        start_h: int,
        start_m: int,
        end_h: int,
        end_m: int,
        flag: int,
        run_s: int,
        stop_s: int,
    ) -> None:
        self.state.work_start = f"{start_h:02d}:{start_m:02d}"
        self.state.work_end = f"{end_h:02d}:{end_m:02d}"
        self.state.work_flag_raw = flag & 0xFF
        self.state.work_enabled = bool(flag & 0x80)
        self.state.work_days_mask = flag & 0x7F
        # Keep a human-friendly representation for UI entities.
        try:
            self.state.work_days = self._decode_days_mask(self.state.work_days_mask or 0)
        except Exception:
            self.state.work_days = None
        self.state.work_run_s = int(run_s)
        self.state.work_stop_s = int(stop_s)

    def _parse_workmode_frame(self, p: bytes) -> None:
        """Parse 0x32 0x01 WorkTime frame."""
        try:
            if len(p) != 11 or p[0] != 0x32:
                return
            # 32 01 sh sm eh em flag runHi runLo stopHi stopLo
            start_h, start_m, end_h, end_m = p[2], p[3], p[4], p[5]
            flag = p[6]
            run_s = int.from_bytes(p[7:9], "big", signed=False)
            stop_s = int.from_bytes(p[9:11], "big", signed=False)
            self._set_work_schedule(start_h, start_m, end_h, end_m, flag, run_s, stop_s)
        except Exception as e:
            self.logger.debug("Failed parsing workmode frame: %s", e)

    def _parse_bulk_settings(self, p: bytes) -> None:
        """Parse 0x0C bulk settings frame.

        Based on captures, bytes 11..19 embed the same WorkTime payload minus the leading 32 01:
          [11]=sh [12]=sm [13]=eh [14]=em [15]=flag [16:18]=runBE [18:20]=stopBE
        """
        try:
            if len(p) < 20 or p[0] != 0x0C:
                return

            sh, sm, eh, em = p[11], p[12], p[13], p[14]
            flag = p[15]
            run_s = int.from_bytes(p[16:18], "big", signed=False)
            stop_s = int.from_bytes(p[18:20], "big", signed=False)
            # Basic sanity
            if 0 <= sh <= 23 and 0 <= eh <= 23 and 0 <= sm <= 59 and 0 <= em <= 59:
                self._set_work_schedule(sh, sm, eh, em, flag, run_s, stop_s)
        except Exception as e:
            self.logger.debug("Failed parsing bulk settings: %s", e)

    def _parse_simple_frame(self, p: bytes) -> None:
        """Parse simple single-property frames."""
        try:
            cmd = p[0]
            # power: 0x03 0x01/0x00
            if cmd == 0x03 and len(p) >= 2:
                self.state.power_on = bool(p[1])
                return

            # fan: 0x04 0x01/0x00
            if cmd == 0x04 and len(p) >= 2:
                self.state.fan_on = bool(p[1])
                return

            # oil name: 0x08 + bytes
            if cmd == 0x08 and len(p) >= 2:
                name_bytes = p[1:]
                if 0 in name_bytes:
                    name_bytes = name_bytes.split(b"\x00", 1)[0]
                name = name_bytes.decode("utf-8", errors="ignore").strip()
                if name:
                    self.state.oil_name = name
                return

            # consumption: 0x0E + uint16 (tenths ml/h)
            if cmd == 0x0E and len(p) >= 3:
                raw = int.from_bytes(p[1:3], "big", signed=False)
                self.state.consumption = raw / 10.0
                return

            # capacity: 0x0F + uint16 (ml)
            if cmd == 0x0F and len(p) >= 3:
                raw = int.from_bytes(p[1:3], "big", signed=False)
                self.state.capacity = raw
                if self.state.remain_oil is not None and raw > 0:
                    self.state.liquid_level = int((self.state.remain_oil * 100) // raw)
                return

            # remain oil: 0x10 + uint16 (ml)
            if cmd == 0x10 and len(p) >= 3:
                raw = int.from_bytes(p[1:3], "big", signed=False)
                self.state.remain_oil = raw
                if self.state.capacity and self.state.capacity > 0:
                    self.state.liquid_level = int((raw * 100) // self.state.capacity)
                return

        except Exception as e:
            self.logger.debug("Failed parsing simple frame: %s", e)

    # ---------------- commands ----------------
    def publish_power(self, on: bool) -> None:
        self._publish(bytes([0x03, 0x01 if on else 0x00]), key="power")
        self.state.power_on = on
        self._emit()

    def publish_fan(self, on: bool) -> None:
        self._publish(bytes([0x04, 0x01 if on else 0x00]), key="fan")
        self.state.fan_on = on
        self._emit()

    def publish_oil_name(self, name: str) -> None:
        b = name.encode("utf-8", errors="ignore")[:10]
        self._publish(bytes([0x08]) + b, key="oil_name")
        self.state.oil_name = name
        self._emit()

    def publish_consumption(self, value_ml_per_h: float) -> None:
        raw = int(round(value_ml_per_h * 10))
        raw = max(0, min(raw, 65535))
        self._publish(bytes([0x0E]) + raw.to_bytes(2, "big"), key="consumption")
        self.state.consumption = raw / 10.0
        self._emit()

    def publish_capacity(self, ml: int) -> None:
        raw = max(0, min(int(ml), 65535))
        self._publish(bytes([0x0F]) + raw.to_bytes(2, "big"), key="capacity")
        self.state.capacity = raw
        self._emit()

    def publish_remain_oil(self, ml: int) -> None:
        raw = max(0, min(int(ml), 65535))
        self._publish(bytes([0x10]) + raw.to_bytes(2, "big"), key="remain_oil")
        self.state.remain_oil = raw
        self._emit()

    # ---- Work schedule (WorkTime) ----
    def _parse_hhmm(self, value: str) -> tuple[int, int]:
        v = (value or "").strip()
        hh_s, mm_s = v.split(":", 1)
        hh = int(hh_s)
        mm = int(mm_s)
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            raise ValueError("Invalid HH:MM")
        return hh, mm

    def _days_str_to_mask(self, value: str) -> int:
        """Parse days like: 'Mon,Wed' or 'Lun,Mié'. Mapping: Sun=1, Mon=2, Tue=4, Wed=8, Thu=16, Fri=32, Sat=64."""
        if value is None:
            raise ValueError("days is None")

        raw = value.strip()
        if not raw:
            return 0

        # Allow numeric masks too (e.g. '0x7F' or '127')
        try:
            if raw.lower().startswith("0x"):
                return int(raw, 16) & 0x7F
            if raw.isdigit():
                return int(raw) & 0x7F
        except Exception:
            pass

        tokens = [t.strip().lower() for t in raw.replace(";", ",").replace("|", ",").split(",") if t.strip()]
        mapping = {
            # English
            "mon": 2,
            "monday": 2,
            "tue": 4,
            "tues": 4,
            "tuesday": 4,
            "wed": 8,
            "wednesday": 8,
            "thu": 16,
            "thur": 16,
            "thurs": 16,
            "thursday": 16,
            "fri": 32,
            "friday": 32,
            "sat": 64,
            "saturday": 64,
            "sun": 1,
            "sunday": 1,
            # Spanish
            "lun": 2,
            "lunes": 2,
            "mar": 4,
            "martes": 4,
            "mie": 8,
            "mié": 8,
            "mier": 8,
            "miércoles": 8,
            "miercoles": 8,
            "jue": 16,
            "jueves": 16,
            "vie": 32,
            "viernes": 32,
            "sab": 64,
            "sáb": 64,
            "sábado": 64,
            "sabado": 64,
            "dom": 1,
            "domingo": 1,
            # Short single-letter (optional)
            "m": 2,
            "t": 4,
            "w": 8,
            "r": 16,
            "f": 32,
            "s": 64,
            "u": 1,
        }

        mask = 0
        for tok in tokens:
            if tok in ("all", "every", "todos", "diario", "daily"):
                return 0x7F
            bit = mapping.get(tok)
            if bit is None:
                raise ValueError(f"Unknown day token: {tok}")
            mask |= bit
        return mask & 0x7F

    def publish_work_schedule(
        self,
        *,
        start: str | None = None,
        end: str | None = None,
        run_s: int | None = None,
        stop_s: int | None = None,
        enabled: bool | None = None,
        days_mask: int | None = None,
        days: str | None = None,
    ) -> None:
        """Send WorkTime (32 01 ...) using current state as defaults."""
        # Defaults
        sh, sm = (9, 0)
        eh, em = (21, 0)
        if self.state.work_start:
            try:
                sh, sm = self._parse_hhmm(self.state.work_start)
            except Exception:
                pass
        if self.state.work_end:
            try:
                eh, em = self._parse_hhmm(self.state.work_end)
            except Exception:
                pass

        cur_run = self.state.work_run_s if self.state.work_run_s is not None else 30
        cur_stop = self.state.work_stop_s if self.state.work_stop_s is not None else 190
        cur_enabled = self.state.work_enabled if self.state.work_enabled is not None else True
        cur_days = self.state.work_days_mask if self.state.work_days_mask is not None else 0x7F

        # Apply updates
        if start is not None:
            sh, sm = self._parse_hhmm(start)
        if end is not None:
            eh, em = self._parse_hhmm(end)
        if run_s is not None:
            cur_run = int(run_s)
        if stop_s is not None:
            cur_stop = int(stop_s)
        if enabled is not None:
            cur_enabled = bool(enabled)
        if days is not None:
            cur_days = self._days_str_to_mask(days)
        if days_mask is not None:
            cur_days = int(days_mask) & 0x7F

        # Build flag: enable + days
        flag = (0x80 if cur_enabled else 0x00) | (cur_days & 0x7F)

        payload = (
            bytes([
                0x32,
                0x01,
                sh & 0xFF,
                sm & 0xFF,
                eh & 0xFF,
                em & 0xFF,
                flag & 0xFF,
            ])
            + int(cur_run).to_bytes(2, "big")
            + int(cur_stop).to_bytes(2, "big")
        )

        self._publish(payload, key="work_schedule")
        # Optimistic update
        self._set_work_schedule(sh, sm, eh, em, flag, int(cur_run), int(cur_stop))
        self._emit()

    def publish_work_enabled(self, on: bool) -> None:
        self.publish_work_schedule(enabled=bool(on))

    def publish_work_start(self, hhmm: str) -> None:
        self.publish_work_schedule(start=hhmm)

    def publish_work_end(self, hhmm: str) -> None:
        self.publish_work_schedule(end=hhmm)

    def publish_work_run_s(self, run_s: int) -> None:
        self.publish_work_schedule(run_s=int(run_s))

    def publish_work_stop_s(self, stop_s: int) -> None:
        self.publish_work_schedule(stop_s=int(stop_s))

    def publish_work_days(self, days: str) -> None:
        self.publish_work_schedule(days=days)

    # ---------------- helpers ----------------
    def _as_int_option(self, key: str, default: int, *, min_v: int, max_v: int) -> int:
        try:
            v = int(self.entry.options.get(key, default))
        except Exception:
            v = int(default)
        return max(min_v, min(v, max_v))

    def _as_float_option(self, key: str, default: float, *, min_v: float, max_v: float) -> float:
        try:
            v = float(self.entry.options.get(key, default))
        except Exception:
            v = float(default)
        return max(min_v, min(v, max_v))
