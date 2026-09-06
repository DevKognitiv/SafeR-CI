# SafeR mobile app

SafeR is a Tuya-Smart-style smart home & security app, branded for **SafeR CI**.
It onboards, displays and controls devices from many brands (Tuya, Hikvision, Dahua,
Ajax, Matter, ONVIF cameras, Home Assistant bridge) through a single unified device
model, and adds SafeR CI's SOS / incident features (emergency numbers, geolocated SOS
alerts).

The app talks **only** to the SafeR Hub API (`/api/v1/hub`, see `SPEC.md` at the repo
root) through the typed client in `lib/core/api/hub_client.dart`; realtime updates come
from the hub WebSocket (`lib/core/api/ws_client.dart`).

Flutter package: `safer_ci` — display name **SafeR**.

## Screens

Bottom navigation (Tuya-style): **Accueil · Scènes · Sécurité · Moi**.

| Area | Screens |
|------|---------|
| Auth | Splash, Login, Register (with hub-URL sheet + "Tester la connexion") |
| Accueil | Home (weather header, room tabs, device grid with optimistic quick toggles, alarm / offline banners, home switcher, "+"), Room management (create / rename / reorder / delete rooms) |
| Ajouter un appareil | Brand catalogue (search, category grid, brand list), Pairing wizard (method chooser, form built from `PairingMethod.fields`, discovery step with checkboxes, progress, success), QR scanner (Matter `MT:` / Tuya QR / manual code) |
| Appareil | Device detail routed by category to a panel (switch/plug/siren, light, cover, thermostat, sensors & alarm zones, camera/doorbell/NVR, lock, alarm panel, gateway, generic fallback), Device settings (rename, room, icon, info, history, remove) |
| Scènes | Tap-to-Run + Automations tabs, Scene editor (actions: device command, delay, security mode, notify, run scene), Automation editor (triggers, conditions, actions, enable/disable, manual test) |
| Sécurité | Security (arm-mode cards, panels & zones, alarm banner, alarm history, SOS card), SOS (Côte d'Ivoire emergency numbers 170 Police · 180 Pompiers · 185 SAMU · 111 Gendarmerie, geolocated SOS to the hub, recent alerts) |
| Moi | Me, Profile, Home management (+ Members per home), Message center (alarm / home / notice, unread badge), Settings (language, theme, realtime alerts, hub URL), Integrations, About |

Every async list has loading / empty / error states, every user-facing string goes
through `context.tr(fr:, en:)` (French first), navigation only uses the `Routes`
constants from `lib/core/routes.dart`.

## Running

```bash
cd mobile
flutter pub get

# default hub URL: http://localhost:8000
flutter run

# Android emulator (the host machine is 10.0.2.2 from inside the emulator)
flutter run --dart-define=SAFER_HUB_URL=http://10.0.2.2:8000

# physical device on the LAN
flutter run --dart-define=SAFER_HUB_URL=http://192.168.1.20:8000

# web
flutter run -d chrome --dart-define=SAFER_HUB_URL=http://localhost:8000
flutter build web --release --dart-define=SAFER_HUB_URL=http://localhost:8000
```

The hub URL can also be changed at runtime from the login screen (gear icon in the
footer) or from *Moi › Paramètres › Hub SafeR*; the value is persisted in
`SharedPreferences` and overrides the build-time default.

Start the hub with `uvicorn app.hub.app:app --host 0.0.0.0 --port 8000` from `backend/`
(the hub also exposes demo devices when `HUB_DEMO_ENABLED=true`).

## Testing

```bash
flutter analyze          # must print "No issues found!"
flutter test             # whole suite (offline, deterministic)
flutter test test/device_test.dart   # a single feature
```

Widget tests use `test/helpers/pump_app.dart` (`pumpApp(tester, widget, client:,
authenticated:, overrides:)`) which wraps the widget in a `MaterialApp` + `ProviderScope`
with a `FakeHubClient` (`test/helpers/fake_hub_client.dart`), realtime disabled and the
hub probe stubbed. `settle(tester)` pumps a few bounded frames — avoid `pumpAndSettle`
with infinite animations. Feature-specific fakes (`*_fake_client.dart`) and router
harnesses (`*_router.dart`) live next to it.

| Test file | Covers |
|-----------|--------|
| `core_test.dart` | models, hub client, providers |
| `auth_test.dart` | splash / login / register, hub URL sheet |
| `home_test.dart` | home screen, rooms, quick toggles |
| `add_device_test.dart`, `matter_payload_test.dart` | catalogue, wizard, QR scan, Matter payload parser |
| `device_test.dart` | every device panel + device settings |
| `scenes_test.dart` | scenes, automations and their editors |
| `security_test.dart` | security screen and SOS |
| `me_test.dart` | Me tab, profile, homes, members, messages, settings, integrations, about |

## Folder structure

```
lib/
  main.dart, app.dart              # bootstrap (storage, media_kit) + MaterialApp.router
  core/
    config.dart                    # AppConfig: SAFER_HUB_URL, api prefix, emergency numbers
    theme.dart                     # SafeRColors + Material 3 light/dark themes
    i18n.dart                      # context.tr(fr:, en:), supported locales
    routes.dart / router.dart      # Routes constants / go_router with auth redirects + shell
    storage.dart                   # SharedPreferences wrapper (token, home, hub URL, locale, theme)
    api/                           # hub_client.dart (Dio), ws_client.dart, api_exception.dart
    models/                        # hand-written fromJson/toJson models
    providers/                     # Riverpod 2 providers (auth, homes, devices, scenes, security, messages, brands, ws, weather…)
    widgets/                       # DeviceTile, LoadingView, EmptyState, ErrorView, SectionHeader, StateChip, icon map…
  features/
    auth/          splash, login, register (+ widgets/)
    home/          home_screen, room_management_screen (+ widgets/)
    add_device/    brand_catalog_screen, pairing_wizard_screen, qr_scan_screen, matter_payload.dart (+ widgets/)
    device/        device_detail_screen, device_settings_screen, panels/, widgets/
    scenes/        scenes_screen, scene_editor_screen, automation_editor_screen (+ widgets/)
    security/      security_screen, sos_screen (+ widgets/)
    me/            me, profile, home_management, members, message_center, settings, integrations, about (+ widgets/)
    shell/         main_shell.dart (bottom navigation + badges)
test/
  helpers/                         # pump_app, fake_hub_client, feature fakes and router harnesses
  *_test.dart                      # one file per feature area
```

Conventions: Riverpod 2 (`Notifier` / `AsyncNotifier`, no codegen), go_router, Dio,
`web_socket_channel`, Material 3, cards with 16 px radius, bottom sheets for pickers,
`FilledButton` for primary actions, `showSnack` / `showErrorSnack` for feedback,
`Semantics` labels on icon-only buttons.

## Adding a device panel

Panels render the controls of one device category (the Tuya "product panel").

1. Create `lib/features/device/panels/<category>_panel.dart` with a widget taking
   `Device device`. Read state with `device.boolValue / numValue / stringValue(code)`
   and capabilities with `device.capability(code)` / `device.hasCapability(code)`.
2. Send commands through the shared helper in
   `lib/features/device/widgets/device_command.dart` (it does the optimistic update,
   calls `POST /devices/{id}/commands` and shows an error snack on failure).
3. Reuse the building blocks in `lib/features/device/widgets/`: `PanelCard`,
   `BigPowerButton`, `CapabilitySlider`, `ModeSelector`, `HueSaturationPicker`, `PtzPad`,
   status chips (`BatteryChip`, `SignalChip`, `BoolChip`, `OnlineChip`), info rows
   (`ValueRow`, `ReadoutTile`, `GaugeTile`), `DeviceEventsList`, `GenericControls`.
4. Register the category in `panelForDevice` (`lib/features/device/panels/device_panel.dart`).
   Unknown categories fall back to `GenericPanel`, which renders every capability
   from its type (bool → switch, enum → chips, int/float → slider, read-only → row).
5. Add a widget test in `test/device_test.dart` using `DeviceFakeHubClient`
   (`test/helpers/device_fake_client.dart`) to seed a device with the new category,
   and assert the sent commands with `client.commands`.

## Adding a brand pairing form

Forms are **not** hard-coded in the app: the wizard builds them from the hub's
`GET /onboarding/brands/{brand}` → `BrandInfo.methods[].fields` (`FormField`
`type: text | password | number | select | qr | toggle | textarea`).

- To add a brand or a pairing method, implement it in the hub adapter
  (`backend/app/hub/adapters/<brand>.py`, `info()` → `PairingMethod.fields`); the app
  picks it up automatically: method chooser → form → optional discovery step
  (`supports_discovery`) → pairing → success.
- To support a new field type, add a case to `_buildField` in
  `lib/features/add_device/widgets/pairing_form.dart` (and, if needed, its validation in
  `_validate`). `qr` fields get a "Scanner" button that opens `QrScanScreen` in
  result mode (`scanForResultLocation()`).
- Brand tiles get their colour from `lib/features/add_device/widgets/brand_color.dart`
  (falls back to `BrandInfo.color` / a palette) and their icon from
  `iconFromName(brand.icon)` in `lib/core/widgets/icon_map.dart`.
- Hub error codes (`auth_failed`, `unreachable`, `invalid_input`, `unsupported`,
  `not_found`) are mapped to localized hints in `widgets/pairing_error_card.dart`.
- Cover the new method in `test/add_device_test.dart` by extending `FakeHubClient.demoBrands`
  through the `pumpAddDevice` harness.

## Platform notes

- **Camera streams** use `media_kit` (RTSP/HLS/HTTP). `MediaKit.ensureInitialized()` is
  wrapped in a try/catch in `main.dart`, so the app still starts where the native libs
  are missing; the snapshot poster is always shown underneath the player.
- **QR scanning** uses `mobile_scanner`; a manual-entry dialog is always available.
- **Geolocation** for SOS uses `geolocator` with graceful fallback when permission is
  denied; the SOS is still sent without coordinates.
- The web build (`flutter build web`) is part of the definition of done, alongside
  `flutter analyze` and `flutter test`.
