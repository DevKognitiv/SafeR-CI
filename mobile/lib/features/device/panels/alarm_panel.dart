import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/i18n.dart';
import '../../../core/models/device.dart';
import '../../../core/theme.dart';
import '../../../core/widgets/widgets.dart';
import '../widgets/device_children_list.dart';
import '../widgets/device_command.dart';
import '../widgets/generic_controls.dart';
import '../widgets/mode_selector.dart';
import '../widgets/panel_card.dart';

/// Alarm panel: arm mode selector, alarm banner, ready status and zones with bypass.
class AlarmPanel extends ConsumerWidget {
  const AlarmPanel({super.key, required this.device});

  final Device device;

  static IconData modeIcon(String mode) {
    switch (mode) {
      case 'armed_home':
        return Icons.home_outlined;
      case 'armed_away':
        return Icons.directions_walk;
      case 'armed_night':
        return Icons.bedtime_outlined;
      default:
        return Icons.lock_open;
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final armCap = writableCapability(device, 'arm_mode', type: 'enum');
    final mode = device.stringValue('arm_mode') ?? 'disarmed';
    final alarm = device.boolValue('alarm') ?? false;
    final zone = device.stringValue('triggered_zone');
    final ready = device.hasCapability('ready') ? (device.boolValue('ready') ?? false) : null;
    final modeColor = SafeRColors.forSecurityMode(mode);
    final modes = armCap?.values.isNotEmpty == true ? armCap!.values : const ['disarmed', 'armed_home', 'armed_away', 'armed_night'];

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (alarm) ...[
          PanelCard(
            color: SafeRColors.danger,
            child: Row(
              children: [
                const Icon(Icons.notifications_active, color: Colors.white, size: 32),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(context.tr(fr: 'ALARME DÉCLENCHÉE', en: 'ALARM TRIGGERED'),
                          style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w900, letterSpacing: 1)),
                      Text(
                        zone != null && zone.isNotEmpty
                            ? context.tr(fr: 'Zone : $zone', en: 'Zone: $zone')
                            : context.tr(fr: 'Désarmez pour arrêter la sirène', en: 'Disarm to stop the siren'),
                        style: const TextStyle(color: Colors.white),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
        ],
        PanelCard(
          padding: const EdgeInsets.symmetric(vertical: 24, horizontal: 16),
          child: Column(
            children: [
              Container(
                width: 96,
                height: 96,
                decoration: BoxDecoration(shape: BoxShape.circle, color: (alarm ? SafeRColors.danger : modeColor).withValues(alpha: 0.14)),
                child: Icon(alarm ? Icons.notifications_active : (mode == 'disarmed' ? Icons.shield_outlined : Icons.shield),
                    size: 48, color: alarm ? SafeRColors.danger : modeColor),
              ),
              const SizedBox(height: 12),
              Text(securityModeLabel(context, mode), style: theme.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800, color: modeColor)),
              if (ready != null) ...[
                const SizedBox(height: 6),
                StateChip(
                  label: ready ? context.tr(fr: 'Prêt à armer', en: 'Ready to arm') : context.tr(fr: 'Non prêt — zone ouverte', en: 'Not ready — zone open'),
                  icon: ready ? Icons.check_circle_outline : Icons.error_outline,
                  color: ready ? SafeRColors.success : SafeRColors.warning,
                ),
              ],
              if (armCap != null) ...[
                const SizedBox(height: 20),
                ModeSelector<String>(
                  options: [
                    for (final value in modes)
                      ModeOption(value: value, label: securityModeLabel(context, value), icon: modeIcon(value), color: SafeRColors.forSecurityMode(value))
                  ],
                  selected: mode,
                  enabled: device.online,
                  onSelected: (value) => sendDeviceCommand(context, ref, device, 'arm_mode', value),
                ),
              ],
            ],
          ),
        ),
        GenericControls(device: device, exclude: const {'arm_mode', 'alarm', 'triggered_zone', 'ready'}),
        SectionHeader(title: context.tr(fr: 'Zones', en: 'Zones'), padding: const EdgeInsets.fromLTRB(4, 20, 4, 8)),
        DeviceChildrenList(
          parent: device,
          showBypass: true,
          emptyTitle: context.tr(fr: 'Aucune zone', en: 'No zones'),
          emptySubtitle: context.tr(fr: 'Les zones de la centrale apparaîtront ici', en: 'Panel zones will appear here'),
        ),
      ],
    );
  }
}
