# Felshare Diffuser (Cloud MQTT) — Home Assistant Custom Integration

Control Felshare waterless diffusers via the Felshare cloud MQTT service.

## Features

- **Power** switch
- **Fan** switch
- Oil **consumption**, **capacity**, and **remaining oil** controls
- Work schedule controls:
  - Enable/disable schedule
  - Start/End time (HH:MM)
  - Run/Stop seconds
  - Day-of-week toggles (Mon–Sun)
- Diagnostics sensor with last seen/topic/payload
- **Refresh status** button (forces a cloud status request)

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

## Notes

- This integration is **cloud-based** (Felshare cloud MQTT), not local.
- Home Assistant UI icons/branding shown in the official integrations list come from the
  `home-assistant/brands` repository. For a HACS custom repo, HACS will use the `icon.png`
  and `logo.png` in this repository for display.

## Support

- Issues: use the GitHub issue tracker for this repository.

## Disclaimer

This is an unofficial community integration.
