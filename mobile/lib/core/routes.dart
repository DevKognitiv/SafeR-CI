/// Route paths of the SafeR app. Kept apart from `router.dart` so feature
/// screens can reference paths without importing every other screen.
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
