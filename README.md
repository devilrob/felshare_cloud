# Felshare Diffuser (Cloud MQTT) — Home Assistant Custom Integration

Control Felshare waterless diffusers via the Felshare cloud MQTT service.

> ⚠️ **Disclaimer (unofficial / private API)**: Not affiliated with Felshare. This integration uses undocumented/private endpoints and may break at any time. Use at your own risk and respect Felshare’s terms.

## Features

- **Power** switch
- **Fan** switch
- Oil **consumption**, **capacity**, and **remaining oil** controls
- Work schedule controls:
  - Enable/disable schedule
  - Start/End time (HH:MM)
  - Run/Stop seconds
  - Day-of-week mask (Mon–Sun)
- Diagnostics sensor with last seen/topic/payload + timestamps
- **Refresh status** button (best-effort cloud status request)

## Hardening / Stability

- Outbound MQTT publish queue with **rate limiting** + **coalescing**
- Debounced `request_status()` and throttled bulk (0x0C)
- Avoids “startup spam” on MQTT reconnects
- More polite HTTP headers + safer handling of `401/403/429`

## HVAC Sync

If you have a thermostat integrated in Home Assistant (for example **Nest Gen 3**), you can
optionally make the diffuser **follow active airflow**:

- By default, diffuser turns **ON** only when the thermostat reports `hvac_action: cooling`
- Diffuser turns **OFF** when airflow stops (or cooling stops, depending on mode)
- Schedule window uses the diffuser **Work schedule** (days + start/end)
- Built-in **on/off delays** (defaults 60s) to avoid rapid toggles on short-cycles
- While HVAC Sync is ON:
  - manual diffuser controls are **locked** in Home Assistant (Option 2)
  - the integration saves a **persistent manual snapshot** and restores it when Sync is turned OFF
  - the integration temporarily forces **Work run/stop** to **60s / 180s** (restored when Sync is OFF)

### Important: Work schedule must stay enabled

Some Felshare models require **Work schedule (work mode)** to be enabled, otherwise a **Power ON** command has no effect.

HVAC Sync in this integration therefore:
- **never disables Work schedule**
- gates diffusion by toggling **Power ON/OFF**

### Configure from your dashboard (recommended)

The HVAC Sync settings are exposed as entities so you can place them in your own Lovelace
card (no Options Flow required):

- `switch.*hvac_sync` (enable/disable)
- `select.*hvac_sync_thermostat` (pick any `climate.*`)
- `select.*hvac_sync_airflow` (Cooling only / Heat + Cool / Any airflow)
- `number.*hvac_sync_on_delay_s` / `number.*hvac_sync_off_delay_s` (optional)

The schedule window comes from the diffuser **Work schedule** entities:

- `switch.*00_work_schedule` (must be ON)
- `text.*01_work_start` and `text.*02_work_end`
- `switch.*05_work_day_*` (Mon..Sun)

### Tested with Google Nest (example attributes)

HVAC Sync was tested using a Google Nest thermostat entity that exposes:

- `hvac_action: cooling`
- `hvac_modes: heat, cool, heat_cool, off`
- `fan_modes: on, off`
- `preset_modes: none, eco`

If your thermostat uses different `hvac_action` strings (or doesn't expose it), please open an issue and include your climate entity attributes so we can add support.

## Installation (HACS — custom repository)

1. In Home Assistant, open **HACS → Integrations → ⋮ → Custom repositories**.
2. Add your GitHub repo URL (this repository) and choose **Category: Integration**.
3. Install the integration from HACS.
4. Restart Home Assistant.

## Setup

1. Go to **Settings → Devices & services → Add integration**.
2. Search for **Felshare (Cloud MQTT)**.
3. Enter your Felshare app **email** and **password**.
4. Select the device from the list.

## Options (recommended defaults)

In **Settings → Devices & services → Felshare → Configure**:

- **Polling interval (minutes)**: **30–60** (or **0** if MQTT is stable)
- **Min publish interval (seconds)**: **1.0**
- **Max burst messages**: **3**
- **Min request_status interval (seconds)**: **60**
- **Bulk status interval (hours)**: **6**
- **Startup stale threshold (minutes)**: **30**

## Notes

- This integration is **cloud-based** (Felshare cloud MQTT), not local.
- Home Assistant UI icons/branding shown in the official integrations list come from the
  `home-assistant/brands` repository. For a HACS custom repo, HACS will use the `icon.png`
  and `logo.png` in this repository for display.

## Support

- Issues: use the GitHub issue tracker for this repository.

## Disclaimer

This is an unofficial community integration.

## Debug logging

To see detailed logs (queueing/coalescing, WorkTime changes, HVAC Sync decisions), add this to your `configuration.yaml` and restart Home Assistant:

```yaml
logger:
  logs:
    custom_components.felshare: debug
```

Then check **Settings → System → Logs**.