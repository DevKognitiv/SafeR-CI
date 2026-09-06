/// Build-time configuration for the SafeR app.
///
/// Override the hub URL at build/run time:
///   flutter run --dart-define=SAFER_HUB_URL=http://10.0.2.2:8000   (Android emulator)
///   flutter run --dart-define=SAFER_HUB_URL=http://192.168.1.20:8000 (device on the LAN)
class AppConfig {
  AppConfig._();

  static const String appName = 'SafeR';
  static const String version = '0.2.0';

  /// Base URL of the SafeR API (the hub is mounted under [apiPrefix]).
  static const String defaultHubUrl = String.fromEnvironment(
    'SAFER_HUB_URL',
    defaultValue: 'http://localhost:8000',
  );

  static const String apiPrefix = '/api/v1/hub';

  /// Emergency numbers for Côte d'Ivoire (shown on the SOS screen).
  static const List<({String number, String label})> emergencyNumbers = [
    (number: '170', label: 'Police'),
    (number: '180', label: 'Pompiers'),
    (number: '185', label: 'SAMU'),
    (number: '111', label: 'Gendarmerie'),
  ];
}
