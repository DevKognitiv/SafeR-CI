import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/i18n.dart';
import '../../../core/models/device.dart';
import '../widgets/big_power_button.dart';
import '../widgets/capability_format.dart';
import '../widgets/capability_slider.dart';
import '../widgets/device_command.dart';
import '../widgets/generic_controls.dart';
import '../widgets/hue_picker.dart';
import '../widgets/mode_selector.dart';
import '../widgets/panel_card.dart';

/// Light: power, brightness, colour temperature, hue/saturation and work mode.
class LightPanel extends ConsumerWidget {
  const LightPanel({super.key, required this.device});

  final Device device;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final on = device.boolValue('switch') ?? false;
    final switchCap = writableCapability(device, 'switch', type: 'bool');
    final brightness = writableCapability(device, 'brightness');
    final colorTemp = writableCapability(device, 'color_temp');
    final color = writableCapability(device, 'color');
    final workMode = writableCapability(device, 'work_mode', type: 'enum');
    final mode = workMode == null ? null : device.stringValue('work_mode');
    final rawColor = device.state['color'];
    final hsv = rawColor is Map ? Map<String, dynamic>.from(rawColor) : null;
    final showColorTemp = colorTemp != null && (mode == null || mode == 'white');
    final showColor = color != null && (mode == null || mode == 'colour' || mode == 'color');
    final accent = on && mode != 'white' && hsv != null ? colorFromHsv(hsv) : const Color(0xFFF59E0B);
    final enabled = device.online;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        PanelCard(
          padding: const EdgeInsets.symmetric(vertical: 28, horizontal: 16),
          child: Center(
            child: BigPowerButton(
              active: on,
              icon: Icons.lightbulb,
              activeColor: accent,
              semanticsLabel: context.tr(fr: 'Alimentation', en: 'Power'),
              caption: on ? context.tr(fr: 'ALLUMÉE', en: 'ON') : context.tr(fr: 'ÉTEINTE', en: 'OFF'),
              onPressed: enabled && switchCap != null ? () => sendDeviceCommand(context, ref, device, 'switch', !on) : null,
            ),
          ),
        ),
        if (brightness != null || workMode != null || showColorTemp || showColor) ...[
          const SizedBox(height: 12),
          PanelCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (workMode != null) ...[
                  ModeSelector<String>(
                    options: [
                      for (final value in workMode.values)
                        ModeOption(
                          value: value,
                          label: enumValueLabel(context, value),
                          icon: value == 'white'
                              ? Icons.wb_sunny_outlined
                              : value == 'colour' || value == 'color'
                                  ? Icons.palette_outlined
                                  : Icons.auto_awesome_outlined,
                        ),
                    ],
                    selected: mode,
                    enabled: enabled,
                    onSelected: (value) => sendDeviceCommand(context, ref, device, 'work_mode', value),
                  ),
                  const SizedBox(height: 16),
                ],
                if (brightness != null)
                  CapabilitySlider(
                    key: const Key('slider-brightness'),
                    label: context.tr(fr: 'Luminosité', en: 'Brightness'),
                    icon: Icons.brightness_6_outlined,
                    value: (device.numValue('brightness') ?? 0).toDouble(),
                    min: (brightness.min ?? 0).toDouble(),
                    max: (brightness.max ?? 100).toDouble(),
                    divisions: ((brightness.max ?? 100) - (brightness.min ?? 0)).round().clamp(1, 100),
                    unit: brightness.unit ?? '%',
                    enabled: enabled,
                    onCommit: (v) => sendDeviceCommand(context, ref, device, 'brightness', v.round()),
                  ),
                if (showColorTemp)
                  CapabilitySlider(
                    key: const Key('slider-color_temp'),
                    label: context.tr(fr: 'Température de couleur', en: 'Colour temperature'),
                    icon: Icons.thermostat_auto,
                    value: (device.numValue('color_temp') ?? colorTemp.min ?? 2700).toDouble(),
                    min: (colorTemp.min ?? 2700).toDouble(),
                    max: (colorTemp.max ?? 6500).toDouble(),
                    divisions: (((colorTemp.max ?? 6500) - (colorTemp.min ?? 2700)) / (colorTemp.step ?? 100)).round().clamp(1, 200),
                    unit: colorTemp.unit ?? 'K',
                    gradient: kColorTempGradient,
                    enabled: enabled,
                    onCommit: (v) => sendDeviceCommand(context, ref, device, 'color_temp', v.round()),
                  ),
                if (showColor)
                  HueSaturationPicker(
                    hue: (hsv?['h'] as num?)?.round() ?? 0,
                    saturation: (hsv?['s'] as num?)?.round() ?? 100,
                    value: (hsv?['v'] as num?)?.round() ?? (device.numValue('brightness')?.round() ?? 100),
                    onChanged: (h, s) => sendDeviceCommand(context, ref, device, 'color', {'h': h, 's': s, 'v': (hsv?['v'] as num?)?.round() ?? 100}),
                  ),
              ],
            ),
          ),
        ],
        GenericControls(device: device, exclude: const {'switch', 'brightness', 'color_temp', 'color', 'work_mode'}),
      ],
    );
  }
}
