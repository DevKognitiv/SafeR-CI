import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/config.dart';
import 'core/i18n.dart';
import 'core/providers/providers.dart';
import 'core/router.dart';
import 'core/theme.dart';

/// Root widget.
class SafeRApp extends ConsumerWidget {
  const SafeRApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(routerProvider);
    final locale = ref.watch(localeProvider);
    final themeMode = ref.watch(themeModeProvider);
    return MaterialApp.router(
      title: AppConfig.appName,
      debugShowCheckedModeBanner: false,
      theme: SafeRTheme.lightTheme,
      darkTheme: SafeRTheme.darkTheme,
      themeMode: themeMode,
      routerConfig: router,
      locale: locale,
      supportedLocales: kSupportedLocales,
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      localeResolutionCallback: (device, supported) {
        if (locale != null) return locale;
        if (device != null && device.languageCode == 'en') return const Locale('en');
        return const Locale('fr', 'CI');
      },
    );
  }
}
