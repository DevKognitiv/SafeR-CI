import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:safer_ci/core/providers/providers.dart';
import 'package:safer_ci/core/routes.dart';
import 'package:safer_ci/features/add_device/brand_catalog_screen.dart';
import 'package:safer_ci/features/add_device/pairing_wizard_screen.dart';
import 'package:safer_ci/features/add_device/qr_scan_screen.dart';

import 'fake_hub_client.dart';
import 'pump_app.dart';

/// Marker text of the stub Home tab reached by `context.go(Routes.home)`.
const String kHomeStubText = 'HOME_STUB';

/// Marker text of the stub "my homes" page reached by `context.go(Routes.homes)`.
const String kHomesStubText = 'HOMES_STUB';

/// Fake camera preview that emits [code] when the "simulate scan" button is tapped.
QrScannerBuilder fakeScanner(String code) => (context, onCode) => ColoredBox(
      color: Colors.black,
      child: Center(
        child: TextButton(onPressed: () => onCode(code), child: const Text('simulate scan')),
      ),
    );

/// Router with the real add-device screens (same paths as [Routes]) and stub tabs.
GoRouter buildAddDeviceRouter({String initialLocation = Routes.addDevice, QrScannerBuilder? scannerBuilder}) => GoRouter(
      initialLocation: initialLocation,
      routes: [
        GoRoute(path: Routes.home, builder: (_, __) => const Scaffold(body: Center(child: Text(kHomeStubText)))),
        GoRoute(path: Routes.homes, builder: (_, __) => const Scaffold(body: Center(child: Text(kHomesStubText)))),
        GoRoute(path: Routes.addDevice, builder: (_, __) => const BrandCatalogScreen(), routes: [
          GoRoute(path: 'scan', builder: (_, __) => QrScanScreen(scannerBuilder: scannerBuilder)),
          GoRoute(
            path: ':brand',
            builder: (_, state) => PairingWizardScreen(
              brandId: state.pathParameters['brand']!,
              method: state.uri.queryParameters['method'],
              prefill: state.extra is Map<String, dynamic> ? state.extra as Map<String, dynamic> : null,
            ),
          ),
        ]),
      ],
    );

/// Pump the add-device flow inside a nested GoRouter, restore the session and settle.
Future<({ProviderContainer container, GoRouter router})> pumpAddDevice(
  WidgetTester tester, {
  String initialLocation = Routes.addDevice,
  FakeHubClient? client,
  QrScannerBuilder? scannerBuilder,
  Size size = const Size(400, 800),
  bool authenticated = true,
}) async {
  final router = buildAddDeviceRouter(initialLocation: initialLocation, scannerBuilder: scannerBuilder);
  addTearDown(router.dispose);
  final container = await pumpApp(tester, Router.withConfig(config: router), client: client, size: size, authenticated: authenticated);
  if (authenticated) await container.read(authProvider.notifier).restore();
  await settle(tester);
  return (container: container, router: router);
}
