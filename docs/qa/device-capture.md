# Device capture — how evidence from real phones reaches the repository

The critique loop runs on web captures; goldens are pixel truth on the host; neither is an
Android phone. Sign-off (`docs/qa/screen-rubric.md` §5), every performance number and every
"hardware-verified" badge (`docs/qa/hardware-status.md`) need evidence from a device. This
page says how that evidence is produced, named and committed, and who can produce it.

Three sources are accepted, in order of preference:

1. **Firebase Test Lab** runs started by CI or by hand (reproducible, agents can read the artifacts).
2. **adb** against a phone on the tester's desk, or through an agreed remote-adb bridge.
3. **User-pasted recordings and screenshots** taken on the phone itself.

Only the Demo home (`HUB_DEMO_ENABLED=true`, brand "Appareils de démonstration") appears in
committed captures: no real address, member e-mail, phone number, camera still or hub URL.
A capture that shows real data is cropped or redacted before it is committed, or not committed
at all (then the sign-off row points at a private artifact URL instead).

## 1. Reference device matrix

| Role | Device | RAM | Android | Why it is in the matrix |
|---|---|---|---|---|
| Design target | Tecno Spark Go (current generation) | 2 GB | 13/14 Go edition | Cold start, memory and jank budgets are measured here first; Transsion battery manager for push. |
| Low-end 2 | Infinix Smart 8 | 3 GB | 13 Go | Second Transsion device (release gate needs two); HiOS font scaling. |
| Mid | Samsung Galaxy A05 | 4 GB | 13/14 One UI | Most common Samsung in the segment; One UI notification channels and full-screen intent behaviour. |
| Mid 2 | Redmi A3 | 3/4 GB | 14 Go | MIUI/HyperOS battery manager (push and widget data messages). |
| Legacy | any handset on Android 10 or 11 | — | 10/11 | Oldest supported floor in practice; notification runtime permission absent; scoped storage differences. |
| Baseline | a recent Pixel or Samsung flagship | ≥ 6 GB | latest | Impeller baseline: what the app looks like with no GPU or RAM constraint; the "it should look like this" reference. |

Until a device is physically available, its rows read **pending hardware**. Test Lab offers
Go-edition and low-RAM virtual images that serve as an interim proxy, always labelled "Test Lab
proxy" and never reported as a Tecno or Infinix number.

## 2. Naming and location

```
docs/qa/captures/<YYYY-MM-DD>-<device>-<screen>[-<state>][-<variant>].<png|mp4|json>
```

- `<device>` slug from the matrix: `tecno-spark-go`, `infinix-smart-8`, `galaxy-a05`,
  `redmi-a3`, `android-10-<model>`, `pixel-<n>`, `testlab-<model-id>`.
- `<screen>` is the route slug from `docs/qa/state-matrix.md` (`home`, `security`, `sos`,
  `device-light`, `pair-tuya`…); `<state>` only when not the default (`offline-cached`,
  `alarm`, `session-expired`); `<variant>` only when not light/fr/1.0 (`dark`, `en`,
  `scale2`).
- Traces: same stem with `.timeline.json` (DevTools timeline export) or `.startup.json`
  (`--trace-startup` output); Test Lab runs keep their `results-dir` URL in the sign-off row
  and copy only the PNGs and the trace into `docs/qa/captures/`.
- Videos are capped at 30 s and 10 MB; longer evidence stays out of the repo (artifact URL in
  the sign-off row).
- Each file is referenced from `docs/qa/screen-signoff.md`, `docs/qa/perf-baseline.md` or
  `docs/qa/hardware-status.md`; an unreferenced capture is deleted at the next phase close.

## 3. adb capture commands

Enable USB debugging on the phone, then from the host:

```bash
adb devices                                   # the device must show as "device", not "unauthorized"
PKG=ci.safer.safer_ci                         # applicationId from mobile/android/app/build.gradle.kts

# Install the build under test (release AAB through bundletool, or the profile APK)
adb install -r build/app/outputs/flutter-apk/app-profile.apk

# Screenshot straight to the host
adb exec-out screencap -p > docs/qa/captures/2026-10-18-galaxy-a05-home.png

# Screen recording (max 180 s on the device side; keep it under 30 s)
adb shell screenrecord --time-limit 30 --bit-rate 4000000 /sdcard/safer.mp4
adb pull /sdcard/safer.mp4 docs/qa/captures/2026-10-18-galaxy-a05-sos-hold.mp4
adb shell rm /sdcard/safer.mp4

# Variants without touching the phone's settings UI
adb shell settings put system font_scale 2.0        # text scale 2.0 (1.0 restores)
adb shell cmd uimode night yes                      # dark mode (no restores)
adb shell "setprop persist.sys.locale en-US; setprop ctl.restart zygote"   # locale (reboots the UI; prefer the in-app language setting)
adb shell settings put global animator_duration_scale 0   # disableAnimations equivalent

# Force the app into a matrix state through the debug hooks (debug/profile builds only)
adb shell am start -n $PKG/.MainActivity --es safer_state offline-cached --es safer_route /security
```

The `safer_state` / `safer_route` extras are the same hooks the Playwright harness uses as
query strings; the app ignores them in release builds.

### Performance capture

```bash
# Cold start: kill, clear from recents, start, read TotalTime (ms) — repeat 5×, report the median
adb shell am force-stop $PKG
adb shell am start -W -n $PKG/.MainActivity | grep -E "TotalTime|WaitTime"

# Warm start: background with Home, bring back
adb shell input keyevent KEYCODE_HOME && sleep 2 && adb shell am start -W -n $PKG/.MainActivity | grep TotalTime

# Frame times on a scripted Home scroll (profile build)
adb shell dumpsys gfxinfo $PKG reset
# … scroll the Home grid for 10 s (by hand or with `adb shell input swipe`) …
adb shell dumpsys gfxinfo $PKG framestats > docs/qa/captures/2026-10-18-tecno-spark-go-home.gfxinfo.txt

# RSS on Home and with one SD stream open
adb shell dumpsys meminfo $PKG | grep -E "TOTAL RSS|TOTAL PSS"

# Flutter-side timeline
flutter run --profile --trace-startup -d <serial>          # writes build/start_up_info.json
flutter run --profile -d <serial>                           # then DevTools → Performance → export .json
```

Budgets (targets until measured, then gates): cold start to cached Home ≤ 2.0 s on the Tecno
Spark Go (≤ 1.2 s on the Galaxy A05), warm start ≤ 600 ms, p95 frame build+raster ≤ 16 ms on a
40-tile Home scroll with < 1 % jank, RSS ≤ 150 MB on Home and ≤ 220 MB with one SD stream,
first camera frame ≤ 3 s on 4G SD only once the stream relay exists.

**Rule: every performance number in any document, PR or release note reads "pending hardware"
until the trace or `gfxinfo` file it comes from is committed under `docs/qa/captures/` and
referenced from `docs/qa/perf-baseline.md` with the device, build, commit and the five raw
values behind the median.** The web-profile `perf_budget_test` is a regression proxy labelled
"web proxy" and is never quoted as an Android number.

## 4. Firebase Test Lab

CI runs the instrumentation smoke script when the `FIREBASE_TEST_LAB_SA` secret is present and
skips with a visible notice otherwise. By hand:

```bash
gcloud auth activate-service-account --key-file=sa.json
gcloud config set project <firebase-project>

# Instrumentation run (flutter_driver / integration_test smoke) on a Go image and a mid-range image
gcloud firebase test android run \
  --type instrumentation \
  --app build/app/outputs/apk/debug/app-debug.apk \
  --test build/app/outputs/apk/androidTest/debug/app-debug-androidTest.apk \
  --device model=oriole,version=33,locale=fr,orientation=portrait \
  --device model=<go-image-id>,version=30,locale=fr,orientation=portrait \
  --environment-variables font_scale=2.0 \
  --results-bucket gs://<bucket> --results-dir safer-$(git rev-parse --short HEAD) \
  --timeout 15m

# Robo crawl (pre-launch-report style) for crash and accessibility findings
gcloud firebase test android run --type robo --app <apk> --device model=oriole,version=34
```

Artifacts to copy into `docs/qa/captures/`: the screenshots the smoke script takes (named by
the script with the route slug), `logcat` excerpts for a crash, and the performance trace
(`perfetto`/`systrace` file) when a budget is being recorded. The `results-dir` URL goes in the
sign-off row. List the available images with `gcloud firebase test android models list`; the
Go-edition and low-RAM entries are the interim proxies for the Transsion devices.

## 5. User-pasted evidence

When the tester has the phone but no host machine:

1. Take the screenshot or screen recording on the phone (power + volume down; or the
   screen-recorder tile) with the app showing the Demo home.
2. Send it in the PR or the session with the device model, Android version, app version
   (`Moi › À propos › Version`), text scale and theme.
3. The implementer renames it per §2, strips metadata (`exiftool -all= file.png` or re-encode),
   checks it shows no real data, commits it and fills the sign-off row with "user capture".

A pasted recording is enough for sign-off evidence and for ticking a hardware checklist
(`docs/qa/hardware-status.md`), never for a performance number (§3 rule).

## 6. Remote-adb bridge (optional)

If the tester agrees to leave a phone connected, `adb -L tcp:localhost:5037` over an SSH tunnel
or a `scrcpy`/`adb connect <phone-ip>:5555` session on the same network lets a session run the
§3 commands directly. The bridge is opt-in per session, the phone stays on the Demo home, and
the tester can cut it at any time; nothing in this process requires it.

## 7. What a capture must show to count

- The app version and commit under test (About screen, or the build name in the sign-off row).
- The route and state named in the file name, recognisable without guessing.
- For text-scale evidence: the whole screen at 2.0, including the bottom of the scroll.
- For push and alarm evidence: the notification shade or the takeover with the device's clock
  visible, and the hub-side log line (time) in the PR.
- For hardware checklists: the exact line of the checklist it satisfies.
