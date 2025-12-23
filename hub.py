from __future__ import annotations

import json
import asyncio
import logging
import ssl
import threading
import time
import urllib.request
import urllib.parse
from datetime import datetime
from typing import Callable, Optional
import paho.mqtt.client as mqtt
from paho.mqtt.client import CallbackAPIVersion

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    DOMAIN,
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
)
from .models import FelshareState


StateCallback = Callable[[FelshareState], None]


def _bytes_to_hex(b: bytes) -> str:
    return b.hex(" ", 1)


class FelshareHub:
    """Handles API login + MQTT in a background thread (paho-mqtt)."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.logger = logging.getLogger(__name__)

        self.email: str = entry.data[CONF_EMAIL]
        self.password: str = entry.data[CONF_PASSWORD]
        self.device_id: str = entry.data[CONF_DEVICE_ID]

        self.state = FelshareState(device_id=self.device_id)

        # Learn/persist the app's "status request" TXD payload so HA can request state on startup.
        self._store = Store(hass, 1, f"{DOMAIN}.sync_{entry.entry_id}")
        self._sync_payload: bytes | None = None
        self._last_txd_payload: bytes | None = None
        self._last_txd_ts: float = 0.0

        self._token: Optional[str] = None
        self._mqtt: Optional[mqtt.Client] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._cb: Optional[StateCallback] = None

        self._lock = threading.Lock()

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
        with self._lock:
            c = self._mqtt
            self._mqtt = None
        try:
            if c:
                c.disconnect()
                c.loop_stop()
        except Exception:
            pass

    def _emit(self) -> None:
        if self._cb:
            # Always marshal to the HA event loop to avoid thread-safety warnings.
            self.hass.loop.call_soon_threadsafe(self._cb, self.state)

    def _persist_sync_payload(self, payload: bytes) -> None:
        async def _save() -> None:
            await self._store.async_save({"payload_hex": payload.hex()})

        try:
            self.hass.loop.call_soon_threadsafe(lambda: asyncio.create_task(_save()))
        except Exception as e:
            self.logger.debug("Failed persisting sync payload: %s", e)

    def request_status(self) -> None:
        """Ask the device to publish its current status (learned from the mobile app)."""
        # In practice we can safely request state with 0x05 (status) and 0x0C (bulk settings).
        # Some firmwares also use a proprietary "sync" payload learned from the mobile app; we still support it.
        try:
            if self._sync_payload:
                self._publish(self._sync_payload)
            else:
                self._publish(b"\x05")
            # Bulk (includes work schedule / days)
            self._publish(b"\x0C")
        except Exception as e:
            self.logger.debug("request_status failed: %s", e)


    def _login(self) -> bool:
        """Login to Felshare cloud API and store session token.

        Uses stdlib urllib to avoid external deps/requirements (and HA pip constraint issues).
        """
        try:
            url = f"{API_BASE}/login"
            payload = json.dumps({"username": self.email, "password": self.password}).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read()
            data = json.loads(raw.decode("utf-8", errors="ignore"))
            tok = data.get("data", {}).get("token") if isinstance(data, dict) else None
            if tok:
                self._token = tok
                return True
        except Exception as e:
            self.logger.error("Login failed: %s", e)
        self._token = None
        return False

    def _run(self) -> None:
        # Keep trying login + mqtt connect until stopped
        while not self._stop.is_set():
            if not self._token:
                ok = self._login()
                if not ok:
                    self._set_connected(False)
                    time.sleep(5)
                    continue

            try:
                self._connect_mqtt()
                # Wait until disconnected or stop
                while not self._stop.is_set() and self._mqtt is not None:
                    time.sleep(0.5)
            except Exception as e:
                self.logger.error("MQTT loop error: %s", e)

            self._set_connected(False)
            # force relogin after connection errors
            self._token = None
            time.sleep(3)

    def _set_connected(self, connected: bool) -> None:
        self.state.connected = connected
        if not connected:
            # Keep last values, but mark disconnected.
            pass
        self._emit()

    # ---------------- MQTT ----------------
    def _connect_mqtt(self) -> None:
        dev = self.device_id
        client_id = f"{dev}{CLIENT_ID_SUFFIX}ha"

        c = mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id=client_id,
            transport="websockets",
            protocol=mqtt.MQTTv311,
            clean_session=True,
        )
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
            if getattr(reason_code, "value", reason_code) == 0:
                with self._lock:
                    self._mqtt = client
                self._set_connected(True)
                self.logger.info("MQTT connected")
                client.subscribe(topic_rxd, qos=0)
                # subscribe txd for debugging only; we DO NOT parse state from it
                client.subscribe(topic_txd, qos=0)
                # Ask device to publish current state on startup.
                # Always request both status (0x05) and bulk settings (0x0C) so HA has values even when the phone app is closed.
                try:
                    if self._sync_payload:
                        client.publish(topic_txd, self._sync_payload, qos=0, retain=False)
                        self.logger.debug("Sent learned sync payload on connect: %s", _bytes_to_hex(self._sync_payload))
                    else:
                        client.publish(topic_txd, b"\x05", qos=0, retain=False)
                        self.logger.debug("Sent default status request (05) on connect")

                    client.publish(topic_txd, b"\x0C", qos=0, retain=False)
                    self.logger.debug("Sent bulk request (0C) on connect")
                except Exception as e:
                    self.logger.debug("Failed sending startup requests: %s", e)
            else:
                self.logger.error("MQTT connect failed: %s", reason_code)
                self._set_connected(False)

        def on_disconnect(client, userdata, disconnect_flags, reason_code, properties=None):
            with self._lock:
                if self._mqtt is client:
                    self._mqtt = None
            self.logger.warning("MQTT disconnected: %s", reason_code)
            self._set_connected(False)

        def on_message(client, userdata, msg):
            payload: bytes = msg.payload or b""
            self.state.last_seen = datetime.utcnow()
            self.state.last_topic = msg.topic
            self.state.last_payload_hex = _bytes_to_hex(payload)

            # Remember last TXD payload (often the app sends a "status request" and device replies with 0x05).
            if msg.topic == topic_txd and payload:
                self._last_txd_payload = payload
                self._last_txd_ts = time.time()

            # Parse frames coming from the device.
            if payload and msg.topic in (topic_rxd, topic_txd):
                if payload[0] == 0x05:
                    # If we just saw a TXD packet and now we get a status frame, learn the TXD as "sync" request.
                    if self._last_txd_payload and (time.time() - self._last_txd_ts) < 2.0:
                        op = self._last_txd_payload[0]
                        # Ignore our own "set" commands; we want the app's "status request".
                        if op not in (0x03, 0x04, 0x08, 0x0E, 0x0F, 0x10, 0x32):
                            if self._sync_payload != self._last_txd_payload:
                                self._sync_payload = self._last_txd_payload
                                self._persist_sync_payload(self._last_txd_payload)
                                self.logger.info("Learned sync payload from app: %s", _bytes_to_hex(self._last_txd_payload))
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

        c.connect(MQTT_HOST, MQTT_PORT, keepalive=20)
        c.loop_start()

        # wait for connect or stop
        t0 = time.time()
        while not self._stop.is_set():
            if self.state.connected:
                return
            if time.time() - t0 > 15:
                raise RuntimeError("MQTT connect timeout")

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
        # Mon..Sun (same mapping we used in the Python capture app)
        names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        out = [names[i] for i in range(7) if (mask >> i) & 1]
        return ",".join(out) if out else "-"


    def _set_work_schedule(self, start_h: int, start_m: int, end_h: int, end_m: int, flag: int, run_s: int, stop_s: int) -> None:
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
        """Parse simple single-property frames.

        Some firmwares send individual updates instead of the big 0x05 status frame.
        This keeps the HA UI from being "blank" (unknown) when those are used.
        """
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
        # 0x03 0x01 = ON, 0x03 0x00 = OFF (captured)
        self._publish(bytes([0x03, 0x01 if on else 0x00]))
        self.state.power_on = on
        self._emit()

    def publish_fan(self, on: bool) -> None:
        # 0x04 0x01 = ON, 0x04 0x00 = OFF (captured)
        self._publish(bytes([0x04, 0x01 if on else 0x00]))
        self.state.fan_on = on
        self._emit()

    def publish_oil_name(self, name: str) -> None:
        # 0x08 + ASCII bytes (captured). Limit to 10 bytes like app seems to do.
        b = name.encode("utf-8", errors="ignore")[:10]
        self._publish(bytes([0x08]) + b)
        self.state.oil_name = name
        self._emit()

    def publish_consumption(self, value_ml_per_h: float) -> None:
        # Captured: 0x0E 0x00 0x23 where 0x0023 = 35 => 3.5
        raw = int(round(value_ml_per_h * 10))
        raw = max(0, min(raw, 65535))
        self._publish(bytes([0x0E]) + raw.to_bytes(2, "big"))
        self.state.consumption = raw / 10.0
        self._emit()

    def publish_capacity(self, ml: int) -> None:
        raw = max(0, min(int(ml), 65535))
        self._publish(bytes([0x0F]) + raw.to_bytes(2, "big"))
        self.state.capacity = raw
        self._emit()

    def publish_remain_oil(self, ml: int) -> None:
        raw = max(0, min(int(ml), 65535))
        self._publish(bytes([0x10]) + raw.to_bytes(2, "big"))
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
        """Parse days like: 'Mon,Wed' or 'Lun,Mié'. Mapping: Mon=1 .. Sun=64."""
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
            "mon": 1,
            "monday": 1,
            "tue": 2,
            "tues": 2,
            "tuesday": 2,
            "wed": 4,
            "wednesday": 4,
            "thu": 8,
            "thur": 8,
            "thurs": 8,
            "thursday": 8,
            "fri": 16,
            "friday": 16,
            "sat": 32,
            "saturday": 32,
            "sun": 64,
            "sunday": 64,
            # Spanish
            "lun": 1,
            "lunes": 1,
            "mar": 2,
            "martes": 2,
            "mie": 4,
            "mié": 4,
            "mier": 4,
            "miércoles": 4,
            "miercoles": 4,
            "jue": 8,
            "jueves": 8,
            "vie": 16,
            "viernes": 16,
            "sab": 32,
            "sáb": 32,
            "sábado": 32,
            "sabado": 32,
            "dom": 64,
            "domingo": 64,
            # Short single-letter (optional)
            "m": 1,
            "t": 2,
            "w": 4,
            "r": 8,
            "f": 16,
            "s": 32,
            "u": 64,
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
        """Send WorkTime (32 01 ...) using current state as defaults.

        This device expects a full payload whenever you change any part.
        """
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
        cur_flag = self.state.work_flag_raw if self.state.work_flag_raw is not None else ((0x80 if cur_enabled else 0x00) | (cur_days & 0x7F))

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

        # Build flag: preserve nothing except enable+days (bit7 + low7)
        flag = (0x80 if cur_enabled else 0x00) | (cur_days & 0x7F)
        # If we already have a raw flag from the device, keep any unknown bits *within* bit7+low7 representation.
        # (We still overwrite enable/days because user requested it.)
        _ = cur_flag  # reserved for future, keep variable to avoid unused warnings in edits.

        payload = bytes([
            0x32,
            0x01,
            sh & 0xFF,
            sm & 0xFF,
            eh & 0xFF,
            em & 0xFF,
            flag & 0xFF,
        ]) + int(cur_run).to_bytes(2, "big") + int(cur_stop).to_bytes(2, "big")

        self._publish(payload)
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

    def _publish(self, payload: bytes) -> None:
        dev = self.device_id
        topic = f"/device/txd/{dev}"
        with self._lock:
            c = self._mqtt
        if not c or not self.state.connected:
            raise RuntimeError("MQTT not connected")
        c.publish(topic, payload, qos=0, retain=False)