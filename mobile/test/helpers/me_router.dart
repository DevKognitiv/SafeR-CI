import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:safer_ci/core/providers/providers.dart';
import 'package:safer_ci/core/router.dart';
import 'package:safer_ci/features/me/about_screen.dart';
import 'package:safer_ci/features/me/home_management_screen.dart';
import 'package:safer_ci/features/me/integrations_screen.dart';
import 'package:safer_ci/features/me/me_screen.dart';
import 'package:safer_ci/features/me/members_screen.dart';
import 'package:safer_ci/features/me/message_center_screen.dart';
import 'package:safer_ci/features/me/profile_screen.dart';
import 'package:safer_ci/features/me/settings_screen.dart';
import 'package:safer_ci/features/me/widgets/home_location.dart';
import 'package:safer_ci/features/me/widgets/me_common.dart';

import 'me_fake_client.dart';
import 'pump_app.dart';

/// Marker texts of the stub pages reached from the Me tab.
const String kMeAddDeviceStubText = 'ADD_DEVICE_STUB';
const String kMeDeviceStubText = 'DEVICE_STUB';

/// Records the links opened by "Aide & FAQ" / the about screen instead of launching a browser.
class RecordingLinkOpener extends LinkOpener {
  const RecordingLinkOpener(this.opened, {this.succeed = true});

  final List<Uri> opened;
  final bool succeed;

  @override
  Future<bool> open(Uri uri) async {
    opened.add(uri);
    return succeed;
  }
}

/// Router with the real Me screens (same paths as [Routes]) and stub pages elsewhere.
GoRouter buildMeRouter({String initialLocation = Routes.me}) => GoRouter(
      initialLocation: initialLocation,
      routes: [
        GoRoute(path: Routes.home, builder: (_, __) => const Scaffold(body: Center(child: Text('HOME_STUB')))),
        GoRoute(path: Routes.addDevice, builder: (_, __) => const Scaffold(body: Center(child: Text(kMeAddDeviceStubText)))),
        GoRoute(path: '/devices/:id', builder: (_, state) => Scaffold(body: Center(child: Text('$kMeDeviceStubText ${state.pathParameters['id']}')))),
        GoRoute(path: Routes.me, builder: (_, __) => const MeScreen(), routes: [
          GoRoute(path: 'profile', builder: (_, __) => const ProfileScreen()),
          GoRoute(path: 'homes', builder: (_, __) => const HomeManagementScreen(), routes: [
            GoRoute(path: ':homeId/members', builder: (_, state) => MembersScreen(homeId: state.pathParameters['homeId']!)),
          ]),
          GoRoute(path: 'messages', builder: (_, state) => MessageCenterScreen(initialKind: state.uri.queryParameters['kind'])),
          GoRoute(path: 'settings', builder: (_, __) => const SettingsScreen()),
          GoRoute(path: 'about', builder: (_, __) => const AboutScreen()),
          GoRoute(path: 'integrations', builder: (_, __) => const IntegrationsScreen()),
        ]),
      ],
    );

/// Pump the Me flow inside a nested GoRouter, restore the session and settle.
Future<({ProviderContainer container, GoRouter router, MeFakeHubClient client, List<Uri> links})> pumpMe(
  WidgetTester tester, {
  String initialLocation = Routes.me,
  MeFakeHubClient? client,
  HomeGeoPoint? location = (lat: 5.3599, lon: -4.0083),
  List<Override> overrides = const [],
}) async {
  final fake = client ?? MeFakeHubClient();
  final links = <Uri>[];
  final router = buildMeRouter(initialLocation: initialLocation);
  addTearDown(router.dispose);
  final container = await pumpApp(
    tester,
    Router.withConfig(config: router),
    client: fake,
    overrides: [
      linkOpenerProvider.overrideWithValue(RecordingLinkOpener(links)),
      homeLocationServiceProvider.overrideWithValue(FixedHomeLocationService(location)),
      ...overrides,
    ],
  );
  await container.read(authProvider.notifier).restore();
  await settle(tester);
  return (container: container, router: router, client: fake, links: links);
}
