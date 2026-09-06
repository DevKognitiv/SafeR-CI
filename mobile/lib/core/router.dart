import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../features/add_device/brand_catalog_screen.dart';
import '../features/add_device/pairing_wizard_screen.dart';
import '../features/add_device/qr_scan_screen.dart';
import '../features/auth/login_screen.dart';
import '../features/auth/register_screen.dart';
import '../features/auth/splash_screen.dart';
import '../features/device/device_detail_screen.dart';
import '../features/device/device_settings_screen.dart';
import '../features/home/home_screen.dart';
import '../features/home/room_management_screen.dart';
import '../features/me/about_screen.dart';
import '../features/me/home_management_screen.dart';
import '../features/me/integrations_screen.dart';
import '../features/me/me_screen.dart';
import '../features/me/members_screen.dart';
import '../features/me/message_center_screen.dart';
import '../features/me/profile_screen.dart';
import '../features/me/settings_screen.dart';
import '../features/scenes/automation_editor_screen.dart';
import '../features/scenes/scene_editor_screen.dart';
import '../features/scenes/scenes_screen.dart';
import '../features/security/security_screen.dart';
import '../features/security/sos_screen.dart';
import '../features/shell/main_shell.dart';
import 'providers/auth_provider.dart';

/// Route names/paths used across the app.
class Routes {
  Routes._();

  static const splash = '/splash';
  static const login = '/login';
  static const register = '/register';
  static const home = '/';
  static const rooms = '/rooms';
  static const scenes = '/scenes';
  static const sceneNew = '/scenes/new';
  static const automationNew = '/scenes/automations/new';
  static const security = '/security';
  static const sos = '/security/sos';
  static const me = '/me';
  static const profile = '/me/profile';
  static const homes = '/me/homes';
  static const messages = '/me/messages';
  static const settings = '/me/settings';
  static const about = '/me/about';
  static const integrations = '/me/integrations';
  static const addDevice = '/add-device';
  static const scan = '/add-device/scan';

  static String scene(String id) => '/scenes/$id';
  static String automation(String id) => '/scenes/automations/$id';
  static String members(String homeId) => '/me/homes/$homeId/members';
  static String device(String id) => '/devices/$id';
  static String deviceSettings(String id) => '/devices/$id/settings';
  static String pair(String brandId, {String? method}) => '/add-device/$brandId${method == null ? '' : '?method=$method'}';
}

final _rootKey = GlobalKey<NavigatorState>(debugLabel: 'root');

/// Router that redirects according to the auth state.
final routerProvider = Provider<GoRouter>((ref) {
  final listenable = ValueNotifier<AuthStatus>(ref.read(authProvider).status);
  ref.listen<AuthState>(authProvider, (_, next) => listenable.value = next.status);
  ref.onDispose(listenable.dispose);

  return GoRouter(
    navigatorKey: _rootKey,
    initialLocation: Routes.splash,
    refreshListenable: listenable,
    debugLogDiagnostics: false,
    redirect: (context, state) {
      final status = ref.read(authProvider).status;
      final location = state.matchedLocation;
      final onAuthPage = location == Routes.login || location == Routes.register;
      if (status == AuthStatus.unknown) return location == Routes.splash ? null : Routes.splash;
      if (status == AuthStatus.unauthenticated) return onAuthPage ? null : Routes.login;
      if (onAuthPage || location == Routes.splash) return Routes.home;
      return null;
    },
    routes: [
      GoRoute(path: Routes.splash, builder: (_, __) => const SplashScreen()),
      GoRoute(path: Routes.login, builder: (_, __) => const LoginScreen()),
      GoRoute(path: Routes.register, builder: (_, __) => const RegisterScreen()),
      StatefulShellRoute.indexedStack(
        builder: (context, state, navigationShell) => MainShell(navigationShell: navigationShell),
        branches: [
          StatefulShellBranch(routes: [
            GoRoute(path: Routes.home, builder: (_, __) => const HomeScreen(), routes: [
              GoRoute(path: 'rooms', builder: (_, __) => const RoomManagementScreen()),
            ]),
          ]),
          StatefulShellBranch(routes: [
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
          ]),
          StatefulShellBranch(routes: [
            GoRoute(path: Routes.security, builder: (_, __) => const SecurityScreen(), routes: [
              GoRoute(path: 'sos', parentNavigatorKey: _rootKey, builder: (_, __) => const SosScreen()),
            ]),
          ]),
          StatefulShellBranch(routes: [
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
          ]),
        ],
      ),
      // Full-screen flows outside the bottom navigation
      GoRoute(path: Routes.addDevice, parentNavigatorKey: _rootKey, builder: (_, __) => const BrandCatalogScreen(), routes: [
        GoRoute(path: 'scan', parentNavigatorKey: _rootKey, builder: (_, __) => const QrScanScreen()),
        GoRoute(
          path: ':brand',
          parentNavigatorKey: _rootKey,
          builder: (_, state) => PairingWizardScreen(
            brandId: state.pathParameters['brand']!,
            method: state.uri.queryParameters['method'],
            prefill: state.extra is Map<String, dynamic> ? state.extra as Map<String, dynamic> : null,
          ),
        ),
      ]),
      GoRoute(path: '/devices/:id', parentNavigatorKey: _rootKey, builder: (_, state) => DeviceDetailScreen(deviceId: state.pathParameters['id']!), routes: [
        GoRoute(path: 'settings', parentNavigatorKey: _rootKey, builder: (_, state) => DeviceSettingsScreen(deviceId: state.pathParameters['id']!)),
      ]),
    ],
  );
});
