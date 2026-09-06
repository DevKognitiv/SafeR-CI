import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:safer_ci/core/providers/providers.dart';
import 'package:safer_ci/core/widgets/widgets.dart';
import 'package:safer_ci/features/home/home_screen.dart';
import 'package:safer_ci/features/home/room_management_screen.dart';
import 'package:safer_ci/features/home/widgets/alarm_banner.dart';
import 'package:safer_ci/features/home/widgets/offline_banner.dart';

import 'helpers/fake_hub_client.dart';
import 'helpers/home_fake_client.dart';
import 'helpers/pump_app.dart';

/// Pump a screen, restore the session (homesProvider only loads once authenticated) and settle.
Future<ProviderContainer> pumpAuthenticated(WidgetTester tester, Widget screen, {FakeHubClient? client}) async {
  final container = await pumpApp(tester, screen, client: client);
  await container.read(authProvider.notifier).restore();
  await settle(tester);
  return container;
}

void main() {
  group('HomeScreen', () {
    testWidgets('shows the home name, the weather and the security mode', (tester) async {
      await pumpAuthenticated(tester, const HomeScreen());
      expect(find.text('Maison Cocody'), findsOneWidget);
      expect(find.text('29.5°C'), findsOneWidget);
      expect(find.textContaining('Humidité 74%'), findsOneWidget);
      expect(find.textContaining('Partiellement nuageux'), findsOneWidget);
      expect(find.text('Désarmé'), findsOneWidget);
      expect(find.byType(AlarmBanner), findsNothing);
    });

    testWidgets('renders device tiles from the fake client', (tester) async {
      await pumpAuthenticated(tester, const HomeScreen());
      expect(find.byType(DeviceTile), findsWidgets);
      expect(find.text('Lampe salon'), findsOneWidget);
      expect(find.text('Prise TV'), findsOneWidget);
      expect(find.text('ON · 80%'), findsOneWidget);
      // Room tabs: "Tous", each room and "Non assignés" (the fake has devices without a room).
      expect(find.text('Tous'), findsOneWidget);
      expect(find.text('Salon'), findsOneWidget);
      expect(find.text('Chambre'), findsOneWidget);
      expect(find.text('Non assignés'), findsOneWidget);
    });

    testWidgets('room tab filters devices', (tester) async {
      await pumpAuthenticated(tester, const HomeScreen());
      await tester.tap(find.text('Chambre'));
      await settle(tester);
      expect(find.text('Volet chambre'), findsOneWidget);
      expect(find.text('Lampe salon'), findsNothing);
      expect(find.byType(DeviceTile), findsOneWidget);

      await tester.ensureVisible(find.text('Non assignés'));
      await settle(tester);
      await tester.tap(find.text('Non assignés'));
      await settle(tester);
      expect(find.text('Interrupteur cuisine'), findsOneWidget);
      expect(find.text('Volet chambre'), findsNothing);

      await tester.ensureVisible(find.text('Tous'));
      await settle(tester);
      await tester.tap(find.text('Tous'));
      await settle(tester);
      expect(find.text('Lampe salon'), findsOneWidget);
    });

    testWidgets('toggling a tile sends a command to the hub', (tester) async {
      final client = FakeHubClient();
      await pumpAuthenticated(tester, const HomeScreen(), client: client);
      final plugTile = find.widgetWithText(DeviceTile, 'Prise TV');
      expect(find.descendant(of: plugTile, matching: find.text('OFF')), findsOneWidget);
      await tester.tap(find.descendant(of: plugTile, matching: find.byType(Switch)));
      await settle(tester);
      expect(client.commands, hasLength(1));
      expect(client.commands.single.deviceId, 'dev-plug');
      expect(client.commands.single.code, 'switch');
      expect(client.commands.single.value, isTrue);
      expect(find.descendant(of: plugTile, matching: find.text('ON · 0 W')), findsOneWidget);
    });

    testWidgets('alarm banner appears when the home has an active alarm', (tester) async {
      final client = FakeHubClient()..alarmActive = true;
      await pumpAuthenticated(tester, const HomeScreen(), client: client);
      expect(find.byType(AlarmBanner), findsOneWidget);
      expect(find.text('Alarme en cours'), findsOneWidget);
    });

    testWidgets('shows the create-home empty state when the user has no home', (tester) async {
      await pumpAuthenticated(tester, const HomeScreen(), client: HomeFakeHubClient(noHomes: true));
      expect(find.text('Créez votre première maison'), findsOneWidget);
      expect(find.text('Créer une maison'), findsOneWidget);
      expect(find.byType(DeviceTile), findsNothing);
    });

    testWidgets('falls back to device counts when the weather is unavailable', (tester) async {
      await pumpAuthenticated(tester, const HomeScreen(), client: HomeFakeHubClient(weatherAvailable: false));
      expect(find.text('12 appareils'), findsOneWidget);
      expect(find.textContaining('12 en ligne'), findsOneWidget);
      expect(find.text('29.5°C'), findsNothing);
      expect(find.textContaining('Humidité'), findsNothing);
    });

    testWidgets('long-press opens the device actions and renames the device', (tester) async {
      await pumpAuthenticated(tester, const HomeScreen());
      await tester.longPress(find.text('Prise TV'));
      await settle(tester);
      expect(find.text('Renommer'), findsOneWidget);
      expect(find.text('Déplacer vers une pièce'), findsOneWidget);
      expect(find.text("Paramètres de l'appareil"), findsOneWidget);

      await tester.tap(find.text('Renommer'));
      await settle(tester);
      await tester.enterText(find.byType(TextField), 'Prise salon');
      await tester.pump();
      await tester.tap(find.text('Enregistrer'));
      await settle(tester);
      expect(find.text('Prise salon'), findsOneWidget);
      expect(find.text('Prise TV'), findsNothing);
      expect(find.text('Appareil renommé'), findsOneWidget);
    });

    testWidgets('long-press moves a device to another room', (tester) async {
      await pumpAuthenticated(tester, const HomeScreen());
      await tester.longPress(find.text('Prise TV'));
      await settle(tester);
      await tester.tap(find.text('Déplacer vers une pièce'));
      await settle(tester);
      // Room picker: the rooms and "Aucune pièce"; pick "Chambre" (the sheet's ListTile, not the tab pill).
      expect(find.text('Aucune pièce'), findsOneWidget);
      await tester.tap(find.widgetWithText(ListTile, 'Chambre'));
      await settle(tester);
      expect(find.text('Appareil déplacé'), findsOneWidget);
      await tester.tap(find.text('Chambre'));
      await settle(tester);
      expect(find.text('Prise TV'), findsOneWidget);
      expect(find.text('Volet chambre'), findsOneWidget);
      expect(find.byType(DeviceTile), findsNWidgets(2));
    });

    testWidgets('pull-to-refresh reloads the devices', (tester) async {
      final client = HomeFakeHubClient();
      await pumpAuthenticated(tester, const HomeScreen(), client: client);
      final before = client.devicesCalls;
      expect(before, greaterThanOrEqualTo(1));
      await tester.fling(find.byType(CustomScrollView), const Offset(0, 300), 1000);
      await tester.pump();
      await tester.pump(const Duration(seconds: 1)); // scroll animation
      await tester.pump(const Duration(seconds: 1)); // indicator settle
      await tester.pump(const Duration(seconds: 1)); // indicator hide
      expect(client.devicesCalls, before + 1);
      expect(find.text('Lampe salon'), findsOneWidget);
    });

    testWidgets('does not show the offline banner when realtime is disabled', (tester) async {
      await pumpAuthenticated(tester, const HomeScreen());
      expect(find.byType(OfflineBanner), findsNothing);
    });
  });

  group('RoomManagementScreen', () {
    testWidgets('lists rooms with device counts', (tester) async {
      await pumpAuthenticated(tester, const RoomManagementScreen(), client: HomeFakeHubClient());
      expect(find.text('Salon'), findsOneWidget);
      expect(find.text('Chambre'), findsOneWidget);
      expect(find.text('Entrée'), findsOneWidget);
      expect(find.text('3 appareils'), findsOneWidget); // Salon: lamp, plug, thermostat
      expect(find.text('1 appareil'), findsOneWidget); // Chambre: cover
      expect(find.text('2 appareils'), findsOneWidget); // Entrée: door sensor, camera
    });

    testWidgets('adds a room', (tester) async {
      final client = HomeFakeHubClient();
      await pumpAuthenticated(tester, const RoomManagementScreen(), client: client);
      await tester.tap(find.text('Ajouter une pièce'));
      await settle(tester);
      await tester.enterText(find.byType(TextField), 'Bureau');
      await tester.pump(); // enable the confirm button (disabled while the field is empty)
      await tester.tap(find.text('Ajouter'));
      await settle(tester);
      expect(client.rooms_.map((r) => r.name), contains('Bureau'));
      expect(find.text('Bureau'), findsOneWidget);
      expect(find.text('Pièce ajoutée'), findsOneWidget);
    });

    testWidgets('renames a room', (tester) async {
      final client = HomeFakeHubClient();
      await pumpAuthenticated(tester, const RoomManagementScreen(), client: client);
      await tester.tap(find.text('Chambre'));
      await settle(tester);
      await tester.tap(find.text('Renommer'));
      await settle(tester);
      await tester.enterText(find.byType(TextField), 'Chambre parents');
      await tester.pump();
      await tester.tap(find.text('Enregistrer'));
      await settle(tester);
      expect(find.text('Chambre parents'), findsOneWidget);
      expect(client.rooms_.firstWhere((r) => r.id == 'room-2').name, 'Chambre parents');
    });

    testWidgets('deletes a room after confirmation', (tester) async {
      final client = HomeFakeHubClient();
      await pumpAuthenticated(tester, const RoomManagementScreen(), client: client);
      await tester.tap(find.text('Entrée'));
      await settle(tester);
      await tester.tap(find.text('Supprimer'));
      await settle(tester);
      expect(find.textContaining('Supprimer « Entrée »'), findsOneWidget);
      // Confirm in the dialog (the sheet is closed, so only the dialog button remains).
      await tester.tap(find.widgetWithText(FilledButton, 'Supprimer'));
      await settle(tester);
      expect(find.text('Entrée'), findsNothing);
      expect(client.rooms_.map((r) => r.id), isNot(contains('room-3')));
      expect(find.text('Pièce supprimée'), findsOneWidget);
    });
  });
}
