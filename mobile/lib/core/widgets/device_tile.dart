import 'package:flutter/material.dart';

import '../i18n.dart';
import '../models/device.dart';
import '../theme.dart';
import 'icon_map.dart';

/// Tuya-style device card: icon, name, state summary and a quick toggle.
class DeviceTile extends StatelessWidget {
  const DeviceTile({super.key, required this.device, this.onTap, this.onToggle, this.compact = false});

  final Device device;
  final VoidCallback? onTap;
  final ValueChanged<bool>? onToggle;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final toggleCode = device.primaryToggleCode;
    final on = device.isOn;
    final alerting = device.isAlerting;
    final accent = alerting ? SafeRColors.danger : (on ? SafeRColors.primary : theme.colorScheme.onSurfaceVariant);
    return Card(
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: onTap,
        child: Padding(
          padding: EdgeInsets.all(compact ? 12 : 14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Row(
                children: [
                  Container(
                    width: 40,
                    height: 40,
                    decoration: BoxDecoration(color: accent.withValues(alpha: 0.14), borderRadius: BorderRadius.circular(12)),
                    child: Icon(iconFromName(device.icon, fallback: categoryIcon(device.category)), color: accent, size: 22),
                  ),
                  const Spacer(),
                  if (!device.online)
                    Icon(Icons.cloud_off, size: 18, color: theme.colorScheme.onSurfaceVariant)
                  else if (toggleCode != null && onToggle != null)
                    Semantics(
                      label: 'toggle ${device.name}',
                      child: Switch.adaptive(value: on, onChanged: onToggle),
                    ),
                ],
              ),
              const SizedBox(height: 10),
              Text(device.name, maxLines: 1, overflow: TextOverflow.ellipsis, style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w600)),
              const SizedBox(height: 2),
              Text(
                device.online ? deviceStateSummary(context, device) : context.tr(fr: 'HORS LIGNE', en: 'OFFLINE'),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.bodySmall?.copyWith(color: alerting ? SafeRColors.danger : theme.colorScheme.onSurfaceVariant, fontWeight: alerting ? FontWeight.w700 : null),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
