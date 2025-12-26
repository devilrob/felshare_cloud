# Changelog

## 0.1.6.13
### ⏱️ HVAC Sync forces Work run/stop (60/180)
- When **HVAC Sync** is turned ON, the integration sets:
  - **Work run (seconds)** = **60**
  - **Work stop (seconds)** = **180**
  (device-safe values under the 999s limit)
- When HVAC Sync is turned OFF, the integration restores the previous manual Work schedule values
  from the persistent manual snapshot.

## 0.1.6.12
### 🌬️ HVAC Sync improved for Felshare "Work mode required" devices
- HVAC Sync **no longer disables Work schedule (work mode)**.
  - Some Felshare models ignore **Power ON** unless Work mode is enabled.
  - HVAC Sync now **keeps Work schedule enabled** and gates diffusion by toggling **Power ON/OFF**.
- New entity: **HVAC sync airflow** (select)
  - Choose what counts as "air running": **Cooling only** (default), **Heat + Cool**, or **Any airflow (Heat/Cool/Fan)**.
- README updated with guidance for **Google Nest** thermostats and the new airflow mode.

## 0.1.6.11
### 🧠 HVAC Sync manual snapshot + lock
- When **HVAC Sync** is turned ON, the integration saves a **persistent snapshot** of the diffuser's last manual settings.
- While HVAC Sync is ON, **manual diffuser controls are locked** (attempts to change them from HA will be rejected).
- When HVAC Sync is turned OFF, the integration **restores the last saved manual settings** automatically.

## 0.1.6.10
### 🔁 HVAC Sync now reuses Work schedule (no duplicates)
- HVAC Sync no longer has its own separate days/start/end entities.
- HVAC Sync uses the diffuser **Work schedule** (days + start/end) and simply toggles the diffuser schedule ON/OFF based on thermostat **cooling**.
- Legacy HVAC Sync day/time entities are automatically **disabled & hidden** on upgrade to reduce clutter.
- Work schedule edits (days/start/end/on/off) now trigger an immediate HVAC Sync re-evaluation.

## 0.1.6.9
### 🧩 UI / Entity grouping
- Removed `entity_category: config` from user-facing controls (Work schedule, HVAC Sync, oil settings).
  - This prevents Home Assistant from putting *everything* under the device **Configuration** section.
  - Entities now show under normal **Controls/Sensors** and can be arranged in Lovelace cards as you prefer.
  - On upgrade, the integration also clears previously stored "config" categories from the entity registry.

## 0.1.6.8
### ✅ Release cleanup (publish-ready)
- Version scheme normalized to **0.1.6.8** (no extra suffix).
- Package cleaned (no `__pycache__` / `.pyc`).
- Manifest validated for HACS (keys sorted, valid JSON).
- Short README disclaimer for **unofficial / private API** usage.

## 0.1.6.7
### 🧾 Logging & Diagnostics
- Added verbose logs for:
  - outbound MQTT queueing / coalescing / sending
  - status polling debounce + bulk (0x0C) throttling decisions
  - Work Schedule publish + parsing
  - HVAC Sync evaluations and actions
- Added diagnostic attributes on MQTT status sensor:
  - `last_tx_*`, `outbox_len`, `last_error`, `hvac_sync_*`

### ⏱️ Work run/stop limit
- UI + validation capped at **999 seconds** for:
  - Work run (seconds)
  - Work stop (seconds)
- Values above 999 are clamped and logged.

## 0.1.6.6
### 🌬️ HVAC Sync (Home Assistant local control)
- User can pick a thermostat (`climate.*`) and sync diffuser with **cooling** (`hvac_action: cooling`).
- Schedule controls: days of week + start/end time.
- Optional on/off delays to prevent rapid toggling.

## 0.1.6.5
### 🔒 Stability / “polite” behavior (private API friendly)
- Rate limiting outbound MQTT (default 1s min interval, burst 3).
- Coalescing / deduplication of repeated commands.
- Debounced `request_status()` (min 60s).
- Throttled bulk status `0x0C` (max every 6h, or when stale).
- Reduced reconnect “startup spam” (no automatic 0x05/0x0C unless needed).
- HTTP login uses standard headers + explicit handling of 401/403/429 with controlled backoff.
