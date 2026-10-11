/// `signalDemoReady()` / `signalDemoError()`: the web build sets
/// `window.saferReady` / `window.saferError` for the capture harness; every
/// other platform gets the no-op stub.
library;

export 'ready_signal_stub.dart' if (dart.library.js_interop) 'ready_signal_web.dart';
