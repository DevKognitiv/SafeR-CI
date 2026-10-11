import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:safer_ci/core/providers/providers.dart';
import 'package:safer_ci/features/home/home_screen.dart';

import '../helpers/home_fake_client.dart';
import '../helpers/pump_app.dart';

/// Phone frame shared with the goldens: 360x780 logical px, device pixel ratio 1.
const Size kPhone = Size(360, 780);

/// Pumps the Home tab (fr, light, text scale 1.0) with the demo home and settles it.
Future<void> pumpHome(WidgetTester tester) async {
  final container = await pumpApp(tester, const HomeScreen(), client: HomeFakeHubClient(), size: kPhone);
  await container.read(authProvider.notifier).restore();
  await settle(tester);
}

/// Phase 0 accessibility baseline of the Home tab (docs/qa/a11y-baseline.md).
void main() {
  group('HomeScreen accessibility (fr, light, 1.0)', () {
    testWidgets('every tap target is at least 48x48 dp', (tester) async {
      final handle = tester.ensureSemantics();
      await pumpHome(tester);
      await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
      handle.dispose();
    });

    testWidgets('every tap target has a label', (tester) async {
      final handle = tester.ensureSemantics();
      await pumpHome(tester);
      await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
      handle.dispose();
    });

    testWidgets('text contrast meets WCAG AA everywhere except the unread badge (Phase 0 baseline)', (tester) async {
      final handle = tester.ensureSemantics();
      await pumpHome(tester);
      final evaluation = await textContrastGuideline.evaluate(tester);
      handle.dispose();
      // Known baseline: for the 11 sp "2" of the message-center badge the guideline pairs the
      // badge red (colorScheme.error, #DC2626) with the app-bar surface (#F3F4F6) at 4.39:1
      // (the white-on-red text pair itself is 4.83:1). Fixing it is a token change (Phase 1).
      // Once it passes, replace this test with `meetsGuideline(textContrastGuideline)`.
      expect(evaluation.passed, isFalse, reason: 'The badge now passes: assert meetsGuideline(textContrastGuideline) instead.');
      final reason = evaluation.reason ?? '';
      final failures = reason.split('\n').where((line) => line.startsWith('Expected contrast ratio')).toList();
      expect(failures, hasLength(1), reason: 'Only the unread badge may fail; got:\n$reason');
      expect(reason, contains('tooltip: "Centre de messages"'), reason: 'The single failure must be the unread badge; got:\n$reason');
    });
  });
}
