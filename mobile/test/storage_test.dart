import 'package:flutter/services.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:safer_ci/core/storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// In-memory secure store whose next write can be made to fail once (a transient keystore
/// error), or whose every call throws a non-platform error (the web plugin on an insecure origin).
class _FlakySecureStorage extends FlutterSecureStorage {
  _FlakySecureStorage({this.throwAlways = false});

  final Map<String, String> values = {};
  final bool throwAlways;
  bool failNextWrite = false;
  int deleteCalls = 0;

  @override
  Future<String?> read({
    required String key,
    IOSOptions? iOptions,
    AndroidOptions? aOptions,
    LinuxOptions? lOptions,
    WebOptions? webOptions,
    MacOsOptions? mOptions,
    WindowsOptions? wOptions,
  }) async {
    if (throwAlways) throw StateError('crypto.subtle is undefined');
    return values[key];
  }

  @override
  Future<void> write({
    required String key,
    required String? value,
    IOSOptions? iOptions,
    AndroidOptions? aOptions,
    LinuxOptions? lOptions,
    WebOptions? webOptions,
    MacOsOptions? mOptions,
    WindowsOptions? wOptions,
  }) async {
    if (throwAlways) throw StateError('crypto.subtle is undefined');
    if (failNextWrite) {
      failNextWrite = false;
      throw PlatformException(code: 'keystore', message: 'AEADBadTagException');
    }
    values[key] = value ?? '';
  }

  @override
  Future<void> delete({
    required String key,
    IOSOptions? iOptions,
    AndroidOptions? aOptions,
    LinuxOptions? lOptions,
    WebOptions? webOptions,
    MacOsOptions? mOptions,
    WindowsOptions? wOptions,
  }) async {
    deleteCalls++;
    if (throwAlways) throw StateError('crypto.subtle is undefined');
    values.remove(key);
  }
}

/// Secure store whose platform plugin fails (unsupported platform, broken keystore).
/// With [failReads] false, reads answer "nothing stored" and only writes fail.
class _BrokenSecureStorage extends FlutterSecureStorage {
  const _BrokenSecureStorage({this.failReads = true});

  final bool failReads;

  static Never _fail() => throw PlatformException(code: 'unsupported_platform');

  @override
  Future<String?> read({
    required String key,
    IOSOptions? iOptions,
    AndroidOptions? aOptions,
    LinuxOptions? lOptions,
    WebOptions? webOptions,
    MacOsOptions? mOptions,
    WindowsOptions? wOptions,
  }) async =>
      failReads ? _fail() : null;

  @override
  Future<void> write({
    required String key,
    required String? value,
    IOSOptions? iOptions,
    AndroidOptions? aOptions,
    LinuxOptions? lOptions,
    WebOptions? webOptions,
    MacOsOptions? mOptions,
    WindowsOptions? wOptions,
  }) async =>
      _fail();

  @override
  Future<void> delete({
    required String key,
    IOSOptions? iOptions,
    AndroidOptions? aOptions,
    LinuxOptions? lOptions,
    WebOptions? webOptions,
    MacOsOptions? mOptions,
    WindowsOptions? wOptions,
  }) async =>
      _fail();
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const secure = FlutterSecureStorage();

  Future<Map<String, Object>> prefsDump() async {
    final prefs = await SharedPreferences.getInstance();
    return {for (final key in prefs.getKeys()) key: prefs.get(key)!};
  }

  group('AppStorage', () {
    test('keeps the token and the hub URL in secure storage, never in SharedPreferences', () async {
      SharedPreferences.setMockInitialValues({});
      FlutterSecureStorage.setMockInitialValues({});
      final storage = await AppStorage.create();
      expect(storage.secureStorageAvailable, isTrue);
      expect(storage.token, isNull);
      expect(storage.hubUrl, isNull);

      await storage.setToken('jwt-secret');
      await storage.setHubUrl('https://hub.example.com');
      await storage.setCurrentHomeId('home-1');
      await storage.setLocale('fr');

      expect(storage.token, 'jwt-secret');
      expect(storage.hubUrl, 'https://hub.example.com');
      expect(await secure.read(key: AppStorage.tokenKey), 'jwt-secret');
      expect(await secure.read(key: AppStorage.hubUrlKey), 'https://hub.example.com');

      final prefs = await prefsDump();
      expect(prefs.keys, isNot(contains(AppStorage.tokenKey)));
      expect(prefs.keys, isNot(contains(AppStorage.hubUrlKey)));
      expect(prefs.values, isNot(contains('jwt-secret')));
      expect(prefs['safer.home_id'], 'home-1');
      expect(prefs['safer.locale'], 'fr');

      // A fresh instance reads the secrets back from the secure store.
      final reloaded = await AppStorage.create();
      expect(reloaded.token, 'jwt-secret');
      expect(reloaded.hubUrl, 'https://hub.example.com');
    });

    test('moves legacy secrets from SharedPreferences to secure storage once', () async {
      SharedPreferences.setMockInitialValues({
        AppStorage.tokenKey: 'legacy-token',
        AppStorage.hubUrlKey: 'http://192.168.1.20:8000',
        'safer.home_id': 'home-1',
      });
      FlutterSecureStorage.setMockInitialValues({});
      final storage = await AppStorage.create();

      expect(storage.token, 'legacy-token');
      expect(storage.hubUrl, 'http://192.168.1.20:8000');
      expect(storage.currentHomeId, 'home-1');
      expect(await secure.read(key: AppStorage.tokenKey), 'legacy-token');
      expect(await secure.read(key: AppStorage.hubUrlKey), 'http://192.168.1.20:8000');

      final prefs = await prefsDump();
      expect(prefs.keys, isNot(contains(AppStorage.tokenKey)));
      expect(prefs.keys, isNot(contains(AppStorage.hubUrlKey)));
      expect(prefs['safer.home_id'], 'home-1');
    });

    test('a secret already in secure storage wins over a stale legacy value, which is still deleted', () async {
      SharedPreferences.setMockInitialValues({AppStorage.tokenKey: 'stale-token'});
      FlutterSecureStorage.setMockInitialValues({AppStorage.tokenKey: 'current-token'});
      final storage = await AppStorage.create();
      expect(storage.token, 'current-token');
      expect(await secure.read(key: AppStorage.tokenKey), 'current-token');
      expect((await prefsDump()).keys, isNot(contains(AppStorage.tokenKey)));
    });

    test('clearSession clears the token and the current home but keeps the hub URL and preferences', () async {
      SharedPreferences.setMockInitialValues({'safer.home_id': 'home-1', 'safer.locale': 'en'});
      FlutterSecureStorage.setMockInitialValues({AppStorage.tokenKey: 'jwt-secret', AppStorage.hubUrlKey: 'https://hub.example.com'});
      final storage = await AppStorage.create();
      expect(storage.token, 'jwt-secret');

      await storage.clearSession();
      expect(storage.token, isNull);
      expect(storage.currentHomeId, isNull);
      expect(storage.hubUrl, 'https://hub.example.com');
      expect(storage.locale, 'en');
      expect(await secure.read(key: AppStorage.tokenKey), isNull);
      expect(await secure.read(key: AppStorage.hubUrlKey), 'https://hub.example.com');
    });

    test('setToken(null) and empty values delete the secret', () async {
      SharedPreferences.setMockInitialValues({});
      FlutterSecureStorage.setMockInitialValues({AppStorage.tokenKey: 'jwt-secret'});
      final storage = await AppStorage.create();
      await storage.setToken('');
      expect(storage.token, isNull);
      expect(await secure.read(key: AppStorage.tokenKey), isNull);
    });

    test('falls back to memory for the session when the secure store throws', () async {
      SharedPreferences.setMockInitialValues({AppStorage.tokenKey: 'legacy-token'});
      final storage = await AppStorage.create(secure: const _BrokenSecureStorage());
      expect(storage.secureStorageAvailable, isFalse);
      // The legacy value is still migrated out of SharedPreferences (into memory).
      expect(storage.token, 'legacy-token');
      expect((await prefsDump()).keys, isNot(contains(AppStorage.tokenKey)));

      await storage.setToken('new-token');
      await storage.setHubUrl('https://hub.example.com');
      expect(storage.token, 'new-token');
      expect(storage.hubUrl, 'https://hub.example.com');
      final prefs = await prefsDump();
      expect(prefs.keys, isNot(contains(AppStorage.tokenKey)));
      expect(prefs.keys, isNot(contains(AppStorage.hubUrlKey)));
      expect(prefs.values, isNot(contains('new-token')));

      await storage.clearSession();
      expect(storage.token, isNull);
    });

    test('a transient write failure never disables the later writes and deletes', () async {
      SharedPreferences.setMockInitialValues({});
      final plugin = _FlakySecureStorage();
      final storage = await AppStorage.create(secure: plugin);
      await storage.setToken('jwt-secret');
      expect(plugin.values[AppStorage.tokenKey], 'jwt-secret');
      plugin.failNextWrite = true;
      await storage.setHubUrl('https://hub.example.com');
      expect(storage.secureStorageAvailable, isFalse);
      expect(storage.hubUrl, 'https://hub.example.com'); // kept in memory for the session
      // Logging out after the hiccup still deletes the persisted token: the next launch must not restore it.
      await storage.clearSession();
      expect(plugin.deleteCalls, 1);
      expect(plugin.values.containsKey(AppStorage.tokenKey), isFalse);
      expect(storage.secureStorageAvailable, isTrue);
      final relaunch = await AppStorage.create(secure: plugin);
      expect(relaunch.token, isNull);
    });

    test('any plugin error, not only a platform exception, falls back to memory', () async {
      SharedPreferences.setMockInitialValues({AppStorage.tokenKey: 'legacy-token'});
      final storage = await AppStorage.create(secure: _FlakySecureStorage(throwAlways: true));
      expect(storage.secureStorageAvailable, isFalse);
      expect(storage.token, 'legacy-token');
      await storage.setToken('jwt-secret'); // must not throw
      expect(storage.token, 'jwt-secret');
      await storage.clearSession();
      expect(storage.token, isNull);
      expect((await prefsDump()).values, isNot(contains('jwt-secret')));
    });

    test('a write failure after startup also falls back to memory', () async {
      SharedPreferences.setMockInitialValues({});
      final storage = await AppStorage.create(secure: const _BrokenSecureStorage(failReads: false));
      expect(storage.secureStorageAvailable, isTrue);
      await storage.setToken('jwt-secret');
      expect(storage.token, 'jwt-secret');
      expect(storage.secureStorageAvailable, isFalse);
      expect((await prefsDump()).values, isNot(contains('jwt-secret')));
    });
  });
}
