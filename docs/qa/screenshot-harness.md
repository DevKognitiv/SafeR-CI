# Screenshot harness — the critique instrument

Phase 0 quality gate. The SafeR app can be built in **demo mode**
(`--dart-define=SAFER_DEMO=1`): it boots on an in-memory hub with a signed-in session, and
the web build reads capture hooks from the page URL. A Playwright script
(`mobile/tool/screenshots/capture.mjs`) opens every reference screen in every variant,
masks what moves, and writes PNGs that the reviewer agents of the critique loop read and
score against `docs/qa/screen-rubric.md`. This file explains what the captures are for,
how to run the harness, the hooks and the forced states (the contract with the app), the
masks, the baseline, and what a web capture can and cannot tell you.

## 1. Purpose: a critique instrument, not final verification

The captures exist so that an agent (or a person) can **look at** a screen in 16+ variants
in a minute, find what is wrong and write a finding with a path. They are the input of the
screen rubric and of the colour-vision step. They are not pixel truth (that is the golden
harness, `docs/qa/golden-harness.md`) and they are not device evidence (that is
`docs/qa/device-capture.md`): the sign-off rule in `screen-rubric.md` §5 requires a human
approval or an Android capture of the same commit on top of the critique scores. §6 lists
what differs between these captures and a phone.

## 2. How to run

```sh
cd mobile
flutter build web --release --dart-define=SAFER_DEMO=1 --no-web-resources-cdn
node tool/screenshots/capture.mjs                      # 162 PNGs -> mobile/tool/screenshots/out/
node tool/screenshots/capture.mjs --only=home,security # subset
node tool/screenshots/capture.mjs --build              # build + capture
node tool/screenshots/capture.mjs --serve-only         # serve the build on :8089 for a manual look
node tool/screenshots/capture.mjs --check              # verify out/manifest.json covers the matrix
```

- Node 22 and Playwright 1.56 with its Chromium (`npx playwright@1.56.1 install --with-deps
  chromium`). The script has no other dependency and installs nothing; `playwright` must be
  resolvable by `require` (`NODE_PATH`, or `npm i --no-save playwright@1.56.1` in
  `mobile/tool/screenshots/`).
- The build self-hosts CanvasKit (`--no-web-resources-cdn`) and the harness serves the
  engine's fallback Roboto from the Flutter SDK cache instead of `fonts.gstatic.com`
  (every other Google Fonts request is aborted), so a run needs no outbound network. Set
  `FLUTTER_ROOT` or pass `--fonts-dir` when the SDK is not at `/opt/flutter` or on `PATH`.
- Output: `mobile/tool/screenshots/out/<screen>/<theme>-<locale>-<scale>-<w>x<h>.png` and
  `out/manifest.json` (route, states, variant, viewport, path, sha256, bytes, masks,
  console errors, font requests, first app error). Both are git-ignored; CI uploads the
  folder as the `mobile-screenshots` artifact for 14 days. The script exits non-zero when
  any variant of the matrix is missing or failed, so an incomplete capture fails the job. A
  partial run (`--only`, a narrowed matrix) merges into the existing manifest, so one
  screen can be re-captured after a mask change without losing the rest.
- Variants are captured two at a time (`--parallel`), each in a fresh browser context
  (Android user agent, touch, DPR 2, `prefers-color-scheme` set to the theme, reduced
  motion, `Africa/Abidjan`). The first full run on this branch (Chromium 141, four shared
  cores) captured 162/162 variants in 319 s with no app error and no console error; the
  demo web build itself took 86 s to compile.

The same demo mode drives the Firebase Test Lab robo smoke run (`flutter build apk --debug
--dart-define=SAFER_DEMO=1`): on Android the hooks keep their defaults (French, light,
Home, no forced state) because there is no query string to read.

## 3. The hooks and the states (contract with the app)

Read once at startup from `Uri.base.queryParameters`, on the web build only, only when
`SAFER_DEMO=1`; without the define `kDemoMode` is a compile-time `false` and the demo code
is dropped from the binary (`mobile/lib/core/demo/`).

| Query parameter | Values | Default | Implemented by |
|---|---|---|---|
| `locale` | `fr`, `en` | `fr` | `localeProvider` override (`DemoLocaleNotifier`) |
| `theme` | `light`, `dark` | `light` (never "system") | `themeModeProvider` override |
| `textScale` | `1.0`, `1.3`, `2.0` (0.5–3.0 accepted) | `1.0` | `MaterialApp.builder` → `MediaQuery(textScaler: TextScaler.linear(…))` above the navigator |
| `route` | an app location, e.g. `/security/sos`, `/devices/dev-cam`, `/scenes?tab=automations` | `/` | `DemoFrame` calls `GoRouter.go` once the session is restored and the splash redirect applied; the auth redirect still wins (`/` while `loggedOut` lands on `/login`) |
| `state` | comma list of the names below | none | `DemoHubClient.fromStates` + provider overrides |
| `animations` | `off` | on | `MediaQuery(disableAnimations: true)` plus `timeDilation = 0.05` |

Readiness: two frames after the requested route has painted the app sets
`window.saferReady = true` (`dart:js_interop` behind a conditional import, no-op elsewhere);
the first uncaught Flutter error is exposed as `window.saferError` and fails the variant.
The harness then waits `--settle` ms (1500 by default) so the demo hub's microtask answers
and the first layout pass are on screen.

Session: the demo signs in as Alice Kouassi (owner of "Maison Cocody", the data of
`FakeHubClient`, which moved from the test helpers to `mobile/lib/core/demo/` and is
re-exported for the widget tests unchanged). Token and current home live in memory only;
nothing is written to the device, and a logout in the demo is a logout for that run.
Platform services are replaced by inert stand-ins so no permission prompt or external app
can interrupt a capture: location (fixed Cocody point, or none with `locationDenied`),
dialer and link opener (report success, open nothing), QR scanner (a dark frame with a
"Simuler un code Matter" button), camera surface (a drawn scene, no network image, no
player). The realtime socket is off (`realtimeEnabledProvider` → false) and the hub probe
answers from the fake.

`state` names (`DemoState`, `mobile/lib/core/demo/demo_options.dart`); unknown names are
ignored and logged:

| State | What the fake does | Matrix row it forces |
|---|---|---|
| `loggedOut` | no token: the router lands on `/login` | auth group |
| `offline` | every call fails "Impossible de joindre le hub" (`failNetwork`) | error |
| `noHomes` | `GET /homes` → `[]` | empty (no home) |
| `noDevices` | `GET /homes/{id}/devices` → `[]` | empty (no device) |
| `noWeather` | weather `available: false` | weather fallback |
| `member` | role `member` (no add/edit affordances) | permission denied (role) |
| `armedAway` / `armedHome` / `armedNight` | security mode | armed states |
| `alarm` | `alarm_active` with `dev-pir` blamed (mode armed away unless another armed state is given) | alarm active |
| `openings` | `dev-door` contact open and `dev-zone` open | openings before arming |
| `offlineDevices` | `dev-light` and `dev-cam` offline; commands to them fail 409 | device offline |
| `noScenes` / `noAutomations` | empty lists | empty |
| `noMessages` | no message, no unread badge | empty |
| `protectedStreams` | `auth_required` without credentials: snapshot-only overlay | protected stream |
| `sosAlerts` | two alerts listed (one open and forwarded, one resolved) | alerts list |
| `locationDenied` | SOS alerts carry no position | permission denied (location) |
| `failDevices` / `failWeather` / `failSecurity` / `failScenes` / `failUnread` | the matching request fails (network, 502, network, 500, 503) | error |

Demo ids used by routes: light `dev-light`, camera `dev-cam`, motion sensor `dev-pir`,
door `dev-door`, zone `dev-zone`, home `home-1`, user `user-1`.

## 4. Screens, variants and masks

`mobile/tool/screenshots/routes.json` lists the ten reference screens of
`docs/screenshots/`: login (`/login`, `loggedOut`), home (`/`), security (`/security`), sos
(`/security/sos`), scenes (`/scenes`), me (`/me`), add-device (`/add-device`), pair-tuya
(`/add-device/tuya`), device-light (`/devices/dev-light`), device-camera
(`/devices/dev-cam`).

Matrix per screen: {light, dark} × {fr, en} × text scale {1.0, 2.0} × viewport {360×780,
412×915} CSS px at device scale factor 2 (PNGs are 720×1560 and 824×1830), plus a 600×960
tablet variant (light/fr/1.0) for home and security. 10 × 16 + 2 = **162** PNGs.
`--states=a,b` appends forced states to every screen for a state sweep (for example
`--only=home,security --states=alarm`).

Masks (`masks.json`) are named rectangles in CSS px, painted as opaque grey `div`s over the
page before the shot, with optional filters per screen, scale, viewport, theme or locale:

| Mask | Screens | Why |
|---|---|---|
| `sos-button` | sos | The SOS button pulses continuously (two rings every 1.8 s); the ring area differs between shots. Two rectangles, one per text scale, because the home line above it wraps at 2.0. |
| `auth-logo` | login | The brand mark is a Phase 1 asset; reviewers score the layout, not the placeholder glyph. |

Nothing else on the ten screens depends on the clock: the demo hub creates its "il y a 5
min" timestamps relative to boot, so relative ages are stable from run to run. Add a mask
rather than a sleep when a new screen shows a clock, a spinner or a live value.

Colour-vision step: `python3 mobile/tool/screenshots/simulate_cvd.py --all
mobile/tool/screenshots/out/security` writes `.deutan.png` and `.protan.png` next to each
capture (Machado, Oliveira and Fernandes 2009 dichromat matrices, the ones browser DevTools
use, applied in linear RGB; Pillow required, numpy optional: without it the matrix is applied
in gamma space, which is an approximation).

## 5. Baseline

`docs/qa/baseline/` holds the first captures of the Phase 0 foundations branch (360×780,
downscaled to 1× for size) so later reviews can be compared against where the app started;
its README lists the files and the commit context. Full-size captures are not committed:
CI regenerates them on every push.

## 6. Limits: web is not Android

- **Rendering**: CanvasKit in Chromium, not Skia/Impeller on a phone. Anti-aliasing,
  shadows and sub-pixel text differ; the fonts are the engine's Roboto until Phase 1 wires
  the bundled Manrope/Inter into the theme. Do not score typography pixel details here.
- **No native chrome**: no status bar, no navigation bar, no gesture inset, no display
  cutout. A 360×780 CSS viewport is a 360×780 dp app area; on a phone the usable height is
  smaller.
- **No haptics, no native splash, no OEM font scaling**: Transsion and Xiaomi font and
  display-size settings, bold-text accessibility, and the Android 12 splash are only
  visible on a device (`docs/qa/device-capture.md`).
- **Demo data**: "Maison Cocody" with 12 demo devices; no real snapshot, no video, no push.
  Camera panels show a drawn placeholder scene.
- **Animations**: `animations=off` sets the MediaQuery hint and speeds time up twenty-fold;
  widgets that loop on their own (the SOS pulse) keep running and are masked. Loading
  states are not captured on purpose: the demo hub answers in microtasks.
- **Overflow stripes**: a release web build does not paint `RenderFlex overflowed` stripes
  (they are debug-mode asserts). Clipped text at scale 2.0 shows as clipped text; the golden
  harness (debug mode) is where overflows are counted.
- **Chromium headless**: `prefers-color-scheme` follows the variant, but the app forces the
  theme through `themeModeProvider`, so the browser setting is only cosmetic.

## 7. CI

Job `mobile-screenshots` (`.github/workflows/safer-hub-ci.yml`): Flutter 3.47.2, `flutter
build web --release --dart-define=SAFER_DEMO=1 --no-web-resources-cdn`, Node 22,
`npm i --no-save playwright@1.56.1` in `mobile/tool/screenshots`, `npx playwright install
--with-deps chromium`, `node tool/screenshots/capture.mjs`, then `--check`; the `out/`
folder is uploaded as the `mobile-screenshots` artifact (14 days). The job fails when a
matrix entry is missing or a variant raised an app error.
