# SafeR Hub

The SafeR Hub is the smart-home & security backend of the SafeR app (Tuya-Smart-style,
multi-brand). It is a self-contained FastAPI + async SQLAlchemy package (`backend/app/hub/`)
that normalises every supported brand into **one unified device model** (canonical categories
and capability codes, see `capabilities.py`) and exposes the Hub API used by the Flutter app:

- auth, homes/rooms/members, devices (state, commands, streams, snapshots, events)
- onboarding (brand catalog, discovery, pairing, QR/manual-code parsing, integrations)
- scenes & automations (engine in `automation/`), home security modes & SOS
- Message Center, realtime WebSocket, inbound webhooks, health

It is mounted in the main API (`backend/app/main.py`) under `/api/v1/hub` and also runs
standalone with the same prefix.

## Run standalone

```bash
cd backend
pip install -r requirements.txt
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"   # required, never a placeholder
HUB_DATABASE_URL=sqlite+aiosqlite:///./safer_hub.db uvicorn app.hub.app:app --port 8000
```

- API: `http://localhost:8000/api/v1/hub/...` - OpenAPI docs: `http://localhost:8000/docs`
- Health: `GET /api/v1/hub/health` -> `{status, version, adapters, sia_receiver, categories}`
- The first registered user (`POST /auth/register`) becomes hub admin.
- Realtime: `WS /api/v1/hub/ws?token=<jwt>&home_id=<home>` (send `{"type":"ping"}`).

Background services (device poller, push subscriptions, automation engine, optional SIA
receiver, weather) are started by the app lifespan (`runtime.py`).

## Run tests and lint

```bash
cd backend
pytest app/hub/tests -q                     # pytest-asyncio, asyncio_mode=auto (pytest.ini)
pylint --rcfile=.pylintrc app/hub           # CI gate: score >= 9.0
```

Tests never touch the network: adapters do all HTTP through `ctx.http()` so tests inject
`httpx.MockTransport` via `AdapterContext(transport=...)`; WebSocket adapters (Matter) accept an
injectable connector. Each test gets a fresh in-memory SQLite database (`tests/conftest.py`).

## Environment variables (`settings.py`)

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | **required** (placeholders such as `change-me`/`dev` are refused) | JWT signing key (reuse the app's `SECRET_KEY`); the hub refuses to start without it |
| `HUB_DATABASE_URL` | `DATABASE_URL`, else `sqlite+aiosqlite:///./safer_hub.db` | Async SQLAlchemy URL |
| `HUB_ENCRYPTION_KEY` | derived from `SECRET_KEY` | Fernet key for device/integration credentials (a warning is logged when it is derived) |
| `HUB_TOKEN_TTL_DAYS` | `30` | JWT lifetime |
| `HUB_POLL_INTERVAL` | `30` | Seconds between refreshes of devices without push |
| `HUB_HTTP_TIMEOUT` | `10.0` | Timeout for adapter HTTP calls |
| `HUB_SIA_PORT` | `0` (off) | TCP port of the SIA DC-09 receiver |
| `HUB_SIA_ACCOUNTS` | `""` | Comma separated `account:home_id` pairs accepted by the receiver; events of a bound account only reach that home, and pairing the account into another home is refused |
| `HUB_WEATHER_ENABLED` | `true` | Open-Meteo weather on `GET /homes/{id}/weather` |
| `HUB_DEMO_ENABLED` | `true` | Expose the `demo` brand (virtual devices) |
| `HUB_ALLOW_OPEN_REGISTRATION` | `true` | Allow `POST /auth/register` after the first user |
| `MATTER_SERVER_URL` | `ws://localhost:5580/ws` | python-matter-server WebSocket URL |
| `SAFER_INCIDENTS_URL` / `SAFER_INCIDENTS_TOKEN` | `""` | Forward SOS alerts to SafeR CI incidents (fire-and-forget) |

## Adapters

All adapters live in `adapters/` and register themselves on import (`adapters/__init__.py`).
Every brand maps its native data points to the canonical capability codes in `capabilities.py`
(unknown points become `raw_<code>`). Pairing methods are what the app renders as forms.

| Brand id | Name / vendor | Protocols | Pairing methods (`method` id) | Notes |
|---|---|---|---|---|
| `tuya` | Tuya / Smart Life (Tuya Inc.) | `tuya_cloud`, `tuya_local` | `cloud_project` (region, access_id, access_secret, uid; discovery, creates an integration) - `local_key` (device_id, local_key, host, version, name, category) | Tuya OpenAPI v1.0/v2.0 (HMAC-SHA256 signing, token refresh, DP-code mapping for switches, lights, covers, thermostats, sensors, sirens, locks, cameras, panels). Local mode uses the Tuya LAN protocol (3.1/3.3/3.4) with the device local key. |
| `hikvision` | Hikvision | `isapi` | `ip_credentials` (host, port, https, username, password, rtsp_port, name) | ISAPI over HTTP Digest auth: cameras, NVR/DVR (one child device per channel `SERIAL:chN`), AX PRO alarm panels (arm/disarm, zones, alarm clear). RTSP main/sub streams, JPEG snapshots, PTZ. |
| `dahua` | Dahua / IMOU / Amcrest / Lorex | `dahua_http` | `ip_credentials` (host, port, https, username, password, rtsp_port, name) | Dahua HTTP CGI API (Digest auth): cameras and NVR/DVR/XVR with per-channel children, RTSP streams, snapshots, PTZ, motion/recording state. |
| `ajax` | Ajax Systems | `ajax_cloud`, `sia_dc09` | `cloud_account` (api_key, login, password, base_url; discovery, integration) - `sia_receiver` (account, name) | Ajax Enterprise API (session tokens, hubs -> panel, devices -> zones/sensors/sirens/plugs, arm/disarm). SIA DC-09 mode registers a panel account with the hub's `SiaReceiver` (`HUB_SIA_PORT`) which maps Contact-ID/SIA codes to panel and zone state; also works for Hikvision AX PRO, Paradox, DSC... |
| `matter` | Matter (CSA) | `matter` | `qr_code` (code, wifi_ssid, wifi_password, server_url) - `manual_code` (11/21-digit code) - `on_network` (setup_pin, ip, server_url) | Commissions through python-matter-server (WebSocket JSON-RPC, injectable connector). Parses `MT:` QR payloads (base38) and manual pairing codes (`adapters/matter_payload.py`), maps Descriptor device types to categories and normalises the well-known clusters (OnOff 6, LevelControl 8, ColorControl 768, WindowCovering 258, DoorLock 257, Thermostat 513, BooleanState 69, OccupancySensing 1030, Temperature/Humidity/Illuminance measurement, SmokeCoAlarm 92, PowerSource 47, ElectricalPower/Energy 144/145, Switch 59) and subscribes to `attribute_updated` push events. |
| `onvif` | ONVIF cameras (Reolink, Uniview, Tapo/VIGI, Axis...) | `onvif` | `ip_credentials` (host, port, username, password, name) | ONVIF Profile S SOAP over HTTP with WS-UsernameToken password digest (camera clock offset synced first): GetDeviceInformation, GetCapabilities/services, media profiles -> RTSP main/sub URIs (credentials injected), snapshot URI + JPEG fetch, PTZ ContinuousMove/Stop when the camera exposes a PTZ service. No event subscription (polled). |
| `home_assistant` | Home Assistant (Open Home Foundation) | `ha_rest` | `long_lived_token` (url, token; discovery, integration, `selected_external_ids` filter) | HA REST API: imports entities (light, switch, binary_sensor, sensor, lock, cover, climate, alarm_control_panel, camera, siren...) and calls services for commands; maps HA device classes to SafeR categories. |
| `demo` | Demo devices (SafeR) | `demo` | `virtual` (prefix; discovery) | 13 virtual devices (light, plug, 2-gang switch, cover, thermostat, sensors, camera, lock, panel + zone) for QA and app demos. Enabled by `HUB_DEMO_ENABLED`. |

Adapter errors are raised as `AdapterError(message, code=...)` and mapped by the API:
`invalid_input` -> 400, `auth_failed` -> 401, `not_found` -> 404, `unsupported` -> 501,
`unreachable` -> 502.

## How to add an adapter

1. Create `adapters/<brand>.py` with a `BrandAdapter` subclass (`adapters/base.py`); use
   `adapters/demo.py` as the reference for style.
   - `brand_id` and `info()` -> `BrandInfo` (protocols, categories, `PairingMethod`s with
     `FormField`s the app renders).
   - `pair(method_id, payload, ctx)` -> `PairResult` of `DeviceDraft`s (+ optional
     `IntegrationDraft` for cloud accounts); `discover()` when the method supports it.
   - `refresh(device, ctx)` -> `DeviceState`; `send_command(device, code, value, ctx)` -> partial
     state for every writable capability; optional `stream`, `snapshot`, `subscribe` (push),
     `unpair`.
   - Map every native data point to the canonical codes with the preset helpers in
     `capabilities.py` (`switch_caps`, `light_caps`, `camera_caps`, `alarm_panel_caps`...).
   - Do all I/O through `async with ctx.http() as client:`; raise `AdapterError` with the codes
     above; keep the adapter pure (no DB, no global state besides the registry).
2. Register it at module import: `registry.register(MyAdapter())` and add the module to the
   import list in `adapters/__init__.py`.
3. Add `tests/test_<brand>.py` mocking the device/cloud with `httpx.MockTransport` and realistic
   sample responses (pairing, refresh, commands, error mapping).
4. Run `pytest app/hub/tests -q` and `pylint --rcfile=.pylintrc app/hub`.
