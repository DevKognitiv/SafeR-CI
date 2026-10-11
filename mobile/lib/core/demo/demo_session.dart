import 'package:flutter/material.dart';

import '../providers/app_providers.dart';
import '../providers/homes_provider.dart';
import 'demo_config.dart';
import 'demo_options.dart';
import 'fake_hub_client.dart';

/// Session notifiers of the demo build.
///
/// They replace the storage-backed notifiers so the demo opens signed in on
/// the demo home with the locale and theme of the capture hooks, and so that
/// nothing the demo does (logout, theme switch, home change) is ever written
/// to the device: every value lives in memory for the run.

/// Signed-in token, or none for the `loggedOut` state.
class DemoTokenNotifier extends TokenNotifier {
  DemoTokenNotifier(this._initial);

  final String? _initial;

  @override
  String? build() => _initial;

  @override
  Future<void> set(String? token) async => state = token;
}

/// The demo home is selected from the start (no "pick a home" step).
class DemoCurrentHomeIdNotifier extends CurrentHomeIdNotifier {
  DemoCurrentHomeIdNotifier(this._initial);

  final String? _initial;

  @override
  String? build() => _initial;

  @override
  void set(String? id) => state = id;
}

/// Locale forced by `?locale=` (the Settings screen can still change it for
/// the session).
class DemoLocaleNotifier extends LocaleNotifier {
  DemoLocaleNotifier(this._initial);

  final Locale _initial;

  @override
  Locale? build() => _initial;

  @override
  Future<void> set(Locale? locale) async => state = locale;
}

/// Theme forced by `?theme=`; defaults to light (never "system") so a capture
/// does not depend on the browser's colour scheme.
class DemoThemeModeNotifier extends ThemeModeNotifier {
  DemoThemeModeNotifier(this._initial);

  final ThemeMode _initial;

  @override
  ThemeMode build() => _initial;

  @override
  Future<void> set(ThemeMode mode) async => state = mode;
}

/// Token of the demo session for [options] (none when logged out).
String? demoToken(DemoOptions options) => options.has(DemoState.loggedOut) ? null : kDemoToken;

/// Current home of the demo session for [options] (none when logged out or
/// when the user has no home).
String? demoHomeId(DemoOptions options) => options.has(DemoState.loggedOut) || options.has(DemoState.noHomes) ? null : FakeHubClient.homeId;
