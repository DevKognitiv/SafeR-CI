# State matrix — the coverage contract for goldens

Every route in `mobile/lib/core/routes.dart` is listed here with every state it must render.
This file is the enumeration the golden job and the Playwright capture job are meant to read.
Today CI enforces the **committed** goldens only (`flutter test --tags golden test/goldens`,
Home in eight variants, see `golden-harness.md`); the matrix walker that fails CI for an
`exists` cell without a golden is a proposed job (§11). **A state marked `missing` is a
Phase 1/2 backlog item with its French copy decided here, not in the PR that implements it.**

Cells are written as of the Phase 0 foundations branch (2026-10-11):

- `exists` — the screen renders a dedicated state today. The name in parentheses is the
  switch on the test fake (`mobile/test/helpers/*_fake_client.dart`) or provider override that
  forces it. When no switch exists the parenthesis says how the test reaches it.
- `missing` — the state can happen but the screen has no dedicated rendering (raw error text,
  silent omission or a spinner). The parenthesis says what is shown today and which proposed
  switch (§4) will force it.
- `n/a` — the state cannot occur on that route.

Variants per state (definition of done): light/dark × fr/en × text scale 1.0/2.0, plus 1.3 for
Home, Security, Device detail and SOS, plus one 600 dp portrait variant and one greyscale
variant for Home and Security. Frame: 360×780 dp (and 412×915 in Playwright).

## 1. The states

| State | Definition | Expected French copy (en in the ARB) | Forced today by |
|---|---|---|---|
| loading | First fetch in flight, nothing cached. | spinner only; Phase 1 replaces with skeletons, never a spinner for more than 400 ms without a label | default fake before `settle()` |
| empty | Fetch succeeded with nothing to show (no home, no device, no scene, no message…). | route-specific, see tables | `noHomes`, `noScenes`, `noAutomations`, room filter |
| offline-local | **Mode local**: the hub answers on the LAN but the internet does not (no relay, weather, incident forwarding). | "Mode local — fonctions internet indisponibles" chip; weather hidden; SOS screen says the alert reaches the hub only | proposed `reachability: local` |
| offline-cached | **Hors ligne**: the hub is unreachable and a cached snapshot exists. | "Hors ligne — dernières données connues" banner + age chip per section ("Mis à jour il y a 4 min") | proposed `cachedSnapshot` + `failNetwork` |
| stale | Online, but a section's data is older than its freshness budget (devices 60 s, security 30 s, messages 5 min). | age chip "Mis à jour il y a 12 min" with a refresh affordance | proposed `freshnessAt` |
| error | A request failed (network, 5xx) with no cache. | "Impossible de charger les données" + reason + "Réessayer" | `failNetwork`, `failDevices`, `failWeather`, `failUnread`, `failSecurity`, `failScenes` |
| session expired | 401 after a previously valid session. | full-screen "Session expirée" / "Reconnectez-vous pour continuer." with the emergency numbers row and "Se reconnecter" | `authenticated: false` (today: raw "Not authenticated" or silent redirect); proposed `sessionExpired` |
| hub version mismatch | `/health` says the app is too old (`min_app_version`) or the hub is too old. | "Mise à jour requise" / "Hub à mettre à jour" (`docs/contracts/hub-health.md` §2) | proposed `healthOverride` |
| maintenance | Hub answers 503 on every call (upgrade in progress). | "Hub en maintenance" / "Réessayez dans quelques minutes." with a retry countdown | `failUnread` (503 on one call only); proposed `maintenance` |
| clock unsynced | `/health.clock_synced == false`. | "Horloge du hub non synchronisée" banner; relative ages hidden | proposed `healthOverride(clockSynced: false)` |
| permission denied | An OS permission is denied for good (location, camera, notifications) or the member's role forbids the action. | location: "Position non disponible : indiquez votre adresse aux secours."; camera: "Autorisez l'accès à la caméra dans les réglages pour scanner un code."; role: "Demandez à un administrateur…" | `FixedLocationService(null)`, `MobileScannerErrorCode.permissionDenied`, `role: 'member'` |
| no SIM / no WhatsApp | The dialer, SMS composer or WhatsApp cannot be launched. | "Impossible d'ouvrir le téléphone pour le 170"; composer: "Aucune application SMS" with the message to copy; WhatsApp: "WhatsApp n'est pas installé" | `phoneDialer` override; proposed fake `UrlLauncherPlatform` |
| data-saver interstitial | Cellular connection with data saver on and an HD stream requested. | "Flux HD sur données mobiles ?" / "Lire en SD" / "Lire en HD une fois" | proposed `connectivity: cellular` |
| alarm for a non-current home | `security.alarm` (WS or push) for a home that is not the selected one. | takeover "Alarme — Maison Cocody" naming the home, "Voir" switches home | proposed `alarmInHome(homeId)` with two homes |
| SOS raised by another member | `sos.raised` for the current home from another member. | banner "SOS déclenché par Bob" with "Voir" and "Appeler Bob" | `seededAlerts` (list only); proposed `sosByOther` |
| text scale 2.0 | Same content at `textScaler: 2.0` on a 360 dp frame. | no overflow, no clipped label, no ellipsis on a state word | `MediaQuery(textScaler: 2.0)` in the golden harness |

Two extra rows appear where they matter: **alarm active** (Home, Security) and **device
offline / device removed while open** (device panels).

## 2. Auth group — `/splash`, `/login`, `/register`, hub-URL sheet

| State | `/splash` | `/login` | `/register` | Hub-URL sheet (from login) |
|---|---|---|---|---|
| loading | exists (spinner over the brand; default) | exists (button spinner while `login()` awaits; pump before `settle`) | exists (same) | exists ("Tester la connexion" probe; `hubProbeProvider` override) |
| empty | n/a | n/a | n/a | n/a |
| offline-local | n/a | n/a | n/a | n/a |
| offline-cached | missing (cold start must render the cached Home; today splash waits on `/auth/me` then falls to login) | n/a | n/a | n/a |
| stale | n/a | n/a | n/a | n/a |
| error | exists (`failNetwork` → login with "Impossible de joindre le hub") | exists (`failNetwork`; wrong password shows the hub text "Invalid e-mail or password" verbatim, copy fix pending: "E-mail ou mot de passe incorrect") | exists (`taken@safer.ci` → "E-mail already registered" verbatim, copy pending) | exists (probe false → "Hub injoignable"; public `http://` → validator message "Utilisez https:// pour un hub public (http uniquement sur le réseau local)"; "Connexion non sécurisée refusée : utilisez https" is the `HubClient` refusal when a request would carry a secret anyway) |
| session expired | missing (silent redirect; `authenticated: false`) | missing ("Session expirée" explanation on arrival) | n/a | n/a |
| hub version mismatch | missing (`healthOverride`) | missing | missing | missing (show `hub_version` after a probe) |
| maintenance | missing | missing | missing | missing |
| clock unsynced | n/a | n/a | n/a | n/a |
| permission denied | n/a | n/a | n/a | n/a |
| no SIM / no WhatsApp | n/a | n/a | n/a | n/a |
| data-saver interstitial | n/a | n/a | n/a | n/a |
| alarm for a non-current home | n/a | n/a | n/a | n/a |
| SOS raised by another member | n/a | n/a | n/a | n/a |
| text scale 2.0 | missing (no golden) | missing (hero + form at 360 dp unverified) | missing | missing |
| 429 / 423 throttled | n/a | missing (`rate_limited` countdown, `account_locked` message; `docs/contracts/hub-health.md` §5) | missing | n/a |
| registration closed (403) | n/a | missing (hide "Créer un compte" from `flags.open_registration`) | missing ("Inscriptions fermées sur ce hub") | n/a |

## 3. Home group — `/`, `/rooms`, home switcher sheet, device actions sheet

| State | `/` (Accueil) | `/rooms` (Gestion des pièces) | Home switcher sheet | Device actions sheet (long press) |
|---|---|---|---|---|
| loading | exists (default before `settle`) | exists | exists | n/a |
| empty | exists: no home (`noHomes` → "Créez votre première maison"); no device in room (select an empty room, proposed `noDevices` → "Aucun appareil dans cette pièce"); member view ("Demandez à un administrateur d'ajouter des appareils", `role: 'member'`) | exists ("Aucune pièce") | exists (`noHomes`) | n/a |
| offline-local | missing (today: WS-down banner "Hors ligne — reconnexion au hub…" when `realtimeEnabledProvider` is on; weather degrades with `weatherAvailable: false`) | missing | n/a | missing (sheet should say which actions still work) |
| offline-cached | missing (no cache: `failNetwork` gives the error view; `cachedSnapshot`) | missing | missing | missing |
| stale | missing (`freshnessAt`) | n/a | n/a | n/a |
| error | exists (`failDevices` → "Impossible de charger les données"; `failWeather` hides the header; `failUnread` hides the badge) | missing (errors are snackbars only) | exists (`failNetwork`) | exists (command failure → snackbar; no inline retry) |
| session expired | missing (`authenticated: false` → raw "Not authenticated") | missing | missing | missing |
| hub version mismatch | missing | missing | n/a | n/a |
| maintenance | missing | missing | missing | n/a |
| clock unsynced | missing (no ages shown today, so nothing to hide yet) | n/a | n/a | n/a |
| permission denied | exists for role (`role: 'member'` hides "+ Ajouter"); OS permissions n/a | exists (`role: 'member'` → read-only list) | n/a | exists (`role: 'member'` hides "Supprimer") |
| no SIM / no WhatsApp | n/a (Phase 2 SOS pill: see SOS group) | n/a | n/a | n/a |
| data-saver interstitial | n/a (tiles never stream) | n/a | n/a | n/a |
| alarm for a non-current home | missing (`AlarmBanner` only for the selected home; `alarmInHome`) | n/a | missing (badge on the other home) | n/a |
| SOS raised by another member | missing (`sosByOther`) | n/a | n/a | n/a |
| text scale 2.0 | missing (grid uses a fixed `mainAxisExtent`, known overflow) | missing | missing | missing |
| alarm active (current home) | exists (`alarmActive` → `AlarmBanner` "Alarme" + tap to Security) | n/a | n/a | n/a |

## 4. Scenes group — `/scenes`, `/scenes/new`, `/scenes/:id`, `/scenes/automations/new`, `/scenes/automations/:id`

| State | `/scenes` (Scènes + Automatisations tabs) | Scene editor (`new`, `:id`) | Automation editor (`new`, `:id`) |
|---|---|---|---|
| loading | exists (default) | exists (list load; `_busy` on save) | exists |
| empty | exists (`noScenes`, `noAutomations` → "Aucune scène" / "Aucune automatisation"; `noHomes` → `NoHomeView`) | exists (no action yet → "Ajoutez une action") | exists (no trigger yet) |
| offline-local | missing | missing (save still works, local hub) | missing |
| offline-cached | missing (`cachedSnapshot`; scene runs must queue 60 s with "Sera exécutée") | missing (editing refused with explanation) | missing |
| stale | missing | n/a | n/a |
| error | exists (`failScenes` 500, `failNetwork`; `failDevices` in the device picker) | exists (`ErrorView` on list; save failure → snackbar) | exists |
| session expired | missing | missing | missing |
| hub version mismatch | missing | missing | missing |
| maintenance | missing | missing | missing |
| clock unsynced | n/a (no ages) | n/a | n/a |
| permission denied | exists for role (`role: 'member'` → run only, no edit affordances) | exists (`role: 'member'` → read-only) | exists |
| no SIM / no WhatsApp | n/a | n/a | n/a |
| data-saver interstitial | n/a | n/a | n/a |
| alarm for a non-current home | missing (takeover is global) | missing | missing |
| SOS raised by another member | missing | missing | missing |
| text scale 2.0 | missing (scene cards with icon + name) | missing | missing |

## 5. Security group — `/security`

| State | `/security` (Sécurité) |
|---|---|
| loading | exists (`LoadingView` while `securityProvider` loads) |
| empty | exists: no home (`noHomes` → "Créez votre première maison"); no panel ("Aucune centrale d'alarme" + Ajouter); no zone ("Aucune zone configurée"); no sensor ("Aucun capteur ni serrure"); no history ("Aucune alarme récente") — reached by removing the demo devices from the fake |
| offline-local | missing (arming must say "Mode local : l'alarme reste locale, pas de notification à distance") |
| offline-cached | missing (`cachedSnapshot`: last mode with age, controls disabled with "Mode, serrure et sirène ne peuvent pas être modifiés hors ligne") |
| stale | missing (`changedAt` is 12 min in the fake; today shown without a freshness rule) |
| error | exists (`failSecurity` → full error; `failDevices` 500; history error → "Historique indisponible" + Réessayer via `failUnread`-style message failure) |
| session expired | missing |
| hub version mismatch | missing |
| maintenance | missing |
| clock unsynced | missing (mode "depuis 12 min" must hide; `healthOverride(clockSynced: false)`) |
| permission denied | n/a for role today (any member may arm, hub rule); Phase 2 guest role: missing |
| no SIM / no WhatsApp | n/a (numbers live on the SOS route) |
| data-saver interstitial | n/a |
| alarm for a non-current home | missing (`alarmInHome`) |
| SOS raised by another member | missing (`seededAlerts` lists alerts; no banner naming the member; `sosByOther`) |
| text scale 2.0 | missing (arm-mode selector with four tiles) |
| alarm active (current home) | exists (`alarmActive` + `alarmDeviceId` → `SecurityAlarmBanner` with the blamed device and "Acquitter") |
| openings before arming | exists (`openIds` → "Ouvertures détectées… armer quand même ?") |

## 6. SOS group — `/security/sos`

| State | `/security/sos` |
|---|---|
| loading | exists (phases `locating` "Localisation...", `sending` "Envoi de l'alerte..."; alerts list spinner) |
| empty | exists ("Aucune alerte récente" / "Vos alertes SOS apparaîtront ici."; `noHomes` → "Créez votre première maison") |
| offline-local | missing (must say the alert reached the hub but not SafeR CI: today only after the fact via `sosForwarded: false` → "Le hub a déclenché l'alarme mais n'est pas relié aux secours : appelez un numéro d'urgence ci-dessous.") |
| offline-cached | missing (hub unreachable → the SMS/WhatsApp composer "Prévenir mes proches" must open within 4 s; today `failNetwork` → "Échec de l'envoi, réessayez") |
| stale | n/a |
| error | exists (`failNetwork` → phase `failed` "Échec de l'envoi, réessayez"; alerts `ErrorView`) |
| session expired | missing (numbers must stay dialable on that screen) |
| hub version mismatch | missing (same rule) |
| maintenance | missing |
| clock unsynced | missing (alert times are relative) |
| permission denied | exists (location denied → "Position non disponible : indiquez votre adresse aux secours." via `FixedLocationService(null)`); `422 position_required` handling: exists (`requireAddress` → "Position inconnue : indiquez une adresse ou un repère", address field + "Les secours iront à cette adresse" confirmation, resend with `address_confirmed`) |
| no SIM / no WhatsApp | exists for the dialer failure ("Impossible d'ouvrir le téléphone pour le 170", `phoneDialer` override); composer/WhatsApp: missing |
| data-saver interstitial | n/a |
| alarm for a non-current home | n/a |
| SOS raised by another member | missing (`seededAlerts` shows the row; no "déclenché par Bob" treatment; `sosByOther`) |
| text scale 2.0 | missing (200 dp button + status + numbers row) |
| sent phases | exists (`sent`: "Alerte enregistrée sur le hub" / "Alerte transmise aux secours" via `sosForwarded`; the emoji check-mark prefixes are removed by the no-emoji rule) |
| hold-to-send / cancel window | missing (single tap today; Phase 2: hold 2 s, 5 s cancel, "Envoyer maintenant") |
| status rail beyond "Transmise" | missing by contract (`docs/contracts/incident-webhook.md`) |

## 7. Me group — `/me`, `/me/profile`, `/me/homes`, `/me/homes/:id/members`, `/me/messages`, `/me/settings`, `/me/about`, `/me/integrations`

| State | `/me` | `/me/profile` | `/me/homes` | `…/members` | `/me/messages` | `/me/settings` | `/me/about` | `/me/integrations` |
|---|---|---|---|---|---|---|---|---|
| loading | missing (renders with empty data, no spinner) | n/a (form) | exists | exists | exists | n/a | exists (brands row) | exists |
| empty | exists ("Aucune maison" card, `noHomes`) | n/a | exists (`noHomes` → "Créez votre première maison") | exists ("Aucun membre") | exists ("Aucun message") | n/a | exists ("Aucune marque disponible sur ce hub.") | exists (`NoHomeView`; "Aucune intégration") |
| offline-local | missing (relay status row "Relais SafeR : non connecté") | n/a | missing | missing | missing | missing (hub row should show reachability) | n/a | missing |
| offline-cached | missing (Messages must render from cache with ages) | n/a | missing | missing | missing (`cachedSnapshot`) | n/a | n/a | missing |
| stale | n/a | n/a | n/a | n/a | missing (`freshnessAt`) | n/a | n/a | n/a |
| error | missing (unread badge silently 0 on `failUnread`) | exists (save failure → snackbar) | exists (`failNetwork`) | exists (`failNetwork`; `nobody@safer.ci` → "User not found" verbatim) | exists (`failNetwork`) | n/a | exists (brands retry) | exists (`failNetwork`) |
| session expired | missing | missing | missing | missing | missing | missing | missing | missing |
| hub version mismatch | missing (About must show hub version and min versions) | n/a | missing | missing | missing | missing | missing (`healthOverride`) | missing |
| maintenance | missing | missing | missing | missing | missing | missing | missing | missing |
| clock unsynced | n/a | n/a | n/a | missing (joined "il y a…") | missing (message ages) | n/a | missing (show "Horloge non synchronisée" row) | missing (created "il y a 3 j") |
| permission denied | n/a | n/a | exists (`role: 'member'` hides Modifier/Supprimer) | exists (`role`, `isOwner`: who can change roles, remove, leave) | n/a | n/a | n/a | exists (`role: 'member'` → read-only) |
| no SIM / no WhatsApp | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| data-saver interstitial | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| alarm for a non-current home | missing (home list should badge "Alarme" on the other home) | n/a | missing | n/a | n/a | n/a | n/a | n/a |
| SOS raised by another member | missing | n/a | n/a | n/a | missing (message row exists; no treatment) | n/a | n/a | n/a |
| text scale 2.0 | missing (quick-action grid) | missing | missing | missing | missing | missing | missing | missing |

## 8. Add-device group — `/add-device`, `/add-device/scan`, `/add-device/:brand[?method=]`

| State | `/add-device` (catalogue) | `/add-device/scan` | Wizard: method + form | Wizard: discovery | Wizard: pairing + success |
|---|---|---|---|---|---|
| loading | exists (brands and categories `LoadingView`) | exists (camera start) | exists (`pairingBrandProvider`) | exists ("Recherche des appareils...") | exists (`PairingProgress`) |
| empty | exists ("Aucune marque" when `brands()` is empty) | n/a | exists (no method → `EmptyState`) | exists ("Aucun appareil trouvé" with Modifier/Réessayer) | n/a |
| offline-local | missing (cloud methods must warn "Internet requis pour Tuya Cloud / Ajax", LAN methods keep working) | n/a | missing | missing | missing |
| offline-cached | missing (catalogue from cache, pairing disabled with explanation) | n/a | missing | n/a | n/a |
| stale | n/a | n/a | n/a | n/a | n/a |
| error | exists (`failNetwork` → `ErrorView` with retry) | exists ("Code non reconnu" snackbar; "Caméra indisponible.") | exists (`ErrorView` on brand load) | exists (`PairingErrorCard` with Réessayer / Modifier) | exists (`host: 10.0.0.99` → 502 `unreachable` → `PairingErrorCard` "Connexion impossible") |
| session expired | missing | missing | missing | missing | missing |
| hub version mismatch | missing | n/a | missing | missing | missing |
| maintenance | missing | n/a | missing | missing | missing |
| clock unsynced | n/a | n/a | n/a | n/a | n/a |
| permission denied | exists (`role: 'member'` → `AdminOnlyView`) | exists (camera denied → "Autorisez l'accès à la caméra dans les réglages pour scanner un code." + "Saisir le code manuellement") | exists (`AdminOnlyView`) | n/a | n/a |
| no SIM / no WhatsApp | n/a | n/a | n/a | n/a | n/a |
| data-saver interstitial | n/a | n/a | n/a | n/a | n/a |
| alarm for a non-current home | missing (takeover is global) | missing | missing | missing | missing |
| SOS raised by another member | missing | missing | missing | missing | missing |
| text scale 2.0 | missing (brand cards 3 per row) | missing (overlay text) | missing (dynamic form) | missing | missing |

## 9. Device panels — `/devices/:id` by category, and `/devices/:id/settings`

Resolved by `DeviceResolver` (home → device list → device). Columns are the panel widgets in
`mobile/lib/features/device/panels/`.

| State | light | switch / plug | cover | thermostat | sensors (contact, motion, smoke, water, gas, temp/hum, multi) | camera / NVR / doorbell | lock | alarm panel (+ zones) | gateway | generic | `/devices/:id/settings` |
|---|---|---|---|---|---|---|---|---|---|---|---|
| loading | exists | exists | exists | exists | exists | exists (+ player opening) | exists | exists | exists (children list) | exists | exists |
| empty | n/a | n/a | n/a | n/a | n/a (readings hidden when absent) | exists ("Aucun canal" on NVR) | n/a | exists ("Aucune zone") | exists ("Aucun appareil connecté") | exists (no writable capability → read-only rows) | n/a |
| offline-local | missing | missing | missing | missing | missing | missing (LAN RTSP still works in local mode; cloud cameras do not) | missing | missing | missing | missing | missing |
| offline-cached | missing (toggle queues 60 s: "Sera envoyé à la reconnexion") | missing (same) | missing (position queues) | missing (setpoint queues) | missing (last reading + age) | missing (cached still + age; no live) | missing (refused: "Impossible hors ligne") | missing (mode refused with explanation; bypass refused) | missing | missing | missing (rename refused) |
| stale | missing (`freshnessAt`) | missing | missing | missing | missing ("Mis à jour il y a…" shown today only from `lastSeenAt`, no freshness rule) | missing | missing | missing | missing | missing | n/a |
| error | exists (`failNetwork`; unknown id → 404 `ErrorView`; command failure → snackbar) | exists | exists | exists | exists | exists (`StreamPlayer` failure → "Lecture vidéo indisponible"; snapshot "Image illisible") | exists | exists | exists | exists | exists (snackbar) |
| session expired | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| hub version mismatch | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| maintenance | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| clock unsynced | n/a | n/a | n/a | n/a | missing ("Mis à jour il y a…" must hide) | missing (event list times) | missing (history times) | missing (history) | n/a | n/a | n/a |
| permission denied | n/a (members control) | n/a | n/a | n/a | n/a | missing (guest role: no PTZ/siren) | missing (guest: no unlock) | missing (guest: no bypass) | n/a | n/a | exists (`role: 'member'` → read-only rows; no Supprimer) |
| no SIM / no WhatsApp | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| data-saver interstitial | n/a | n/a | n/a | n/a | n/a | missing (HD on cellular needs a tap; `connectivity: cellular`) | n/a | n/a | n/a | n/a | n/a |
| alarm for a non-current home | missing (global takeover) | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| SOS raised by another member | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing | missing |
| text scale 2.0 | missing (big power button + sliders) | missing | missing | missing | missing (state words "OUVERT"/"FERMÉ" are ALL-CAPS today, to be sentence-cased) | missing (chips "MOUVEMENT"/"CALME" ALL-CAPS today) | missing ("VERROUILLÉE"/"OUVERTE" ALL-CAPS today) | missing ("ALARME DÉCLENCHÉE" ALL-CAPS today) | missing | missing | missing |
| device offline | exists (`offlineIds` → `DeviceOfflineBanner` "Appareil hors ligne" + "Dernière activité…" + Actualiser; "Appareil toujours hors ligne" after refresh) | exists | exists | exists | exists | exists | exists | exists | exists | exists | exists (online chip "EN LIGNE"/"HORS LIGNE", ALL-CAPS today) |
| device removed while open | missing (`deleteDevice` from another client → 404 on refresh; must show "Appareil supprimé" and pop) | missing | missing | missing | missing | missing | missing | missing | missing | missing | exists for own delete ("Appareil supprimé" then pop) |
| protected stream (no credentials) | n/a | n/a | n/a | n/a | n/a | exists (`protectedStreams: true` → "Flux protégé : la lecture directe est désactivée…" overlay, key `stream-protected`, over the hub snapshot) | n/a | n/a | n/a | n/a | n/a |

## 10. Switches to add to the fakes (Phase 0 Lane A backlog)

The golden harness needs every `missing` cell to become forceable. Proposed switches, to be
added to `FakeHubClient` (shared) unless noted:

| Switch | Forces | Notes |
|---|---|---|
| `healthOverride: HealthInfo(...)` | hub version mismatch, clock unsynced, every flag | `HealthInfo` is the app-side model of `docs/contracts/hub-health.md`; replaces the `bool` returned by `health()` today |
| `sessionExpired: true` | 401 on every authenticated call after the first success | distinct from `authenticated: false` (never logged in) |
| `maintenance: true` | 503 on every call with `Retry-After` | |
| `reachability: HubReachability.local \| online \| offline` | offline-local, offline-cached | provider override once `HubReachability` exists |
| `cachedSnapshot: Snapshot(...)` | offline-cached, stale | written into the Hive box before `pumpApp` |
| `freshnessAt: DateTime` | stale | |
| `noDevices: true` | Home empty (devices) | |
| `alarmInHome: 'home-2'` | alarm for a non-current home | needs a second home in the shared fake |
| `sosByOther: SosAlert(userId: 'user-2')` | SOS raised by another member | emits `sos.raised` on the fake socket |
| `deviceRemoved: 'dev-light'` | device removed while open | emits `device.removed` then 404s |
| `throttled: (status: 429 \| 423, retryAfter: 42)` | auth throttling | |
| `connectivity: cellular` | data-saver interstitial | `connectivity_plus` fake |
| fake `UrlLauncherPlatform` | no SIM / no WhatsApp | asserts exact `tel:170`, `sms:` and WhatsApp URIs |

## 11. Reading this file from CI

Today (Phase 0): the `mobile` job runs the committed goldens
(`mobile/test/goldens/<screen>/<theme>_<locale>_<scale>.png`, `golden-harness.md` §4) and the
`mobile-screenshots` job captures the ten reference screens in their default state from
`mobile/tool/screenshots/routes.json` into
`mobile/tool/screenshots/out/<screen>/<theme>-<locale>-<scale>-<w>x<h>.png` as a CI artifact
(`screenshot-harness.md`).

Proposed (Phase 1, with the first screen PRs): a matrix walker that reads sections 2–9, builds
the Cartesian product of `exists` cells × variants, fails when a golden is absent for one of
them, and fails for a new route in `routes.dart` without a section here or for a cell flipped
from `missing` to `exists` without its goldens. The capture job then takes its state list from
the same sections through the `state=` hook instead of `routes.json`.
