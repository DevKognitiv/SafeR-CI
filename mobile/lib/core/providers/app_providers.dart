import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/hub_client.dart';
import '../config.dart';
import '../storage.dart';

/// Persistent storage — overridden in main() once SharedPreferences is ready.
final storageProvider = Provider<AppStorage>((ref) => throw UnimplementedError('storageProvider must be overridden'));

/// Hub base URL (user override from settings > build-time default).
class HubUrlNotifier extends Notifier<String> {
  @override
  String build() => ref.watch(storageProvider).hubUrl ?? AppConfig.defaultHubUrl;

  Future<void> set(String? url) async {
    final value = (url ?? '').trim();
    await ref.read(storageProvider).setHubUrl(value.isEmpty ? null : value);
    state = value.isEmpty ? AppConfig.defaultHubUrl : value;
  }
}

final hubUrlProvider = NotifierProvider<HubUrlNotifier, String>(HubUrlNotifier.new);

/// Session token kept in memory + storage.
class TokenNotifier extends Notifier<String?> {
  @override
  String? build() => ref.watch(storageProvider).token;

  Future<void> set(String? token) async {
    state = token;
    await ref.read(storageProvider).setToken(token);
  }
}

final tokenProvider = NotifierProvider<TokenNotifier, String?>(TokenNotifier.new);

/// Typed API client. Reads the token lazily so it never needs to be rebuilt on login.
final hubClientProvider = Provider<HubClient>((ref) {
  final url = ref.watch(hubUrlProvider);
  return HubClient(baseUrl: url, tokenProvider: () => ref.read(tokenProvider));
});

/// App locale (null = follow system, resolved against supported locales).
class LocaleNotifier extends Notifier<Locale?> {
  @override
  Locale? build() {
    final code = ref.watch(storageProvider).locale;
    return code == null ? null : Locale(code);
  }

  Future<void> set(Locale? locale) async {
    state = locale;
    await ref.read(storageProvider).setLocale(locale?.languageCode);
  }
}

final localeProvider = NotifierProvider<LocaleNotifier, Locale?>(LocaleNotifier.new);

class ThemeModeNotifier extends Notifier<ThemeMode> {
  @override
  ThemeMode build() {
    switch (ref.watch(storageProvider).themeMode) {
      case 'light':
        return ThemeMode.light;
      case 'dark':
        return ThemeMode.dark;
      default:
        return ThemeMode.system;
    }
  }

  Future<void> set(ThemeMode mode) async {
    state = mode;
    await ref.read(storageProvider).setThemeMode(mode.name);
  }
}

final themeModeProvider = NotifierProvider<ThemeModeNotifier, ThemeMode>(ThemeModeNotifier.new);

/// Set to false in widget tests to avoid opening real WebSockets.
final realtimeEnabledProvider = Provider<bool>((ref) => true);
