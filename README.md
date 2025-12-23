# Felshare (Cloud MQTT) — Home Assistant Custom Integration

> **Unofficial / Unaffiliated**: This component is a *custom integration* for Home Assistant. It is not an official Felshare product.

Integration to control **Felshare smart diffusers** (and compatible devices) using the **Felshare Cloud**:
- Login via Felshare API to obtain a token.
- Connection to **MQTT over WebSockets (TLS)** on the cloud.
- Publishing/receiving device status and commands.

---

## Features

- Diffuser **Power** On/Off
- **Fan** Control (if your model supports it)
- **Oil Name** / Fragrance
- Oil Parameters:
  - **Consumption (ml/h)**
  - **Oil Capacity (ml)**
  - **Remaining Oil (ml)**
  - **Liquid Level (%)** Sensor
- **WorkTime** Scheduling (operating hours):
  - Enable/Disable schedule
  - Start/End Time (HH:MM)
  - Work Duration (seconds) and Pause (seconds)
  - Days of the Week (individual switch per day)
- Diagnostic Sensors:
  - **MQTT Status**
  - **Work Schedule Info** (summary text of the schedule)

---

## Requirements

- Home Assistant (Core/Supervised/OS)
- Felshare Account (the same one used in the app)
- The device must be added to your account in the Felshare app.
- Internet access is required to `app.felsharegroup.com` on **443/TCP**.

> **Important**: This integration is **cloud-based** (not local). If the cloud service goes down or changes its API, this integration may stop working.

---

## Installation (Manual)

1. Copy the folder:
   ```
   custom_components/felshare
   ```
   into your Home Assistant configuration directory:
   ```
   <your-home-assistant-config>/custom_components/felshare
   ```

2. Restart Home Assistant.

---

## Configuration (UI)

1. Navigate to **Settings → Devices & Services → Add Integration**.
2. Search for **Felshare (Cloud MQTT)**.
3. Enter your:
   - **Email**
   - **Password**
4. Select the **Device ID** from the provided list.

Upon completion, Home Assistant will create a "Felshare <device_id>" device with its associated entities.

---

## Created Entities

### Switches
- `switch.<...>_power` — **Power**
- `switch.<...>_fan` — **Fan**
- `switch.<...>_00_work_schedule` — **Work Schedule** (enables the schedule)
- `switch.<...>_05_work_day_mon` … `switch.<...>_05_work_day_sun` — **Work Day <Day>**

### Text
- `text.<...>_oil_name` — **Oil Name**
- `text.<...>_01_work_start` — **Work Start (HH:MM)**
- `text.<...>_02_work_end` — **Work End (HH:MM)**

### Number
- `number.<...>_consumption` — **Consumption (ml/h)**
- `number.<...>_capacity` — **Oil Capacity (ml)**
- `number.<...>_remain_oil` — **Remaining Oil (ml)**
- `number.<...>_03_work_run_s` — **Work Run (seconds)**
- `number.<...>_04_work_stop_s` — **Work Stop (seconds)**

### Sensor
- `sensor.<...>_liquid_level` — **Liquid Level (%)**
- `sensor.<...>_mqtt_status` — **MQTT Status** (diagnostic)
- `sensor.<...>_work_schedule` — **Work Schedule Info** (diagnostic)

---

## How to Use "WorkTime" (Scheduling)

1. Enable the **Work Schedule** switch.
2. Define:
   - **Work Start (HH:MM)** (e.g., `09:00`)
   - **Work End (HH:MM)** (e.g., `21:00`)
3. Define:
   - **Work Run (seconds)** (e.g., `30`)
   - **Work Stop (seconds)** (e.g., `190`)
4. Enable the **Work Day** switches for your desired days.

> Note: The device expects a "complete" payload when you change any part of the schedule. This integration handles re-sending the full package to ensure it's applied correctly.

---

## Troubleshooting

### Entities showing `unknown` or not updating

- Verify the diffuser is **online** within the Felshare app.
- Ensure Home Assistant has internet connectivity (DNS and access to port 443).
- Open the Felshare app and navigate to the device's screen at least once. This allows the integration to **learn the initial "sync payload"** by observing the app's traffic and save it in the `.storage` file.
- Restart Home Assistant or reload the integration.

### Enabling Debugging Logs

Add the following to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.felshare: debug
```

Then, restart Home Assistant and check **Settings → System → Logs**.

---

## How it Works (Technical Summary)

- Cloud API (Login): `http://app.felsharegroup.com:7001/login`
- Device List: `http://app.felsharegroup.com:7001/device` (requires `token` in header)
- MQTT over WebSockets (TLS):
  - Host: `app.felsharegroup.com`
  - Port: `443`
  - Path: `/mqtt`
  - Topics:
    - RX: `/device/rxd/<device_id>`
    - TX: `/device/txd/<device_id>`

---

## Disclaimer

This project is provided "as is" without any warranty. Use it at your own risk.



# Felshare (Cloud MQTT) — Home Assistant Custom Integration

> **Unofficial / no afiliado**: Este componente es un *custom integration* para Home Assistant. No es un producto oficial de Felshare.

Integración para controlar **difusores “smart” Felshare** (y dispositivos compatibles) usando el **Cloud de Felshare**:
- Login por API de Felshare para obtener token
- Conexión a **MQTT por WebSockets (TLS)** en el cloud
- Publicación/recepción de estado y comandos

---

## Funciones

- Encendido/apagado del difusor (**Power**)
- Control del ventilador (**Fan**) *(si tu modelo lo soporta)*
- Nombre del aceite/fragancia (**Oil name**)
- Parámetros de aceite:
  - **Consumption (ml/h)**  
  - **Oil capacity (ml)**
  - **Remain oil (ml)**
  - Sensor **Liquid level (%)**
- Programación **WorkTime** (horario de trabajo):
  - Activar/desactivar horario
  - Hora inicio/fin (HH:MM)
  - Tiempo de trabajo (segundos) y pausa (segundos)
  - Días de la semana (switch por día)
- Sensores de diagnóstico:
  - **MQTT status**
  - **Work schedule info** (texto resumen del horario)

---

## Requisitos

- Home Assistant (Core/Supervised/OS)
- Cuenta de Felshare (la misma que usas en la app)
- El dispositivo debe estar agregado a tu cuenta en la app Felshare
- Salida a internet permitida hacia `app.felsharegroup.com` por **443/TCP**

> **Importante:** esta integración es **cloud** (no local). Si el cloud cae o cambia, la integración puede dejar de funcionar.

---

## Instalación (manual)

1. Copia la carpeta:
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

1. Ve a **Settings → Devices & Services → Add Integration**
2. Busca **Felshare (Cloud MQTT)**
3. Ingresa:
   - **Email**
   - **Password**
4. Selecciona el **Device ID** de la lista

Al finalizar, Home Assistant creará un dispositivo “Felshare <device_id>” con sus entidades.

---

## Entidades creadas

### Switches
- `switch.<...>_power` — **Power**
- `switch.<...>_fan` — **Fan**
- `switch.<...>_00_work_schedule` — **Work schedule** (habilitar horario)
- `switch.<...>_05_work_day_mon` … `switch.<...>_05_work_day_sun` — **Work day <día>**

### Text
- `text.<...>_oil_name` — **Oil name**
- `text.<...>_01_work_start` — **Work start (HH:MM)**
- `text.<...>_02_work_end` — **Work end (HH:MM)**

### Number
- `number.<...>_consumption` — **Consumption (ml/h)**
- `number.<...>_capacity` — **Oil capacity (ml)**
- `number.<...>_remain_oil` — **Remain oil (ml)**
- `number.<...>_03_work_run_s` — **Work run (seconds)**
- `number.<...>_04_work_stop_s` — **Work stop (seconds)**

### Sensor
- `sensor.<...>_liquid_level` — **Liquid level (%)**
- `sensor.<...>_mqtt_status` — **MQTT status** *(diagnóstico)*
- `sensor.<...>_work_schedule` — **Work schedule info** *(diagnóstico)*

---

## Cómo usar “WorkTime” (horario)

1. Activa el switch **Work schedule**
2. Define:
   - **Work start (HH:MM)** (ej. `09:00`)
   - **Work end (HH:MM)** (ej. `21:00`)
3. Define:
   - **Work run (seconds)** (ej. `30`)
   - **Work stop (seconds)** (ej. `190`)
4. Enciende los switches de **Work day** para los días deseados.

> Nota: El dispositivo espera un payload “completo” cuando cambias algo del horario; la integración se encarga de re-enviar el paquete completo.

---

## Troubleshooting

### Entidades en `unknown` o sin cambios
- Verifica que el difusor esté **online** en la app Felshare.
- Asegura conectividad desde HA a internet (DNS + 443).
- Abre la app Felshare y entra a la pantalla del dispositivo al menos una vez:  
  la integración puede **aprender el “sync payload”** observando el tráfico de la app y guardarlo en `.storage`.
- Reinicia Home Assistant o recarga la integración.

### Habilitar logs de depuración
Agrega en `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.felshare: debug
```

Luego reinicia y revisa **Settings → System → Logs**.

---

## Cómo funciona (resumen técnico)

- API cloud (login): `http://app.felsharegroup.com:7001/login`
- Lista de dispositivos: `http://app.felsharegroup.com:7001/device` (header `token`)
- MQTT por WebSockets (TLS):
  - Host: `app.felsharegroup.com`
  - Puerto: `443`
  - Path: `/mqtt`
  - Topics:
    - RX: `/device/rxd/<device_id>`
    - TX: `/device/txd/<device_id>`

---

## Aviso

Este proyecto se ofrece “tal cual”, sin garantía. Úsalo bajo tu responsabilidad.
