import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:safer_ci/core/models/models.dart';
import 'package:safer_ci/core/providers/providers.dart';
import 'package:safer_ci/core/widgets/widgets.dart';

import 'helpers/fake_hub_client.dart';
import 'helpers/pump_app.dart';

void main() {
  group('models', () {
    test('Device.fromJson parses capabilities and state helpers', () {
      final device = Device.fromJson({
        'id': 'd1',
        'home_id': 'h1',
        'name': 'Lampe',
        'brand': 'tuya',
        'protocol': 'tuya_cloud',
        'category': 'light',
        'external_id': 'x',
        'online': true,
        'capabilities': [
          {'code': 'switch', 'type': 'bool', 'writable': true},
          {'code': 'brightness', 'type': 'int', 'writable': true, 'min': 0, 'max': 100},
        ],
        'state': {'switch': true, 'brightness': 42},
        'created_at': '2026-09-01T10:00:00',
      });
      expect(device.primaryToggleCode, 'switch');
      expect(device.isOn, isTrue);
      expect(device.numValue('brightness'), 42);
      expect(device.stateSummary, 'ON · 42%');
      expect(device.createdAt!.isUtc, isTrue);
      final off = device.withState({'switch': false});
      expect(off.isOn, isFalse);
      expect(off.state['brightness'], 42);
    });

    test('HubEvent parses device.state frames', () {
      final event = HubEvent.fromJson({'type': 'device.state', 'home_id': 'h', 'device_id': 'd', 'state': {'switch': true}, 'online': true});
      expect(event.type, HubEvent.deviceState);
      expect(event.state, {'switch': true});
      expect(event.online, isTrue);
    });

    test('StreamInfo embeds credentials', () {
      const info = StreamInfo(url: 'rtsp://cam:554/main', username: 'admin', password: 'p@ss');
      expect(info.authenticatedUrl, 'rtsp://admin:p%40ss@cam:554/main');
    });
  });

  group('providers', () {
    testWidgets('devices load from the hub and commands update state optimistically', (tester) async {
      final client = FakeHubClient();
      final container = await pumpApp(tester, const SizedBox(), client: client);
      final devices = await container.read(devicesProvider(FakeHubClient.homeId).future);
      expect(devices.length, greaterThan(10));
      final plug = devices.firstWhere((d) => d.id == 'dev-plug');
      expect(plug.isOn, isFalse);
      await container.read(devicesProvider(FakeHubClient.homeId).notifier).toggle(plug);
      expect(container.read(devicesProvider(FakeHubClient.homeId)).value!.firstWhere((d) => d.id == 'dev-plug').isOn, isTrue);
      expect(client.commands.single.code, 'switch');
    });

    testWidgets('auth restore validates the stored token', (tester) async {
      final container = await pumpApp(tester, const SizedBox());
      await container.read(authProvider.notifier).restore();
      expect(container.read(authProvider).isAuthenticated, isTrue);
      expect(container.read(authProvider).user?.name, 'Alice Kouassi');
    });

    testWidgets('auth restore drops an invalid token', (tester) async {
      final container = await pumpApp(tester, const SizedBox(), client: FakeHubClient(authenticated: false));
      await container.read(authProvider.notifier).restore();
      expect(container.read(authProvider).status, AuthStatus.unauthenticated);
      expect(container.read(tokenProvider), isNull);
    });
  });

  group('widgets', () {
    testWidgets('DeviceTile shows name, state and toggle', (tester) async {
      final device = FakeHubClient.demoDevices('h').first;
      bool? toggled;
      await pumpApp(tester, Scaffold(body: SizedBox(width: 180, height: 140, child: DeviceTile(device: device, onToggle: (v) => toggled = v))));
      expect(find.text('Lampe salon'), findsOneWidget);
      expect(find.text('ON · 80%'), findsOneWidget);
      await tester.tap(find.byType(Switch));
      expect(toggled, isFalse);
    });

    testWidgets('EmptyState renders action', (tester) async {
      var tapped = false;
      await pumpApp(tester, Scaffold(body: EmptyState(icon: Icons.devices, title: 'Aucun appareil', actionLabel: 'Ajouter', onAction: () => tapped = true)));
      await tester.tap(find.text('Ajouter'));
      expect(tapped, isTrue);
    });
  });
}
