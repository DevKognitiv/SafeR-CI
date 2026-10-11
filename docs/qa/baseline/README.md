# Baseline captures — Phase 0 foundations

The first run of the screenshot critique harness (`docs/qa/screenshot-harness.md`) over the
ten reference screens, kept so later reviews can be compared against where the app started.
They are **critique input, not sign-off evidence** (`docs/qa/screen-rubric.md` §5): web
captures of the demo build, Chromium/CanvasKit, not Android.

## Commit context

- Branch `claude/phase0-foundations`, captured on top of `5e099c3` (which already carries the
  Phase 0 session 1 mobile security, golden harness, hub security and CI lanes) with the demo
  mode and screenshot harness of this lane still uncommitted in the working tree; the commit
  that adds this folder is the one the captures belong to.
- Manifest: `162/162` variants captured, 0 failed
  (`mobile/tool/screenshots/out/manifest.json`, generated 2026-10-11T16:55:13Z).
- Build: `flutter build web --release --dart-define=SAFER_DEMO=1 --no-web-resources-cdn`,
  Flutter 3.47.2; Playwright 1.56.1, Chromium 141, viewport 360×780 CSS px at device scale
  factor 2.
- Files are the harness PNGs downscaled to 50 % (360×780, Lanczos) to stay under the 2 MB
  budget of this folder; the sha256 column is that of the full-size capture in the manifest,
  so a reviewer can match a file back to the run.
- The theme is the pre-Phase-1 Material 3 skeleton (stock Roboto, brand blue, red "Absent"):
  what the rubric scores are expected to be low on. Phase 1 replaces it.

## Files

| File | Screen | Route | Variant | Size | Masks | Full-size sha256 |
|---|---|---|---|---|---|---|
| `login-light-fr-1.0.png` | login | `/login` (`loggedOut`) | light-fr-1.0 | 49 KiB | auth-logo | `aa6cc7f99048655a…` |
| `home-light-fr-1.0.png` | home | `/` | light-fr-1.0 | 72 KiB | — | `006fae25b8f2d33d…` |
| `security-light-fr-1.0.png` | security | `/security` | light-fr-1.0 | 124 KiB | — | `43a22236b3fe78b1…` |
| `sos-light-fr-1.0.png` | sos | `/security/sos` | light-fr-1.0 | 45 KiB | sos-button | `e713d8a02866ee5f…` |
| `scenes-light-fr-1.0.png` | scenes | `/scenes` | light-fr-1.0 | 33 KiB | — | `bee13384b61315d7…` |
| `me-light-fr-1.0.png` | me | `/me` | light-fr-1.0 | 79 KiB | — | `9c480c96c74d1b61…` |
| `add-device-light-fr-1.0.png` | add-device | `/add-device` | light-fr-1.0 | 73 KiB | — | `678c8826a56478d4…` |
| `pair-tuya-light-fr-1.0.png` | pair-tuya | `/add-device/tuya` | light-fr-1.0 | 47 KiB | — | `048e391c0cc5a5c4…` |
| `device-light-light-fr-1.0.png` | device-light | `/devices/dev-light` | light-fr-1.0 | 45 KiB | — | `a750bf59895553da…` |
| `device-camera-light-fr-1.0.png` | device-camera | `/devices/dev-cam` | light-fr-1.0 | 54 KiB | — | `0273989e40cbb428…` |
| `home-dark-fr-1.0.png` | home | `/` | dark-fr-1.0 | 81 KiB | — | `85e91cfe6c57ad8c…` |
| `security-dark-fr-1.0.png` | security | `/security` | dark-fr-1.0 | 112 KiB | — | `e7ccf5238218fc7a…` |
| `home-light-fr-2.0.png` | home | `/` | light-fr-2.0 | 84 KiB | — | `c41ea92bb9a0edb2…` |
| `security-light-fr-2.0.png` | security | `/security` | light-fr-2.0 | 151 KiB | — | `dee620a55c807d34…` |

Total: 1050 KiB in 14 files.

Variant naming: `<theme>-<locale>-<textScale>` as in the harness output (`light-fr-1.0`,
`dark-fr-1.0`, `light-fr-2.0`). The dark and 2.0 variants are kept for Home and Security
only, the two hero screens of the Phase 2 redesign.

## First observations (for the reviewer agents, not findings yet)

- Login: the hero column is only as wide as its tagline, so the logo and wordmark sit left
  of centre at 1.0 (and move with locale); the harness masks the logo band for that reason.
- Home at 2.0: the weather temperature wraps character by character ("29 / .5° / C") and
  tile names are ellipsised; the fixed-extent grid is the known overflow of
  `docs/qa/a11y-baseline.md`.
- Security: "Absent" (armed away) is red, the colour the rubric reserves for alarm, SOS and
  destructive confirmations; the mode tiles truncate at 2.0 ("Dés…", "Pré…").
- Device states are ALL-CAPS ("ON · 80%", "FERMÉ", "CALME"), against criterion 9.
- Me at 2.0: the quick-action grid clips its labels ("Home / mon…", "Messa / ges") and the
  action buttons of the home card are cut ("Membe…", "Manag…").
- SOS: the pulsing button is masked; the status line reads "Appuyez sur le bouton en cas
  d'urgence" and the four emergency numbers are 48 dp tiles.
