import 'package:flutter/material.dart';

import '../../../core/theme.dart';

/// Icon names offered by the scene editor (all resolvable through `iconFromName`).
const List<String> kSceneIconNames = [
  'play_circle',
  'bedtime',
  'wb_twilight',
  'movie',
  'celebration',
  'flight_takeoff',
  'directions_walk',
  'home',
  'bolt',
  'auto_awesome',
  'shield',
  'lightbulb',
];

/// Preset colours offered by the scene editor (hex strings as stored by the hub).
const List<String> kSceneColors = ['#2563EB', '#7C3AED', '#DC2626', '#EA580C', '#16A34A', '#0891B2', '#DB2777', '#475569'];

/// Parse a `#RRGGBB` / `#AARRGGBB` string sent by the hub.
Color colorFromHex(String? hex, {Color fallback = SafeRColors.primary}) {
  if (hex == null || hex.trim().isEmpty) return fallback;
  var digits = hex.trim().replaceFirst('#', '');
  if (digits.length == 3) digits = digits.split('').map((c) => '$c$c').join();
  if (digits.length == 6) digits = 'FF$digits';
  if (digits.length != 8) return fallback;
  final value = int.tryParse(digits, radix: 16);
  return value == null ? fallback : Color(value);
}
