import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/i18n.dart';
import '../../../core/models/device.dart';
import '../../../core/theme.dart';
import '../widgets/capability_slider.dart';
import '../widgets/device_command.dart';
import '../widgets/generic_controls.dart';
import '../widgets/panel_card.dart';

/// Cover / blind: open · stop · close buttons and a position slider.
class CoverPanel extends ConsumerWidget {
  const CoverPanel({super.key, required this.device});

  final Device device;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final control = writableCapability(device, 'control', type: 'enum');
    final positionCap = device.capability('position');
    final position = device.numValue('position');
    final enabled = device.online;
    final fraction = position == null ? 1.0 : (position / 100).clamp(0.0, 1.0).toDouble();

    Widget button(String value, IconData icon, String label) {
      final supported = control?.values.contains(value) ?? false;
      return Expanded(
        child: Semantics(
          button: true,
          label: label,
          child: FilledButton.tonal(
            style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(56), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14))),
            onPressed: enabled && supported ? () => sendDeviceCommand(context, ref, device, 'control', value) : null,
            child: Column(mainAxisSize: MainAxisSize.min, children: [Icon(icon), const SizedBox(height: 2), Text(label, style: const TextStyle(fontSize: 12))]),
          ),
        ),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        PanelCard(
          child: Column(
            children: [
              // Blind illustration: the covered part grows as the position decreases.
              Container(
                height: 140,
                width: 180,
                decoration: BoxDecoration(borderRadius: BorderRadius.circular(16), border: Border.all(color: theme.colorScheme.outlineVariant, width: 2), color: const Color(0xFFBFDBFE).withValues(alpha: 0.5)),
                clipBehavior: Clip.antiAlias,
                child: Align(
                  alignment: Alignment.topCenter,
                  child: AnimatedFractionallySizedBox(
                    duration: const Duration(milliseconds: 300),
                    heightFactor: 1 - fraction,
                    widthFactor: 1,
                    child: Container(
                      decoration: BoxDecoration(
                        gradient: LinearGradient(begin: Alignment.topCenter, end: Alignment.bottomCenter, colors: [SafeRColors.primary.withValues(alpha: 0.9), SafeRColors.primaryDark]),
                      ),
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 16),
              Text(position == null ? '—' : '${position.round()} %', style: theme.textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.w800)),
              Text(
                position == null
                    ? context.tr(fr: 'Position inconnue', en: 'Unknown position')
                    : position >= 100
                        ? context.tr(fr: 'Ouvert', en: 'Open')
                        : position <= 0
                            ? context.tr(fr: 'Fermé', en: 'Closed')
                            : context.tr(fr: 'Partiellement ouvert', en: 'Partially open'),
                style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant),
              ),
            ],
          ),
        ),
        if (control != null) ...[
          const SizedBox(height: 12),
          PanelCard(
            child: Row(
              children: [
                button('open', Icons.keyboard_arrow_up, context.tr(fr: 'Ouvrir', en: 'Open')),
                const SizedBox(width: 10),
                button('stop', Icons.stop, context.tr(fr: 'Stop', en: 'Stop')),
                const SizedBox(width: 10),
                button('close', Icons.keyboard_arrow_down, context.tr(fr: 'Fermer', en: 'Close')),
              ],
            ),
          ),
        ],
        if (positionCap != null && positionCap.writable) ...[
          const SizedBox(height: 12),
          PanelCard(
            child: CapabilitySlider(
              key: const Key('slider-position'),
              label: context.tr(fr: 'Position', en: 'Position'),
              icon: Icons.height,
              value: (position ?? 0).toDouble(),
              min: (positionCap.min ?? 0).toDouble(),
              max: (positionCap.max ?? 100).toDouble(),
              divisions: 100,
              unit: '%',
              enabled: enabled,
              onCommit: (v) => sendDeviceCommand(context, ref, device, 'position', v.round()),
            ),
          ),
        ],
        GenericControls(device: device, exclude: const {'position', 'control'}),
      ],
    );
  }
}
