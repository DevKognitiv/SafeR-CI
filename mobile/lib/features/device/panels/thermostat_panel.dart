import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/i18n.dart';
import '../../../core/models/device.dart';
import '../../../core/theme.dart';
import '../widgets/capability_format.dart';
import '../widgets/device_command.dart';
import '../widgets/generic_controls.dart';
import '../widgets/info_rows.dart';
import '../widgets/mode_selector.dart';
import '../widgets/panel_card.dart';

/// Thermostat: current temperature, setpoint stepper, mode chips and humidity.
class ThermostatPanel extends ConsumerWidget {
  const ThermostatPanel({super.key, required this.device});

  final Device device;

  static Color modeColor(String mode) {
    switch (mode) {
      case 'heat':
        return SafeRColors.warning;
      case 'cool':
        return SafeRColors.primary;
      case 'auto':
        return SafeRColors.success;
      default:
        return const Color(0xFF64748B);
    }
  }

  static IconData modeIcon(String mode) {
    switch (mode) {
      case 'heat':
        return Icons.local_fire_department_outlined;
      case 'cool':
        return Icons.ac_unit;
      case 'auto':
        return Icons.autorenew;
      case 'off':
        return Icons.power_settings_new;
      default:
        return Icons.thermostat;
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final current = device.numValue('temp_current');
    final setCap = writableCapability(device, 'temp_set');
    final setpoint = device.numValue('temp_set');
    final modeCap = writableCapability(device, 'mode', type: 'enum');
    final mode = device.stringValue('mode');
    final humidity = device.hasCapability('humidity_current') ? device.numValue('humidity_current') : null;
    final unit = device.capability('temp_current')?.unit ?? setCap?.unit ?? '°C';
    final step = (setCap?.step ?? 0.5).toDouble();
    final min = (setCap?.min ?? 5).toDouble();
    final max = (setCap?.max ?? 35).toDouble();
    final accent = modeColor(mode ?? '');
    final enabled = device.online && setCap != null;

    Future<void> adjust(double delta) async {
      final base = (setpoint ?? current ?? min).toDouble();
      final next = ((base + delta) / step).round() * step;
      final clamped = next.clamp(min, max);
      final value = double.parse(clamped.toStringAsFixed(2));
      if (value == setpoint) return;
      await sendDeviceCommand(context, ref, device, 'temp_set', value);
    }

    String temp(num? v) => v == null ? '—' : (v == v.roundToDouble() ? v.round().toString() : v.toStringAsFixed(1));

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        PanelCard(
          padding: const EdgeInsets.symmetric(vertical: 24, horizontal: 16),
          child: Column(
            children: [
              Container(
                width: 180,
                height: 180,
                decoration: BoxDecoration(shape: BoxShape.circle, color: accent.withValues(alpha: 0.10), border: Border.all(color: accent.withValues(alpha: 0.5), width: 6)),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text.rich(
                      TextSpan(children: [
                        TextSpan(text: temp(current), style: theme.textTheme.displaySmall?.copyWith(fontWeight: FontWeight.w800, color: theme.colorScheme.onSurface)),
                        TextSpan(text: unit, style: theme.textTheme.titleMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
                      ]),
                    ),
                    Text(context.tr(fr: 'Actuelle', en: 'Current'), style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
                  ],
                ),
              ),
              if (setCap != null) ...[
                const SizedBox(height: 20),
                Text(context.tr(fr: 'Consigne', en: 'Setpoint'), style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
                const SizedBox(height: 8),
                Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    IconButton.filledTonal(
                      tooltip: context.tr(fr: 'Diminuer', en: 'Decrease'),
                      iconSize: 28,
                      constraints: const BoxConstraints(minWidth: 56, minHeight: 56),
                      onPressed: enabled && (setpoint ?? min) > min ? () => adjust(-step) : null,
                      icon: const Icon(Icons.remove),
                    ),
                    SizedBox(
                      width: 120,
                      child: Text('${temp(setpoint)} $unit', textAlign: TextAlign.center, style: theme.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800, color: accent)),
                    ),
                    IconButton.filledTonal(
                      tooltip: context.tr(fr: 'Augmenter', en: 'Increase'),
                      iconSize: 28,
                      constraints: const BoxConstraints(minWidth: 56, minHeight: 56),
                      onPressed: enabled && (setpoint ?? max) < max ? () => adjust(step) : null,
                      icon: const Icon(Icons.add),
                    ),
                  ],
                ),
              ],
            ],
          ),
        ),
        if (modeCap != null) ...[
          const SizedBox(height: 12),
          PanelCard(
            title: context.tr(fr: 'Mode', en: 'Mode'),
            child: ModeSelector<String>(
              options: [for (final value in modeCap.values) ModeOption(value: value, label: enumValueLabel(context, value), icon: modeIcon(value), color: modeColor(value))],
              selected: mode,
              enabled: device.online,
              onSelected: (value) => sendDeviceCommand(context, ref, device, 'mode', value),
            ),
          ),
        ],
        if (humidity != null) ...[
          const SizedBox(height: 12),
          PanelCard(
            child: Row(
              children: [
                Expanded(child: ReadoutTile(value: formatNumber(humidity, decimals: 0), unit: device.capability('humidity_current')?.unit ?? '%', label: context.tr(fr: 'Humidité', en: 'Humidity'), icon: Icons.water_drop_outlined)),
              ],
            ),
          ),
        ],
        GenericControls(device: device, exclude: const {'temp_current', 'temp_set', 'mode', 'humidity_current'}),
      ],
    );
  }
}
