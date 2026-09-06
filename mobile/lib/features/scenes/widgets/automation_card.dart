import 'package:flutter/material.dart';

import '../../../core/i18n.dart';
import '../../../core/models/models.dart';
import '../../../core/theme.dart';
import '../../../core/widgets/widgets.dart';
import 'labels.dart';

/// Automation card: name, enabled switch, "Si / Et si / Alors" summary and a "Tester" action.
class AutomationCard extends StatelessWidget {
  const AutomationCard({super.key, required this.automation, required this.devices, this.scenes = const [], this.onTap, this.onLongPress, this.onToggle, this.onTest});

  final Automation automation;
  final List<Device> devices;
  final List<Scene> scenes;
  final VoidCallback? onTap;
  final VoidCallback? onLongPress;
  final ValueChanged<bool>? onToggle;
  final VoidCallback? onTest;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final muted = theme.colorScheme.onSurfaceVariant;
    final triggers = automation.triggers.map((t) => ruleSummary(context, t, devices: devices)).toList();
    final conditions = automation.conditions.map((c) => ruleSummary(context, c, devices: devices)).toList();
    final actions = automation.actions.map((a) => actionSummary(context, a, devices: devices, scenes: scenes)).toList();
    return Card(
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: onTap,
        onLongPress: onLongPress,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      automation.name,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700, color: automation.enabled ? null : muted),
                    ),
                  ),
                  Semantics(
                    label: context.tr(fr: 'Activer ${automation.name}', en: 'Enable ${automation.name}'),
                    child: Switch.adaptive(value: automation.enabled, onChanged: onToggle),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              _RuleLines(
                prefix: context.tr(fr: 'Si', en: 'If'),
                lines: triggers.isEmpty ? [context.tr(fr: 'Aucun déclencheur', en: 'No trigger')] : triggers,
                color: SafeRColors.primary,
                badge: automation.triggers.length > 1 ? (automation.match == 'any' ? context.tr(fr: 'OU', en: 'OR') : context.tr(fr: 'ET', en: 'AND')) : null,
              ),
              if (conditions.isNotEmpty) _RuleLines(prefix: context.tr(fr: 'Et si', en: 'And if'), lines: conditions, color: SafeRColors.warning),
              _RuleLines(
                prefix: context.tr(fr: 'Alors', en: 'Then'),
                lines: actions.isEmpty ? [context.tr(fr: 'Aucune action', en: 'No action')] : actions,
                color: SafeRColors.success,
              ),
              const SizedBox(height: 4),
              Row(
                children: [
                  Expanded(
                    child: Text(
                      automation.lastTriggeredAt == null
                          ? context.tr(fr: 'Jamais déclenchée', en: 'Never triggered')
                          : context.tr(fr: 'Dernier déclenchement : ${timeAgo(context, automation.lastTriggeredAt)}', en: 'Last triggered: ${timeAgo(context, automation.lastTriggeredAt)}'),
                      style: theme.textTheme.bodySmall?.copyWith(color: muted),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  TextButton.icon(
                    onPressed: onTest,
                    icon: const Icon(Icons.play_arrow, size: 18),
                    label: Text(context.tr(fr: 'Tester', en: 'Test')),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _RuleLines extends StatelessWidget {
  const _RuleLines({required this.prefix, required this.lines, required this.color, this.badge});

  final String prefix;
  final List<String> lines;
  final Color color;
  final String? badge;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(width: 48, child: Text(prefix, style: theme.textTheme.labelLarge?.copyWith(color: color, fontWeight: FontWeight.w800))),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                for (final line in lines) Text(line, maxLines: 2, overflow: TextOverflow.ellipsis, style: theme.textTheme.bodyMedium),
              ],
            ),
          ),
          if (badge != null) Padding(padding: const EdgeInsets.only(left: 8), child: StateChip(label: badge!, color: color)),
        ],
      ),
    );
  }
}
