# Screenshot critique harness

Playwright captures of the SafeR demo web build, one PNG per screen and variant, for the
reviewer agents of the critique loop (`docs/qa/screen-rubric.md`). It is a critique
instrument: web captures are not Android and never sign a screen off on their own
(`docs/qa/screenshot-harness.md` §6).

## Run

```sh
cd mobile
flutter build web --release --dart-define=SAFER_DEMO=1 --no-web-resources-cdn   # or: --build below
node tool/screenshots/capture.mjs                 # full matrix -> tool/screenshots/out/
node tool/screenshots/capture.mjs --only=home,sos # a subset
node tool/screenshots/capture.mjs --build         # builds first (3-5 min)
node tool/screenshots/capture.mjs --serve-only    # serve build/web on :8089 and stay up
node tool/screenshots/capture.mjs --check         # is out/manifest.json complete?
```

Requirements: Node 22 and the `playwright` module resolvable by `require`
(`NODE_PATH`, or `npm i --no-save playwright@1.56.1` in this folder), with the Chromium
build installed (`npx playwright@1.56.1 install --with-deps chromium`). Nothing is
installed by the script.

## What it does

1. Serves the built web directory (`--web-dir`, default `mobile/build/web`) from a static
   server on `127.0.0.1` (random free port, `--port` to pin).
2. For every screen in `routes.json` and every variant of the matrix opens
   `/?locale=…&theme=…&textScale=…&route=…&state=…&animations=off` in a fresh Chromium
   context (Android user agent, touch, `deviceScaleFactor: 2`, `prefers-color-scheme`
   matching the theme, reduced motion, `Africa/Abidjan`).
3. Waits for `window.saferReady === true` (set by the app two frames after the requested
   route has painted) or `window.saferError` (first uncaught Flutter error, which fails the
   variant), then waits `--settle` ms (default 1500).
4. Paints the masks of `masks.json` as opaque fixed `div`s over the page and takes the
   screenshot.
5. Writes `out/<screen>/<theme>-<locale>-<scale>-<w>x<h>.png` and `out/manifest.json`
   (route, states, variant, viewport, path, sha256, bytes, masks, console errors, font
   requests) and exits non-zero when any variant failed (`--no-strict` to downgrade). A
   partial run (`--only`, a narrowed matrix) merges its entries into the existing manifest,
   so re-capturing one screen after a mask change keeps `--check` meaningful.

## Matrix

| Axis | Values |
|---|---|
| theme | light, dark |
| locale | fr, en |
| text scale | 1.0, 2.0 |
| viewport (CSS px, DPR 2) | 360×780, 412×915 |
| tablet | 600×960, light/fr/1.0 only, for screens with `"tablet": true` (home, security) |

10 screens × 16 variants + 2 tablet shots = 162 PNGs. `--themes`, `--locales`, `--scales`,
`--viewports`, `--no-tablet` and `--only` narrow it; `--states=a,b` appends forced states to
every screen (names in `docs/qa/screenshot-harness.md` §3).

## Fonts and CDNs

The web build self-hosts CanvasKit (`--no-web-resources-cdn`). The engine still fetches its
fallback Roboto from `fonts.gstatic.com` at runtime; the harness answers those requests with
the Roboto files of the Flutter SDK cache (`$FLUTTER_ROOT/bin/cache/artifacts/material_fonts`,
`--fonts-dir` to point elsewhere) and aborts any other Google Fonts request, so a capture
needs no outbound network at all.

## Files

- `capture.mjs` — the harness (Node 22, ESM, no dependencies beyond `playwright`).
- `routes.json` — the screens: name, app route, forced states, tablet flag.
- `masks.json` — named rectangles painted before each shot (SOS pulse, brand mark).
- `simulate_cvd.py` — deuteranopia / protanopia simulation of a capture for the colour-vision
  step of the rubric (`python3 simulate_cvd.py out/security/light-fr-1.0-360x780.png`;
  Machado 2009 matrices in linear RGB, Pillow required, numpy recommended).
- `out/` — generated, git-ignored.
