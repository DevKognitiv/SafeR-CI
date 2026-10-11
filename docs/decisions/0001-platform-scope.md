# 0001 — Platform scope and the Phase 0 product questions

```
Status: Proposed (decision request)
Decides: product owner
Date: 2026-10-11
```

This is a **decision request**. Every topic below ends with a `Decision: pending` line for the
product owner to replace. Until a line is filled in, implementers build the *recommended default*
and keep it behind a flag or a documented assumption so it can be reversed without a rebuild.

The eleven topics are the ones Phase 1 (design system and shell) and Phase 2 (hero screens, push,
SOS contract) cannot start without. Context, options and consequences are written against the
code on the Phase 0 foundations branch (2026-10-11): routes in `mobile/lib/core/routes.dart`, the Android
manifest and `res/xml/network_security_config.xml`, `mobile/lib/core/config.dart`,
`backend/app/hub/settings.py`, the hub `/health` contract (`docs/contracts/hub-health.md`), the
relay proposal (`docs/contracts/relay.md`) and the incident webhook proposal
(`docs/contracts/incident-webhook.md`).

---

## 1. iOS: go or no-go for release 1

**Context.** The Flutter project builds for Android, iOS and web, but only Android is exercised:
CI runs `flutter analyze`, `flutter test` and a web build (`.github/workflows/safer-hub-ci.yml`),
there is no macOS lane, no iOS golden, no VoiceOver checklist, and `ios/Runner/Info.plist` carries
usage strings for the camera, location-when-in-use and the local network only: nothing for the
photo library, contacts or Face ID, no background modes and no push entitlement. Push through
FCM on iOS needs APNs keys and, for alarm-grade notifications, the critical-alert entitlement
that Apple grants case by case. The reference devices are all Android (Tecno Spark Go 2 GB,
Infinix Smart 8, Galaxy A05, Redmi A3), which is where the users are.

**Options.**

- A. **Android first; iOS after the Phase 2 closed track.** iOS stays buildable but is not a
  deliverable until Home, Security, SOS and the alarm takeover have shipped to the Android
  closed track. Then a dedicated iOS lane is planned (macOS CI, iOS goldens, VoiceOver
  checklist, APNs via FCM, critical-alert request, Info.plist strings, Cupertino chrome where
  Material is wrong).
- B. **iOS in parallel from Phase 1.** Every screen is signed off on both platforms; every
  fan-out gets an iOS implementer; the Apple Developer account, APNs and TestFlight are set up
  in week 1.
- C. **No iOS for release 1 at all.** The iOS folder is left as is and documented as unsupported.

**Recommended default: A.** It keeps the design and QA effort on the devices users own and
avoids blocking Phase 1 on an Apple Developer account, while not throwing away the platform.

**Consequences of A.** No macOS CI lane in Phase 0 or 1; the state matrix, goldens and TalkBack
checklist are Android-only; `docs/qa/talkback.md` carries a VoiceOver section marked "if iOS is
go"; the About screen and store copy never mention iOS; the Apple Developer account is not
needed before Phase 2 closes. If B is chosen instead, add the iOS lane to the Phase 0 CI work
and an Apple Developer account to the week-1 inputs.

**Decision: pending**

---

## 2. Web build: non-shipping QA and screenshot proxy

**Context.** CI already builds the web target and the screenshots in `docs/screenshots/` come
from a release web build driven end to end. The Phase 0 critique loop (Playwright over the Demo
home) depends on that build. Nothing in the plan makes web a product: no web login story, no
deep links, no hub discovery, camera playback through `media_kit` is not available on web.

**Options.**

- A. **Web is a non-shipping QA proxy.** Built in CI, used by the Playwright capture job and by
  reviewers; never linked, never deployed to a public URL, `noindex` if it is ever hosted for
  convenience. Web captures are a critique instrument, never a sign-off.
- B. **Web gets its own definition of done** (responsive layout, keyboard navigation, no
  camera playback promise) and a hosted URL for members without a phone.

**Recommended default: A.**

**Consequences of A.** `docs/qa/screen-rubric.md` states that web captures never constitute
sign-off; the web build keeps `--dart-define=SAFER_DEMO=1` hooks for locale, theme, text scale
and forced states; no web-specific states enter `docs/qa/state-matrix.md`; store listing and
About never mention a web app.

**Decision: pending**

---

## 3. Portrait lock on phones

**Context.** `AndroidManifest.xml` declares `configChanges` including `orientation` and
`screenSize` but sets no `screenOrientation`; the app rotates freely. The 2-column device grid
and the SOS screen were designed portrait-only, the audits flagged the grid at tablet widths,
and every golden and screenshot variant is portrait.

**Options.**

- A. **Portrait locked on phones (smallest width < 600 dp), except camera fullscreen** which
  may rotate to landscape and restores portrait on exit.
- B. **Free rotation everywhere**, with a landscape golden variant for every route (doubles the
  golden set).

**Recommended default: A.**

**Consequences of A.** `SystemChrome.setPreferredOrientations` in `main.dart` gated on the
smallest width; the camera panel's fullscreen player opts out; `android:screenOrientation` stays
unset (the Flutter-side lock is enough and keeps tablets free); the state matrix has no
landscape column; a widget test asserts the lock call.

**Decision: pending**

---

## 4. Tablet and foldable support: one 600 dp variant only

**Context.** Nothing is tablet-specific today. The Me tab already supports several homes and
owners of a Galaxy Tab or a foldable will open the app; the 2-column grid stretches badly at
600 dp and above.

**Options.**

- A. **One 600 dp portrait variant** in goldens and Playwright captures for Home and Security
  only; the grid grows to 3 columns at 600 dp and 4 at 840 dp through the token layer; no
  tablet-specific navigation (no rail), no landscape work, no tablet store screenshots.
- B. **Full tablet layout** (navigation rail, master-detail for devices, landscape) with its own
  golden set and store listing.
- C. **Phones only** declared in the Play listing (`<supports-screens>` restrictions), tablets
  excluded.

**Recommended default: A.**

**Consequences of A.** `docs/qa/state-matrix.md` adds a 600 dp column only to Home and
Security; the golden job renders those two routes at 600×960; the store listing is phone-only
but tablets are not blocked from installing.

**Decision: pending**

---

## 5. minSdk: keep the Flutter default

**Context.** `mobile/android/app/build.gradle.kts` uses `flutter.minSdkVersion`, which is **24
(Android 7.0)** in the Flutter 3.47 toolchain used by CI. The plugins in `pubspec.yaml`
(`flutter_secure_storage`, `media_kit`, `mobile_scanner`, `geolocator`) all accept 24. The
reference device matrix spans Android 10 to 14, including Go editions.

**Options.**

- A. **Keep the Flutter default (24)**, tracked with the toolchain. Devices on Android 5 and 6
  are excluded.
- B. **Pin a lower level (21)** to reach the oldest second-hand phones; costs plugin
  compatibility work (secure storage and the video stack) and more Test Lab images.
- C. **Pin a higher level (26+)** to drop legacy notification code paths; excludes some
  Android 7/8 handsets still in circulation.

**Recommended default: A.**

**Consequences of A.** The Android 10/11 handset in the device matrix is the oldest tested
floor; Play's pre-launch report runs on API 24+ images only; the Data Safety and store
listing state "Android 7.0 or newer"; CI fails if a plugin bump silently raises the floor
(the AAB job records the manifest `minSdkVersion`).

**Decision: pending**

---

## 6. Hub remote-access model

**Context.** The app only talks to the hub (`AppConfig.apiPrefix = /api/v1/hub`). A hub on a
Raspberry Pi in a home is reachable on the LAN, not from outside, so today a member away from
home has no path to it: no push (the hub cannot hold a Firebase service account safely, see
`docs/contracts/relay.md`), no status, no alarm takeover. `HUB_ALLOW_OPEN_REGISTRATION`
defaults to true and `SAFER_INCIDENTS_URL` points at the SafeR CI platform, so hubs already
expect a cloud peer.

**Options.**

- A. **Cloud relay registration via `api.safer-ci.app`.** Each hub registers once with a
  registration key and from then on sends push and SMS requests through the relay (never
  holding provider secrets). Remote *control* of the hub stays out of scope for release 1; the
  relay carries notifications and, later, a reverse tunnel.
- B. **Explicit local-only mode.** No cloud component. The app shows what cannot work away
  from home (no push, no alarm takeover, SOS reaches the platform only while on the LAN).
- C. **Relay plus local-only fallback (recommended).** A hub with a registration key uses the
  relay; a hub without one runs in local-only mode and the app shows the limitations
  ("Notifications indisponibles : hub local") instead of failing silently. The owner can add a
  key later from `Moi › Intégrations`.

**Recommended default: C.**

**Consequences of C.** The relay contract (`docs/contracts/relay.md`) is implemented one
phase ahead with a dry-run mode in CI; `/health` exposes a `relay` flag (proposed addition,
not in the current contract) so the app can render the local-only limitation; the state matrix
gets an "offline-local" column distinct from "offline-cached"; `HUB_ALLOW_OPEN_REGISTRATION`
must default to false on any hub registered with the relay (separate question, see "Related
questions" below).

**Decision: pending**

---

## 7. LAN hub transport on Android

**Context.** Release and profile builds now ship `res/xml/network_security_config.xml`:
cleartext HTTP is off by default and allowed only to `localhost`, `127.0.0.1`, `10.0.2.2` and
`*.local` names. Android cannot express RFC 1918 ranges in a domain config, so a release build
**cannot reach `http://192.168.1.20:8000`**; it can reach `http://safer-hub.local:8000` or any
`https://` URL. Debug builds overlay the config and allow cleartext everywhere. The app-side
policy (`mobile/lib/core/hub_url_policy.dart`) accepts `http://` to private hosts and refuses
it to public hosts with "Connexion non sécurisée refusée : utilisez https".

**Options.**

- A. **`.local` mDNS names plus https (recommended).** Hubs advertise `safer-hub.local`
  (Avahi on the Pi image); release builds talk cleartext only to `*.local` and the loopback
  addresses; anything else must be https. Phase 4 ships mDNS and QR discovery so users never
  type an IP. Debug builds stay permissive.
- B. **Permit cleartext to raw private IPs** by adding each IP the user types to the config at
  runtime. Android does not support this; the only way is `usesCleartextTraffic="true"` for
  the whole app, which the audit rejected and Play's pre-launch report flags.
- C. **Https only, everywhere**, with a self-signed certificate per hub pinned through the
  pairing QR code. Strongest, but blocks any hub without the Pi image's TLS setup.

**Recommended default: A**, with C as the Phase 4 upgrade path for hubs exposed outside the
LAN (Caddy with Let's Encrypt when the hub has a public name, self-signed plus QR pinning
otherwise).

**Consequences of A.** Pi image enables Avahi with `safer-hub.local`; the hub-URL sheet
suggests `.local` names and explains why a raw IP will not work in a release build; the
onboarding docs (`docs/device-onboarding.md`, `docs/deployment.md`) say the same; a widget test
covers the rejection of `http://` to a public host; the Play reviewer cross-check expects no
cleartext warning.

**Decision: pending**

---

## 8. Emergency numbers to display

**Context.** `AppConfig.emergencyNumbers` shows four tiles on the SOS screen, dialled with a
`tel:` intent (`<queries>` for `tel`, `sms`, `smsto`, `mailto`, `https` and `com.whatsapp` are
in the manifest): **170 Police**, **180 Pompiers**, **185 SAMU**, **111 Gendarmerie**. The
planning inputs also mention 100 and the Plan Alerte Enlèvement WhatsApp line as optional.
These numbers are user-facing promises: a wrong or discontinued number on an SOS screen is a
safety defect.

**Options.**

- A. **Confirm the four as they are** (170, 180, 185, 111) with their current French labels.
- B. **Four plus optional extras** (100, a WhatsApp line) behind a "Plus" row, so the four
  primary tiles stay large and thumb-reachable.
- C. **Different set or different labels** (for example "Sapeurs-pompiers" instead of
  "Pompiers", or a regional number).

**Recommended default: A** for release 1, extras deferred until a source the product owner
trusts confirms them.

**Consequences.** The numbers and labels become a reviewed constant with a unit test that
fails when they change without a decision reference; the widget test asserts the exact
`tel:170`, `tel:180`, `tel:185`, `tel:111` URIs; store copy and the About screen list the same
numbers; the SOS screen keeps dialling them on the session-expired and forced-update screens.

**Decision: pending** (please confirm each number and label, and whether any extra is wanted)

---

## 9. Tuya consumer pairing licensing

**Context.** Today Tuya devices enter SafeR through `cloud_project` (Access ID / Secret of a
Tuya IoT Platform project, with the Smart Life account linked by QR) or `local_key`
(`docs/device-onboarding.md`). Pairing a brand-new device in EZ/AP Wi-Fi mode needs Tuya's
proprietary app SDK, which requires a commercial agreement; the current UI is honest about it
("Pair them once with Smart Life, then import them"). The consumer-first redesign hides Access
ID/Secret behind "Options avancées / Installateur".

**Options.**

- A. **Smart Life OAuth** (Tuya "Smart Life App Account" authorisation): the user logs into
  Smart Life from SafeR and the hub imports the devices; pairing new devices still happens in
  Smart Life. Needs a Tuya developer account with the OAuth product enabled and a review by
  Tuya.
- B. **Cloud project only (today's path)**, presented as an installer step; the consumer never
  sees it because the installer sets it up once per home.
- C. **Tuya Home SDK licence** for in-app EZ/AP pairing: full consumer experience, commercial
  agreement with Tuya, native SDK integration on Android (and iOS if go).

**Recommended default: B for release 1, A investigated for Phase 4** (the identity and pairing
phase), C only if the business case exists.

**Consequences of B.** The pairing wizard keeps the cloud-project form but moves it behind the
installer gate with plain-French guidance; the About screen states that new Tuya devices are
paired in Smart Life first; `docs/qa/hardware-status.md` keeps Tuya cloud "mock-verified" until
a real project is run through the checklist.

**Decision: pending**

---

## 10. Web-dashboard brand alignment

**Context.** `web-dashboard/tailwind.config.js` defines the current brand (`safer-blue #2563EB`,
`safer-red #DC2626`, `safer-orange #EA580C`, `safer-dark #0F172A`), and `mobile/lib/core/theme.dart`
uses the same hex values. The Calm Guardian direction moves the app to a linen canvas with teal
(armed), green (ready) and red reserved for alarm, SOS and destructive actions. Without a
decision, operators on the dashboard and users in the app will see two SafeR brands and two
vocabularies for the same incident.

**Options.**

- A. **Align in Phase 5**: Phase 1 exports the token sheet as CSS variables and a Tailwind
  preset plus a shared fr/en glossary (mode words, incident statuses); Phase 5 restyles the
  dashboard shell and shared vocabulary with that export.
- B. **Defer explicitly**: the dashboard keeps its brand; the export and glossary still ship so
  the restyle can happen later; release notes say the dashboard is unchanged.
- C. **Align before Phase 1**: block the app redesign on a dashboard redesign.

**Recommended default: A.**

**Consequences of A.** The Phase 1 design-system work includes `tokens.css` and a Tailwind
preset generated from the Flutter token file with a CI check that they stay in sync; the
glossary lives in `docs/` and is used by the app, the hub message keys and the dashboard; the
Phase 5 scope gains a dashboard item with its own sign-off.

**Decision: pending**

---

## 11. SafeR brand mark, and Manrope + Inter as the type pair

**Context.** The app shows a text/icon logo (`mobile/lib/features/me/widgets/safer_logo.dart`)
and uses the stock system font; the dashboard has no mark file either. The Calm Guardian
direction bundles **Manrope** (display, headings) and **Inter** (body, tabular figures for
values and times), both under the SIL Open Font Licence at no cost, and proposes a drafted
brand mark (SVG) plus placeholder illustrations until a designer delivers. Fonts count toward
the AAB size budget (the plan caps fonts at 450 KB with subsetting).

**Options.**

- A. **Approve Manrope + Inter and a drafted mark**; the drafted mark can be replaced by
  designer work at any time without touching layout, because the mark is a single SVG asset
  with a fixed box.
- B. **Supply brand assets** (SVG mark, colour values, type choice) before Phase 1; Phase 1
  waits for them.
- C. **Approve the type pair now, mark later**: Phase 1 ships with the current text logo in the
  reserved box.

**Recommended default: C**, so Phase 1 is not blocked on art, with A as soon as the product
owner is happy with a draft.

**Consequences.** Fonts are bundled (no runtime download) and subset to Latin plus the
characters French needs; the AAB job tracks the font bytes; a single `assets/brand/mark.svg`
slot is referenced from the splash, the login hero, About and the notification icon; the store
feature graphic is produced from the same file; the glyph/word pairing for every status colour
(teal armed, green ready, red alarm) uses Phosphor icons until bespoke glyphs exist.

**Decision: pending** (approve the type pair; approve a drafted mark or say when assets arrive)

---

## Related questions filed for later records

These came out of the same planning pass. They do not block Phase 1 and will get their own
numbered records when their phase starts, but an early answer helps:

- One-tap SOS as an explicit accessibility setting (default off): allowed or not.
- Play SMS stance: composer plus relay, never `SEND_SMS` (recommended).
- Premium/free boundary: all safety features free (recommended).
- Who signs off screens: the product owner, or device captures reviewed through the critique
  loop (`docs/qa/screen-rubric.md`).
- SOS and snapshot retention period on the hub (recommended 90 days).
- Whether `HUB_ALLOW_OPEN_REGISTRATION` may stay true on any publicly reachable hub
  (recommended: false on every hub registered with the relay).
