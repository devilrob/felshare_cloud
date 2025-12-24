# Changelog

## 0.1.6.5-hardened-2 (Bugfix)
Base: **0.1.6.5-hardened-1**

### ✅ Fixes
- **Work Schedule days mapping corrected** to match Felshare app / device bitmask (**Sun=1, Mon=2, Tue=4, Wed=8, Thu=16, Fri=32, Sat=64**).
  - Day switches in Home Assistant now **match the same day** in the Felshare app.
- **Fixed Work Schedule day toggles action error**
  - Wrapped `publish_work_schedule(...days_mask=...)` with `functools.partial()` to avoid passing kwargs directly into `HomeAssistant.async_add_executor_job()`.

## 0.1.6.5-hardened-1 (Hardening / Stability / Lower-risk client behavior)
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
  - Sent at most **once per 6 hours** by default, or when state is stale

### 🔌 MQTT Reconnections
- **Removed “startup spam”**
  - On MQTT reconnect we do **not** automatically send 0x05 / 0x0C
  - Only requested if there is no prior state or `last_seen` is too old

### 🌐 Login & HTTP
- **More “polite” HTTP headers** for login
  - `User-Agent: HomeAssistant-Felshare/<version>`
  - `Accept: application/json`
- **Explicit HTTP error handling**
  - 401 / 403: token invalid → controlled pause, no aggressive loops
  - 429: stronger backoff

### ⚙️ Configuración & UX
- **New Options Flow settings**
  - Min interval between MQTT publishes
  - Min interval for `request_status()`
  - Bulk status interval (0x0C)

### 📊 Observabilidad
- Added internal timestamps:
  - `last_seen_ts`
  - `last_publish_ts`
  - `last_status_request_ts`
  - `last_bulk_request_ts`

### 🧩 Compatibilidad
- ✅ Compatible with Home Assistant
- ✅ Does not break existing entities
- ✅ No YAML changes required
- ❌ No evasion/spoofing techniques (intentional)
