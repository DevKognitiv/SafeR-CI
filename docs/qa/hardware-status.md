# Hardware and contract status

**Rule: this file is the only source that may back a "verified" claim in release notes, in the
About screen ("Marques compatibles") or in store copy.** An adapter or a contract is
`mock-verified` (Matter: `decode-verified only`) until a human runs its checklist on real
equipment and edits the badge to `hardware-verified <date> <model> <tester>`. An automated agent
or an implementer may write the checklist, help run it, parse pasted logs and prepare the edit,
but never flips a badge on its own evidence. Release notes name every adapter and contract that
is not hardware-verified.

Badge format: `mock-verified` · `decode-verified only` · `hardware-verified YYYY-MM-DD <model/firmware> <tester>` · `pending hardware/contract`.

## 1. Adapters (`backend/app/hub/adapters/`)

| Adapter | Badge | What CI exercises (mocks) | Human checklist to flip the badge |
|---|---|---|---|
| **Demo** (`demo.py`) | mock-verified (virtual by design; never becomes hardware-verified) | The whole virtual home (13 devices) through pytest and every widget test. | — |
| **Home Assistant** (`home_assistant.py`) | mock-verified | REST `/api/states`, `/api/services/*`, camera proxy and the WebSocket `state_changed` flow with `httpx.MockTransport` and a fake socket (`test_home_assistant.py`). | 1. HA instance reachable from the hub; long-lived token created. 2. Pair with `long_lived_token`, import a light, a binary_sensor (door), a sensor (temperature), a lock or cover, an alarm_control_panel if present. 3. Toggle the light from SafeR and from HA: both directions update within 5 s. 4. Open the door sensor: SafeR shows "Ouvert" within 5 s. 5. Arm from SafeR: HA panel arms. 6. Restart HA: subscription reconnects, state resyncs. Record HA version. |
| **Tuya cloud** (`tuya.py`, `cloud_project`) | mock-verified | OpenAPI v1.0 signature v2 (token, refresh, device list, status, functions, commands, stream action) with `MockTransport` (`test_tuya.py`). | 1. IoT platform project with IoT Core and Authorization APIs, Smart Life account linked. 2. Pair with region, Access ID/Secret; discovery lists the devices. 3. Import a plug and a light: toggle, brightness and colour from SafeR; Smart Life shows the change. 4. Physical toggle on the device: SafeR updates within one poll interval (`HUB_POLL_INTERVAL`, 30 s). 5. Token expiry: leave the hub running > 2 h, commands still work (refresh path). 6. Wrong secret: pairing fails with a readable error. |
| **Tuya LAN** (`tuya.py`, `local_key`) | mock-verified | DPS mapping tables and command translation (pure functions); no socket test. | 1. `tinytuya` installed on the hub. 2. Device id, local key, IP, protocol version (3.3/3.4) from the IoT platform. 3. Pair; toggle and read state with the internet disconnected from the hub. 4. Device IP change: error is readable and re-pair works. |
| **Hikvision ISAPI cameras / NVR** (`hikvision.py`) | mock-verified | Digest auth, `deviceInfo`, channel lists, snapshot, PTZ, `alertStream` multipart parsing (split chunks, heartbeats ignored, NVR channel routing) with `httpx.MockTransport` (`test_hikvision.py`). | 1. Camera with ISAPI and RTSP enabled, digest auth. 2. Pair with `ip_credentials`; device info correct (model, firmware). 3. Snapshot shows a current image. 4. RTSP main and sub play on the LAN in the app (with `HUB_STREAM_CREDENTIALS_TO_CLIENTS=true`) and through the Phase 3 relay (without). 5. PTZ on a PTZ model: four directions and zoom. 6. Walk in front of the camera: motion event within 3 s, message-centre entry created. 7. NVR: one child per channel, channel snapshot. 8. Power-cycle the camera: subscription reconnects. |
| **Hikvision AX PRO** (`hikvision.py`, panel paths) | mock-verified | `SecurityCP` sub-systems and zones JSON, arm/disarm/bypass/clear commands, CID events on the alert stream (`test_hikvision.py`). | 1. AX PRO with ISAPI user (admin or installer). 2. Pair: panel becomes `alarm_panel` with one `alarm_zone` per zone. 3. Arm away / stay / disarm from SafeR: panel LEDs and the Hik-Connect app agree. 4. Open a zone while armed: alarm in SafeR within 5 s, siren audible, "Acquitter" clears it. 5. Bypass a zone, arm, open it: no alarm. 6. Tamper and low battery events show on the zone. Record panel firmware. |
| **Dahua / IMOU / Amcrest** (`dahua.py`) | mock-verified | `magicBox`, `configManager` channel titles, snapshot, PTZ, coaxial light/siren, `eventManager.cgi?action=attach` stream parsing (split chunks, heartbeats, NVR channel index) with `httpx.MockTransport` (`test_dahua.py`). | Same steps as Hikvision cameras, plus: white light and siren toggles on a model that has them; IMOU/Amcrest OEM identifies correctly; 0/1-based channel numbering verified on an NVR (channel 2 snapshot is channel 2). |
| **Ajax Enterprise API** (`ajax.py`, `cloud_account`) | mock-verified | Login/refresh, hubs, devices, groups, arming commands, socket command, webhook callback (`test_ajax.py`). Access to the real API requires an Ajax-issued key. | 1. Enterprise API key and an Ajax account with a hub. 2. Pair: hub → `alarm_panel`, MotionProtect/DoorProtect/FireProtect/LeaksProtect → sensors, Socket → plug. 3. Arm / night mode / disarm from SafeR: Ajax app agrees (night mode for `armed_home` and `armed_night`). 4. Trigger a detector while armed: alarm in SafeR within 5 s. 5. Webhook: configure `POST /webhooks/ajax/{integration_id}?secret=`; an event arrives without polling. 6. Session expiry after 24 h: commands still work. |
| **Ajax SIA DC-09 receiver** (`services/sia_receiver.py`, `sia_receiver` method) | mock-verified | Frame codec (CRC-16/ARC, length, timestamp), SIA-DCS and ADM-CID event mapping, ACK/NAK/DUH answers, account-to-home binding (`test_sia.py`). | 1. `HUB_SIA_PORT=10001`, `HUB_SIA_ACCOUNTS=<acct>:<home>`; port reachable from the panel. 2. Ajax hub (or AX PRO) → monitoring station → SIA DC-09, plain mode, object number = account. 3. Panel sends a test event: hub logs ACK, no NAK. 4. Arm/disarm on the panel: SafeR mode follows (CL/OP). 5. Alarm (BA/FA/PA), tamper, AC loss, low battery: each reaches the message centre. 6. Keep-alive (NULL) frames every interval, no disconnect over 24 h. |
| **Matter** (`matter.py`, `matter_payload.py`) | **decode-verified only** | QR (`MT:`) and manual-code decoding with known vectors and random round trips; cluster-to-category classification; attribute mapping; command payloads; a fake python-matter-server WebSocket for pair, refresh, commands, attribute events and reconnect (`test_matter.py`). **No BLE/Thread/Wi-Fi commissioning is exercised.** | 1. python-matter-server next to the hub with host networking (mDNS + BLE), `MATTER_SERVER_URL` set. 2. A commissionable Wi-Fi device (new or factory-reset) within BLE range of the hub. 3. Scan its QR in SafeR, enter Wi-Fi credentials: commissioning completes within 4 minutes, device appears with the right category. 4. Toggle/dim from SafeR; physical toggle updates SafeR within 2 s (attribute event). 5. Manual code path with a second device. 6. Thread device through a border router (optional, record separately). 7. Multi-admin: open a commissioning window from the panel and add the device to a second controller. Only after step 4 passes may the badge read `hardware-verified`. |
| **ONVIF** (`onvif.py`) | mock-verified | SOAP envelopes with WS-UsernameToken, clock offset, `GetDeviceInformation`, `GetCapabilities`, profiles, stream and snapshot URIs, PTZ (`test_onvif.py`). No WS-Discovery, no event subscription (polled). | 1. ONVIF Profile S camera (Reolink, Uniview, Tapo…) with an ONVIF user. 2. Pair with `ip_credentials`: manufacturer/model/firmware correct. 3. RTSP main/sub play on the LAN; snapshot works. 4. PTZ on a PTZ model. 5. Camera clock 10 minutes off: pairing still succeeds (offset handling). 6. Wrong password: readable error. |

## 2. Contracts and platform-dependent features

| Row | Badge | What exists today | What flips it |
|---|---|---|---|
| **Push via relay** (`docs/contracts/relay.md` §3) | pending hardware/contract | Hub stores push tokens (`POST /auth/push-token`); no relay client, no FCM sender. | Relay deployed; an alarm raised on the hub reaches two physical Android phones (one Transsion) with the app in the background and with the app killed (public-notification variant), each within 10 s; `security.cleared` cancels the notification on both; evidence per `docs/qa/device-capture.md` §7. |
| **Widget data messages** (Android home-screen widget refresh through FCM data messages) | pending hardware/contract | Nothing. | Widget refreshes from a data message on a Transsion and a Xiaomi device with the app not running; otherwise the widget is documented as "refreshes on app open". |
| **Inbound SMS → incident** (`relay.md` §5) | pending hardware/contract | Nothing; the app's SMS feature is a composer labelled "Prévenir mes proches par SMS". | A short code or long number on each operator; `SOS <code>` from a real SIM creates an incident and the receipt SMS arrives within 60 s. |
| **OTP per operator — Orange** | pending hardware/contract | No OTP endpoint on the hub yet (Phase 4). | OTP SMS delivered to an Orange CI SIM within 30 s on three consecutive tries; WhatsApp OTP if the template is approved. |
| **OTP per operator — MTN** | pending hardware/contract | same | same on an MTN CI SIM |
| **OTP per operator — Moov** | pending hardware/contract | same | same on a Moov CI SIM |
| **SafeR CI incident callback** (`docs/contracts/incident-webhook.md`) | pending hardware/contract | Hub forwards SOS (`forward_sos`) and parses the incident id; no inbound status route yet. | Staging platform calls `POST /webhooks/incidents/{sos_id}` with a valid signature for `received`, `acknowledged`, `dispatched`, `closed`; the app's rail shows each within 5 s of the callback; `false_alarm` from the app reaches the platform. |
| **Tuya Pulsar** (message queue for real-time Tuya cloud events instead of polling) | pending hardware/contract | Not implemented; cloud devices are polled every `HUB_POLL_INTERVAL`. | Pulsar subscription enabled on the IoT project; a physical toggle reaches SafeR in under 3 s without polling. |
| **ONVIF WS-Discovery and events** | pending hardware/contract | Not implemented (manual IP, polled state). | Cameras on the LAN appear in the discovery step without typing an IP; motion events arrive through a PullPoint subscription on a real camera. |
| **Matter BLE commissioning** | pending hardware/contract | See the Matter row: decode and controller protocol only. | Step 3 of the Matter checklist on a real device next to the hub. |
| **SOS SMS/WhatsApp composer fallback** (app side) | pending hardware/contract | `<queries>` for `tel`, `sms`, `smsto`, `mailto`, `https` and `com.whatsapp` are in the manifest; the dialer works through `tel:`; no composer yet. | In airplane mode on a physical phone, SOS opens the prefilled SMS composer within 4 s and the WhatsApp deep link opens when installed; `tel:170` dials. |
| **Hub TLS for public hubs** (decision 0001 §7) | pending hardware/contract | App refuses `http://` to public hosts; Pi image has no TLS setup. | A Pi hub reachable by a public name over https (Caddy/Let's Encrypt) or self-signed with QR pinning, used by a release build. |

## 3. How to run a checklist session

1. Pick the row; the implementer prepares a short script from the checklist with the exact
   hub log lines to look for (`safer.hub.<brand>` loggers).
2. The tester runs the steps on the real equipment, pastes hub logs, app screenshots or a
   recording per `docs/qa/device-capture.md` §5, and says pass/fail per step.
3. The implementer records the outcome in the PR, edits the badge here with date, model and
   firmware, and tester name, and links the evidence files.
4. A badge is reset to `mock-verified` when the adapter's protocol code changes in a way the
   mocks cannot prove (new endpoint, new auth flow); the PR that does it says so in this table.

## 4. Where the badges are displayed

- Release notes: a "Compatibilité matérielle" section generated from §1 and §2.
- About screen (`/me/about`, "Marques compatibles"): each brand tile carries "Vérifié sur
  matériel" or "Non vérifié sur matériel" from the same table (Phase 5 copies this file's
  badges into an asset at build time; until then the About screen says nothing about
  verification).
- `docs/device-onboarding.md` per-brand headings get the badge inline when it changes.
