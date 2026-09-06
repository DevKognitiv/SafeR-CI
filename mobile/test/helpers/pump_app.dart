import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:safer_ci/core/i18n.dart';
import 'package:safer_ci/core/providers/providers.dart';
import 'package:safer_ci/core/storage.dart';
import 'package:safer_ci/core/theme.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'fake_hub_client.dart';

/// Build a ProviderScope with the fake hub client and storage for widget tests.
Future<ProviderContainer> pumpApp(
  WidgetTester tester,
  Widget child, {
  FakeHubClient? client,
  bool authenticated = true,
  String? homeId = FakeHubClient.homeId,
  List<Override> overrides = const [],
  Locale locale = const Locale('fr'),
  Size size = const Size(400, 800),
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  SharedPreferences.setMockInitialValues({
    if (authenticated) 'safer.token': 'test-token',
    if (homeId != null) 'safer.home_id': homeId,
  });
  final storage = await AppStorage.create();
  final fake = client ?? FakeHubClient(authenticated: authenticated);
  final container = ProviderContainer(overrides: [
    storageProvider.overrideWithValue(storage),
    hubClientProvider.overrideWithValue(fake),
    realtimeEnabledProvider.overrideWithValue(false),
    ...overrides,
  ]);
  addTearDown(container.dispose);
  await tester.pumpWidget(UncontrolledProviderScope(
    container: container,
    child: MaterialApp(
      theme: SafeRTheme.lightTheme,
      locale: locale,
      supportedLocales: kSupportedLocales,
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
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
