/// Build-time switch of the in-app demo mode.
///
/// `flutter run --dart-define=SAFER_DEMO=1` (or `=true`) boots the app on an
/// in-memory hub (`DemoHubClient`) with a signed-in session, so every screen
/// can be reached without a network, a hub or an account. Without the define
/// the constant is `false` and the compiler drops the whole demo branch.
const String _demoFlag = String.fromEnvironment('SAFER_DEMO');

/// True when the app was built with `--dart-define=SAFER_DEMO=1`.
const bool kDemoMode = _demoFlag == '1' || _demoFlag == 'true';

/// Session token of the demo user (never sent anywhere: the demo client
/// ignores it).
const String kDemoToken = 'demo-token';
