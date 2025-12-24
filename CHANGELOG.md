# Changelog

## 0.1.6.5

- Added options: polling interval, TXD learning toggle, and max backoff.
- Improved reconnect behavior to reuse tokens, apply exponential backoff with jitter, and avoid aggressive re-login loops.
- Cleanly stop paho loop threads on disconnect to prevent leaked clients/threads.

## 0.1.6.4

- HACS-ready repository layout (added `hacs.json`, docs, and repository assets)
- Added `paho-mqtt==2.1.0` to `manifest.json` requirements
- Minor internal improvements for thread safety and persistence
