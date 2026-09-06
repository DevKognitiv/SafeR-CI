import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:safer_ci/core/models/models.dart';
import 'package:safer_ci/core/providers/providers.dart';
import 'package:safer_ci/features/device/device_detail_screen.dart';
import 'package:safer_ci/features/device/device_settings_screen.dart';
import 'package:safer_ci/features/device/panels/alarm_panel.dart';
import 'package:safer_ci/features/device/panels/camera_panel.dart';
import 'package:safer_ci/features/device/panels/generic_panel.dart';
import 'package:safer_ci/features/device/panels/light_panel.dart';
import 'package:safer_ci/features/device/panels/sensor_panel.dart';
import 'package:safer_ci/features/device/widgets/device_offline_banner.dart';
import 'package:safer_ci/features/device/widgets/ptz_pad.dart';
import 'package:safer_ci/features/device/widgets/stream_player.dart';

import 'helpers/device_fake_client.dart';
import 'helpers/fake_hub_client.dart';
import 'helpers/pump_app.dart';

/// Test surface: never touches media_kit, just echoes the stream URL.
Widget placeholderSurface(BuildContext context, CameraSurfaceRequest request) =>
    Center(child: Text(request.loading ? 'PLAYER loading' : 'PLAYER ${request.info?.url ?? 'none'}'));

/// Pump a device screen inside a detached GoRouter (so context.push/go can be asserted),
/// restore the session and settle.
Future<({ProviderContainer container, GoRouter router, DeviceFakeHubClient client})> pumpDevice(
  WidgetTester tester,
  Widget screen, {
  DeviceFakeHubClient? client,
  String initialLocation = '/devices/x',
}) async {
  final fake = client ?? DeviceFakeHubClient();
  final router = GoRouter(
    initialLocation: initialLocation,
    routes: [
      GoRoute(path: '/', builder: (_, __) => const SizedBox()),
      GoRoute(path: '/me/homes', builder: (_, __) => const SizedBox()),
      GoRoute(path: '/devices/:id', builder: (_, __) => const SizedBox(), routes: [
        GoRoute(path: 'settings', builder: (_, __) => const SizedBox()),
      ]),
    ],
  );
  addTearDown(router.dispose);
  final container = await pumpApp(
    tester,
    InheritedGoRouter(goRouter: router, child: screen),
    client: fake,
    overrides: [cameraSurfaceBuilderProvider.overrideWithValue(placeholderSurface)],
  );
  await container.read(authProvider.notifier).restore();
  await settle(tester);
  return (container: container, router: router, client: fake);
}

Finder sliderIn(Key key) => find.descendant(of: find.byKey(key), matching: find.byType(Slider));

void main() {
  group('DeviceDetailScreen', () {
    testWidgets('light panel shows the brightness slider and sends brightness / work_mode commands', (tester) async {
      final r = await pumpDevice(tester, const DeviceDetailScreen(deviceId: 'dev-light'));
      expect(find.text('Lampe salon'), findsOneWidget);
      expect(find.byType(LightPanel), findsOneWidget);
      expect(find.text('ALLUMÉE'), findsOneWidget);
      expect(sliderIn(const Key('slider-brightness')), findsOneWidget);
      expect(find.text('80%'), findsOneWidget);
      // White mode: colour temperature slider visible, colour picker hidden.
      expect(sliderIn(const Key('slider-color_temp')), findsOneWidget);
      expect(find.byKey(const Key('slider-hue')), findsNothing);

      await tester.tap(sliderIn(const Key('slider-brightness')));
      await settle(tester);
      expect(r.client.commands.where((c) => c.code == 'brightness'), hasLength(1));
      expect(r.client.commands.last.deviceId, 'dev-light');
      expect(r.client.commands.last.value, isA<int>());

      await tester.tap(find.text('Couleur'));
      await settle(tester);
      expect(r.client.commands.last.code, 'work_mode');
      expect(r.client.commands.last.value, 'colour');
      expect(find.byKey(const Key('slider-hue')), findsOneWidget);
      expect(find.byKey(const Key('slider-saturation')), findsOneWidget);
      expect(sliderIn(const Key('slider-color_temp')), findsNothing);

      await tester.tap(sliderIn(const Key('slider-hue')));
      await settle(tester);
      expect(r.client.commands.last.code, 'color');
      expect(r.client.commands.last.value, isA<Map>());
      expect((r.client.commands.last.value as Map).keys, containsAll(['h', 's', 'v']));
    });

    testWidgets('switch panel toggles gangs and the big power button', (tester) async {
      final r = await pumpDevice(tester, const DeviceDetailScreen(deviceId: 'dev-switch'));
      expect(find.text('Voie 1'), findsOneWidget);
      expect(find.text('Voie 2'), findsOneWidget);
      expect(find.text('ALLUMÉ'), findsOneWidget); // gang 1 is on
      expect(find.byType(Switch), findsNWidgets(2));

      await tester.tap(find.byType(Switch).last);
      await settle(tester);
      expect(r.client.commands.single.code, 'switch_2');
      expect(r.client.commands.single.value, isTrue);

      // Big button turns every gang off when one is on.
      await tester.tap(find.bySemanticsLabel('Alimentation'));
      await settle(tester);
      expect(r.client.commands.map((c) => c.code).toList(), ['switch_2', 'switch_1', 'switch_2']);
      expect(r.client.commands.last.value, isFalse);
      expect(find.text('ÉTEINT'), findsOneWidget);
    });

    testWidgets('plug panel sends switch from the power button', (tester) async {
      final r = await pumpDevice(tester, const DeviceDetailScreen(deviceId: 'dev-plug'));
      expect(find.text('ÉTEINT'), findsOneWidget);
      expect(find.text('Consommation'), findsOneWidget);
      await tester.tap(find.bySemanticsLabel('Alimentation'));
      await settle(tester);
      expect(r.client.commands.single.code, 'switch');
      expect(r.client.commands.single.value, isTrue);
      expect(find.text('ALLUMÉ'), findsOneWidget);
    });

    testWidgets('thermostat stepper sends temp_set in 0.5 steps and mode chips send mode', (tester) async {
      final r = await pumpDevice(tester, const DeviceDetailScreen(deviceId: 'dev-thermo'));
      expect(find.text('24 °C'), findsOneWidget);
      await tester.tap(find.byTooltip('Augmenter'));
      await settle(tester);
      expect(r.client.commands.single.code, 'temp_set');
      expect(r.client.commands.single.value, 24.5);
      expect(find.text('24.5 °C'), findsOneWidget);

      await tester.tap(find.byTooltip('Diminuer'));
      await settle(tester);
      expect(r.client.commands.last.value, 24.0);

      await tester.tap(find.text('Chauffage'));
      await settle(tester);
      expect(r.client.commands.last.code, 'mode');
      expect(r.client.commands.last.value, 'heat');
    });

    testWidgets('sensor panel shows the contact status, battery and history', (tester) async {
      await pumpDevice(tester, const DeviceDetailScreen(deviceId: 'dev-door'));
      expect(find.byType(SensorPanel), findsOneWidget);
      expect(find.text('FERMÉ'), findsOneWidget);
      expect(find.text('92%'), findsOneWidget);
      expect(find.text('Historique'), findsOneWidget);
      expect(find.text('Mouvement détecté'), findsOneWidget);
    });

    testWidgets('smoke sensor in alarm shows a red hero', (tester) async {
      final r = await pumpDevice(tester, const DeviceDetailScreen(deviceId: 'dev-smoke'));
      expect(find.text('OK'), findsOneWidget);
      expect(find.text('100%'), findsOneWidget);
      // Push an alarm state through the notifier (as a realtime event would).
      final notifier = r.container.read(devicesProvider(FakeHubClient.homeId).notifier);
      notifier.state = AsyncData([
        for (final d in notifier.state.value!) d.id == 'dev-smoke' ? d.withState({'smoke': true}) : d
      ]);
      await settle(tester);
      expect(find.text('FUMÉE !'), findsOneWidget);
      expect(find.text('OK'), findsNothing);
    });

    testWidgets('camera panel renders the placeholder player, toggles quality and sends ptz', (tester) async {
      final r = await pumpDevice(tester, const DeviceDetailScreen(deviceId: 'dev-cam'));
      expect(find.byType(CameraPanel), findsOneWidget);
      expect(find.text('PLAYER rtsp://demo.safer.local:554/cam1/main'), findsOneWidget);
      expect(find.text('REC'), findsOneWidget);
      expect(find.text('Instantané'), findsOneWidget);

      await tester.tap(find.text('SD'));
      await settle(tester);
      expect(find.text('PLAYER rtsp://demo.safer.local:554/cam1/sub'), findsOneWidget);
      expect(r.client.streamQualities, ['main', 'sub']);

      await tester.ensureVisible(find.byType(PtzPad));
      await settle(tester);
      expect(find.bySemanticsLabel('PTZ haut'), findsOneWidget);
      expect(find.bySemanticsLabel('Zoom avant'), findsOneWidget);
      await tester.tap(find.bySemanticsLabel('PTZ haut'));
      await settle(tester);
      final ptz = r.client.commands.where((c) => c.code == 'ptz').map((c) => c.value).toList();
      expect(ptz, ['up', 'stop']);

      await tester.ensureVisible(find.text('Sirène'));
      await settle(tester);
      await tester.tap(find.widgetWithText(SwitchListTile, 'Sirène'));
      await settle(tester);
      expect(r.client.commands.last.code, 'siren');
      expect(r.client.commands.last.value, isTrue);
    });

    testWidgets('lock panel asks for confirmation then sends locked=false', (tester) async {
      final r = await pumpDevice(tester, const DeviceDetailScreen(deviceId: 'dev-lock'));
      expect(find.text('VERROUILLÉE'), findsOneWidget);
      expect(find.text('65%'), findsOneWidget);
      await tester.tap(find.bySemanticsLabel('Déverrouiller'));
      await settle(tester);
      expect(find.text('Déverrouiller la serrure ?'), findsOneWidget);
      expect(r.client.commands, isEmpty);

      await tester.tap(find.text('Annuler'));
      await settle(tester);
      expect(r.client.commands, isEmpty);

      await tester.tap(find.bySemanticsLabel('Déverrouiller'));
      await settle(tester);
      await tester.tap(find.widgetWithText(FilledButton, 'Déverrouiller'));
      await settle(tester);
      expect(r.client.commands.single.code, 'locked');
      expect(r.client.commands.single.value, isFalse);
      expect(find.text('OUVERTE'), findsOneWidget);
      expect(find.text('Serrure déverrouillée'), findsOneWidget);
    });

    testWidgets('alarm panel arm buttons send arm_mode and zones expose a bypass switch', (tester) async {
      final r = await pumpDevice(tester, const DeviceDetailScreen(deviceId: 'dev-panel'));
      expect(find.byType(AlarmPanel), findsOneWidget);
      expect(find.text('Prêt à armer'), findsOneWidget);
      await tester.tap(find.text('Absent'));
      await settle(tester);
      expect(r.client.commands.single.code, 'arm_mode');
      expect(r.client.commands.single.value, 'armed_away');
      expect(find.text('Absent'), findsNWidgets(2)); // hero + selector

      await tester.ensureVisible(find.text('Zone salon'));
      await settle(tester);
      expect(find.text('Zone salon'), findsOneWidget);
      await tester.tap(find.byType(Switch));
      await settle(tester);
      expect(r.client.commands.last.deviceId, 'dev-zone');
      expect(r.client.commands.last.code, 'bypass');
      expect(r.client.commands.last.value, isTrue);
    });

    testWidgets('generic panel renders enum chips, switches, sliders and read-only rows', (tester) async {
      final r = await pumpDevice(tester, const DeviceDetailScreen(deviceId: 'dev-generic'));
      expect(find.byType(GenericPanel), findsOneWidget);
      expect(find.text('Faible'), findsOneWidget);
      expect(find.text('Medium'), findsOneWidget);
      expect(find.text('Fort'), findsOneWidget);
      expect(find.byType(ChoiceChip), findsNWidgets(3));
      expect(find.byType(Switch), findsOneWidget);
      expect(sliderIn(const Key('slider-level')), findsOneWidget);
      expect(find.text('Status'), findsOneWidget); // raw_ prefix stripped from unknown codes
      expect(find.text('idle'), findsOneWidget);

      await tester.tap(find.text('Fort'));
      await settle(tester);
      expect(r.client.commands.single.deviceId, 'dev-generic');
      expect(r.client.commands.single.code, 'speed');
      expect(r.client.commands.single.value, 'high');
    });

    testWidgets('cover panel sends control commands and shows the position', (tester) async {
      final r = await pumpDevice(tester, const DeviceDetailScreen(deviceId: 'dev-cover'));
      expect(find.text('100 %'), findsOneWidget);
      await tester.tap(find.text('Fermer'));
      await settle(tester);
      expect(r.client.commands.single.code, 'control');
      expect(r.client.commands.single.value, 'close');
      expect(find.text('0 %'), findsOneWidget);
    });

    testWidgets('gateway panel lists the children and opens a child device', (tester) async {
      final r = await pumpDevice(tester, const DeviceDetailScreen(deviceId: 'dev-gw'));
      expect(find.text('Passerelle Zigbee'), findsOneWidget);
      expect(find.text('Capteur porte garage'), findsOneWidget);
      await tester.tap(find.text('Capteur porte garage'));
      await settle(tester);
      expect(r.router.routeInformationProvider.value.uri.toString(), '/devices/dev-gw-child-1');
    });

    testWidgets('offline banner appears for an offline device and refresh hits the hub', (tester) async {
      final r = await pumpDevice(tester, const DeviceDetailScreen(deviceId: 'dev-plug'), client: DeviceFakeHubClient(offlineIds: const {'dev-plug'}));
      expect(find.byType(DeviceOfflineBanner), findsOneWidget);
      expect(find.text('Appareil hors ligne'), findsOneWidget);
      await tester.tap(find.text('Actualiser'));
      await settle(tester);
      expect(r.client.refreshCalls, 1);
      expect(find.text('Appareil toujours hors ligne'), findsOneWidget);
    });

    testWidgets('offline generic device: switches, sliders, chips and the send button are disabled', (tester) async {
      final r = await pumpDevice(tester, const DeviceDetailScreen(deviceId: 'dev-generic'), client: DeviceFakeHubClient(offlineIds: const {'dev-generic'}));
      expect(find.byType(DeviceOfflineBanner), findsOneWidget);
      expect(tester.widget<Switch>(find.byType(Switch)).onChanged, isNull);
      expect(tester.widget<Slider>(sliderIn(const Key('slider-level'))).onChanged, isNull);
      for (final chip in tester.widgetList<ChoiceChip>(find.byType(ChoiceChip))) {
        expect(chip.onSelected, isNull);
      }
      await tester.tap(find.text('Fort'));
      await tester.tap(find.byType(Switch));
      await settle(tester);
      expect(r.client.commands, isEmpty);
    });

    testWidgets('offline zone: the bypass switch of the panel children list is disabled', (tester) async {
      final r = await pumpDevice(tester, const DeviceDetailScreen(deviceId: 'dev-panel'), client: DeviceFakeHubClient(offlineIds: const {'dev-zone'}));
      await tester.ensureVisible(find.text('Zone salon'));
      await settle(tester);
      expect(tester.widget<Switch>(find.byType(Switch)).onChanged, isNull);
      await tester.tap(find.byType(Switch));
      await settle(tester);
      expect(r.client.commands, isEmpty);
    });

    testWidgets('offline colour light: hue and saturation sliders are disabled like brightness', (tester) async {
      final rgb = Device(
        id: 'dev-rgb',
        homeId: FakeHubClient.homeId,
        name: 'Bandeau LED',
        brand: 'tuya',
        protocol: 'tuya_cloud',
        category: 'light',
        externalId: 'rgb-1',
        capabilities: const [
          Capability(code: 'switch', type: 'bool', writable: true),
          Capability(code: 'brightness', type: 'int', writable: true, min: 0, max: 100),
          Capability(code: 'color', type: 'color', writable: true),
          Capability(code: 'work_mode', type: 'enum', writable: true, values: ['white', 'colour']),
        ],
        state: const {'switch': true, 'brightness': 50, 'color': {'h': 120, 's': 80, 'v': 100}, 'work_mode': 'colour'},
      );
      await pumpDevice(tester, const DeviceDetailScreen(deviceId: 'dev-rgb'), client: DeviceFakeHubClient(offlineIds: const {'dev-rgb'}, extras: [rgb]));
      expect(find.byType(LightPanel), findsOneWidget);
      expect(tester.widget<Slider>(sliderIn(const Key('slider-brightness'))).onChanged, isNull);
      expect(tester.widget<Slider>(sliderIn(const Key('slider-hue'))).onChanged, isNull);
      expect(tester.widget<Slider>(sliderIn(const Key('slider-saturation'))).onChanged, isNull);
    });

    testWidgets('online device has no offline banner and "..." opens the settings route', (tester) async {
      final r = await pumpDevice(tester, const DeviceDetailScreen(deviceId: 'dev-light'));
      expect(find.byType(DeviceOfflineBanner), findsNothing);
      await tester.tap(find.byTooltip("Paramètres de l'appareil"));
      await settle(tester);
      expect(r.router.routeInformationProvider.value.uri.toString(), '/devices/dev-light/settings');
    });

    testWidgets('shows the create-home empty state when the user has no home', (tester) async {
      await pumpDevice(tester, const DeviceDetailScreen(deviceId: 'dev-light'), client: DeviceFakeHubClient(noHomes: true));
      expect(find.text('Aucune maison'), findsOneWidget);
      expect(find.text('Créer une maison'), findsOneWidget);
    });

    testWidgets('unknown device falls back to a fetch and shows an error when missing', (tester) async {
      await pumpDevice(tester, const DeviceDetailScreen(deviceId: 'dev-nope'));
      expect(find.text('Impossible de charger les données'), findsOneWidget);
      expect(find.text('Réessayer'), findsOneWidget);
    });
  });

  group('DeviceSettingsScreen', () {
    testWidgets('shows device information and history', (tester) async {
      await pumpDevice(tester, const DeviceSettingsScreen(deviceId: 'dev-light'));
      expect(find.text("Paramètres de l'appareil"), findsOneWidget);
      expect(find.text('Lampe salon'), findsNWidgets(2)); // header + name row
      expect(find.text('Salon'), findsOneWidget);
      expect(find.text('SafeR Virtual'), findsOneWidget);
      expect(find.text('1.0.0'), findsOneWidget);
      expect(find.text('En ligne'), findsOneWidget);
      await tester.ensureVisible(find.text("Supprimer l'appareil"));
      await settle(tester);
      expect(find.text('Mouvement détecté'), findsOneWidget);
      expect(find.text('Actualiser'), findsOneWidget);
    });

    testWidgets('renames the device', (tester) async {
      final r = await pumpDevice(tester, const DeviceSettingsScreen(deviceId: 'dev-light'));
      await tester.tap(find.text('Nom'));
      await settle(tester);
      await tester.enterText(find.byType(TextField), 'Lampe bureau');
      await tester.pump();
      await tester.tap(find.text('Enregistrer'));
      await settle(tester);
      expect(find.text('Lampe bureau'), findsNWidgets(2));
      expect(find.text('Appareil renommé'), findsOneWidget);
      final devices = await r.client.devices(FakeHubClient.homeId);
      expect(devices.firstWhere((d) => d.id == 'dev-light').name, 'Lampe bureau');
    });

    testWidgets('moves the device to another room and changes its icon', (tester) async {
      final r = await pumpDevice(tester, const DeviceSettingsScreen(deviceId: 'dev-light'));
      await tester.tap(find.text('Pièce'));
      await settle(tester);
      await tester.tap(find.widgetWithText(ListTile, 'Chambre'));
      await settle(tester);
      expect(find.text('Appareil déplacé'), findsOneWidget);
      expect(find.text('Chambre'), findsOneWidget);
      var devices = await r.client.devices(FakeHubClient.homeId);
      expect(devices.firstWhere((d) => d.id == 'dev-light').roomId, 'room-2');
      await tester.pump(const Duration(seconds: 5)); // let the first snackbar expire
      await settle(tester);

      await tester.tap(find.text('Icône'));
      await settle(tester);
      await tester.tap(find.bySemanticsLabel('blinds'));
      await settle(tester);
      devices = await r.client.devices(FakeHubClient.homeId);
      expect(devices.firstWhere((d) => d.id == 'dev-light').icon, 'blinds');
      expect(find.text('Icône mise à jour'), findsOneWidget);
    });

    testWidgets('removes the device after confirmation and goes home', (tester) async {
      final r = await pumpDevice(tester, const DeviceSettingsScreen(deviceId: 'dev-plug'), initialLocation: '/devices/dev-plug/settings');
      final before = (await r.client.devices(FakeHubClient.homeId)).length;
      await tester.ensureVisible(find.text("Supprimer l'appareil"));
      await settle(tester);
      await tester.tap(find.text("Supprimer l'appareil"));
      await settle(tester);
      expect(find.text("Supprimer l'appareil ?"), findsOneWidget);
      await tester.tap(find.widgetWithText(FilledButton, 'Supprimer'));
      await settle(tester);
      final after = (await r.client.devices(FakeHubClient.homeId)).length;
      expect(after, before - 1);
      expect(r.container.read(devicesProvider(FakeHubClient.homeId)).value!.any((d) => d.id == 'dev-plug'), isFalse);
      expect(r.router.routeInformationProvider.value.uri.toString(), '/');
    });

    testWidgets('members get a read-only settings screen (no rename/move/icon/remove)', (tester) async {
      final r = await pumpDevice(tester, const DeviceSettingsScreen(deviceId: 'dev-plug'), client: DeviceFakeHubClient(role: 'member'));
      expect(find.text('Zone de danger'), findsNothing);
      expect(find.text("Supprimer l'appareil"), findsNothing);
      expect(find.textContaining('Seuls les administrateurs peuvent renommer'), findsOneWidget);
      await tester.tap(find.text('Nom'));
      await settle(tester);
      expect(find.byType(TextField), findsNothing);
      // Refresh stays available to members.
      await tester.ensureVisible(find.text('Actualiser'));
      await tester.tap(find.text('Actualiser'));
      await settle(tester);
      expect(r.client.refreshCalls, 1);
    });

    testWidgets('refresh action calls the hub', (tester) async {
      final r = await pumpDevice(tester, const DeviceSettingsScreen(deviceId: 'dev-light'));
      await tester.ensureVisible(find.text('Actualiser'));
      await settle(tester);
      await tester.tap(find.text('Actualiser'));
      await settle(tester);
      expect(r.client.refreshCalls, 1);
      expect(find.text('Appareil actualisé'), findsOneWidget);
    });
  });
}
