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
- Health: `GET /api/v1/hub/health` -> `{status, version, adapters, sia_receiver, categories, hub_version,
  api_version, min_app_version, flags, clock_synced, server_time}` (see *App/hub contract* below).
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
injectable connector. Each test gets a fresh in-memory SQLite database (`tests/conftest.py`,
`create_all`; the Alembic path is covered by `tests/test_migrations.py`).

## Migrations

The schema is versioned with Alembic (`backend/alembic.ini`, `backend/alembic/`). `env.py` binds
`app.hub.db.Base` with every model imported and resolves the database URL from `-x url=...`, else
`HUB_DATABASE_URL`, else `DATABASE_URL`, else `sqlite:///./safer_hub.db`; async URLs are converted
to their sync drivers (`sqlite+aiosqlite` -> `sqlite`, `postgresql+asyncpg` -> `postgresql+psycopg2`)
and SQLite runs in batch mode. The version table is `hub_alembic_version` (the main API may share
the database). It never reads `.env` and never logs credentials.

On startup (`HUB_AUTO_MIGRATE=true`, the default) the runtime brings the database to `head` through
its own engine: an empty database is created, a hub created with `create_all` before migrations
existed (tables, no `hub_alembic_version`) is stamped `0001_baseline` then upgraded, and any other
database is upgraded. With `HUB_AUTO_MIGRATE=false` the hub only runs `create_all` (missing tables,
never column changes) and you run the upgrade yourself.

```bash
cd backend
# Upgrade (the running hub does this itself unless HUB_AUTO_MIGRATE=false)
python -m alembic -c alembic.ini upgrade head
python -m alembic -c alembic.ini -x url=sqlite:////var/lib/safer/hub.db upgrade head
python -m alembic -c alembic.ini current            # which revision the database is at

# New revision after changing models.py (autogenerate, then review the file by hand)
python -m alembic -c alembic.ini -x url=sqlite:////tmp/autogen.db upgrade head
python -m alembic -c alembic.ini -x url=sqlite:////tmp/autogen.db revision --autogenerate \
    -m "short description" --rev-id 0003_short_description

# Rollback rehearsal before a hub release (on a copy of the production database)
cp /var/lib/safer/hub.db /tmp/rehearsal.db
python -m alembic -c alembic.ini -x url=sqlite:////tmp/rehearsal.db upgrade head
python -m alembic -c alembic.ini -x url=sqlite:////tmp/rehearsal.db downgrade -1
python -m alembic -c alembic.ini -x url=sqlite:////tmp/rehearsal.db upgrade head
```

Rules: revision ids are `NNNN_slug`, every revision has a working `downgrade()`, and
`tests/test_migrations.py` fails when the models and the migrations disagree (`compare_metadata`
after `upgrade head` must be empty), so add a revision in the same change as the model edit. SQLite
cannot alter columns in place: `op.batch_alter_table` recreates the table, which is why the baseline
and every revision use batch mode.

## Security on `/auth`

`POST /auth/login`, `/auth/register` and `/auth/push-token` go through an in-process sliding-window
limiter (`ratelimit.py`, one instance per runtime): `HUB_LOGIN_PER_IP_PER_MINUTE`,
`HUB_LOGIN_PER_ACCOUNT_PER_MINUTE`, `HUB_REGISTER_PER_IP_PER_HOUR`,
`HUB_PUSH_TOKEN_PER_USER_PER_MINUTE`, and `HUB_LOGIN_LOCKOUT_THRESHOLD` consecutive failed logins
on one e-mail within `HUB_LOGIN_LOCKOUT_WINDOW_SECONDS` lock it for `HUB_LOGIN_LOCKOUT_SECONDS`.
Over-limit requests answer `429` and locked accounts `423`, both with a `Retry-After` header and a
`detail` object `{"code": "rate_limited" | "account_locked", "message", "retry_after"}`. Unknown
e-mails are counted, locked and bcrypt-checked exactly like existing ones so nothing reveals which
accounts exist. The client IP is the TCP peer unless `HUB_TRUST_PROXY_HEADERS=true` (then the first
`X-Forwarded-For` entry when it is a valid IP address, only behind a proxy you control that
*overwrites* the header, e.g. nginx `proxy_set_header X-Forwarded-For $remote_addr`; an appending
proxy would let clients choose their own entry). Counters are per process: Raspberry Pi
hubs run one uvicorn worker; a multi-worker deployment needs a shared store (Redis) behind the same
interface before the limits mean anything globally.

## App/hub contract

- `GET /health` also returns `hub_version` (= `version`), `api_version` (`"1"`),
  `min_app_version` (`HUB_MIN_APP_VERSION`; an older app shows its forced-update screen),
  `flags` (`sos_require_address`, `stream_credentials_to_clients`, `demo_enabled`,
  `rate_limit_enabled`, `open_registration`), `clock_synced` (system time past the build floor
  and, when `timedatectl` answers, `NTPSynchronized=yes`; the app hides relative ages when false)
  and `server_time` (ISO-8601 UTC).
- `GET /devices/{id}/stream` returns `StreamOut`: `{url, type, headers, auth_required,
  credentials_included, username, password}`. Camera credentials and any `user:pass@` in the URL
  are stripped; `auth_required` tells the app the stream needs them. Only with
  `HUB_STREAM_CREDENTIALS_TO_CLIENTS=true` (the owner accepts that every member's phone receives
  the camera admin password over the LAN, until the hub stream relay exists) are `username` /
  `password` filled and `credentials_included` true; the hub logs a warning at startup.
- `POST /homes/{id}/sos` accepts `address` (free text, 300 chars) and `address_confirmed`. The
  incident position is the phone position, else the home coordinates, else the Abidjan-Plateau
  default, reported as `location_source` (`phone|home|default`) and `location_confidence`
  (`gps|home|none`); a default position prefixes the description with
  `Position inconnue (defaut Abidjan-Plateau) - `. With `SAFER_SOS_REQUIRE_ADDRESS=true` an SOS
  that would use the default is refused with `422 {"detail": {"code": "position_required",
  "message"}}` unless `address` is given and `address_confirmed` is true; nothing is created then.

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
| `HUB_MIN_APP_VERSION` | `0.2.0` | Oldest app version served, announced on `/health` |
| `HUB_AUTO_MIGRATE` | `true` | Run Alembic `upgrade head` on startup (see *Migrations*) |
| `SAFER_SOS_REQUIRE_ADDRESS` | `false` | Refuse an SOS without phone/home position unless the user confirmed an address (422 `position_required`) |
| `HUB_STREAM_CREDENTIALS_TO_CLIENTS` | `false` | Include camera credentials in `GET /devices/{id}/stream` (LAN risk, logged at startup) |
| `HUB_RATE_LIMIT_ENABLED` | `true` | Rate limits + lockout on `/auth` |
| `HUB_TRUST_PROXY_HEADERS` | `false` | Take the client IP from the first `X-Forwarded-For` entry (only behind a trusted proxy) |
| `HUB_LOGIN_PER_IP_PER_MINUTE` / `HUB_LOGIN_PER_ACCOUNT_PER_MINUTE` | `10` / `5` | Login attempts allowed per minute |
| `HUB_REGISTER_PER_IP_PER_HOUR` | `5` | Registrations per client IP per hour |
| `HUB_PUSH_TOKEN_PER_USER_PER_MINUTE` | `10` | Push-token registrations per user per minute |
| `HUB_LOGIN_LOCKOUT_THRESHOLD` / `HUB_LOGIN_LOCKOUT_WINDOW_SECONDS` / `HUB_LOGIN_LOCKOUT_SECONDS` | `5` / `900` / `900` | Consecutive failures within the window that lock an account, and for how long (423 `account_locked`) |
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
4. Run `pytest app/hub/tests -q` and `pylint --rcfile=.pylintrc app/hub`. Never put secrets in
   `DeviceDraft.config`/`state` or `IntegrationDraft.config` (the app reads them): credentials go in
   `credentials` (encrypted at rest) and stream credentials in `StreamInfo.username`/`password`, which
   the API strips before answering the app.
