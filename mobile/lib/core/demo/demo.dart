/// In-app demo mode (`--dart-define=SAFER_DEMO=1`): the app boots on an
/// in-memory hub with a signed-in session, and the web build reads capture
/// hooks from the page URL. See `docs/qa/screenshot-harness.md`.
library;

export 'demo_config.dart';
export 'demo_frame.dart';
export 'demo_hub_client.dart';
export 'demo_options.dart';
export 'demo_overrides.dart';
export 'demo_session.dart';
export 'fake_hub_client.dart';
