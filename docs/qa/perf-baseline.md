# Performance baseline

The numbers the app is measured against. Every row carries the commit, the build, where the
number came from and a link to the raw evidence; a number without evidence reads **pending
hardware** and is never quoted. Device procedures and the reference device matrix are in
`device-capture.md`; the size gate is `tool/ci/aab_check.py` with `tool/ci/size_budget.json`.

## 1. Android app bundle (measured in CI)

Source: the `SafeR app (Android bundle size + 16 KB alignment)` job of
`.github/workflows/safer-hub-ci.yml`, which builds `flutter build appbundle --release` on
`ubuntu-latest` and runs the gate. The report of every run is in the job summary and in the
`aab-report` artifact (30 days).

| Measure | Baseline (commit 7b5a051, run 38155948270, 2026-10-11) | Budget (gate) |
|---|---|---|
| Bundle file (`app-release.aab`, all ABIs) | 83.94 MB (88 015 187 B) | 96 800 000 B |
| Download estimate, arm64-v8a | 18.52 MB (19 417 698 B) | 21 360 000 B |
| Download estimate, armeabi-v7a | 17.66 MB (18 521 902 B) | 20 370 000 B |
| Download estimate, x86_64 | 19.78 MB (20 743 505 B) | 22 820 000 B |
| Bundled fonts (`assets/fonts/`) | 357.4 KB (Manrope + Inter subsets, see `golden-harness.md`) | 460 800 B (450 KB) |
| Bundled images and illustrations | 0 KB | 256 000 B (250 KB) |
| 16 KB page alignment, 64-bit libraries | all aligned (arm64-v8a, x86_64) | required |

Download estimate = compressed size of the base module's common entries (dex, resources,
assets, manifest) plus the compressed native libraries of that ABI, the way Play serves a
split per device; it is an estimate of the first install, not the on-device footprint.

Budget rule: **baseline + 10 %** on each measure, re-based by hand whenever a deliberate
change moves the number (new native dependency, dropped dependency, asset wave), until the
arm64 download estimate is under 35 MB; from then on the gate is a fixed 35 MB. The fonts and
images budgets are fixed by the plan (450 KB and 250 KB).

### Where the bytes are (arm64-v8a, uncompressed)

| Native library | Size | Origin | Note |
|---|---|---|---|
| `libmpv.so` | 11.80 MB | media_kit (camera playback) | Largest single contributor; the Phase 3 stream relay may allow the lighter media_kit variant. |
| `libflutter.so` | 11.20 MB | Flutter engine | Fixed cost of the SDK version. |
| `libapp.so` | 8.81 MB | Dart AOT code | Grows with features; watch the delta per PR. |
| `libbarhopper_v3.so` | 4.72 MB | mobile_scanner (ML Kit barcode) | Only needed for QR pairing; a lighter scanner is a Phase 6 candidate. |
| `libmediakitandroidhelper.so` | 377.6 KB | media_kit | — |
| `libdartjni.so` | 128.2 KB | jni (plugin bridge) | — |
| others | < 50 KB each | plugins | — |

The 32-bit `libbarhopper_v3.so` (armeabi-v7a) is 4 KB aligned; the gate ignores 32-bit
libraries because the Play 16 KB requirement applies to 64-bit code only.

Gradle `bundleRelease` took 403 s on the runner at this commit; a CI timing regression is a
signal, not a gate.

## 2. Device budgets (pending hardware)

Budgets from `device-capture.md` §3. Each cell is filled only from a committed trace
(`docs/qa/captures/<date>-<device>-<measure>.*`) with the five raw values behind the median;
Test Lab virtual images are labelled "Test Lab proxy" and never reported as a device number.

| Measure | Budget | Tecno Spark Go (design target) | Infinix Smart 8 | Galaxy A05 | Redmi A3 | Android 10/11 handset | Flagship baseline |
|---|---|---|---|---|---|---|---|
| Cold start to cached Home (median of 5) | ≤ 2.0 s (≤ 1.2 s on the A05) | pending hardware | pending hardware | pending hardware | pending hardware | pending hardware | pending hardware |
| Warm start | ≤ 600 ms | pending hardware | pending hardware | pending hardware | pending hardware | pending hardware | pending hardware |
| p95 frame build + raster, 40-tile Home scroll | ≤ 16 ms, < 1 % jank | pending hardware | pending hardware | pending hardware | pending hardware | pending hardware | pending hardware |
| RSS on Home | ≤ 150 MB | pending hardware | pending hardware | pending hardware | pending hardware | pending hardware | pending hardware |
| RSS with one SD camera stream | ≤ 220 MB | pending hardware | pending hardware | pending hardware | pending hardware | pending hardware | pending hardware |
| First camera frame on 4G (after the relay exists) | ≤ 3 s | pending hardware | pending hardware | pending hardware | pending hardware | pending hardware | pending hardware |

## 3. Web proxy

No web performance number is recorded yet. When the web-profile regression proxy exists it is
reported here under its own heading, labelled "web proxy", and never quoted as an Android
number.

## 4. Updating this file

1. Read the `aab-report` artifact or the job summary of the run you are re-basing on.
2. Copy the measured values into §1 with the commit and run id, set each budget to the
   measured value + 10 % (rounded down to the nearest 10 000 B), and write the same numbers
   into `tool/ci/size_budget.json` (`_comment` carries the baseline).
3. Note the reason for the move in the PR description (new dependency, dropped dependency,
   asset wave).
4. Device rows change only through `device-capture.md`.
