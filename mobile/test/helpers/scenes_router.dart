import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:safer_ci/core/providers/providers.dart';
import 'package:safer_ci/core/routes.dart';
import 'package:safer_ci/features/scenes/automation_editor_screen.dart';
import 'package:safer_ci/features/scenes/scene_editor_screen.dart';
import 'package:safer_ci/features/scenes/scenes_screen.dart';

import 'pump_app.dart';
import 'scenes_fake_client.dart';

/// Marker text of the stub "my homes" page reached by `context.push(Routes.homes)`.
const String kScenesHomesStubText = 'HOMES_STUB';

/// Router with the real Scenes screens (same paths as [Routes]) and stub pages elsewhere.
GoRouter buildScenesRouter({String initialLocation = Routes.scenes}) => GoRouter(
      initialLocation: initialLocation,
      routes: [
        GoRoute(path: Routes.home, builder: (_, __) => const Scaffold(body: Center(child: Text('HOME_STUB')))),
        GoRoute(path: Routes.homes, builder: (_, __) => const Scaffold(body: Center(child: Text(kScenesHomesStubText)))),
        GoRoute(
          path: Routes.scenes,
          builder: (_, state) => ScenesScreen(initialTab: state.uri.queryParameters['tab'] == 'automations' ? 1 : 0),
          routes: [
            GoRoute(path: 'new', builder: (_, __) => const SceneEditorScreen()),
            GoRoute(path: 'automations/new', builder: (_, __) => const AutomationEditorScreen()),
            GoRoute(path: 'automations/:id', builder: (_, state) => AutomationEditorScreen(automationId: state.pathParameters['id'])),
            GoRoute(path: ':id', builder: (_, state) => SceneEditorScreen(sceneId: state.pathParameters['id'])),
          ],
        ),
      ],
    );

/// Pump the Scenes flow inside a nested GoRouter, restore the session and settle.
Future<({ProviderContainer container, GoRouter router, ScenesFakeHubClient client})> pumpScenes(
  WidgetTester tester, {
  String initialLocation = Routes.scenes,
  ScenesFakeHubClient? client,
}) async {
  final fake = client ?? ScenesFakeHubClient();
  final router = buildScenesRouter(initialLocation: initialLocation);
  addTearDown(router.dispose);
  final container = await pumpApp(tester, Router.withConfig(config: router), client: fake);
  await container.read(authProvider.notifier).restore();
  await settle(tester);
  return (container: container, router: router, client: fake);
}
