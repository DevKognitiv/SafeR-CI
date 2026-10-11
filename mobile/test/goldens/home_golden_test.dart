@Tags(['golden'])
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:safer_ci/core/providers/providers.dart';
import 'package:safer_ci/features/home/home_screen.dart';

import '../helpers/home_fake_client.dart';
import '../helpers/pump_app.dart';
import 'golden_support.dart';

/// Home tab with the demo home (weather, three rooms, twelve devices), captured in the eight
/// variants of the matrix. Goldens live in `home/<variant>.png` next to this file.
void main() {
  group('HomeScreen golden', () {
    for (final variant in kGoldenVariants) {
      testWidgets(variant.name, (tester) async {
        final overflows = await runAllowingOverflow(() async {
          final container = await pumpApp(
            tester,
            const HomeScreen(),
            client: HomeFakeHubClient(),
            locale: variant.locale,
            size: kGoldenPhone,
            theme: variant.theme,
            textScaler: variant.textScaler,
          );
          // homesProvider only loads once the session is restored; settle is bounded (no
          // pumpAndSettle: the refresh indicator and switches would never report idle).
          await container.read(authProvider.notifier).restore();
          await settle(tester);
          await expectLater(find.byType(MaterialApp), matchesGoldenFile('home/${variant.name}.png'));
        });
        reportOverflows('home/${variant.name}', overflows);
      });
    }
  });
}
