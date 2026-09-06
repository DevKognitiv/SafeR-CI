# SafeR app & SafeR Hub — smart home and security (multi-brand)

SafeR is the SafeR CI mobile application rebuilt as a **Tuya-Smart-style smart home & security
app**: one app to onboard, monitor and control devices from many brands, plus the SafeR CI SOS
and incident features. It ships in two parts that share one contract:

| Part | Where | Role |
|------|-------|------|
| **SafeR Hub** | `backend/app/hub/` (FastAPI, mounted at `/api/v1/hub`) | Normalises every brand into one device model, stores homes/rooms/devices/scenes, runs automations, pushes realtime events |
| **SafeR app** | `mobile/` (Flutter, package `safer_ci`, display name *SafeR*) | Tuya-like UI: Home · Scenes · Security · Me, add-device wizards, device panels, SOS |

The hub runs on the SafeR API server **or** on a Raspberry Pi next to Home Assistant
(`uvicorn app.hub.app:app` with SQLite). The app only ever talks to the hub.

## Supported brands and protocols

| Brand | Protocol(s) | Pairing methods | Devices |
|-------|-------------|-----------------|---------|
| **Tuya / Smart Life** | Tuya Cloud OpenAPI, Tuya local (tinytuya) | `cloud_project` (Access ID / Secret / region, optional app-account UID), `local_key` (device id + local key + IP) | switches, plugs, lights, covers, thermostats, sensors, cameras, locks, sirens, alarm hosts, gateways |
| **Hikvision** | ISAPI (HTTP digest) | `ip_credentials` (host, port, HTTPS, user, password, RTSP port) | IP cameras, NVR/DVR (one child per channel), **AX PRO** alarm panels (areas + zones) |
| **Dahua** (IMOU/Amcrest-style) | Dahua HTTP CGI (digest) | `ip_credentials` | cameras, NVR/XVR (channels), PTZ, event stream |
| **Ajax Systems** | Ajax Enterprise API (cloud), **SIA DC-09** receiver | `cloud_account` (API key + login), `sia_receiver` (account) | hubs (alarm panel), MotionProtect, DoorProtect, FireProtect, LeaksProtect, sirens, sockets |
| **Matter** | python-matter-server (WebSocket controller) | `qr_code` (MT: payload), `manual_code` (11/21 digits), `on_network` | lights, plugs, locks, contact/occupancy/temperature/humidity sensors, thermostats, covers, smoke/CO alarms, bridges |
| **ONVIF** | ONVIF Profile S (SOAP) | `ip_credentials` | any ONVIF camera (Reolink, Uniview, Tapo, Axis…) |
| **Home Assistant** | REST + WebSocket | `long_lived_token` (URL + token) | every HA entity: Zigbee, Z-Wave, MQTT, LoRaWAN gateways… — this is how SafeR CI's HA nodes surface in the app |
| **Demo** | virtual | `virtual` | a full virtual home for QA and screenshots |

See [device-onboarding.md](device-onboarding.md) for the per-brand walkthrough.

## Unified device model

Every adapter maps its devices to one shape (`Device` in `backend/app/hub/models.py` and
`mobile/lib/core/models/device.dart`):

```
Device { id, home_id, room_id, parent_id, name, brand, protocol, category,
         external_id, online, capabilities: [Capability], state: {code: value}, config }
Capability { code, type: bool|int|float|enum|string|json|color, writable, unit, min, max, step, values }
```

Categories (Tuya-like): `switch plug light cover thermostat sensor_contact sensor_motion
sensor_temperature sensor_humidity sensor_smoke sensor_water sensor_gas sensor_multi camera nvr
doorbell lock siren alarm_panel alarm_zone gateway remote generic`.

Canonical capability codes are defined once in `backend/app/hub/capabilities.py`
(`switch`, `brightness`, `color_temp`, `color`, `position`, `temp_set`, `contact`, `motion`,
`stream_main`, `ptz`, `locked`, `arm_mode`, …). Adapters translate to/from brand specifics
(Tuya DP codes, Matter clusters, ISAPI XML, HA services…), so the app never contains brand logic.

## Hub API (prefix `/api/v1/hub`)

| Area | Endpoints |
|------|-----------|
| Auth | `POST /auth/register`, `POST /auth/login`, `GET/PATCH /auth/me`, `POST /auth/push-token` |
| Homes | `GET/POST /homes`, `GET/PATCH/DELETE /homes/{id}`, rooms (`/homes/{id}/rooms`, `/rooms/{id}`, reorder), members (`/homes/{id}/members`), `GET /homes/{id}/weather` |
| Devices | `GET /homes/{id}/devices`, `GET/PATCH/DELETE /devices/{id}`, `POST /devices/{id}/refresh`, `POST /devices/{id}/commands`, `GET /devices/{id}/stream`, `GET /devices/{id}/snapshot`, `GET /devices/{id}/events`, `GET /devices/{id}/children` |
| Onboarding | `GET /onboarding/brands`, `GET /onboarding/categories`, `POST /onboarding/parse-code`, `POST /onboarding/{brand}/discover`, `POST /onboarding/{brand}/pair`, `GET /homes/{id}/integrations`, `DELETE /integrations/{id}` |
| Scenes | `GET/POST /homes/{id}/scenes`, `GET/PATCH/DELETE /scenes/{id}`, `POST /scenes/{id}/run` |
| Automations | `GET/POST /homes/{id}/automations`, `GET/PATCH/DELETE /automations/{id}`, `POST /automations/{id}/enable|disable|trigger` |
| Security | `GET /homes/{id}/security`, `POST /homes/{id}/security/mode`, `POST /homes/{id}/security/alarm/clear`, `POST /homes/{id}/sos`, `GET /homes/{id}/sos` |
| Messages | `GET /homes/{id}/messages`, `GET /homes/{id}/messages/unread-count`, `POST /messages/{id}/read`, `POST /homes/{id}/messages/read-all` |
| Realtime | `WS /ws?token=&home_id=` — `device.state`, `device.event`, `device.added/removed`, `message.new`, `security.mode`, `security.alarm`, `scene.ran` |
| Webhooks | `POST /webhooks/{brand}/{integration_id}?secret=` (Ajax cloud pushes, generic devices) |

Interactive docs: `http://localhost:8000/docs` when running the hub standalone.

### Security model

* JWT bearer tokens (`SECRET_KEY`, 30-day TTL by default), every home-scoped route checks the
  caller's membership (`owner` > `admin` > `member`).
* Device and integration credentials (camera passwords, Tuya secrets, Ajax sessions, HA tokens)
  are encrypted at rest with Fernet (`HUB_ENCRYPTION_KEY`, derived from `SECRET_KEY` when unset)
  and are **never** returned by the API.
* Inbound webhooks require a per-integration secret; the SIA DC-09 receiver validates CRCs and
  can be restricted to known accounts (`HUB_SIA_ACCOUNTS`).

### Software alarm panel

Homes have a security mode (`disarmed | armed_home | armed_away | armed_night`). Setting the mode
propagates to every hardware panel (Ajax hub, Hikvision AX PRO, Tuya alarm host, HA
`alarm_control_panel`) **and** turns the hub into a software panel for plain sensors: when armed,
a Tuya door sensor or a Matter contact sensor opening trips the home alarm, creates an alarm
message, pushes a realtime `security.alarm` event and shows the red banner in the app. Life-safety
sensors (smoke, CO, gas, water) alarm in every mode.

### Background services

| Service | File | Role |
|---------|------|------|
| Poller | `services/poller.py` | Refreshes devices of adapters without push every `HUB_POLL_INTERVAL` s |
| Subscriptions | `services/subscriptions.py` | Keeps push subscriptions alive (Hikvision alertStream, Dahua eventManager, Matter attribute updates, HA state_changed) |
| Automation engine | `automation/engine.py` | Evaluates automations on device state, security mode and a minute tick |
| SIA receiver | `services/sia_receiver.py` | TCP server for SIA DC-09 / Contact ID reports from alarm panels |

## Running

```bash
# Hub standalone (SQLite, no PostgreSQL needed)
cd backend
pip install -r requirements.txt aiosqlite
SECRET_KEY=dev uvicorn app.hub.app:app --reload --port 8000
# Tests
pytest app/hub/tests -q

# Full SafeR API (incidents + hub) with PostgreSQL/Redis/Matter server
cp .env.example .env && docker compose up -d

# App
cd ../mobile
flutter pub get
flutter run --dart-define=SAFER_HUB_URL=http://10.0.2.2:8000     # Android emulator
flutter run -d chrome --dart-define=SAFER_HUB_URL=http://localhost:8000
flutter test && flutter analyze
```

First launch: register an account (the first user becomes hub admin), create a home, then
**+ → Appareils de démonstration** to get a full virtual home, or pick a real brand.

## App structure (`mobile/lib`)

```
core/        config, theme, i18n (context.tr), router (go_router), storage
  api/       HubClient (dio) + HubSocket (WebSocket with reconnect)
  models/    Device, Home, Room, Member, Scene, Automation, HubMessage, BrandInfo, SecurityState…
  providers/ Riverpod: auth, homes, devices (live-patched from the socket), scenes, security, messages…
  widgets/   DeviceTile, LoadingView/EmptyState/ErrorView, icon map
features/
  auth/        splash, login, register (hub URL configurable)
  home/        Home tab: weather header, room tabs, device grid, quick toggles, room management
  add_device/  brand catalogue, category grid, QR scanner, dynamic pairing wizard, Matter payload codec
  device/      device detail routed to panels (switch, light, cover, thermostat, sensor, camera, lock, alarm, gateway, generic), settings
  scenes/      tap-to-run scenes, automations (triggers / conditions / actions editors)
  security/    arm modes, alarm banner, zones/sensors, alarm history, SOS screen (SafeR CI)
  me/          profile, home management, members, message center, settings, integrations, about
  shell/       bottom navigation
```

## Relationship with the rest of SafeR CI

* `POST /homes/{id}/sos` forwards to the SafeR CI incident API (`SAFER_INCIDENTS_URL`) so an SOS
  from the smart-home app still lands on the national dashboard and triggers SMS/WhatsApp alerts.
* The Home Assistant adapter imports the entities defined in `ha-config/` (panic buttons, smoke,
  flood sensors) so neighbourhood hubs appear as regular SafeR devices.
* The hub is self-contained (`backend/app/hub`) and does not depend on the legacy backend modules
  that are still being completed in other pull requests.
