import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../features/add_device/qr_scan_screen.dart';
import '../../features/device/widgets/stream_player.dart';
import '../../features/me/widgets/me_common.dart';
import '../../features/security/widgets/location_service.dart';
import '../../features/security/widgets/phone_dialer.dart';
import '../i18n.dart';
import '../providers/providers.dart';
import 'demo_camera_surface.dart';
import 'demo_hub_client.dart';
import 'demo_options.dart';
import 'demo_session.dart';
import 'ready_signal.dart';

/// Options the demo build was started with (defaults outside demo mode).
final demoOptionsProvider = Provider<DemoOptions>((_) => DemoOptions.defaults);

/// Position attached to demo SOS alerts (the demo home, Cocody).
const GeoPoint kDemoPosition = (lat: 5.36, lon: -4.0);

/// Provider overrides that turn the app into the demo: in-memory hub, no
/// socket, no probe, signed-in session, forced locale and theme, and
/// platform services (location, dialer, links, camera, QR scanner) replaced by
/// inert stand-ins so no permission prompt or external app can interrupt a
/// capture.
List<Override> demoOverrides(DemoOptions options, {DemoHubClient? client}) {
  final hub = client ?? DemoHubClient.fromStates(options.states);
  return [
    demoOptionsProvider.overrideWithValue(options),
    hubClientProvider.overrideWithValue(hub),
    hubProbeProvider.overrideWithValue((_) async => !hub.failNetwork),
    realtimeEnabledProvider.overrideWithValue(false),
    tokenProvider.overrideWith(() => DemoTokenNotifier(demoToken(options))),
    currentHomeIdProvider.overrideWith(() => DemoCurrentHomeIdNotifier(demoHomeId(options))),
    localeProvider.overrideWith(() => DemoLocaleNotifier(options.locale)),
    themeModeProvider.overrideWith(() => DemoThemeModeNotifier(options.themeMode)),
    locationServiceProvider.overrideWithValue(FixedLocationService(options.has(DemoState.locationDenied) ? null : kDemoPosition)),
    phoneDialerProvider.overrideWithValue(const DemoPhoneDialer()),
    linkOpenerProvider.overrideWithValue(const DemoLinkOpener()),
    cameraSurfaceBuilderProvider.overrideWithValue((context, request) => DemoCameraSurface(request: request)),
    qrScannerBuilderProvider.overrideWithValue((context, onCode) => DemoQrScanner(onCode: onCode)),
  ];
}

/// Resolves the demo options, installs the error hooks and returns the
/// overrides for `main()`. Only ever called when `kDemoMode` is true.
List<Override> bootstrapDemo() {
  final options = DemoOptions.resolve();
  debugPrint('SafeR demo mode: $options');
  installDemoErrorHooks();
  return demoOverrides(options);
}

/// Forwards the first uncaught error to the capture harness
/// (`window.saferError` on the web) while keeping the default console output.
void installDemoErrorHooks() {
  final previous = FlutterError.onError;
  FlutterError.onError = (details) {
    signalDemoError(details.exceptionAsString());
    if (previous != null) {
      previous(details);
    } else {
      FlutterError.presentError(details);
    }
  };
  PlatformDispatcher.instance.onError = (error, stack) {
    signalDemoError(error.toString());
    return false;
  };
}

/// Pretends the dialer opened (nothing leaves the demo).
class DemoPhoneDialer extends PhoneDialer {
  const DemoPhoneDialer();

  @override
  Future<bool> call(String number) async => true;
}

/// Pretends the browser opened (nothing leaves the demo).
class DemoLinkOpener extends LinkOpener {
  const DemoLinkOpener();

  @override
  Future<bool> open(Uri uri) async => true;
}

/// Stand-in for the camera viewfinder: a dark frame with a button that feeds
/// a sample Matter code to the scanner flow.
class DemoQrScanner extends StatelessWidget {
  const DemoQrScanner({super.key, required this.onCode});

  final ValueChanged<String> onCode;

  /// Sample Matter onboarding payload (vendor 0xFFF1, the test vendor id).
  static const String sampleMatterCode = 'MT:Y.K9042C00KA0648G00';

  @override
  Widget build(BuildContext context) => ColoredBox(
        color: const Color(0xFF0F172A),
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.qr_code_scanner, color: Colors.white54, size: 56),
              const SizedBox(height: 12),
              Text(context.tr(fr: 'Caméra de démonstration', en: 'Demo camera'), style: const TextStyle(color: Colors.white70)),
              const SizedBox(height: 12),
              OutlinedButton(
                onPressed: () => onCode(sampleMatterCode),
                style: OutlinedButton.styleFrom(foregroundColor: Colors.white, side: const BorderSide(color: Colors.white54)),
                child: Text(context.tr(fr: 'Simuler un code Matter', en: 'Simulate a Matter code')),
              ),
            ],
          ),
        ),
      );
}
