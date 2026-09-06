import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:safer_ci/core/models/models.dart';
import 'package:safer_ci/core/providers/providers.dart';
import 'package:safer_ci/core/widgets/widgets.dart';
import 'package:safer_ci/features/security/security_screen.dart';
import 'package:safer_ci/features/security/sos_screen.dart';
import 'package:safer_ci/features/security/widgets/alarm_banner_card.dart';
import 'package:safer_ci/features/security/widgets/arm_mode_selector.dart';
import 'package:safer_ci/features/security/widgets/location_service.dart';
import 'package:safer_ci/features/security/widgets/phone_dialer.dart';
import 'package:safer_ci/features/security/widgets/sos_alert_list.dart';
import 'package:safer_ci/features/security/widgets/sos_button.dart';

import 'helpers/fake_hub_client.dart';
import 'helpers/pump_app.dart';
import 'helpers/security_fake_client.dart';

/// Records dialled numbers instead of opening the phone app.
class RecordingDialer extends PhoneDialer {
  final List<String> calls = [];

  @override
  Future<bool> call(String number) async {
    calls.add(number);
    return true;
  }
}

/// Pump a security screen inside a minimal GoRouter, restore the session and settle.
Future<({ProviderContainer container, GoRouter router, SecurityFakeHubClient client, RecordingDialer dialer})> pumpSecurity(
  WidgetTester tester,
  Widget screen, {
  SecurityFakeHubClient? client,
  GeoPoint? location = (lat: 5.36, lon: -4.0),
  String initialLocation = '/security',
}) async {
  final fake = client ?? SecurityFakeHubClient();
  final dialer = RecordingDialer();
  final router = GoRouter(
    initialLocation: initialLocation,
    routes: [
      GoRoute(path: '/', builder: (_, __) => const SizedBox()),
      GoRoute(path: '/security', builder: (_, __) => const SizedBox(), routes: [
        GoRoute(path: 'sos', builder: (_, __) => const SizedBox()),
      ]),
      GoRoute(path: '/me/homes', builder: (_, __) => const SizedBox()),
      GoRoute(path: '/me/messages', builder: (_, __) => const SizedBox()),
      GoRoute(path: '/add-device', builder: (_, __) => const SizedBox()),
      GoRoute(path: '/devices/:id', builder: (_, __) => const SizedBox()),
    ],
  );
  addTearDown(router.dispose);
  final container = await pumpApp(
    tester,
    InheritedGoRouter(goRouter: router, child: screen),
    client: fake,
    overrides: [
      phoneDialerProvider.overrideWithValue(dialer),
      locationServiceProvider.overrideWithValue(FixedLocationService(location)),
    ],
  );
  await container.read(authProvider.notifier).restore();
  await settle(tester);
  return (container: container, router: router, client: fake, dialer: dialer);
}

String location(GoRouter router) => router.routeInformationProvider.value.uri.toString();

void main() {
  group('SecurityScreen', () {
    testWidgets('renders the four arm modes and arms away on tap', (tester) async {
      final r = await pumpSecurity(tester, const SecurityScreen());
      expect(find.text('Sécurité'), findsOneWidget);
      expect(find.text('Maison Cocody'), findsOneWidget);
      expect(find.byType(ArmModeButton), findsNWidgets(4));
      expect(find.text('Présent'), findsOneWidget);
      expect(find.text('Absent'), findsOneWidget);
      expect(find.text('Nuit'), findsOneWidget);
      // Disarmed: the hero title and the selected button both say "Désarmé".
      expect(find.text('Désarmé'), findsNWidgets(2));
      expect(find.byKey(const Key('security-current-mode')), findsOneWidget);
      expect(find.byType(SecurityAlarmBanner), findsNothing);

      await tester.tap(find.byKey(const ValueKey('arm-mode-armed_away')));
      await settle(tester);
      expect(r.client.securityMode, 'armed_away');
      expect(find.text('Absent'), findsNWidgets(2));
      expect(find.text('Mode « Absent » activé'), findsOneWidget);
      expect(r.container.read(currentHomeProvider)?.securityMode, 'armed_away');
    });

    testWidgets('asks for confirmation when an opening is detected before arming', (tester) async {
      final r = await pumpSecurity(tester, const SecurityScreen(), client: SecurityFakeHubClient(openIds: {'dev-door'}));
      expect(find.text('1 ouverture détectée'), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('arm-mode-armed_night')));
      await settle(tester);
      expect(find.text('Des ouvertures sont détectées, armer quand même ?'), findsOneWidget);
      expect(find.text("• Porte d'entrée"), findsOneWidget);
      await tester.tap(find.text('Annuler'));
      await settle(tester);
      expect(r.client.securityMode, 'disarmed');

      await tester.tap(find.byKey(const ValueKey('arm-mode-armed_night')));
      await settle(tester);
      await tester.tap(find.text('Armer quand même'));
      await settle(tester);
      expect(r.client.securityMode, 'armed_night');
      // Disarming never asks.
      await tester.tap(find.byKey(const ValueKey('arm-mode-disarmed')));
      await settle(tester);
      expect(find.text('Des ouvertures sont détectées, armer quand même ?'), findsNothing);
      expect(r.client.securityMode, 'disarmed');
    });

    testWidgets('shows the alarm banner with the device name and acknowledges it', (tester) async {
      final client = SecurityFakeHubClient(alarmDeviceId: 'dev-zone')..alarmActive = true;
      final r = await pumpSecurity(tester, const SecurityScreen(), client: client);
      expect(find.byType(SecurityAlarmBanner), findsOneWidget);
      expect(find.text('🚨 Alarme déclenchée'), findsOneWidget);
      expect(find.text('Déclenchée par : Zone salon'), findsOneWidget);

      await tester.tap(find.text('Acquitter'));
      await settle(tester);
      expect(r.client.alarmActive, isFalse);
      expect(find.byType(SecurityAlarmBanner), findsNothing);
      expect(find.text('Alarme acquittée'), findsOneWidget);
      expect(r.container.read(currentHomeProvider)?.alarmActive, isFalse);
    });

    testWidgets('calls the police from the alarm banner', (tester) async {
      final r = await pumpSecurity(tester, const SecurityScreen(), client: SecurityFakeHubClient()..alarmActive = true);
      await tester.tap(find.text('Appeler la police 170'));
      await settle(tester);
      expect(r.dialer.calls, ['170']);
    });

    testWidgets('lists panels, zones and sensors with state chips', (tester) async {
      await pumpSecurity(tester, const SecurityScreen());
      expect(find.text('Centrales'), findsOneWidget);
      expect(find.text('Zones'), findsOneWidget);
      expect(find.text('Capteurs & serrures'), findsOneWidget);
      expect(find.text("Centrale d'alarme"), findsWidgets);
      expect(find.text('Zone salon'), findsOneWidget);
      expect(find.text('Fermée'), findsOneWidget);
      expect(find.byType(StateChip), findsWidgets);

      await tester.scrollUntilVisible(find.text('Serrure entrée'), 200, scrollable: find.byType(Scrollable).first);
      await settle(tester);
      expect(find.text("Porte d'entrée"), findsOneWidget);
      expect(find.text('Fermé'), findsOneWidget);
      expect(find.text('Détecteur couloir'), findsOneWidget);
      expect(find.text('Calme'), findsOneWidget);
      expect(find.text('Détecteur fumée cuisine'), findsOneWidget);
      expect(find.text('Verrouillée'), findsOneWidget);
      // Non-security devices are not listed here.
      expect(find.text('Lampe salon'), findsNothing);
    });

    testWidgets('shows the alarm history and navigates to the message center', (tester) async {
      final r = await pumpSecurity(tester, const SecurityScreen());
      await tester.scrollUntilVisible(find.text('Historique des alarmes'), 200, scrollable: find.byType(Scrollable).first);
      await settle(tester);
      expect(find.text('Mouvement détecté — Détecteur couloir'), findsOneWidget);
      expect(find.text('Nouvel appareil: Lampe salon'), findsNothing);
      await tester.tap(find.text('Voir tout'));
      await settle(tester);
      expect(location(r.router), '/me/messages?kind=alarm');
    });

    testWidgets('the SOS card opens the SOS screen', (tester) async {
      final r = await pumpSecurity(tester, const SecurityScreen());
      await tester.scrollUntilVisible(find.byKey(const Key('sos-card')), 200, scrollable: find.byType(Scrollable).first);
      await settle(tester);
      expect(find.text('Urgence ? Appuyez ici'), findsOneWidget);
      await tester.tap(find.byKey(const Key('sos-card')));
      await settle(tester);
      expect(location(r.router), '/security/sos');
    });

    testWidgets('shows an empty state without a home', (tester) async {
      await pumpSecurity(tester, const SecurityScreen(), client: SecurityFakeHubClient(noHomes: true));
      expect(find.text('Créez votre première maison'), findsOneWidget);
      expect(find.text('Créer une maison'), findsOneWidget);
      expect(find.byType(ArmModeButton), findsNothing);
    });

    testWidgets('shows an error state with retry when the security call fails', (tester) async {
      final client = SecurityFakeHubClient()..failSecurity = true;
      await pumpSecurity(tester, const SecurityScreen(), client: client);
      expect(find.byType(ErrorView), findsOneWidget);
      expect(find.byType(ArmModeButton), findsNothing);
      client.failSecurity = false;
      await tester.tap(find.text('Réessayer'));
      await settle(tester);
      expect(find.byType(ErrorView), findsNothing);
      expect(find.byType(ArmModeButton), findsNWidgets(4));
    });
  });

  group('SosScreen', () {
    testWidgets('sends an alert with the current location and lists it afterwards', (tester) async {
      final r = await pumpSecurity(tester, const SosScreen(), initialLocation: '/security/sos');
      expect(find.byType(SosButton), findsOneWidget);
      expect(find.text('SOS'), findsWidgets);
      expect(find.text("Appuyez sur le bouton en cas d'urgence"), findsOneWidget);
      expect(find.text('Aucune alerte récente'), findsOneWidget);

      await tester.enterText(find.byType(TextField), 'Intrusion au portail');
      await tester.tap(find.byType(SosButton));
      await settle(tester);
      expect(find.text('✅ Alerte envoyée aux secours'), findsOneWidget);
      expect(r.client.sosCalls, hasLength(1));
      expect(r.client.sosCalls.single.lat, 5.36);
      expect(r.client.sosCalls.single.lon, -4.0);
      expect(r.client.sosCalls.single.note, 'Intrusion au portail');
      expect(r.client.alarmActive, isTrue);
      // The recent list now shows the alert with its status chip.
      expect(find.byType(SosAlertTile), findsOneWidget);
      expect(find.text('Ouverte'), findsOneWidget);
      expect(find.text('Intrusion au portail'), findsWidgets);
      expect(find.text('5.3600, -4.0000'), findsOneWidget);
      expect(find.text('Nouvelle alerte'), findsOneWidget);
    });

    testWidgets('sends without coordinates when location is unavailable', (tester) async {
      final r = await pumpSecurity(tester, const SosScreen(), initialLocation: '/security/sos', location: null);
      await tester.tap(find.byType(SosButton));
      await settle(tester);
      expect(find.text('✅ Alerte envoyée aux secours'), findsOneWidget);
      expect(r.client.sosCalls.single.lat, isNull);
      expect(r.client.sosCalls.single.lon, isNull);
      expect(r.client.sosCalls.single.note, isNull);
      expect(find.text('Position non disponible'), findsOneWidget);
    });

    testWidgets('renders the emergency numbers and dials them', (tester) async {
      final r = await pumpSecurity(tester, const SosScreen(), initialLocation: '/security/sos');
      expect(find.text("Numéros d'urgence"), findsOneWidget);
      for (final n in const ['170', '180', '185', '111']) {
        expect(find.text(n), findsOneWidget);
      }
      expect(find.text('Police'), findsOneWidget);
      expect(find.text('Pompiers'), findsOneWidget);
      expect(find.text('SAMU'), findsOneWidget);
      expect(find.text('Gendarmerie'), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('emergency-180')));
      await settle(tester);
      expect(r.dialer.calls, ['180']);
    });

    testWidgets('marks a recent alert as resolved', (tester) async {
      final seeded = SosAlert(id: 'sos-old', homeId: FakeHubClient.homeId, lat: 5.3, lon: -4.1, note: 'Test', createdAt: DateTime.now().subtract(const Duration(hours: 3)));
      final r = await pumpSecurity(tester, const SosScreen(), initialLocation: '/security/sos', client: SecurityFakeHubClient(seededAlerts: [seeded]));
      expect(find.byType(SosAlertTile), findsOneWidget);
      expect(find.text('Ouverte'), findsOneWidget);
      await tester.tap(find.text('Marquer résolu'));
      await settle(tester);
      expect(r.client.updateSosCalls, [(id: 'sos-old', status: 'resolved')]);
      expect(find.text('Résolue'), findsOneWidget);
      expect(find.text('Marquer résolu'), findsNothing);
    });

    testWidgets('shows an error and re-enables the button when the hub rejects the alert', (tester) async {
      final client = SecurityFakeHubClient();
      await pumpSecurity(tester, const SosScreen(), initialLocation: '/security/sos', client: client);
      client.failNetwork = true;
      await tester.tap(find.byType(SosButton));
      await settle(tester);
      expect(find.text("Échec de l'envoi, réessayez"), findsOneWidget);
      expect(tester.widget<SosButton>(find.byType(SosButton)).state, SosButtonState.idle);
    });
  });
}
