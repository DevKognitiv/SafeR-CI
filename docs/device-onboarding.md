# Onboarding devices in SafeR (per brand)

Open the app → **Home tab → +** → *Ajouter un appareil*. Pick a brand (or a category, or scan a
QR code). Each brand offers one or more **pairing methods**; the app renders the form the hub
describes (`GET /onboarding/brands`), so new brands need no app update.

## Tuya / Smart Life

**Method `cloud_project` (recommended)** — uses the Tuya IoT Platform OpenAPI.

1. Create a project on <https://iot.tuya.com> (Cloud → Development → Create Cloud Project;
   industry *Smart Home*, data center matching your region: *Western Europe*, *US*, *China*, *India*).
2. Subscribe to the free *IoT Core* and *Authorization Token Management* APIs.
3. Devices → *Link Tuya App Account* → scan the QR code with the Tuya / Smart Life app. All the
   devices of that app account are now visible to the project.
4. In SafeR: region, **Access ID**, **Access Secret** (from the project overview) and optionally
   the app-account **UID**. SafeR lists the devices (discovery step); select the ones to import.

SafeR maps Tuya data points to canonical capabilities (`switch_led → switch`,
`bright_value_v2 10–1000 → brightness 0–100`, `colour_data_v2 → color`, `doorcontact_state →
contact`, `pir → motion`, `master_mode → arm_mode`, …) and polls the cloud for state.

**Method `local_key`** — control on the LAN without cloud (needs the device's *local key*,
retrievable from the IoT platform: Cloud → API Explorer → *Query Device Details*). Fill in device
id, local key, IP and protocol version (3.3 for most devices). Requires the `tinytuya` package on
the hub (`pip install tinytuya`).

> Pairing brand-new Tuya devices (EZ/AP Wi-Fi mode) requires Tuya's proprietary app SDK. Pair them
> once with Smart Life, then import them into SafeR through the cloud project.

## Hikvision (cameras, NVR/DVR, AX PRO alarm panels)

Method `ip_credentials`: host/IP, HTTP port (80), HTTPS on/off, username, password, RTSP port (554).

* Enable **ISAPI** and *Hikvision-CGI* on the device (Configuration → Network → Advanced →
  Integration Protocol) and, for RTSP, *RTSP authentication: digest/basic*.
* IP cameras become one `camera` device (RTSP `Streaming/Channels/101` main, `102` sub, snapshot,
  PTZ when supported). NVR/DVRs become an `nvr` device with one `camera` child per channel.
* Motion / line-crossing / intrusion events are received live through
  `/ISAPI/Event/notification/alertStream`.
* **AX PRO** panels are detected automatically and become an `alarm_panel` with one `alarm_zone`
  child per zone: arm/disarm from the Security tab, bypass zones, clear alarms. AX PRO can also
  report to the SafeR SIA receiver (see Ajax below).

## Dahua (also IMOU / Amcrest OEMs)

Method `ip_credentials` (same fields). Uses the Dahua HTTP CGI API with digest auth:
device info (`magicBox.cgi`), channel titles, RTSP `cam/realmonitor?channel=N&subtype=0|1`,
snapshot `snapshot.cgi`, PTZ `ptz.cgi`, white light / siren (`coaxialControlIO.cgi`), and the
live event stream (`eventManager.cgi?action=attach` — motion, local alarm, tripwire, intrusion).
NVR/XVRs expose one camera child per channel.

## Ajax Systems

**Method `cloud_account`** — Ajax *Enterprise API* (requires an API key issued by Ajax Systems
to integrators; contact your Ajax partner). Enter the API key, your Ajax account login and
password. SafeR imports every hub as an `alarm_panel` and its devices as children (MotionProtect
→ motion sensor, DoorProtect → contact sensor, FireProtect → smoke/CO, LeaksProtect → water,
sirens, sockets/relays as switches). Arm / night mode / disarm from the Security tab. Ajax event
pushes can be delivered to `POST /api/v1/hub/webhooks/ajax/{integration_id}?secret=…`
(URL shown under Me → Intégrations).

**Method `sia_receiver`** — no cloud API needed. Enable the SIA receiver on the hub
(`HUB_SIA_PORT=10001`, optionally `HUB_SIA_ACCOUNTS=1234:home-id`), then in the Ajax app →
Hub → *Monitoring station* → protocol **SIA (DC-09)**, IP/port of the hub, *plain* (unencrypted)
mode, object number = the account you enter in SafeR. Arm/disarm (CL/OP), alarms (BA/FA/PA),
tamper, battery and power events update the panel in SafeR in real time. The same works for
Hikvision AX PRO, Paradox, DSC and any panel speaking SIA DC-09 or Contact ID (ADM-CID).

## Matter

SafeR commissions Matter devices through the open-source **python-matter-server** (the controller
Home Assistant uses). Run it next to the hub (`docker compose up matter-server`, host network for
mDNS/BLE) and set `MATTER_SERVER_URL` (default `ws://localhost:5580/ws`).

* **Scan the QR code** (`MT:…` printed on the device) — SafeR decodes it locally (vendor, product,
  discriminator, passcode) and hands it to the controller; for Wi-Fi devices enter the Wi-Fi SSID
  and password once. **Manual pairing code** (11 or 21 digits) works the same way. **On network**
  commissions an already-connected device with its setup PIN.
* Thread devices need a Thread border router reachable by the controller.
* Device types are mapped from Matter clusters: On/Off & Level → light/plug, Door Lock → lock,
  Boolean State → contact, Occupancy → motion, Temperature/Humidity → sensors, Thermostat,
  Window Covering → cover, Smoke/CO Alarm, Aggregator → gateway with bridged children.
* Attribute updates are pushed live to the app; the device is also usable from other Matter
  controllers (multi-admin) by opening a commissioning window from its panel later.

## ONVIF (generic cameras)

Method `ip_credentials`: host, port (80 or 8000/8899 on some brands), username, password.
SafeR reads device information, media profiles, RTSP stream URIs (main/sub), snapshot URI and PTZ
support through SOAP (WS-UsernameToken). Works with Reolink, Uniview, TP-Link Tapo, Axis, and as a
fallback for Hikvision/Dahua.

## Home Assistant (Zigbee, Z-Wave, MQTT, LoRaWAN…)

Method `long_lived_token`: HA URL (e.g. `http://homeassistant.local:8123`) and a long-lived access
token (HA → profile → *Long-lived access tokens*). SafeR lists the entities (discovery) and imports
the selected ones: lights, switches, binary sensors (door/window/motion/smoke/moisture/gas),
temperature/humidity sensors, locks, covers, climate, alarm panels, sirens and cameras (MJPEG
proxy). State changes stream through the HA WebSocket. This is how the SafeR CI neighbourhood
hubs (`ha-config/`) appear in the app.

## Demo

*Appareils de démonstration* creates a complete virtual home (light, plug, 2-gang switch, cover,
thermostat, door/motion/smoke/water sensors, PTZ camera, lock, alarm panel + zone) to try every
screen without hardware. Disable with `HUB_DEMO_ENABLED=false` in production.

## Adding a brand

1. Create `backend/app/hub/adapters/<brand>.py` with a `BrandAdapter` subclass: `info()` returns
   the `BrandInfo` (pairing methods + form fields), `pair()` returns `DeviceDraft`s with canonical
   capabilities, `refresh()` / `send_command()` translate state, optional `stream()`,
   `snapshot()`, `subscribe()`, `handle_webhook()`.
2. Register it (`registry.register(MyAdapter())`) and import the module in `adapters/__init__.py`.
3. Add tests with `httpx.MockTransport` (`AdapterContext(transport=…)`) — no network in tests.
4. Nothing to change in the app: the brand appears in the catalogue and its form renders itself.
