# Changelog

## 0.1.6.5-hardened (Hardening / Stability / Lower-risk client behavior)

Base: **0.1.6.5**

### 🔒 Security & “Anti-ban” hardening (no spoofing)
- **Outbound MQTT rate limiting** (new)
  - Output queue for publishes
  - Defaults: **min 1s** between publishes + **max burst 3** (sliding window)
- **Coalescing / de-dup of commands**
  - Rapid repeated commands are coalesced so **only the latest** is sent
  - Reduces redundant traffic and “spammy” patterns

### 🔁 Polling & State
- **Debounce** for `request_status()`
  - Will not run more than **once per 60s** by default
- **Strict throttle for bulk status (0x0C)**
  - Sent at most **once per 6 hours** by default
  - Allowed earlier only when work-schedule state appears **stale/unknown**

### 🔌 MQTT reconnections
- **Removed “startup spam”** on reconnect
  - On reconnect, the integration does **not** automatically send `0x05/0x0C`
  - It only requests status if **no prior state** exists, or `last_seen` is **stale**

### 🌐 Login & HTTP
- **More polite HTTP headers** on login/device list
  - `User-Agent: HomeAssistant-Felshare/<version>`
  - `Accept: application/json`
- **Explicit HTTP error handling**
  - `401/403`: controlled pause (no aggressive loops)
  - `429`: stronger backoff (server rate limiting)

### ⚙️ Configuration & UX
- New **Options Flow** knobs:
  - Min publish interval (seconds)
  - Max burst messages
  - Min `request_status()` interval (seconds)
  - Bulk (0x0C) interval (hours)
  - Startup stale threshold (minutes)
- Updated safe recommendation:
  - HA polling: **30–60 minutes**, or **0** if MQTT is stable

### 📊 Observability
- Added internal timestamps in diagnostics:
  - `last_seen_ts`
  - `last_publish_ts`
  - `last_status_request_ts`
  - `last_bulk_request_ts`

### 🧩 Compatibility
- 100% compatible with Home Assistant
- Does not break existing entities
- No YAML changes required
- Intentionally **does not** include spoofing/evasion techniques

---

## 0.1.6.5

- Added options: polling interval, TXD learning toggle, and max backoff.
- Improved reconnect behavior to reuse tokens, apply exponential backoff with jitter, and avoid aggressive re-login loops.
- Cleanly stop paho loop threads on disconnect to prevent leaked clients/threads.

## 0.1.6.4

- HACS-ready repository layout (added `hacs.json`, docs, and repository assets)
- Added `paho-mqtt==2.1.0` to `manifest.json` requirements
- Minor internal improvements for thread safety and persistence
