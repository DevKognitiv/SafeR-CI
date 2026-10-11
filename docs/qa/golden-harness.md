# Golden harness — pixel truth for every screen

Phase 0 quality gate. A golden is a PNG of a screen in one variant, committed next to the test
that produces it; CI re-renders the screen and fails when the pixels drift. This file explains
the harness that `mobile/test/flutter_test_config.dart` installs, the bundled fonts it renders
with, the tolerance, the variant matrix, how to add and update goldens, the proof that the gate
bites, and the CI job. `docs/qa/state-matrix.md` lists which routes and states still owe a
golden; `docs/qa/a11y-baseline.md` records what the first goldens revealed.

## 1. What the harness is

- Plain `flutter_test` goldens (`matchesGoldenFile`), no extra package. Every test file under
  `mobile/test/goldens/` gets, from `flutter_test_config.dart`:
  - a `TolerantGoldenFileComparator` (a `LocalFileComparator` subclass) that accepts a golden
    when at most **0.1 %** of the pixels differ (`kGoldenTolerance = 0.001`) and otherwise
    fails exactly like the stock comparator, writing `<variant>_masterImage.png`,
    `_testImage.png`, `_maskedDiff.png` and `_isolatedDiff.png` to `failures/` next to the test;
  - the real fonts (§2) loaded through `FontLoader`, so glyphs are Roboto and Material icons
    instead of the block placeholder font `flutter test` uses by default.
- Test files under `mobile/test/a11y/` get the real fonts too (measured sizes then match a
  device); every other test keeps the stock behaviour, so the existing widget tests are
  untouched.
- The comparator and the fonts are keyed on the test file's directory
  (`LocalFileComparator.basedir`), which the `flutter` tool sets before `testExecutable` runs.
- Rendering is the software rasteriser of `flutter_tester` on Linux. It is deterministic: on
  this container three consecutive runs passed and two consecutive `--update-goldens`
  regenerations produced byte-identical PNGs (same md5 for all eight files). GitHub's
  `ubuntu-latest` runners use the same engine build for the pinned Flutter 3.47.2, and the
  0.1 % tolerance absorbs anti-aliasing drift between engine patch releases without hiding a
  layout change (a 2 px change moves about 7 % of the pixels, §6).
- `pumpApp` (`mobile/test/helpers/pump_app.dart`) gained `theme` and `textScaler` parameters
  (defaults unchanged: light theme, no scaling) and hides the DEBUG ribbon
  (`debugShowCheckedModeBanner: false`), which would otherwise be baked into every golden.
- Goldens are captured from `find.byType(MaterialApp)`, i.e. the whole 360×780 frame.
- Async providers are settled with the bounded `settle()` helper (10 frames × 50 ms of fake
  time) after `authProvider.restore()`; never `pumpAndSettle`, which would hang on the refresh
  indicator and the switch animations.
- A screen that overflows at text scale 2.0 is still captured: `runAllowingOverflow` in
  `mobile/test/goldens/golden_support.dart` filters **only** `A Render… overflowed by …`
  errors from `FlutterError.onError`, records them and prints
  `[golden] <name> tolerated N overflow(s): …` so CI logs name the layouts to fix. Any other
  error still fails the test. The yellow/black overflow stripes are therefore part of those
  goldens on purpose; `docs/qa/a11y-baseline.md` lists them.

## 2. Fonts

Bundled under `mobile/assets/fonts/` (SIL Open Font License 1.1, `OFL.txt` next to each
file) and declared in `mobile/pubspec.yaml` as the families `Manrope` and `Inter`. Phase 1
wires them into the theme; Phase 0 only ships them and renders goldens with them available.

| File | Bytes | Source | What was done |
|---|---|---|---|
| `manrope/Manrope-Variable.ttf` | 112 612 | `google/fonts` `ofl/manrope/Manrope[wght].ttf` (164 700 B) | Latin subset; `wght` axis kept at 200–800 with the default instance moved from ExtraLight (200) to Regular (400); name records renamed accordingly; 424 glyphs. |
| `manrope/OFL.txt` | 4 387 | same directory | — |
| `inter/Inter-Variable.ttf` | 220 676 | `google/fonts` `ofl/inter/Inter[opsz,wght].ttf` (876 576 B) | Latin subset; `opsz` pinned to 14 (the text cut — Manrope is the display face) and `wght` restricted to 400–700 (Regular, Medium, SemiBold, Bold); 1 301 glyphs. |
| `inter/OFL.txt` | 4 377 | same directory | — |
| **Total** | **342 052** (334 KiB) | | Budget: 450 KB. |

Subset ranges (both files, every OpenType layout feature kept):
`U+0000-024F, U+2000-206F, U+20A0-20CF, U+2122, U+2190-21FF, U+2500-25FF, U+FB01-FB02`
(Basic Latin, Latin-1, Latin Extended A/B, general punctuation, currency incl. CFA-compatible
signs, ™, arrows, box drawing, fi/fl ligatures). Tooling: `fonttools` 4.66
(`python3 -m fontTools.varLib.instancer`, `python3 -m fontTools.subset`).

Alternatives measured and rejected: Inter with both axes kept is 393 016 B (486 KB with
Manrope); four static Inter instances (400/500/600/700 at opsz 14, every feature) are
544 588 B together. Dropping the stylistic sets and character variants instead would have
saved 40 KB but removed features Phase 1 may want (tabular figures are kept either way).

Flutter note: `FontWeight` alone does not move a variable font's `wght` axis. The theme must
set `fontVariations: [FontVariation('wght', 600)]` (or `FontVariation.weight`) on each text
style; with a single declared asset Flutter would otherwise synthesise bold.

Test fonts: `loadRealFonts()` registers every family of the test asset bundle's
`FontManifest.json` (Manrope, Inter, MaterialIcons, CupertinoIcons) and the twelve
`Roboto-*.ttf` files of the Flutter SDK cache (`$FLUTTER_ROOT/bin/cache/artifacts/material_fonts`,
located through `FLUTTER_ROOT` or the `flutter_tester` path). It throws when Roboto is missing
rather than silently capturing with the placeholder font.

No system fallback: `flutter_tester` has no OS font stack, so a character missing from every
loaded font renders as a box. Today that is the right arrow of the thermostat summary
(`27.5 °C → 24.0 °C` on the climate tile, `→` U+2192, absent from the SDK's Roboto cut) and
it is visible in every Home golden. On an Android phone the system fallback draws it. Treat a
box in a golden as a font-coverage question for Phase 1 (bundled fonts carry U+2190-21FF),
not as a layout regression.

## 3. Tolerance

`kGoldenTolerance = 0.001` = 0.1 % of the pixels of the frame (281 pixels of a 360×780
golden). Identical bytes short-circuit; a size mismatch is reported as 100 % and always fails.
The failure message carries both the stock text (`Pixel test failed, 6.71%, 18849px diff
detected`) and `Pixel difference 6.71% exceeds the golden tolerance of 0.10%`.

## 4. Variant matrix

`kGoldenVariants` in `golden_support.dart`: {light, dark} × {fr, en} × {text scale 1.0, 2.0}
= 8 PNGs per screen, on `kGoldenPhone` = 360×780 logical px at device pixel ratio 1 (a small
Android phone). Files: `mobile/test/goldens/<screen>/<theme>_<locale>_<scale>.png`, e.g.
`home/dark_en_2.0.png`. The definition of done adds 1.3 for hero screens, a 600 dp frame and
a greyscale variant for Home and Security (Phase 1/2); add them to the matrix, not to
individual tests.

Current goldens (eight, about 50 KB each): `mobile/test/goldens/home/{light,dark}_{fr,en}_{1.0,2.0}.png`
of `HomeScreen` with `HomeFakeHubClient` (demo home, weather, three rooms, twelve devices).

## 5. Adding and updating goldens

Add a screen:

1. Create `mobile/test/goldens/<screen>_golden_test.dart` starting with `@Tags(['golden'])`
   and `library;`.
2. Loop over `kGoldenVariants`; pump with `pumpApp(tester, screen, client: …, locale:
   variant.locale, size: kGoldenPhone, theme: variant.theme, textScaler: variant.textScaler)`,
   restore the session if the screen needs it, `await settle(tester)`.
3. Wrap the pump and the capture in `runAllowingOverflow` and call `reportOverflows`.
4. `expectLater(find.byType(MaterialApp), matchesGoldenFile('<screen>/${variant.name}.png'))`.
5. Generate (below), inspect every PNG, run twice, commit the PNGs with the test.

Generate or update (from `mobile/`):

```
flutter test --update-goldens test/goldens          # all screens
flutter test --update-goldens test/goldens/home_golden_test.dart
flutter test test/goldens                            # verify; run it twice before committing
```

Only update goldens for an intentional visual change, in the same commit as the change, and
describe the diff in the commit message. Inspect `test/goldens/failures/` first; never commit
that directory.

## 6. Proof that the gate bites

Temporary change: `+2` on the pinned room-tab header height in
`mobile/lib/features/home/home_screen.dart` (`height: RoomTabBar.height + 2`), which shifts
everything below the tabs by two pixels.

```
$ flutter test test/goldens
00:04 +0 -8: Some tests failed.
Golden "home/light_fr_1.0.png": Pixel test failed, 6.71%, 18849px diff detected.
Golden "home/light_fr_2.0.png": Pixel test failed, 7.18%, 20168px diff detected.
Golden "home/light_en_1.0.png": Pixel test failed, 6.73%, 18894px diff detected.
Golden "home/light_en_2.0.png": Pixel test failed, 7.11%, 19969px diff detected.
Golden "home/dark_fr_1.0.png":  Pixel test failed, 6.72%, 18883px diff detected.
Golden "home/dark_fr_2.0.png":  Pixel test failed, 7.22%, 20280px diff detected.
Golden "home/dark_en_1.0.png":  Pixel test failed, 6.74%, 18925px diff detected.
Golden "home/dark_en_2.0.png":  Pixel test failed, 7.15%, 20086px diff detected.
Pixel difference 6.71% exceeds the golden tolerance of 0.10%.
```

All eight variants failed (6.71–7.22 %, 67–72× the tolerance) and `failures/` received the
four diagnostic images per variant. The edit was then reverted from a byte copy
(`git diff -- mobile/lib/features/home/home_screen.dart` is empty) and
`flutter test test/goldens` passed again (`+8: All tests passed!`).

## 7. CI

The `mobile` job of `.github/workflows/safer-hub-ci.yml` runs the suite in two steps so the
goldens have their own signal and keep their diagnostics when they fail:

```yaml
      - name: Test (unit, widget and accessibility guidelines)
        run: flutter test --exclude-tags golden
      - name: Golden tests (pixel truth, 0.1 % tolerance)
        run: flutter test --tags golden test/goldens
      - name: Upload golden failure diffs
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: golden-failures
          path: mobile/test/**/failures/**
          if-no-files-found: ignore
```

The accessibility guideline tests (`test/a11y/`) are untagged and run inside the first step.
The `golden` tag is declared in `mobile/dart_test.yaml`, so `--tags` / `--exclude-tags` work
without the "tag was used that wasn't specified" warning.

Roboto comes from the SDK cache that `subosito/flutter-action` populates (`flutter pub get`
downloads the `material_fonts` artifact). Running on a runner image whose engine differs from
the committed goldens shows up as a drift under the tolerance or as a clear failure, never as
a silent pass; the first runs on `ubuntu-latest` matched the goldens captured in the
development container byte for byte.
