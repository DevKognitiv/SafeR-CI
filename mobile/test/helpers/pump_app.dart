import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:safer_ci/core/i18n.dart';
import 'package:safer_ci/core/providers/providers.dart';
import 'package:safer_ci/core/storage.dart';
import 'package:safer_ci/core/theme.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'fake_hub_client.dart';

/// Build a ProviderScope with the fake hub client and storage for widget tests.
///
/// [theme] defaults to the light theme and [textScaler] to no scaling, so existing tests are
/// unaffected; goldens pass the dark theme and `TextScaler.linear(2.0)` to cover the matrix.
Future<ProviderContainer> pumpApp(
  WidgetTester tester,
  Widget child, {
  FakeHubClient? client,
  bool authenticated = true,
  String? homeId = FakeHubClient.homeId,
  List<Override> overrides = const [],
  Locale locale = const Locale('fr'),
  Size size = const Size(400, 800),
  ThemeData? theme,
  TextScaler textScaler = TextScaler.noScaling,
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  // Secrets live in secure storage, plain preferences in SharedPreferences.
  FlutterSecureStorage.setMockInitialValues({if (authenticated) AppStorage.tokenKey: 'test-token'});
  SharedPreferences.setMockInitialValues({if (homeId != null) 'safer.home_id': homeId});
  final storage = await AppStorage.create();
  final fake = client ?? FakeHubClient(authenticated: authenticated);
  final container = ProviderContainer(overrides: [
    storageProvider.overrideWithValue(storage),
    hubClientProvider.overrideWithValue(fake),
    hubProbeProvider.overrideWithValue((_) async => !fake.failNetwork),
    realtimeEnabledProvider.overrideWithValue(false),
    ...overrides,
  ]);
  addTearDown(container.dispose);
  await tester.pumpWidget(UncontrolledProviderScope(
    container: container,
    child: MaterialApp(
      theme: theme ?? SafeRTheme.lightTheme,
      // The DEBUG ribbon would otherwise be baked into every golden.
      debugShowCheckedModeBanner: false,
      locale: locale,
      supportedLocales: kSupportedLocales,
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      // Applied above the Navigator so dialogs, sheets and snackbars scale with the screen.
      builder: (context, child) => MediaQuery(
        data: MediaQuery.of(context).copyWith(textScaler: textScaler),
        child: child!,
      ),
      home: child,
    ),
  ));
  return container;
}

/// Pump until async providers settle (bounded).
Future<void> settle(WidgetTester tester, {int frames = 10}) async {
  for (var i = 0; i < frames; i++) {
    await tester.pump(const Duration(milliseconds: 50));
  }
}
