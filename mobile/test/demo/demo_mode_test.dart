import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:safer_ci/core/api/api_exception.dart';
import 'package:safer_ci/core/demo/demo.dart';
import 'package:safer_ci/core/providers/providers.dart';
import 'package:safer_ci/core/routes.dart';
import 'package:safer_ci/features/security/widgets/location_service.dart';

/// Demo mode (`--dart-define=SAFER_DEMO=1`): the capture hooks and the forced
/// states are a contract with `mobile/tool/screenshots/`; these tests pin it.
void main() {
  test('demo mode is inert without the define', () {
    expect(kDemoMode, isFalse);
  });

  group('DemoOptions.fromUri', () {
    test('defaults: French, light, 1.0, Home, no state', () {
      final o = DemoOptions.fromUri(Uri.parse('http://127.0.0.1:8089/'));
      expect(o.locale, const Locale('fr'));
      expect(o.themeMode, ThemeMode.light);
      expect(o.textScale, 1.0);
      expect(o.route, Routes.home);
      expect(o.states, isEmpty);
      expect(o.animationsOff, isFalse);
    });

    test('reads every hook', () {
      final o = DemoOptions.fromUri(Uri.parse('http://x/?locale=en&theme=dark&textScale=2.0&route=/security/sos&state=alarm,member&animations=off'));
      expect(o.locale, const Locale('en'));
      expect(o.themeMode, ThemeMode.dark);
      expect(o.textScale, 2.0);
      expect(o.route, Routes.sos);
      expect(o.states, {DemoState.alarm, DemoState.member});
      expect(o.animationsOff, isTrue);
    });

    test('ignores unknown states, bad scales and routes without a leading slash', () {
      final o = DemoOptions.fromUri(Uri.parse('http://x/?state=nope,noHomes&textScale=abc&route=security'));
      expect(o.states, {DemoState.noHomes});
      expect(o.textScale, 1.0);
      expect(o.route, Routes.home);
    });

    test('keeps the query of the route', () {
      final o = DemoOptions.fromUri(Uri.parse('http://x/?route=/scenes%3Ftab%3Dautomations'));
      expect(o.route, '/scenes?tab=automations');
    });

    test('every DemoState name round-trips through the parser', () {
      final names = DemoState.values.map((s) => s.name).join(',');
      expect(DemoState.parseList(names), DemoState.values.toSet());
    });
  });

  group('DemoHubClient.fromStates', () {
    const homeId = FakeHubClient.homeId;

    test('plain demo: owner of Maison Cocody with devices, scenes and messages', () async {
      final c = DemoHubClient.fromStates(const {});
      final homes = await c.homes();
      expect(homes.single.role, 'owner');
      expect(homes.single.rooms.length, 3);
      expect((await c.devices(homeId)).length, 12);
      expect((await c.scenes(homeId)).length, 2);
      expect((await c.unreadCount(homeId)).total, 2);
      expect((await c.security(homeId)).alarmActive, isFalse);
      expect((await c.weather(homeId)).available, isTrue);
    });

    test('offline fails every call like the hub being unreachable', () async {
      final c = DemoHubClient.fromStates({DemoState.offline});
      await expectLater(c.homes(), throwsA(isA<ApiException>().having((e) => e.status, 'status', isNull)));
      await expectLater(c.devices(homeId), throwsA(isA<ApiException>()));
      expect(await c.health(), isFalse);
    });

    test('noHomes, noDevices, noScenes, noMessages, noWeather', () async {
      final c = DemoHubClient.fromStates({DemoState.noHomes, DemoState.noDevices, DemoState.noScenes, DemoState.noAutomations, DemoState.noMessages, DemoState.noWeather});
      expect(await c.homes(), isEmpty);
      expect(await c.devices(homeId), isEmpty);
      expect(await c.scenes(homeId), isEmpty);
      expect(await c.automations(homeId), isEmpty);
      expect(await c.messages(homeId), isEmpty);
      expect((await c.unreadCount(homeId)).total, 0);
      expect((await c.weather(homeId)).available, isFalse);
      expect((await c.security(homeId)).panels, isEmpty);
    });

    test('alarm arms the home and blames the hallway sensor', () async {
      final c = DemoHubClient.fromStates({DemoState.alarm});
      final security = await c.security(homeId);
      expect(security.alarmActive, isTrue);
      expect(security.mode, 'armed_away');
      expect(security.alarmDeviceId, DemoHubClient.alarmDevice);
      expect((await c.homes()).single.alarmActive, isTrue);
      final cleared = await c.clearAlarm(homeId);
      expect(cleared.alarmActive, isFalse);
      expect(cleared.alarmDeviceId, isNull);
    });

    test('armed modes', () async {
      expect((await DemoHubClient.fromStates({DemoState.armedHome}).security(homeId)).mode, 'armed_home');
      expect((await DemoHubClient.fromStates({DemoState.armedNight}).security(homeId)).mode, 'armed_night');
      expect((await DemoHubClient.fromStates({DemoState.alarm, DemoState.armedNight}).security(homeId)).mode, 'armed_night');
    });

    test('openings, offline devices, member role and protected streams', () async {
      final c = DemoHubClient.fromStates({DemoState.openings, DemoState.offlineDevices, DemoState.member, DemoState.protectedStreams});
      final devices = await c.devices(homeId);
      expect(devices.firstWhere((d) => d.id == 'dev-door').boolValue('contact'), isTrue);
      expect(devices.firstWhere((d) => d.id == 'dev-zone').boolValue('open'), isTrue);
      expect(devices.firstWhere((d) => d.id == DemoHubClient.lightDevice).online, isFalse);
      expect((await c.device(DemoHubClient.cameraDevice)).online, isFalse);
      expect((await c.homes()).single.role, 'member');
      expect((await c.members(homeId)).firstWhere((m) => m.userId == FakeHubClient.userId).role, 'member');
      final stream = await c.stream(DemoHubClient.cameraDevice);
      expect(stream.authRequired, isTrue);
      expect(stream.directPlaybackAllowed, isFalse);
      await expectLater(c.sendCommand(DemoHubClient.lightDevice, 'switch', false), throwsA(isA<ApiException>().having((e) => e.code, 'code', 'device_offline')));
    });

    test('sosAlerts seeds two alerts and updateSos resolves one', () async {
      final c = DemoHubClient.fromStates({DemoState.sosAlerts});
      final alerts = await c.sosAlerts(homeId);
      expect(alerts.length, 2);
      expect(alerts.where((a) => a.status == 'open').length, 1);
      final resolved = await c.updateSos(homeId, 'sos-demo-2', 'resolved');
      expect(resolved.status, 'resolved');
      expect((await c.sosAlerts(homeId)).every((a) => a.status == 'resolved'), isTrue);
    });

    test('fail switches hit one request each', () async {
      final c = DemoHubClient.fromStates({DemoState.failDevices, DemoState.failWeather, DemoState.failSecurity, DemoState.failScenes, DemoState.failUnread});
      await expectLater(c.devices(homeId), throwsA(isA<ApiException>()));
      await expectLater(c.weather(homeId), throwsA(isA<ApiException>().having((e) => e.status, 'status', 502)));
      await expectLater(c.security(homeId), throwsA(isA<ApiException>()));
      await expectLater(c.scenes(homeId), throwsA(isA<ApiException>().having((e) => e.status, 'status', 500)));
      await expectLater(c.unreadCount(homeId), throwsA(isA<ApiException>().having((e) => e.status, 'status', 503)));
      expect(await c.homes(), isNotEmpty);
    });

    test('calls the shared fake left to the network work in memory', () async {
      final c = DemoHubClient.fromStates(const {});
      final room = await c.createRoom(homeId, 'Bureau', icon: 'desk');
      expect((await c.homes()).single.rooms.map((r) => r.name), contains('Bureau'));
      await c.updateRoom(room.id, name: 'Atelier');
      await c.reorderRooms(homeId, [room.id, 'room-1', 'room-2', 'room-3']);
      expect((await c.rooms(homeId)).first.name, 'Atelier');
      await c.deleteRoom(room.id);
      expect((await c.rooms(homeId)).length, 3);
      final home = await c.updateHome(homeId, name: 'Villa', address: 'Riviera');
      expect(home.name, 'Villa');
      expect(home.address, 'Riviera');
      final bob = await c.updateMember(homeId, 'user-2', 'admin');
      expect(bob.role, 'admin');
      await c.registerPushToken('android', 'token');
      await c.deleteHome(homeId);
      expect(await c.homes(), isEmpty);
    });
  });

  group('demoOverrides', () {
    test('seed a signed-in session on the demo home with the requested locale and theme', () {
      final options = DemoOptions.fromUri(Uri.parse('http://x/?locale=en&theme=dark&state=noWeather'));
      final container = ProviderContainer(overrides: demoOverrides(options));
      addTearDown(container.dispose);
      expect(container.read(tokenProvider), kDemoToken);
      expect(container.read(currentHomeIdProvider), FakeHubClient.homeId);
      expect(container.read(localeProvider), const Locale('en'));
      expect(container.read(themeModeProvider), ThemeMode.dark);
      expect(container.read(realtimeEnabledProvider), isFalse);
      expect(container.read(hubClientProvider), isA<DemoHubClient>().having((c) => c.weatherAvailable, 'weatherAvailable', isFalse));
      expect(container.read(authProvider).status, AuthStatus.unknown);
      expect(container.read(demoOptionsProvider), same(options));
    });

    test('loggedOut has no token and no current home', () {
      final container = ProviderContainer(overrides: demoOverrides(DemoOptions.fromUri(Uri.parse('http://x/?state=loggedOut'))));
      addTearDown(container.dispose);
      expect(container.read(tokenProvider), isNull);
      expect(container.read(currentHomeIdProvider), isNull);
      expect(container.read(authProvider).status, AuthStatus.unauthenticated);
    });

    test('session writes stay in memory and the location is fixed or denied', () async {
      final container = ProviderContainer(overrides: demoOverrides(DemoOptions.fromUri(Uri.parse('http://x/?state=locationDenied'))));
      addTearDown(container.dispose);
      await container.read(tokenProvider.notifier).set(null);
      expect(container.read(tokenProvider), isNull);
      await container.read(themeModeProvider.notifier).set(ThemeMode.dark);
      expect(container.read(themeModeProvider), ThemeMode.dark);
      expect(await container.read(locationServiceProvider).currentPosition(), isNull);
      final located = ProviderContainer(overrides: demoOverrides(DemoOptions.defaults));
      addTearDown(located.dispose);
      expect(await located.read(locationServiceProvider).currentPosition(), kDemoPosition);
      expect(await located.read(hubProbeProvider)('http://any'), isTrue);
    });
  });
}
