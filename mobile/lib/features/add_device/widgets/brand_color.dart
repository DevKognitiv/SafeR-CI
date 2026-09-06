import 'package:flutter/material.dart';

import '../../../core/theme.dart';

/// Parse a `#RRGGBB` / `#AARRGGBB` hex string sent by the hub (BrandInfo.color).
Color colorFromHex(String? hex, {Color fallback = SafeRColors.primary}) {
  if (hex == null) return fallback;
  var value = hex.trim().replaceFirst('#', '').replaceFirst('0x', '');
  if (value.length == 3) value = value.split('').map((c) => '$c$c').join();
  if (value.length == 6) value = 'FF$value';
  if (value.length != 8) return fallback;
  final parsed = int.tryParse(value, radix: 16);
  return parsed == null ? fallback : Color(parsed);
}
