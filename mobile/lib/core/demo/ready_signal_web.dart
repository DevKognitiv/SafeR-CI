import 'dart:js_interop';

/// Web implementation of the capture readiness signal.
///
/// Playwright waits for `window.saferReady === true` before taking a
/// screenshot; `window.saferError` carries the first uncaught error so a
/// broken variant fails the capture with a message instead of a blank PNG.
/// Top-level JS interop members bind to `globalThis`, which is `window` in a
/// browser, so no extra package is needed.
@JS('saferReady')
external set _saferReady(JSBoolean value);

@JS('saferError')
external set _saferError(JSString value);

void signalDemoReady() => _saferReady = true.toJS;

void signalDemoError(String message) => _saferError = message.toJS;
