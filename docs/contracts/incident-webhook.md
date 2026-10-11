# Incident-status webhook — SafeR CI platform → hub

```
Status: Proposed (pending platform agreement)
Decides: hub maintainer (hub side), SafeR CI platform owner (caller side)
Date: 2026-10-11
External dependency: the SafeR CI incident platform must agree to call this endpoint.
```

## Why

The hub forwards every SOS to the SafeR CI incident platform (`services/sos.py`, §4 below) and
records `forwarded` plus the platform's `incident_id`. Nothing comes back: the hub's SOS status
model is `open`, `resolved`, `false_alarm` (`routes/security.py`, `SOS_STATUSES`), all set by
members. The app can therefore only show "Alerte enregistrée sur le hub" and "Alerte transmise
aux secours"; it cannot show that an operator received, acknowledged or dispatched anything.

This contract adds the return path. Until the platform actually calls it in staging, the SOS
status rail stays at **"Envoyée" and "Enregistrée sur le hub"** (plus "Transmise" when
`forwarded` is true) and `docs/qa/hardware-status.md` lists the callback as
"pending hardware/contract".

## 1. Endpoint

```
POST {hub_base}/api/v1/hub/webhooks/incidents/{sos_id}
Content-Type: application/json
X-SafeR-Timestamp: <unix seconds>
X-SafeR-Delivery: <unique delivery id>
X-SafeR-Signature: <hex HMAC-SHA256>
```

- `{sos_id}` is the hub's `SosAlert.id`, which the hub sent in the outbound payload as `sos_id`
  (§4). The platform stores it with the incident and uses it to address the callback.
- The route is mounted next to the brand and generic webhooks (`routes/webhooks.py`, prefix
  `/webhooks`). No JWT: the signature is the authentication.
- The hub must be reachable by the platform. A hub behind NAT (Raspberry Pi) gets the callback
  only through the relay's inbox (`docs/contracts/relay.md` §5, item kind `incident.status`);
  the same body and the same signature rules apply, the relay just carries them.

## 2. Signature

```
SAFER_INCIDENT_WEBHOOK_SECRET   (hub setting, proposed; one secret per hub, issued by the platform)
string_to_sign = X-SafeR-Timestamp + "." + raw_body_bytes
X-SafeR-Signature = hex(HMAC-SHA256(secret, string_to_sign))
```

- Compared in constant time (`hmac.compare_digest`), like `verify_secret` in `routes/webhooks.py`.
- **Clock skew tolerance: ±300 s** between `X-SafeR-Timestamp` and the hub clock. Outside the
  window: `401 stale_timestamp`. When the hub's own clock is not synchronised
  (`/health.clock_synced=false`) the hub widens the window to ±24 h and logs a warning, so a Pi
  after a power cut does not drop dispatch notices; the timestamp is still required.
- **Replay protection:** `X-SafeR-Delivery` is unique per delivery attempt *content*; the hub
  remembers delivery ids for 24 h (proposed table `hub_webhook_deliveries`, purged daily). A
  delivery id seen before answers `200 {"accepted": false, "duplicate": true}` without
  re-applying anything. Combined with the timestamp window, a captured request cannot be
  replayed later.
- Unset secret: `503 webhook_not_configured` (the platform can detect a hub that is not
  ready). Missing header: `401 missing_signature`. Mismatch: `401 invalid_signature`.
- Body limit 64 KB (`413`).

## 3. Payload

```json
{
  "incident_id": "inc_8821",
  "sos_id": "6f0e…",
  "status": "dispatched",
  "ts": "2026-10-11T12:04:30Z",
  "sequence": 3,
  "operator": {"id": "op_12", "display_name": "Centre Cocody"},
  "eta_minutes": 12,
  "note": "Patrouille en route",
  "closure": null
}
```

| Field | Rule |
|---|---|
| `incident_id` | Required. Must equal `SosAlert.incident_id` when the hub stored one; otherwise the hub adopts it (covers the case where the forward response carried no id). Mismatch: `409 incident_mismatch`. |
| `sos_id` | Required, must equal the path parameter (`400 sos_mismatch`). |
| `status` | One of `received`, `acknowledged`, `dispatched`, `closed`, `false_alarm`. Anything else: `422 invalid_status`. |
| `ts` | Required; when the platform changed the status. Used for ordering and shown in the app. |
| `sequence` | Optional monotonic counter per incident. When present it decides ordering; otherwise `ts` does. |
| `operator` | Optional. `display_name` is shown to members ("Prise en charge par Centre Cocody"); `id` is logged only. No phone number, no personal name of an individual responder. |
| `eta_minutes` | Optional, integer 0–600, only meaningful with `dispatched`. |
| `note` | Optional, max 300 characters, shown verbatim in the message centre. |
| `closure` | Optional object on `closed` / `false_alarm`: `{"reason": "resolved" \| "no_response" \| "cancelled_by_member" \| "false_alarm", "closed_by": "operator" \| "member"}`. |

Statuses are ordered `received < acknowledged < dispatched < closed`, with `false_alarm` as an
alternative terminal state. A callback carrying a status older than the stored one (by
`sequence`, else `ts`) answers `200 {"accepted": false, "ignored": "out_of_order"}` and changes
nothing. A terminal state is never replaced by a non-terminal one. The same status twice with a
newer `ts` updates `operator`, `eta_minutes` and `note` only.

Idempotency of the effect: applying the same `(incident_id, status, sequence)` twice has no
further effect even when the delivery id differs.

## 4. What the hub does with it

Proposed columns on `SosAlert` (Alembic migration): `incident_status` (nullable, the five
values), `incident_updated_at`, `incident_sequence`, `operator_name`, `eta_minutes`,
`incident_note`. The member-facing `status` (`open` / `resolved` / `false_alarm`) is updated when
a terminal platform state arrives: `closed` → `resolved`, `false_alarm` → `false_alarm`; the
existing "last open SOS releases an SOS-only alarm" rule in `routes/security.py` runs the same
way as for a member PATCH.

On every accepted callback the hub:

1. stores the fields above and commits;
2. creates a message-centre entry (`kind: "notice"`, `severity: "info"`, or `"warning"` for
   `dispatched`) with the French title from the table below;
3. publishes a bus event **`sos.updated`** (new constant in `events.py`, mirrored on the
   WebSocket like every other event):

   ```json
   {
     "type": "sos.updated",
     "home_id": "home-1",
     "sos_id": "6f0e…",
     "incident_id": "inc_8821",
     "status": "dispatched",
     "ts": "2026-10-11T12:04:30Z",
     "sequence": 3,
     "operator": "Centre Cocody",
     "eta_minutes": 12
   }
   ```

4. asks the relay for a push of kind `sos.updated` (`docs/contracts/relay.md` §3; the payload
   carries only ids and the timestamp, the app fetches the detail).

Message-centre titles and the app's status rail (the rail shows only statuses the hub can
actually confirm):

| Platform status | Rail label (fr) | Rail label (en) | Message title (fr) |
|---|---|---|---|
| (app, before any answer) | Envoyée | Sent | — |
| (hub `201`) | Enregistrée sur le hub | Recorded on the hub | existing alarm message "SOS déclenché" (`SOS_TITLE`, carries an emoji prefix today that the Phase 2 copy pass removes) |
| (`forwarded=true`) | Transmise à SafeR CI | Forwarded to SafeR CI | — |
| `received` | Reçue par SafeR CI | Received by SafeR CI | SOS reçu par SafeR CI |
| `acknowledged` | Prise en charge | Acknowledged | SOS pris en charge |
| `dispatched` | Secours en route | Help on the way | Secours en route |
| `closed` | Clôturée | Closed | SOS clôturé |
| `false_alarm` | Fausse alerte | False alarm | SOS : fausse alerte |

Member-initiated `false_alarm` after `dispatched` (the app's "Annuler" after the cancel window)
must reach the platform: the hub sends `PATCH {SAFER_INCIDENTS_URL}{incident_id}` with
`{"status": "false_alarm", "source": "mobile_app"}` and the same bearer token as the forward.
This outbound call is part of the same platform agreement and is listed as pending until the
platform confirms the route.

## 5. Responses

| HTTP | Body | When |
|---|---|---|
| 200 | `{"accepted": true, "status": "dispatched", "sequence": 3}` | applied |
| 200 | `{"accepted": false, "duplicate": true}` | delivery id seen before |
| 200 | `{"accepted": false, "ignored": "out_of_order"}` | older than the stored status |
| 400 | `{"detail": {"code": "sos_mismatch"}}` / `malformed_json` | body problems |
| 401 | `missing_signature`, `invalid_signature`, `stale_timestamp` | §2 |
| 404 | `{"detail": {"code": "unknown_sos"}}` | no such alert on this hub |
| 409 | `incident_mismatch` | `incident_id` differs from the stored one |
| 413 | `body_too_large` | |
| 422 | `invalid_status`, `invalid_field` | |
| 503 | `webhook_not_configured` | secret unset |

The platform retries `5xx` and network errors with backoff for at least 24 h, never `4xx`
except `503`.

## 6. Tests the hub PR must carry

Signature accepted / rejected / missing; timestamp inside and outside ±300 s (and the widened
window when `clock_synced` is false, with `health.utcnow` monkeypatched); duplicate delivery id;
out-of-order sequence ignored; terminal state not downgraded; `incident_id` adoption and
mismatch; `sos.updated` published on the bus and visible on the WebSocket; message-centre entry
created; `closed` releases an SOS-only alarm; secret unset answers 503.

---

## 7. The hub's outbound incident payload (today)

Built by `build_incident_payload` in `backend/app/hub/services/sos.py` and sent as
`POST SAFER_INCIDENTS_URL` with `Accept: application/json`, `User-Agent: SafeR-Hub/sos` and
`Authorization: Bearer SAFER_INCIDENTS_TOKEN` when the token is set. Forwarding is
fire-and-forget in a background task; the panic button answers `201` before the platform does.

```json
{
  "incident_type": "panic",
  "severity": "critical",
  "location_lat": 5.36,
  "location_lon": -4.0,
  "location_source": "phone",
  "location_confidence": "gps",
  "source": "mobile_app",
  "description": "Intrusion porte arrière",
  "hub_id": "safer-hub",
  "triggered_by": "alice@safer.ci",
  "home_id": "home-1",
  "home_name": "Maison Cocody",
  "sos_id": "6f0e…",
  "address": "Cocody, rue des Jardins, portail bleu"
}
```

| Field | Source |
|---|---|
| `incident_type` | `SosIn.incident_type`, default `panic` (max 40 chars). |
| `severity` | Always `critical`. |
| `location_lat` / `location_lon` | `resolve_position`: phone position (`SosIn.lat`/`lon`, both or neither) > home position (`Home.lat`/`lon`) > Abidjan-Plateau default (5.36, -4.0083). Sources are never mixed. |
| `location_source` | **New this session.** `phone`, `home` or `default`. |
| `location_confidence` | **New this session.** `gps` (phone), `home` (home coordinates), `none` (default). |
| `description` | `SosIn.note` trimmed, else `SOS SafeR app`. When the default position is used it is prefixed with `Position inconnue (defaut Abidjan-Plateau) - ` so an operator never dispatches to Plateau by mistake. |
| `address` | **New this session.** Present only when the member typed an address or landmark (`SosIn.address`, max 300 chars, whitespace-normalised). |
| `hub_id` | Constant `safer-hub` today; becomes the relay `hub_id` once registration exists. |
| `triggered_by` | The member's e-mail. (Phase 4 phone-first login makes this the phone number or an opaque member id; to be renegotiated then.) |
| `home_id`, `home_name`, `sos_id` | Hub ids and the home label; `sos_id` is what the callback above addresses. |

Gating (`SAFER_SOS_REQUIRE_ADDRESS`, default false): when the position would be the default
and the flag is on, the hub **refuses** the SOS with `422 {"code": "position_required",
"message": "Position inconnue: confirmez une adresse ou un repère avant d'envoyer le SOS"}` unless
`address` is given and `address_confirmed` is true; nothing is created in that case. The
confirmation is a user assertion the hub cannot verify; it is logged as such.

Response parsing: the incident id is read from `id`, `incident_id`, `incident.id` or
`data.id`; any 2xx sets `forwarded=true`. Non-2xx and network errors are logged and the alert
stays `forwarded=false` (the app then shows "Le hub a déclenché l'alarme mais n'est pas relié
aux secours : appelez un numéro d'urgence ci-dessous.").

The hub also publishes `sos.raised` on the bus with `{sos_id, lat, lon, user_id, note, address,
location_source}` for the WebSocket. The relay push for `sos.raised` carries none of these
fields (ids and timestamp only).
