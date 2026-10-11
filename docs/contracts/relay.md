# Cloud relay contract — `api.safer-ci.app`

```
Status: Proposed
Decides: hub maintainer (contract), product owner (remote-access model, decision 0001 §6)
Date: 2026-10-11
Depends on: docs/decisions/0001-platform-scope.md §6 and §7
```

## Why a relay

Hubs run on Raspberry Pis in homes (`docs/safer-app.md`), on SQLite, physically reachable by
anyone in the house. A Firebase service account or an SMS-provider API key copied onto every Pi
is one stolen SD card away from sending push to every SafeR user or burning the SMS budget. The
relay keeps those secrets in one place: **hubs call the relay, and the relay calls Firebase and
the SMS/WhatsApp providers.** A hub never holds a provider credential; it holds only its own
relay credentials, which the relay can revoke individually.

The relay is also the only component that can reach a phone when the app is closed, so the
alarm takeover and the SOS status rail (`docs/contracts/incident-webhook.md`) depend on it.

What the relay is **not**: it does not proxy the hub's API, does not store device state, does
not see camera streams or snapshots, and (in release 1) does not give the app remote control of
the hub. Hubs without a registration key run in local-only mode (0001 §6, option C).

## Terms

| Term | Meaning |
|---|---|
| hub | A SafeR hub instance (`backend/app/hub`) identified by `hub_id`. |
| registration key | One-time secret issued by the SafeR CI operator for a hub (printed on the Pi image label or shown in the operator console). Exchanged once for hub credentials. |
| hub token | Long-lived bearer token returned by registration. Identifies the hub. |
| signing secret | Secret returned by registration, used for the HMAC signature on every call. Rotatable. |
| push token | The FCM registration token an app instance registered with the hub through `POST /api/v1/hub/auth/push-token`. The relay receives it per call and does not keep it. |

Base URL: `https://api.safer-ci.app/relay/v1`. All bodies are JSON (`application/json; charset=utf-8`),
timestamps are ISO-8601 UTC with a `Z` suffix, identifiers are opaque strings up to 64 characters.

## 1. Hub registration

### 1.1 `POST /hubs/register`

Exchanges the registration key for hub credentials. Not signed (the hub has no secret yet);
rate limited per source IP.

```json
{
  "hub_id": "hub_7f3c…",
  "registration_key": "reg_…",
  "hub_version": "0.3.0",
  "api_version": "1",
  "label": "Maison Cocody"
}
```

Response `201`:

```json
{
  "hub_id": "hub_7f3c…",
  "hub_token": "hubtok_…",
  "signing_secret": "sk_…",
  "signing_secret_id": "k1",
  "issued_at": "2026-10-11T12:00:00Z",
  "relay_public_notification_locales": ["fr", "en"]
}
```

- A registration key is single use. A second call with the same key answers `409 key_used`.
- `hub_id` is chosen by the operator when the key is issued; the hub must send the same value.
  The hub stores `hub_token` and `signing_secret` encrypted with its credential vault
  (`HubRuntime.vault`, Fernet) and uses `hub_id` as the `hub_id` of its outbound incident
  payload (today a constant `safer-hub`, see `services/sos.py`; the constant is replaced by the
  registered id).
- Proposed hub settings: `SAFER_RELAY_URL` (empty = local-only mode), `SAFER_RELAY_HUB_ID`,
  `SAFER_RELAY_REGISTRATION_KEY` (consumed on first boot, then cleared from the environment
  file by the operator), `SAFER_RELAY_DRY_RUN=true` in CI (every call is logged and answered
  locally with a synthetic success; no network).

### 1.2 Rotation: `POST /hubs/{hub_id}/keys/rotate`

Signed with the current secret. Returns a new `signing_secret` and `signing_secret_id`. The
previous secret stays valid for **24 hours** so a hub that crashes between the response and the
save does not lock itself out; every request carries `X-SafeR-Key-Id` so the relay knows which
secret to verify with. Rotation is run by the hub every 90 days (scheduled task) and on demand
from `Moi › Intégrations › Relais SafeR › Renouveler la clé` (owner only).

`POST /hubs/{hub_id}/token/rotate` does the same for the bearer token, with the same 24-hour
overlap. The operator console can revoke either immediately; the hub then receives
`401 hub_revoked` and falls back to local-only mode with a message-centre notice
("Relais SafeR déconnecté : notifications push indisponibles").

### 1.3 `GET /hubs/{hub_id}` (signed)

Returns the relay's view of the hub (`label`, `issued_at`, `signing_secret_id`, quotas, last
successful call) for the hub's `/health` and the Intégrations screen.

## 2. Authentication of every signed call

Every call except `POST /hubs/register` carries:

| Header | Value |
|---|---|
| `Authorization` | `Bearer <hub_token>` |
| `X-SafeR-Hub` | `hub_id` |
| `X-SafeR-Key-Id` | `signing_secret_id` of the secret used |
| `X-SafeR-Timestamp` | Unix seconds, hub clock |
| `X-SafeR-Nonce` | 16 random bytes, hex (unique per hub for 10 minutes) |
| `X-SafeR-Signature` | `hex(HMAC-SHA256(signing_secret, string_to_sign))` |

```
string_to_sign = timestamp + "\n" + nonce + "\n" + METHOD + "\n" + path_with_query + "\n" + hex(sha256(raw_body))
```

- `METHOD` upper case; `path_with_query` is the request target as sent (`/relay/v1/push/send`);
  the body hash is over the exact bytes sent (empty body → sha256 of the empty string).
- The relay rejects timestamps more than **300 s** from its own clock (`401 stale_timestamp`).
  A hub whose `/health` reports `clock_synced=false` must not call the relay until the clock is
  synchronised; it queues (see §6) instead of being refused.
- Nonces are remembered per hub for 10 minutes; a reused nonce answers `401 replayed`.
- Signature mismatch, unknown key id, revoked token: `401 invalid_signature`, `401 unknown_key`,
  `401 hub_revoked`. The hub treats every `401` as fatal for the call (no retry) and logs it at
  warning level with the relay's `request_id`.

## 3. Push send API

### 3.1 `POST /push/send`

```json
{
  "idempotency_key": "evt_01J…",
  "kind": "security.alarm",
  "home_id": "home-1",
  "event_id": "evt_01J…",
  "ts": "2026-10-11T12:00:03Z",
  "seq": 4172,
  "priority": "high",
  "ttl_seconds": 600,
  "targets": [
    {"token": "fcm:…", "platform": "android", "locale": "fr"},
    {"token": "fcm:…", "platform": "android", "locale": "en"}
  ],
  "public_notification": {"template": "alarm", "channel": "safer_alarm"}
}
```

| Field | Rule |
|---|---|
| `kind` | One of `security.alarm`, `security.cleared`, `sos.raised`, `sos.updated`, `device.event`, `message.new`. Anything else: `400 unknown_kind`. |
| `home_id`, `event_id`, `ts` | Required. `event_id` is the hub's event id; the app deduplicates WebSocket and push deliveries by it. |
| `seq` | Optional monotonic sequence number of the hub event bus, so the app can detect gaps and resync (proposed `/homes/{id}/activity?since=` hub route, Phase 3). |
| `priority` | `high` only for `security.alarm`, `sos.raised`, `sos.updated`; the relay downgrades anything else to `normal` and reports `priority_downgraded` in the result. |
| `ttl_seconds` | 0–86400; default 600 for alarm kinds, 3600 otherwise. |
| `targets` | 1–500 tokens. Tokens are used for this delivery and are not stored (a salted hash is kept in the delivery log, §7). |
| `public_notification` | Optional. Requests the *visible-notification variant* (§3.3). |

**Payload rule (schema-enforced): the body may not carry an address, coordinates, a snapshot
URL, a device name, a member name, a note, or any free text.** Unknown fields answer
`400 payload_not_allowed` with the offending field name. The phone fetches the detail from the
hub with its own bearer token once it is woken up.

### 3.2 What the phone receives (data-only)

```json
{
  "data": {
    "kind": "security.alarm",
    "hub_id": "hub_7f3c…",
    "home_id": "home-1",
    "event_id": "evt_01J…",
    "ts": "2026-10-11T12:00:03Z",
    "seq": "4172"
  },
  "android": {"priority": "high", "ttl": "600s"}
}
```

No `notification` block: the app builds the local notification itself (channel `safer_alarm`
with full-screen intent for `security.alarm` and `sos.raised`; `safer_updates` otherwise) and
cancels it on `security.cleared` or `sos.updated` with a closing status, on every device of
every member of the home.

### 3.3 Public-notification variant

Some OEM battery managers (Transsion, Xiaomi) drop data-only messages when the app is not
running, and an app that was force-stopped receives nothing. When `public_notification` is
present the relay sends, **in addition to** the data message, a visible notification whose text
is generic and localised by the relay from the target's `locale`:

| template | fr | en |
|---|---|---|
| `alarm` | "Alerte dans votre maison. Ouvrez SafeR." | "Alert in your home. Open SafeR." |
| `sos` | "Un SOS a été déclenché. Ouvrez SafeR." | "An SOS was raised. Open SafeR." |
| `sos_update` | "Mise à jour de votre SOS. Ouvrez SafeR." | "Your SOS was updated. Open SafeR." |
| `message` | "Nouveau message SafeR." | "New SafeR message." |

The visible text never contains the home name, a device, an address, a member or a status
word, so nothing sensitive lands on a lock screen or in a provider log. The hub requests the
variant for `security.alarm`, `sos.raised` and `sos.updated`; the app's "Test de notification"
button requests `message`.

### 3.4 Response

`202`:

```json
{
  "request_id": "req_…",
  "accepted": 2,
  "results": [
    {"token_hash": "…", "status": "sent", "message_id": "projects/…/messages/…"},
    {"token_hash": "…", "status": "invalid_token"}
  ],
  "warnings": ["priority_downgraded"],
  "replayed": false
}
```

`status` per target: `sent`, `invalid_token` (the hub deletes the push token row),
`rate_limited` (relay quota for that token, retry later), `provider_error` (retry),
`unsupported_platform`. The relay never returns the FCM error text to the hub.

### 3.5 Delivery expectations

Push is **best effort**. The WebSocket remains the primary channel while the app is open; the
app deduplicates by `event_id`. Until a relay deployment and two physical phones (one
Transsion) have been exercised, `docs/qa/hardware-status.md` lists push delivery as
"pending hardware/contract" and no screen or release note may say "notifications en temps réel".

## 4. SMS and WhatsApp send

### 4.1 `POST /sms/send`

```json
{
  "idempotency_key": "otp_01J…",
  "purpose": "otp",
  "to": "+2250700000000",
  "channel": "auto",
  "template": "otp",
  "params": {"code": "482913", "ttl_minutes": "10"},
  "locale": "fr",
  "home_id": "home-1"
}
```

| Field | Rule |
|---|---|
| `purpose` | `otp` (login/registration/phone verification), `sos_fallback` (the hub could not reach the incident platform, or the member asked for SMS), `alert` (alarm notice to an emergency contact), `test`. |
| `to` | E.164. The relay refuses numbers outside the configured countries (`+225` first) with `400 destination_not_allowed`. |
| `channel` | `sms`, `whatsapp`, or `auto` (WhatsApp when the number has an account and the template is approved, SMS otherwise). |
| `template`, `params` | Templates live in the relay (so WhatsApp template approval happens once). Free text is not accepted except in `sos_fallback.note` (max 160 chars, see §7). |
| `locale` | `fr` or `en`. |

Templates (fr shown; en exists for each):

| template | purposes | text |
|---|---|---|
| `otp` | otp | "SafeR : votre code est {code}. Valable {ttl_minutes} min. Ne le partagez pas." |
| `sos_fallback` | sos_fallback | "SOS SafeR : {member} a besoin d'aide à {place}. {note} Appelez le 170 (Police) ou le 185 (SAMU)." |
| `alert_contact` | alert | "SafeR : alarme déclenchée à {home_label}. Ouvrez l'application ou appelez {member}." |
| `test` | test | "SafeR : test d'envoi réussi." |

`{place}` is the home label or the user's free-text address, never raw coordinates; `{member}`
is a first name. The emergency numbers in the template are the same constants the app shows
and change only through decision 0001 §8.

Response `202`: `{"message_id": "msg_…", "channel": "sms", "provider": "orange", "status": "queued", "replayed": false}`.

### 4.2 Provider abstraction

The relay picks the provider; the hub never names one. Routing in Côte d'Ivoire by number
prefix after the 2021 10-digit numbering plan: `07` → Orange, `05` → MTN, `01` → Moov, with a
fallback aggregator (Africa's Talking or Twilio) when the operator gateway fails or the number
is foreign. Each provider sits behind one interface (`send(template, params, to) → provider_id`,
`status(provider_id)`, `inbound(webhook) → message`), so adding or swapping an operator is a
relay change only. Per-operator delivery is "pending hardware/contract" until a real SIM on
each network receives an OTP and an SOS fallback (`docs/qa/hardware-status.md`).

### 4.3 Delivery status: `GET /sms/{message_id}`

`{"status": "queued" | "sent" | "delivered" | "failed" | "expired", "channel": "sms", "updated_at": "…", "failure": "no_credit" | "invalid_number" | "provider_down" | null}`.
The hub polls at most once per 30 s per message for 10 minutes and stores the outcome on the
OTP or SOS record; the app shows "SMS envoyé" / "SMS non remis" only from that stored outcome.

## 5. Inbound SMS (future, pending contract)

Goal: an SOS that works without data. A member texts `SOS <home code> [note]` to a SafeR short
code or long number; the relay's provider webhook parses it, creates an incident on the SafeR CI
platform with `source: "sms"` and the home's registered position, and replies with a receipt
SMS ("SafeR : SOS reçu pour {home_label}. Les secours sont prévenus.").

Because the hub cannot be reached from the relay (NAT), the hub learns about it by polling
`GET /hubs/{hub_id}/inbox?since=<cursor>` (signed) every 60 s while registered, or immediately
after any other relay call; each item is `{id, kind: "sms.sos", home_id, received_at, from_hash, note}`.

Not part of release 1. Until a short code or long number exists on Orange, MTN and Moov and
the parser is exercised with real SIMs, the app labels its SMS feature **"Prévenir mes proches
par SMS"** (a composer to the member's own emergency contacts) and never "SOS par SMS".

## 6. Idempotency, retries, queueing

- Every `POST` carries `idempotency_key` (body) and may also send it as the `Idempotency-Key`
  header. The relay remembers keys for **24 hours** per hub. Same key and same body hash →
  the stored response is returned with `"replayed": true` and the original `request_id`. Same
  key, different body → `409 idempotency_mismatch`.
- The hub retries on network errors, `408`, `429` (honouring `Retry-After`) and `5xx` with
  exponential backoff: 1, 2, 4, 8, 16, 32, 60, 60… seconds, jittered ±20 %.
  - Push kinds `security.alarm`, `sos.raised`, `sos.updated`: retried until `ttl_seconds`
    elapses (then dropped with a warning log and a message-centre notice for the owner).
  - `device.event`, `message.new`: at most 5 attempts.
  - `sms/send` with `purpose: sos_fallback`: retried for 24 hours; `otp`: at most 3 attempts
    within the code's validity.
- `4xx` other than `408`/`429` are never retried.
- Queue: an in-process queue persisted to the hub database (`hub_relay_outbox`, proposed
  migration) so a hub restart or a clock-unsynced period does not lose alarm pushes; rows older
  than 7 days are purged. The outbox depth is exposed on `/health` under a proposed `relay`
  object (`{"registered": true, "outbox": 0, "last_ok": "…"}`).

## 7. Rate limits and quotas

Per hub unless stated, answered with `429 rate_limited` and `Retry-After`:

| Endpoint | Limit |
|---|---|
| `POST /hubs/register` | 5 per hour per source IP |
| `POST /push/send` | 600 requests per minute, 60 per second burst; 10 000 targets per minute |
| `POST /push/send` per token | 30 per minute (protects a phone from a looping hub) |
| `POST /sms/send` purpose `otp` | 5 per hour per destination number; 200 per hour per hub |
| `POST /sms/send` purpose `sos_fallback` | 20 per hour per home, never counted against the OTP budget |
| `POST /sms/send` purpose `alert` | 60 per hour per hub |
| `GET /sms/{id}`, `GET /hubs/{id}/inbox` | 120 per minute |

The operator console can lower a hub's quotas or revoke it when a hub misbehaves.

## 8. Privacy and retention

- The relay stores per delivery: `hub_id`, `kind`/`purpose`, `home_id`, `event_id`,
  timestamps, a salted SHA-256 of each push token or destination number, provider ids and
  outcome. **30 days**, then deleted.
- The relay never stores push payloads beyond the delivery attempt (there is nothing sensitive
  in them by construction, §3.1) and never stores OTP codes (template parameters for `otp` are
  redacted from logs before persistence).
- `sos_fallback` notes are kept for **7 days** for abuse investigation, then purged; the
  destination number is kept hashed with the last two digits in clear for support.
- The relay runs in-country where a provider exists (`docs/architecture.md`, "Data locality"),
  otherwise in the nearest region, to be documented in `docs/store/data-safety.md` (Phase 5).
- Hubs can ask `DELETE /hubs/{hub_id}/data` (signed, owner-initiated from the app's account
  deletion flow) to purge every record for that hub ahead of the retention window.

## 9. Error codes

Every error body is `{"error": "<code>", "message": "<english text>", "request_id": "req_…"}`
and, for `429`, a `Retry-After` header.

| HTTP | `error` | When |
|---|---|---|
| 400 | `invalid_body` | JSON or schema error (message names the field) |
| 400 | `unknown_kind` | push `kind` not in the list |
| 400 | `payload_not_allowed` | a forbidden field was sent (address, coordinates, snapshot URL, free text) |
| 400 | `destination_not_allowed` | number outside the allowed countries or not E.164 |
| 400 | `unknown_template` | SMS template not configured |
| 401 | `missing_auth`, `invalid_signature`, `unknown_key`, `stale_timestamp`, `replayed`, `hub_revoked` | §2 |
| 403 | `quota_disabled` | the operator disabled this capability for the hub |
| 404 | `unknown_hub`, `unknown_message` | |
| 409 | `key_used` | registration key already consumed |
| 409 | `idempotency_mismatch` | same key, different body |
| 413 | `too_many_targets` | more than 500 push targets |
| 422 | `template_params` | missing or invalid template parameter |
| 429 | `rate_limited` | §7 |
| 503 | `provider_unavailable` | every provider failed; retry with backoff |

## 10. What the hub implements (checklist for the relay client PR)

- [ ] Settings `SAFER_RELAY_URL`, `SAFER_RELAY_HUB_ID`, `SAFER_RELAY_REGISTRATION_KEY`, `SAFER_RELAY_DRY_RUN`.
- [ ] Registration on first boot; credentials in the vault; `hub_id` replaces the `safer-hub` constant in `services/sos.py`.
- [ ] Signed HTTP client (headers of §2) with injectable clock and transport (`httpx.MockTransport` in tests).
- [ ] Outbox table + worker with the retry policy of §6; bus subscriber mapping hub events to push kinds.
- [ ] Push token fan-out: tokens of every member of the home, platform and locale from the user row.
- [ ] `invalid_token` → delete the push token row.
- [ ] `/health` `relay` object (proposed) and the Intégrations screen entry.
- [ ] pytest: signature vector, stale timestamp, nonce reuse, idempotent replay, forbidden payload field refused client-side before the call, retry schedule, outbox survives restart, dry-run mode in CI.
