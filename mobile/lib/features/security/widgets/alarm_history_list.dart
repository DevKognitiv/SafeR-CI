import 'package:flutter/material.dart';

import '../../../core/i18n.dart';
import '../../../core/models/message.dart';
import '../../../core/theme.dart';

/// Last alarm messages (kind = alarm) as a compact card list.
class AlarmHistoryCard extends StatelessWidget {
  const AlarmHistoryCard({super.key, required this.messages, this.onTap});

  final List<HubMessage> messages;
  final ValueChanged<HubMessage>? onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Card(
        clipBehavior: Clip.antiAlias,
        child: Column(
          children: [
            for (final (index, m) in messages.indexed) ...[
              if (index > 0) const Divider(indent: 52),
              InkWell(
                onTap: onTap == null ? null : () => onTap!(m),
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                  child: Row(
                    children: [
                      Container(
                        width: 28,
                        height: 28,
                        decoration: BoxDecoration(color: SafeRColors.forSeverity(m.severity).withValues(alpha: 0.14), shape: BoxShape.circle),
                        child: Icon(m.severity == 'critical' ? Icons.notifications_active : Icons.warning_amber, size: 16, color: SafeRColors.forSeverity(m.severity)),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(m.title, maxLines: 1, overflow: TextOverflow.ellipsis, style: theme.textTheme.bodyMedium?.copyWith(fontWeight: m.read ? FontWeight.w500 : FontWeight.w700)),
                            if (m.body.isNotEmpty) Text(m.body, maxLines: 1, overflow: TextOverflow.ellipsis, style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
                          ],
                        ),
                      ),
                      const SizedBox(width: 8),
                      Text(timeAgo(context, m.createdAt), style: theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
                    ],
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
