import 'package:shared_preferences/shared_preferences.dart';

/// Thin wrapper over SharedPreferences for the few things the app persists.
class AppStorage {
  AppStorage(this._prefs);

  final SharedPreferences _prefs;

  static const _kToken = 'safer.token';
  static const _kHomeId = 'safer.home_id';
  static const _kLocale = 'safer.locale';
  static const _kHubUrl = 'safer.hub_url';
  static const _kThemeMode = 'safer.theme_mode';
  static const _kOnboarded = 'safer.onboarded';

  static Future<AppStorage> create() async => AppStorage(await SharedPreferences.getInstance());

  String? get token => _prefs.getString(_kToken);
  Future<void> setToken(String? value) => _set(_kToken, value);

  String? get currentHomeId => _prefs.getString(_kHomeId);
  Future<void> setCurrentHomeId(String? value) => _set(_kHomeId, value);

  String? get locale => _prefs.getString(_kLocale);
  Future<void> setLocale(String? value) => _set(_kLocale, value);

  String? get hubUrl => _prefs.getString(_kHubUrl);
  Future<void> setHubUrl(String? value) => _set(_kHubUrl, value);

  String? get themeMode => _prefs.getString(_kThemeMode);
  Future<void> setThemeMode(String? value) => _set(_kThemeMode, value);

  bool get onboarded => _prefs.getBool(_kOnboarded) ?? false;
  Future<void> setOnboarded(bool value) => _prefs.setBool(_kOnboarded, value);

  Future<void> clearSession() async {
    await _prefs.remove(_kToken);
    await _prefs.remove(_kHomeId);
  }

  Future<void> _set(String key, String? value) async {
    if (value == null || value.isEmpty) {
      await _prefs.remove(key);
    } else {
      await _prefs.setString(key, value);
    }
  }
}
