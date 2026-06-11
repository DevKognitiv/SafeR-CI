import 'package:shared_preferences/shared_preferences.dart';

/// Persisted HA connection details. Token is stored in plain SharedPreferences
/// for now; a follow-up should move it to flutter_secure_storage.
class HaConnectionSettings {
  static const _kBaseUrl = 'ha.base_url';
  static const _kToken = 'ha.token';

  final String baseUrl; // e.g. https://homeassistant.local:8123
  final String token;

  const HaConnectionSettings({required this.baseUrl, required this.token});

  bool get isComplete => baseUrl.isNotEmpty && token.isNotEmpty;

  /// Base URL normalized for REST calls: scheme + host + port + any path
  /// prefix (reverse-proxy installs like https://host/homeassistant),
  /// without a trailing slash.
  String get restBase {
    final uri = Uri.parse(baseUrl);
    final port = uri.hasPort ? ':${uri.port}' : '';
    return '${uri.scheme}://${uri.host}$port${_trimmedPath(uri)}';
  }

  /// `wss://host:port[/prefix]/api/websocket` (or `ws://` for http bases).
  String get wsUrl {
    final uri = Uri.parse(baseUrl);
    final scheme = uri.scheme == 'https' ? 'wss' : 'ws';
    final port = uri.hasPort ? ':${uri.port}' : '';
    return '$scheme://${uri.host}$port${_trimmedPath(uri)}/api/websocket';
  }

  static String _trimmedPath(Uri uri) {
    var path = uri.path;
    if (path.isEmpty || path == '/') return '';
    if (path.endsWith('/')) path = path.substring(0, path.length - 1);
    return path;
  }

  static Future<HaConnectionSettings> load() async {
    final p = await SharedPreferences.getInstance();
    return HaConnectionSettings(
      baseUrl: p.getString(_kBaseUrl) ?? '',
      token: p.getString(_kToken) ?? '',
    );
  }

  Future<void> save() async {
    final p = await SharedPreferences.getInstance();
    await p.setString(_kBaseUrl, baseUrl);
    await p.setString(_kToken, token);
  }

  static Future<void> clear() async {
    final p = await SharedPreferences.getInstance();
    await p.remove(_kBaseUrl);
    await p.remove(_kToken);
  }
}
