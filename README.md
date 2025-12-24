# Felshare Diffuser (Cloud MQTT) — Home Assistant Custom Integration

Control Felshare waterless diffusers via the Felshare cloud MQTT service.

> ⚠️ **Unofficial integration / private APIs**: This uses Felshare cloud endpoints that are not documented as an official public API. Using private endpoints may violate vendor terms and may stop working if Felshare changes their backend.

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

## Hardening / Stability (0.1.6.5-hardened)

- Outbound MQTT publish queue with **rate limiting** + **coalescing**
- Debounced `request_status()` and throttled bulk (0x0C)
- Avoids “startup spam” on MQTT reconnects
- More polite HTTP headers + safer handling of `401/403/429`

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
