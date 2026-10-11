import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// The few things the app persists.
///
/// Secrets (the session token and the hub URL) live in the platform secure
/// storage (Android EncryptedSharedPreferences backed by the keystore, iOS
/// keychain, WebCrypto-encrypted localStorage on the web). They are loaded once
/// in [create] and cached in memory so the getters stay synchronous; writes go
/// to secure storage. Plain preferences (current home, locale, theme,
/// onboarding flag) stay in [SharedPreferences].
///
/// A build that predates secure storage left the token and the hub URL in
/// [SharedPreferences]; [create] moves them over once and deletes the legacy
/// keys. When the secure storage plugin is unavailable (unsupported platform,
/// broken keystore) the values are kept in memory for the session only and a
/// single warning is logged: the token is never written to plain preferences.
class AppStorage {
  AppStorage._(this._prefs, this._secure, {required String? token, required String? hubUrl, required bool secureAvailable})
      : _token = token,
        _hubUrl = hubUrl,
        _secureAvailable = secureAvailable;

  final SharedPreferences _prefs;
  final FlutterSecureStorage _secure;

  String? _token;
  String? _hubUrl;
  bool _secureAvailable;

  /// Secure-storage key of the session token (also the legacy preference key).
  static const String tokenKey = 'safer.token';

  /// Secure-storage key of the hub URL (also the legacy preference key).
  static const String hubUrlKey = 'safer.hub_url';

  static const _kHomeId = 'safer.home_id';
  static const _kLocale = 'safer.locale';
  static const _kThemeMode = 'safer.theme_mode';
  static const _kOnboarded = 'safer.onboarded';

  /// Platform options of the secure store: keystore-backed encrypted
  /// preferences on Android, keychain items readable after the first unlock on
  /// Apple platforms (so a background relaunch can restore the session).
  static const FlutterSecureStorage defaultSecureStorage = FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
    iOptions: IOSOptions(accessibility: KeychainAccessibility.first_unlock),
    mOptions: MacOsOptions(accessibility: KeychainAccessibility.first_unlock),
  );

  /// Loads the preferences and the secrets (running the one-time migration).
  ///
  /// [prefs] and [secure] are injectable for tests; production uses the
  /// platform instances.
  static Future<AppStorage> create({SharedPreferences? prefs, FlutterSecureStorage? secure}) async {
    final preferences = prefs ?? await SharedPreferences.getInstance();
    final store = secure ?? defaultSecureStorage;
    var available = true;
    String? token;
    String? hubUrl;
    try {
      token = await store.read(key: tokenKey);
      hubUrl = await store.read(key: hubUrlKey);
    } on PlatformException catch (e) {
      available = false;
      _warnOnce(e);
    } on MissingPluginException catch (e) {
      available = false;
      _warnOnce(e);
    }

    // One-time migration from the previous build (secrets in SharedPreferences).
    final legacyToken = preferences.getString(tokenKey);
    final legacyHubUrl = preferences.getString(hubUrlKey);
    if (legacyToken != null) {
      token ??= legacyToken;
      await preferences.remove(tokenKey);
    }
    if (legacyHubUrl != null) {
      hubUrl ??= legacyHubUrl;
      await preferences.remove(hubUrlKey);
    }
    final storage = AppStorage._(preferences, store, token: token, hubUrl: hubUrl, secureAvailable: available);
    if (available) {
      if (legacyToken != null && token == legacyToken) await storage._writeSecure(tokenKey, legacyToken);
      if (legacyHubUrl != null && hubUrl == legacyHubUrl) await storage._writeSecure(hubUrlKey, legacyHubUrl);
    }
    return storage;
  }

  /// False when the platform secure store failed and the secrets only live in
  /// memory for this session.
  bool get secureStorageAvailable => _secureAvailable;

  String? get token => _token;
  Future<void> setToken(String? value) async {
    _token = _normalize(value);
    await _writeSecure(tokenKey, _token);
  }

  String? get hubUrl => _hubUrl;
  Future<void> setHubUrl(String? value) async {
    _hubUrl = _normalize(value);
    await _writeSecure(hubUrlKey, _hubUrl);
  }

  String? get currentHomeId => _prefs.getString(_kHomeId);
  Future<void> setCurrentHomeId(String? value) => _set(_kHomeId, value);

  String? get locale => _prefs.getString(_kLocale);
  Future<void> setLocale(String? value) => _set(_kLocale, value);

  String? get themeMode => _prefs.getString(_kThemeMode);
  Future<void> setThemeMode(String? value) => _set(_kThemeMode, value);

  bool get onboarded => _prefs.getBool(_kOnboarded) ?? false;
  Future<void> setOnboarded(bool value) => _prefs.setBool(_kOnboarded, value);

  /// Forgets the session: token (secure store) and current home (preferences).
  Future<void> clearSession() async {
    await setToken(null);
    await _prefs.remove(_kHomeId);
  }

  static String? _normalize(String? value) => (value == null || value.isEmpty) ? null : value;

  Future<void> _writeSecure(String key, String? value) async {
    // Belt and braces: a secret never stays in plain preferences.
    if (_prefs.containsKey(key)) await _prefs.remove(key);
    if (!_secureAvailable) return;
    try {
      if (value == null) {
        await _secure.delete(key: key);
      } else {
        await _secure.write(key: key, value: value);
      }
    } on PlatformException catch (e) {
      _secureAvailable = false;
      _warnOnce(e);
    } on MissingPluginException catch (e) {
      _secureAvailable = false;
      _warnOnce(e);
    }
  }

  Future<void> _set(String key, String? value) async {
    if (value == null || value.isEmpty) {
      await _prefs.remove(key);
    } else {
      await _prefs.setString(key, value);
    }
  }

  static bool _warned = false;

  static void _warnOnce(Object error) {
    if (_warned) return;
    _warned = true;
    debugPrint('AppStorage: secure storage unavailable, secrets are kept in memory for this session ($error)');
  }
}
