import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../routes.dart';

/// Forced states of the demo hub, selectable with `?state=a,b` on the web
/// build (`docs/qa/screenshot-harness.md` §3 documents each one). The names
/// are the public contract of the capture harness: renaming one is a
/// breaking change for `mobile/tool/screenshots/routes.json`.
enum DemoState {
  /// No session: the router lands on `/login`.
  loggedOut,

  /// Every hub call fails with "Impossible de joindre le hub" (`failNetwork`).
  offline,

  /// The user has no home (`noHomes`).
  noHomes,

  /// The home has no device at all.
  noDevices,

  /// The weather endpoint reports `available: false`.
  noWeather,

  /// The signed-in user is a plain member (no admin affordances).
  member,

  /// Security mode armed away.
  armedAway,

  /// Security mode armed home.
  armedHome,

  /// Security mode armed night.
  armedNight,

  /// Alarm active, blamed on the hallway motion sensor.
  alarm,

  /// Front door and living-room zone reported open (arming warning).
  openings,

  /// The living-room lamp and the entrance camera are offline.
  offlineDevices,

  /// No scene in the home.
  noScenes,

  /// No automation in the home.
  noAutomations,

  /// No message in the message centre (and no unread badge).
  noMessages,

  /// Camera streams are protected (`auth_required` without credentials).
  protectedStreams,

  /// Two SOS alerts already exist (one open, one resolved).
  sosAlerts,

  /// Location permission denied: SOS alerts carry no position.
  locationDenied,

  /// GET /homes/{id}/devices fails with a network error.
  failDevices,

  /// GET /homes/{id}/weather fails with a 502.
  failWeather,

  /// GET /homes/{id}/security fails with a network error.
  failSecurity,

  /// GET /homes/{id}/scenes fails with a 500.
  failScenes,

  /// GET /homes/{id}/messages/unread-count fails with a 503.
  failUnread;

  /// Parses `?state=a,b` (unknown names are ignored and logged).
  static Set<DemoState> parseList(String? raw) {
    final result = <DemoState>{};
    if (raw == null || raw.trim().isEmpty) return result;
    for (final part in raw.split(',')) {
      final name = part.trim();
      if (name.isEmpty) continue;
      final match = values.where((s) => s.name.toLowerCase() == name.toLowerCase()).firstOrNull;
      if (match == null) {
        debugPrint('Demo: unknown state "$name" ignored (known: ${values.map((s) => s.name).join(', ')})');
        continue;
      }
      result.add(match);
    }
    return result;
  }
}

/// Startup hooks of the demo build, read once from the page URL on the web
/// (`Uri.base.queryParameters`) and left at their defaults everywhere else.
///
/// | Query parameter | Values | Default |
/// |---|---|---|
/// | `locale` | `fr`, `en` | `fr` |
/// | `theme` | `light`, `dark` | `light` |
/// | `textScale` | `1.0`, `1.3`, `2.0` (any 0.5–3.0) | `1.0` |
/// | `route` | an app location, e.g. `/security/sos` | `/` |
/// | `state` | comma list of [DemoState] names | none |
/// | `animations` | `off` | on |
@immutable
class DemoOptions {
  const DemoOptions({
    this.locale = const Locale('fr'),
    this.themeMode = ThemeMode.light,
    this.textScale = 1.0,
    this.route = Routes.home,
    this.states = const {},
    this.animationsOff = false,
  });

  /// Defaults: French, light, no scaling, Home, no forced state.
  static const DemoOptions defaults = DemoOptions();

  final Locale locale;
  final ThemeMode themeMode;
  final double textScale;

  /// Initial location once the session is restored (path plus optional query).
  final String route;
  final Set<DemoState> states;

  /// Disable animations (MediaQuery hint + time dilation) for stable captures.
  final bool animationsOff;

  bool has(DemoState state) => states.contains(state);

  /// Options for the current platform: the page URL on the web, [defaults]
  /// on every other platform (there is no query string to read).
  static DemoOptions resolve() => kIsWeb ? DemoOptions.fromUri(Uri.base) : defaults;

  /// Parses the capture hooks from [uri]'s query string; anything missing or
  /// invalid falls back to the default.
  factory DemoOptions.fromUri(Uri uri) {
    final q = uri.queryParameters;
    final locale = switch (q['locale']?.toLowerCase()) {
      'en' => const Locale('en'),
      _ => const Locale('fr'),
    };
    final themeMode = q['theme']?.toLowerCase() == 'dark' ? ThemeMode.dark : ThemeMode.light;
    final scale = double.tryParse(q['textScale'] ?? '') ?? 1.0;
    final route = q['route'];
    return DemoOptions(
      locale: locale,
      themeMode: themeMode,
      textScale: scale.clamp(0.5, 3.0).toDouble(),
      route: route != null && route.startsWith('/') ? route : Routes.home,
      states: DemoState.parseList(q['state']),
      animationsOff: q['animations']?.toLowerCase() == 'off',
    );
  }

  @override
  String toString() =>
      'DemoOptions(locale: ${locale.languageCode}, theme: ${themeMode.name}, textScale: $textScale, route: $route, states: ${states.map((s) => s.name).join(',')}, animationsOff: $animationsOff)';
}
