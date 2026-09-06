import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/i18n.dart';
import '../../../core/models/device.dart';
import '../../../core/theme.dart';
import '../../../core/widgets/widgets.dart';
import '../widgets/device_children_list.dart';
import '../widgets/generic_controls.dart';
import '../widgets/panel_card.dart';
import '../widgets/status_chips.dart';

/// Gateway / hub / NVR without stream: status header and the list of child devices.
class GatewayPanel extends ConsumerWidget {
  const GatewayPanel({super.key, required this.device});

  final Device device;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final count = device.numValue('child_count');
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        PanelCard(
          child: Row(
            children: [
              Container(
                width: 56,
                height: 56,
                decoration: BoxDecoration(color: SafeRColors.primary.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(16)),
                child: Icon(iconFromName(device.icon, fallback: categoryIcon(device.category)), color: SafeRColors.primary, size: 30),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(categoryLabel(context, device.category), style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
                    if (count != null)
                      Text(
                        context.tr(
                            fr: '${count.round()} appareil${count.round() > 1 ? 's' : ''} connecté${count.round() > 1 ? 's' : ''}',
                            en: '${count.round()} connected device${count.round() > 1 ? 's' : ''}'),
                        style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                      ),
                  ],
                ),
              ),
              OnlineChip(online: device.online),
            ],
          ),
        ),
        GenericControls(device: device, exclude: const {'child_count'}),
        SectionHeader(title: context.tr(fr: 'Appareils connectés', en: 'Connected devices'), padding: const EdgeInsets.fromLTRB(4, 20, 4, 8)),
        DeviceChildrenList(parent: device),
      ],
    );
  }
}
