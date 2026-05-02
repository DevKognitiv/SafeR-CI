import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import 'screens/home_screen.dart';
import 'screens/sos_screen.dart';
import 'screens/map_screen.dart';
import 'screens/alerts_screen.dart';
import 'screens/profile_screen.dart';
import 'core/theme.dart';
import 'core/router.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const ProviderScope(child: SafeRApp()));
}

class SafeRApp extends StatelessWidget {
  const SafeRApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: 'SafeR CI',
      debugShowCheckedModeBanner: false,
      theme: SafeRTheme.lightTheme,
      darkTheme: SafeRTheme.darkTheme,
      themeMode: ThemeMode.system,
      routerConfig: appRouter,
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: const [
        Locale('fr', 'CI'), // Côte d'Ivoire French (primary)
        Locale('fr', ''),   // French fallback
        Locale('en', ''),   // English fallback
      ],
      locale: const Locale('fr', 'CI'),
    );
  }
}
