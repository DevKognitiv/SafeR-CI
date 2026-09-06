import 'package:flutter/material.dart';

import '../../../core/i18n.dart';
import 'capability_slider.dart';

/// Colour from a Tuya-style HSV map ({"h": 0-360, "s": 0-100, "v": 0-100}).
Color colorFromHsv(Map<String, dynamic>? hsv, {Color fallback = Colors.white}) {
  if (hsv == null) return fallback;
  final h = (hsv['h'] as num?)?.toDouble() ?? 0;
  final s = (hsv['s'] as num?)?.toDouble() ?? 100;
  final v = (hsv['v'] as num?)?.toDouble() ?? 100;
  return HSVColor.fromAHSV(1, h.clamp(0, 360).toDouble() % 360, (s / 100).clamp(0, 1).toDouble(), (v / 100).clamp(0, 1).toDouble()).toColor();
}

/// Hue gradient slider + saturation slider with a live preview swatch.
class HueSaturationPicker extends StatelessWidget {
  const HueSaturationPicker({super.key, required this.hue, required this.saturation, required this.value, required this.onChanged, this.enabled = true});

  final int hue;
  final int saturation;
  final int value;
  final void Function(int hue, int saturation) onChanged;

  /// False disables both sliders (offline device).
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final pure = HSVColor.fromAHSV(1, hue.toDouble() % 360, 1, 1).toColor();
    final current = colorFromHsv({'h': hue, 's': saturation, 'v': value});
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(color: current, shape: BoxShape.circle, border: Border.all(color: theme.colorScheme.outlineVariant, width: 2)),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                context.tr(fr: 'Teinte $hue° · Saturation $saturation%', en: 'Hue $hue° · Saturation $saturation%'),
                style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant),
              ),
            ),
          ],
        ),
        const SizedBox(height: 8),
        CapabilitySlider(
          key: const Key('slider-hue'),
          label: context.tr(fr: 'Teinte', en: 'Hue'),
          icon: Icons.palette_outlined,
          value: hue.toDouble(),
          min: 0,
          max: 360,
          divisions: 360,
          unit: '°',
          gradient: kHueGradient,
          enabled: enabled,
          onCommit: (v) => onChanged(v.round(), saturation),
        ),
        CapabilitySlider(
          key: const Key('slider-saturation'),
          label: context.tr(fr: 'Saturation', en: 'Saturation'),
          icon: Icons.opacity,
          value: saturation.toDouble(),
          min: 0,
          max: 100,
          divisions: 100,
          unit: '%',
          gradient: LinearGradient(colors: [Colors.white, pure]),
          enabled: enabled,
          onCommit: (v) => onChanged(hue, v.round()),
        ),
      ],
    );
  }
}
