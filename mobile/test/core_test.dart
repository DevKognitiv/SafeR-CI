import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:safer_ci/core/api/api_exception.dart';
import 'package:safer_ci/core/api/hub_client.dart';
import 'package:safer_ci/core/api/ws_client.dart';
import 'package:safer_ci/core/i18n.dart';
import 'package:safer_ci/core/models/models.dart';
import 'package:safer_ci/core/providers/providers.dart';
import 'package:safer_ci/core/widgets/widgets.dart';
import 'package:safer_ci/features/shell/main_shell.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'helpers/fake_hub_client.dart';
import 'helpers/pump_app.dart';

/// Shared fake whose unread-count endpoint is down.
class _NoUnreadClient extends FakeHubClient {
  @override
  Future<UnreadCount> unreadCount(String homeId) async => throw ApiException('Impossible de joindre le hub', status: null);
}

/// Shared fake whose device list is down (commands still work).
class _NoDevicesClient extends FakeHubClient {
  bool failDevices = true;

  @override
  Future<List<Device>> devices(String homeId, {String? roomId, String? category, String? brand}) {
    if (failDevices) throw ApiException('devices down', status: 500);
    return super.devices(homeId, roomId: roomId, category: category, brand: brand);
  }
}

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
      expect(off.lastSeenAt, isNotNull);
      // An offline report is not a sighting: "last seen" keeps the previous value
      final seen = off.lastSeenAt;
      final offline = off.withState({}, online: false);
      expect(offline.online, isFalse);
      expect(offline.lastSeenAt, seen);
      expect(offline.withState({'switch': true}, online: true).lastSeenAt!.isAfter(seen!) || offline.withState({}, online: true).lastSeenAt != seen, isTrue);
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

  group('HubClient', () {
    test('wsUrl keeps the path prefix of the hub URL and switches the scheme', () {
      final prefixed = HubClient(baseUrl: 'https://example.com/safer/', tokenProvider: () => null);
      expect(prefixed.wsUrl('h1', 't'), 'wss://example.com/safer/api/v1/hub/ws?home_id=h1&token=t');
      final plain = HubClient(baseUrl: 'http://192.168.1.20:8000', tokenProvider: () => null);
      expect(plain.wsUrl('h1', 't'), 'ws://192.168.1.20:8000/api/v1/hub/ws?home_id=h1&token=t');
    });
  });

  group('HubSocket', () {
    test('reports the first failed connection on the status stream', () async {
      final socket = HubSocket(url: 'ws://127.0.0.1:1/ws');
      addTearDown(socket.close);
      final first = socket.status.first;
      socket.connect();
      expect(await first.timeout(const Duration(seconds: 10)), isFalse);
      expect(socket.isConnected, isFalse);
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

    testWidgets('a command sent while the device list is in error recovers the list', (tester) async {
      final client = _NoDevicesClient();
      final container = await pumpApp(tester, const SizedBox(), client: client);
      final sub = container.listen(devicesProvider(FakeHubClient.homeId), (_, __) {});
      addTearDown(sub.close);
      await expectLater(container.read(devicesProvider(FakeHubClient.homeId).future), throwsA(isA<ApiException>()));
      expect(container.read(devicesProvider(FakeHubClient.homeId)).hasValue, isFalse);

      client.failDevices = false;
      final updated = await container.read(devicesProvider(FakeHubClient.homeId).notifier).sendCommand('dev-plug', 'switch', true);
      expect(updated.isOn, isTrue);
      expect(client.commands.single.code, 'switch');
      expect(container.read(devicesProvider(FakeHubClient.homeId)).valueOrNull?.firstWhere((d) => d.id == 'dev-plug').isOn, isTrue);
    });

    testWidgets('the "realtime alerts" preference gates the socket', (tester) async {
      SharedPreferences.setMockInitialValues({kRealtimeAlertsPrefKey: false, 'safer.token': 'test-token'});
      final container = await pumpApp(tester, const SizedBox(), overrides: [realtimeEnabledProvider.overrideWithValue(true)]);
      // pumpApp resets the mock store: re-apply the preference on the live instance.
      final prefs = await SharedPreferences.getInstance();
      await prefs.setBool(kRealtimeAlertsPrefKey, false);
      container.invalidate(realtimeAlertsProvider);
      expect(await container.read(realtimeAlertsProvider.future), isFalse);
      expect(container.read(realtimeActiveProvider), isFalse);
      expect(container.read(hubSocketProvider(FakeHubClient.homeId)).isConnected, isFalse);
    });
  });

  group('widgets', () {
    testWidgets('DeviceTile state summary follows the locale', (tester) async {
      final door = FakeHubClient.demoDevices('h').firstWhere((d) => d.id == 'dev-door');
      await pumpApp(tester, Scaffold(body: SizedBox(width: 180, height: 140, child: DeviceTile(device: door))), locale: const Locale('en'));
      expect(find.text('CLOSED'), findsOneWidget);
      expect(find.text('FERMÉ'), findsNothing);

      await pumpApp(tester, Scaffold(body: SizedBox(width: 180, height: 140, child: DeviceTile(device: door.copyWith(online: false)))), locale: const Locale('en'));
      expect(find.text('OFFLINE'), findsOneWidget);

      await pumpApp(tester, Scaffold(body: SizedBox(width: 180, height: 140, child: DeviceTile(device: door))));
      expect(find.text('FERMÉ'), findsOneWidget);
    });

    testWidgets('deviceStateSummary translates the word-based states', (tester) async {
      final lock = FakeHubClient.demoDevices('h').firstWhere((d) => d.id == 'dev-lock');
      late String en;
      late String fr;
      await pumpApp(tester, Builder(builder: (context) {
        en = deviceStateSummary(context, lock);
        return const SizedBox();
      }), locale: const Locale('en'));
      await pumpApp(tester, Builder(builder: (context) {
        fr = deviceStateSummary(context, lock);
        return const SizedBox();
      }));
      expect(en, 'LOCKED');
      expect(fr, 'VERROUILLÉE');
    });

    testWidgets('MainShell keeps its navigation bar when the unread count fails', (tester) async {
      final router = GoRouter(
        initialLocation: '/',
        routes: [
          StatefulShellRoute.indexedStack(
            builder: (context, state, shell) => MainShell(navigationShell: shell),
            branches: [
              StatefulShellBranch(routes: [GoRoute(path: '/', builder: (_, __) => const Center(child: Text('HOME_TAB')))]),
              StatefulShellBranch(routes: [GoRoute(path: '/scenes', builder: (_, __) => const SizedBox())]),
              StatefulShellBranch(routes: [GoRoute(path: '/security', builder: (_, __) => const SizedBox())]),
              StatefulShellBranch(routes: [GoRoute(path: '/me', builder: (_, __) => const SizedBox())]),
            ],
          ),
        ],
      );
      addTearDown(router.dispose);
      final container = await pumpApp(tester, Router.withConfig(config: router), client: _NoUnreadClient());
      await container.read(authProvider.notifier).restore();
      await settle(tester);
      expect(tester.takeException(), isNull);
      expect(find.byType(NavigationBar), findsOneWidget);
      expect(find.text('HOME_TAB'), findsOneWidget);
    });

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
