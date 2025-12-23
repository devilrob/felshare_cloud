# Felshare (Cloud MQTT) — Home Assistant Custom Integration

[![HACS Validation](https://github.com/devilrob/HA_Felshare_Diffuser/actions/workflows/hacs.yaml/badge.svg)](https://github.com/devilrob/HA_Felshare_Diffuser/actions/workflows/hacs.yaml)
[![Hassfest](https://github.com/devilrob/HA_Felshare_Diffuser/actions/workflows/hassfest.yaml/badge.svg)](https://github.com/devilrob/HA_Felshare_Diffuser/actions/workflows/hassfest.yaml)

Community-made **custom integration** for **Felshare smart diffusers** (and compatible models) using the **Felshare Cloud**:

- Login with your Felshare account (same as the mobile app)
- Connect to **MQTT over WebSockets (TLS)** (cloud)
- Read device status and send commands from Home Assistant

> **Unofficial / Unaffiliated / Not Endorsed**  
> This project is not an official Felshare product and is not endorsed by Felshare or Home Assistant.

---

## Table of contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
  - [HACS (Recommended)](#hacs-recommended)
  - [Manual](#manual)
- [Configuration (UI)](#configuration-ui)
- [Entities](#entities)
- [WorkTime scheduling](#worktime-scheduling)
- [Troubleshooting](#troubleshooting)
- [Branding & icons](#branding--icons)
- [Technical summary](#technical-summary)
- [Support](#support)
- [Legal & responsible use](#legal--responsible-use)
- [Español](#español)

---

## Features

- **Power** on/off
- **Fan** control *(if supported by your model)*
- **Oil name / fragrance label**
- Oil metrics:
  - **Consumption (ml/h)**
  - **Oil capacity (ml)**
  - **Remaining oil (ml)**
  - **Liquid level (%)** sensor
- **WorkTime scheduling**:
  - Enable/disable schedule
  - Start/end time (HH:MM)
  - Work run (seconds) and work stop (seconds)
  - Day-of-week toggles (Mon–Sun)
- Diagnostics:
  - **MQTT status** sensor
  - **Work schedule info** sensor (human-readable summary)
- **Refresh status** button (requests a cloud status update)

---

## Requirements

- Home Assistant **2024.6.0+**
- A Felshare account (same one used in the mobile app)
- Your diffuser already added in the Felshare app
- Outbound internet access to `app.felsharegroup.com` (HTTPS / MQTT over WSS on **443/TCP**)

> **Important:** This integration is **cloud-based** (not local). If Felshare changes the cloud, this integration may stop working.

---

## Installation

### HACS (Recommended)

1. Install HACS (if you don't have it).
2. In Home Assistant: **HACS → Integrations**
3. Click **⋮** (top-right) → **Custom repositories**
4. Add your repository URL and select **Integration**
5. Install **Felshare (Cloud MQTT)**
6. Restart Home Assistant

### Manual

1. Copy:
   ```
   custom_components/felshare
   ```
   to:
   ```
   <your-home-assistant-config>/custom_components/felshare
   ```
2. Restart Home Assistant.

---

## Configuration (UI)

1. **Settings → Devices & Services → Add integration**
2. Search for **Felshare (Cloud MQTT)**
3. Enter:
   - **Email**
   - **Password**
4. Select your **Device ID** from the list

Home Assistant will create a device named like: **Felshare <device_id>**.

---

## Entities

Entity names and exact availability may vary by model/firmware, but you will typically see:

### Switches
- Power
- Fan *(if available)*
- Work schedule enable
- Work day toggles (Mon–Sun)

### Text
- Oil name
- Work start (HH:MM)
- Work end (HH:MM)

### Numbers
- Consumption (ml/h)
- Oil capacity (ml)
- Remaining oil (ml)
- Work run (seconds)
- Work stop (seconds)

### Sensors
- Liquid level (%)
- MQTT status *(diagnostic)*
- Work schedule info *(diagnostic)*

### Button
- Refresh status

---

## WorkTime scheduling

Typical setup:

1. Enable the **Work Schedule** switch
2. Set:
   - **Work Start (HH:MM)** (e.g., `09:00`)
   - **Work End (HH:MM)** (e.g., `21:00`)
3. Set:
   - **Work Run (seconds)** (e.g., `30`)
   - **Work Stop (seconds)** (e.g., `190`)
4. Enable the desired **Work Day** switches

**Note:** Many devices expect a full schedule payload when any schedule value changes.  
This integration re-sends a complete schedule payload so changes apply consistently.

---

## Troubleshooting

### Entities show `unknown`, don't update, or go `unavailable`
- Confirm the diffuser is **online** in the Felshare app
- Confirm Home Assistant can reach the internet (DNS + outbound 443)
- Try pressing **Refresh status**
- Restart Home Assistant or reload the integration

### “Refresh status” doesn't do anything
The integration learns and stores the mobile app's “status request” payload the first time it sees it.
If Home Assistant has never seen that payload yet:
- Open the diffuser screen in the Felshare mobile app once (so the app sends a status request)
- Wait ~30 seconds, then press **Refresh status** again

### Enable debug logs

Add to `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.felshare: debug
    paho.mqtt: warning
```

Restart Home Assistant and check: **Settings → System → Logs**.

---

## Branding & icons

- The **icon/logo shown in Home Assistant's Integrations UI** is pulled from the official `home-assistant/brands` repository.
- This repo includes `icon.png` / `logo.png` for **HACS display** only.

If you want the Felshare brand to appear in the HA UI for this integration, you must submit a PR to `home-assistant/brands` following their guidelines.

---

## Technical summary

For transparency (may change anytime):

- Cloud API base: `http://app.felsharegroup.com:7001`
- Web UI: `https://app.felsharegroup.com`
- MQTT over WebSockets (TLS):
  - Host: `app.felsharegroup.com`
  - Port: `443`
  - Path: `/mqtt`
  - RX topic: `/device/rxd/<device_id>`
  - TX topic: `/device/txd/<device_id>`

---

## Support

- Issues: use the GitHub issue tracker and include logs (**redact tokens/emails/device IDs**)
- PRs are welcome

---

## Legal & responsible use

### No affiliation / trademarks
- “Felshare” and related names/logos are trademarks of their respective owners.
- This project is independent and provided for interoperability/automation purposes only.
- Do not claim sponsorship, partnership, or endorsement by Felshare or Home Assistant.

### No warranty / limitation of liability
This project is provided **“AS IS”**, without warranty of any kind.

To the maximum extent permitted by law, authors/contributors are not liable for damages arising from use of this software (including device malfunction, property damage, lost profits, data loss, outages, or security incidents).

### Compliance & acceptable use
By using this integration, **you** are responsible for ensuring your use:
- Complies with applicable laws and Felshare terms/policies (if any)
- Is limited to devices/accounts you **own or are authorized to control**
- Does not violate contractual obligations (e.g., reverse engineering restrictions)

### Safety notice
Do not rely on this integration for safety-critical use cases. You are responsible for safe diffuser operation (oils, ventilation, fire safety, pets/children, etc.).

### Privacy & credentials
- Credentials are entered during setup and stored by Home Assistant.
- Secure your HA instance and network.
- Prefer a dedicated Felshare account with minimal access if possible.

---

## Español

<details>
<summary><strong>Ver README en Español</strong></summary>

# Felshare (Cloud MQTT) — Integración Custom para Home Assistant

Proyecto comunitario para controlar **difusores Felshare** (y compatibles) usando el **cloud de Felshare**:

- Login con tu cuenta Felshare (la misma de la app móvil)
- Conexión a **MQTT por WebSockets (TLS)** en el cloud
- Lectura de estado y envío de comandos desde Home Assistant

> **No oficial / No afiliado / Sin respaldo**  
> No es un producto oficial de Felshare y no está respaldado por Felshare o Home Assistant.

---

## Funciones

- Encendido/apagado (**Power**)
- Control de ventilador (**Fan**) *(si el modelo lo soporta)*
- **Oil name** (nombre de fragancia)
- Métricas de aceite:
  - **Consumption (ml/h)**
  - **Oil capacity (ml)**
  - **Remaining oil (ml)**
  - **Liquid level (%)**
- Horario **WorkTime**:
  - Activar/desactivar
  - Hora inicio/fin (HH:MM)
  - Tiempo de trabajo y pausa (segundos)
  - Días de semana (Mon–Sun)
- Diagnóstico:
  - **MQTT status**
  - **Work schedule info**
- Botón **Refresh status** (pide actualización al cloud)

---

## Requisitos

- Home Assistant **2024.6.0+**
- Cuenta Felshare
- Difusor agregado en la app Felshare
- Salida a internet hacia `app.felsharegroup.com` por **443/TCP**

> **Importante:** Es cloud (no local). Si el cloud cambia, puede dejar de funcionar.

---

## Instalación

### HACS (Recomendado)

1. Instala HACS (si no lo tienes).
2. **HACS → Integrations**
3. **⋮** → **Custom repositories**
4. Agrega la URL del repo y selecciona **Integration**
5. Instala **Felshare (Cloud MQTT)**
6. Reinicia Home Assistant

### Manual

1. Copia:
   ```
   custom_components/felshare
   ```
   dentro de:
   ```
   <tu_config_de_homeassistant>/custom_components/felshare
   ```
2. Reinicia Home Assistant.

---

## Configuración (UI)

1. **Settings → Devices & Services → Add integration**
2. Busca **Felshare (Cloud MQTT)**
3. Ingresa Email/Password
4. Selecciona el **Device ID**

---

## Troubleshooting (rápido)

- Si sale `unknown`/no actualiza: confirma que el difusor esté **online**, revisa internet/443, presiona **Refresh status**, reinicia o recarga la integración.
- Si **Refresh status** no hace nada: abre la pantalla del dispositivo en la app Felshare una vez, espera ~30s y vuelve a intentar.

Logs (debug):

```yaml
logger:
  default: info
  logs:
    custom_components.felshare: debug
    paho.mqtt: warning
```

---

## Branding / iconos

El logo que se ve dentro de Home Assistant viene del repo oficial `home-assistant/brands`.  
Este repo incluye `icon.png` y `logo.png` solo para que HACS muestre un logo bonito.

---

## Resumen técnico

- API base: `http://app.felsharegroup.com:7001`
- Web: `https://app.felsharegroup.com`
- MQTT (WSS/TLS): `app.felsharegroup.com:443/mqtt`

---

## Aviso legal y uso responsable

Proyecto comunitario “tal cual”, sin garantía.  
Usa solo con dispositivos/cuentas que te pertenecen o tienes autorización de controlar.  
No lo uses para escenarios críticos de seguridad.

</details>
