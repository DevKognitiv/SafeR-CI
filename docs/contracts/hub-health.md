# Hub `/health`, version negotiation, stream and auth error contracts

```
Status: Implemented in Phase 0 (hub side); app behaviour specified here
Decides: hub maintainer
Date: 2026-10-11
Code: backend/app/hub/routes/health.py, schemas.py (HealthOut, StreamOut, SosIn), ratelimit.py,
      routes/security.py, routes/auth.py, routes/devices.py
```

## 1. `GET /api/v1/hub/health`

No authentication. Never blocks: the NTP probe runs in a background thread with a 60 s cache,
and a missing `timedatectl` contributes nothing.

```json
{
  "status": "ok",
  "version": "0.3.0",
  "hub_version": "0.3.0",
  "api_version": "1",
  "min_app_version": "0.2.0",
  "adapters": ["ajax", "dahua", "demo", "hikvision", "home_assistant", "matter", "onvif", "tuya"],
  "sia_receiver": false,
  "categories": ["switch", "plug", "light", "cover", "thermostat", "sensor_contact", "sensor_motion",
                 "sensor_temperature", "sensor_humidity", "sensor_smoke", "sensor_water", "sensor_gas",
                 "sensor_multi", "camera", "nvr", "doorbell", "lock", "siren", "alarm_panel", "alarm_zone",
                 "gateway", "remote", "generic"],
  "flags": {
    "sos_require_address": false,
    "stream_credentials_to_clients": false,
    "demo_enabled": true,
    "rate_limit_enabled": true,
    "open_registration": true
  },
  "clock_synced": true,
  "server_time": "2026-10-11T12:00:00Z"
}
```

| Field | Meaning | Source |
|---|---|---|
| `status` | Liveness, always `ok` when the process answers. | constant |
| `version` | Hub package version (kept for older clients; same value as `hub_version`). | `app.hub.__version__` |
| `hub_version` | Semantic version `major.minor.patch` of the hub build. | `app.hub.__version__` |
| `api_version` | Wire contract generation, `"1"`. Bumped only on an incompatible change; the app refuses an unknown value. | `API_VERSION` |
| `min_app_version` | Oldest app version this hub still serves. | `HUB_MIN_APP_VERSION` (default `0.2.0`) |
| `adapters` | Registered brand ids. | `registry.ids()` |
| `sia_receiver` | True when the SIA DC-09 receiver service is running (`HUB_SIA_PORT` > 0). | runtime services |
| `categories` | Canonical device categories, in the hub's order. | `capabilities.CATEGORIES` |
| `flags` | Feature flags the app adapts to (table below). | `hub_flags(settings)` |
| `clock_synced` | False when the system clock is before the build floor (`BUILD_EPOCH_FLOOR`, bumped each release) or when `timedatectl` reports `NTPSynchronized=no`. "Unknown" (no `timedatectl`) counts as synced. | `clock_synced()` |
| `server_time` | The hub's UTC clock at the time of the answer, ISO-8601 with `Z`. | `utcnow()` |

### Flags

| Flag | Setting | App behaviour |
|---|---|---|
| `sos_require_address` | `SAFER_SOS_REQUIRE_ADDRESS` | When true and the phone has no position, the SOS screen asks for an address or landmark and a confirmation **before** sending; otherwise the hub would answer `422 position_required` (§4). |
| `stream_credentials_to_clients` | `HUB_STREAM_CREDENTIALS_TO_CLIENTS` | When false (default) camera credentials never reach the phone; the camera panel uses the snapshot path and shows the "Lecture vidéo indisponible" chip for protected cameras until the Phase 3 stream relay exists (§3). |
| `demo_enabled` | `HUB_DEMO_ENABLED` | Show the "Appareils de démonstration" brand in the catalogue. |
| `rate_limit_enabled` | `HUB_RATE_LIMIT_ENABLED` | Informational; the app always handles `429`/`423` (§5). |
| `open_registration` | `HUB_ALLOW_OPEN_REGISTRATION` | Show or hide "Créer un compte" on the login screen; the hub answers `403` to `/auth/register` when closed. |

Flags are additive: an unknown flag is ignored by the app, a missing flag reads as `false`.

## 2. Version negotiation (app behaviour)

Performed at boot (splash) and again on every foreground return older than 10 minutes, before
any authenticated call. All three checks keep the emergency numbers and the SMS composer
usable.

Versions compare numerically on `major.minor.patch` (pre-release and build suffixes stripped).
`AppConfig.version` is the app's own version (`0.2.0` today, mirrored from `pubspec.yaml`);
`AppConfig.minHubVersion` (proposed constant) is the oldest hub the app accepts.

| Condition | Screen | French copy | Behaviour |
|---|---|---|---|
| `AppConfig.version < min_app_version` | **Mise à jour requise** | "Mise à jour requise" / "Cette version de SafeR est trop ancienne pour votre hub. Mettez l'application à jour pour continuer." Button "Mettre à jour" (Play Store link). | Blocks every tab; SOS numbers row stays visible and dials; no API call other than `/health`. |
| `hub_version < AppConfig.minHubVersion` or `api_version` unknown | **Hub à mettre à jour** | "Hub à mettre à jour" / "Votre hub SafeR (version {hub_version}) est trop ancien pour cette application. Demandez à votre installateur de le mettre à jour." Secondary "Continuer en mode limité" only when `api_version` matches. | Limited mode: read-only Home and Security, no pairing, no scenes editing. |
| `clock_synced == false` | **Horloge du hub non synchronisée** banner | "Horloge du hub non synchronisée" / "Les heures affichées peuvent être fausses jusqu'à la prochaine synchronisation." | Relative ages ("il y a 4 min", "Dernière activité…") are hidden everywhere and replaced by the banner; absolute times from the hub are shown with a "?" suffix; nothing is blocked. The app re-reads `/health` every 60 s while the banner is up. |
| `/health` unreachable | existing network error path | "Impossible de joindre le hub" | Offline handling (state matrix). |

The hub's compatibility matrix (app version × hub version × `api_version`) is kept in
`docs/ops/hub-upgrade.md` (Lane B deliverable) and updated with every release.

## 3. Stream contract — `GET /api/v1/hub/devices/{id}/stream?quality=main|sub`

Returns `StreamOut`:

```json
{
  "url": "rtsp://192.168.1.50:554/Streaming/Channels/101",
  "type": "rtsp",
  "headers": {},
  "auth_required": true,
  "credentials_included": false
}
```

| Field | Rule |
|---|---|
| `url` | Stream URL with any `user:pass@` userinfo **removed**. |
| `type` | `rtsp`, `hls`, `mjpeg`, `webrtc` or `http`. |
| `headers` | Headers the player must send. `Authorization`, `Cookie`, `X-Api-Key` and other sensitive headers are stripped unless credentials are included. |
| `auth_required` | True when the adapter's stream needs a username, a password or a sensitive header. |
| `credentials_included` | True only when `HUB_STREAM_CREDENTIALS_TO_CLIENTS=true` **and** `auth_required`; then `username`, `password` and the sensitive headers are present. |

Default: **no credentials leave the hub.** The app's `StreamInfo.directPlaybackAllowed` is
`!auth_required || hasCredentials`; when it is false the camera panel does not open the player
and shows the "Lecture vidéo indisponible" chip with the snapshot button still working. The
Phase 3 hub-side relay (signed short-lived stream tokens) replaces this with a playable URL for
every member regardless of role. The owner may set the flag on a trusted LAN deployment,
accepting that every member's phone receives the camera password.

Test switch: `DeviceFakeHubClient(protectedStreams: true)` returns `auth_required: true` without
credentials.

## 4. SOS — `POST /api/v1/hub/homes/{home_id}/sos`

Body (`SosIn`): `lat`/`lon` (both or neither), `note` (≤ 1000), `incident_type` (default
`panic`), `address` (≤ 300, whitespace-normalised), `address_confirmed` (bool).

| HTTP | Body | App behaviour |
|---|---|---|
| 201 | `SosOut` (`id, home_id, user_id, lat, lon, note, address, status, forwarded, incident_id, created_at`) | "Alerte enregistrée sur le hub"; "Alerte transmise aux secours" once `forwarded` is true on refresh. |
| 422 | `{"detail": {"code": "position_required", "message": "Position inconnue: confirmez une adresse ou un repère avant d'envoyer le SOS"}}` | Nothing was created. The app opens the address field, asks for confirmation ("Les secours iront à cette adresse") and resends with `address` + `address_confirmed: true`. The app pre-empts this when `flags.sos_require_address` is true and no position is available. |
| 422 | pydantic validation (for example `lat` without `lon`) | Programming error; shown as a generic failure with retry. |
| 404 | not a member of the home | Generic failure. |

`PATCH /homes/{home_id}/sos/{sos_id}` accepts `{"status": "resolved" | "false_alarm"}`; the
platform-driven statuses of `docs/contracts/incident-webhook.md` are a separate column.

## 5. Auth throttling — `POST /auth/login`, `/auth/register`, `/auth/push-token`

In-process sliding windows (`ratelimit.py`), per hub process. Defaults: login 10/min per IP and
5/min per account, register 5/h per IP, push-token 10/min per user, lockout after 5
consecutive failed logins within 15 min for 15 min.

| HTTP | Body | Header | App behaviour |
|---|---|---|---|
| 429 | `{"detail": {"code": "rate_limited", "message": "Trop de tentatives, réessayez dans quelques instants", "retry_after": 42}}` | `Retry-After: 42` | Disable the submit button for `retry_after` seconds with a countdown; message key `auth.rate_limited`. Never retried automatically. |
| 423 | `{"detail": {"code": "account_locked", "message": "Compte temporairement verrouillé après plusieurs échecs de connexion", "retry_after": 900}}` | `Retry-After: 900` | Same, with the lock message (key `auth.account_locked`) and a "Mot de passe oublié ?" hint once that flow exists. |
| 401 | `{"detail": "Invalid credentials"}` | — | "E-mail ou mot de passe incorrect". |
| 403 | `{"detail": "Registration is closed on this hub"}` | — | Hide the register form; the login screen reads `flags.open_registration` first. |

The app maps `detail.code` to its own strings and never shows the hub's `message` verbatim;
`message` is the fallback for an unknown code. Push-token registration being throttled is
silent (logged, retried on next app start).
