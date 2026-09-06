import 'package:flutter/material.dart';

/// SafeR brand colours (shared with the web dashboard Tailwind config).
class SafeRColors {
  SafeRColors._();

  static const Color primary = Color(0xFF2563EB); // safer-blue
  static const Color primaryDark = Color(0xFF1D4ED8);
  static const Color danger = Color(0xFFDC2626); // safer-red
  static const Color warning = Color(0xFFEA580C); // safer-orange
  static const Color success = Color(0xFF16A34A);
  static const Color surfaceDark = Color(0xFF0F172A); // safer-dark
  static const Color cardDark = Color(0xFF1E293B);
  static const Color surfaceLight = Color(0xFFF3F4F6);
  static const Color cardLight = Colors.white;

  /// Colour for a security mode.
  static Color forSecurityMode(String mode) {
    switch (mode) {
      case 'armed_away':
        return danger;
      case 'armed_home':
        return warning;
      case 'armed_night':
        return const Color(0xFF7C3AED);
      default:
        return success;
    }
  }

  /// Colour for a message severity.
  static Color forSeverity(String severity) {
    switch (severity) {
      case 'critical':
        return danger;
      case 'warning':
        return warning;
      default:
        return primary;
    }
  }
}

/// Material 3 themes for the app.
class SafeRTheme {
  SafeRTheme._();

  static ThemeData get lightTheme => _build(Brightness.light);
  static ThemeData get darkTheme => _build(Brightness.dark);

  static ThemeData _build(Brightness brightness) {
    final dark = brightness == Brightness.dark;
    final scheme = ColorScheme.fromSeed(
      seedColor: SafeRColors.primary,
      brightness: brightness,
      primary: SafeRColors.primary,
      error: SafeRColors.danger,
      surface: dark ? SafeRColors.surfaceDark : SafeRColors.surfaceLight,
    );
    final cardColor = dark ? SafeRColors.cardDark : SafeRColors.cardLight;
    return ThemeData(
      useMaterial3: true,
      brightness: brightness,
      colorScheme: scheme,
      scaffoldBackgroundColor: scheme.surface,
      cardTheme: CardThemeData(
        color: cardColor,
        elevation: 0,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      ),
      appBarTheme: AppBarTheme(
        backgroundColor: scheme.surface,
        foregroundColor: scheme.onSurface,
        elevation: 0,
        scrolledUnderElevation: 0,
        centerTitle: false,
      ),
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: cardColor,
        indicatorColor: SafeRColors.primary.withValues(alpha: 0.15),
        labelTextStyle: WidgetStateProperty.all(const TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          minimumSize: const Size.fromHeight(48),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: cardColor,
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none),
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      ),
      chipTheme: ChipThemeData(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        side: BorderSide.none,
      ),
      snackBarTheme: const SnackBarThemeData(behavior: SnackBarBehavior.floating),
      dividerTheme: DividerThemeData(color: scheme.outlineVariant.withValues(alpha: 0.4), space: 1),
    );
  }
}
