import 'package:flutter/material.dart';

import '../../../core/i18n.dart';
import '../../../core/models/message.dart';
import '../../../core/theme.dart';

/// Message kinds of the Tuya-style message center, in tab order.
const List<String> kMessageKinds = ['alarm', 'home', 'notice'];

IconData messageKindIcon(String kind) {
  switch (kind) {
    case 'alarm':
      return Icons.warning_amber_rounded;
    case 'home':
      return Icons.home_outlined;
    default:
      return Icons.notifications_outlined;
  }
}

String messageKindLabel(BuildContext context, String kind) {
  switch (kind) {
    case 'alarm':
      return context.tr(fr: 'Alarmes', en: 'Alarms');
    case 'home':
      return context.tr(fr: 'Maison', en: 'Home');
    default:
      return context.tr(fr: 'Notifications', en: 'Notifications');
  }
}

/// Swipe-to-delete message row with severity colour, unread dot and relative time.
class MessageTile extends StatelessWidget {
  const MessageTile({super.key, required this.message, required this.onTap, required this.onDelete});

  final HubMessage message;
  final VoidCallback onTap;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final color = SafeRColors.forSeverity(message.severity);
    final muted = theme.colorScheme.onSurfaceVariant;
    return Dismissible(
      key: ValueKey('message-${message.id}'),
      direction: DismissDirection.endToStart,
      onDismissed: (_) => onDelete(),
      background: Container(
        color: SafeRColors.danger,
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.symmetric(horizontal: 20),
        child: Semantics(
          label: context.tr(fr: 'Supprimer', en: 'Delete'),
          child: const Icon(Icons.delete_outline, color: Colors.white),
        ),
      ),
      child: ListTile(
        onTap: onTap,
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
        leading: Container(
          width: 40,
          height: 40,
          decoration: BoxDecoration(color: color.withValues(alpha: 0.14), borderRadius: BorderRadius.circular(12)),
          child: Icon(messageKindIcon(message.kind), color: color, size: 22),
        ),
        title: Text(
          message.title,
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
          style: theme.textTheme.bodyLarge?.copyWith(fontWeight: message.read ? FontWeight.w500 : FontWeight.w700),
        ),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (message.body.isNotEmpty) ...[
              const SizedBox(height: 2),
              Text(message.body, maxLines: 2, overflow: TextOverflow.ellipsis, style: theme.textTheme.bodySmall?.copyWith(color: muted)),
            ],
            const SizedBox(height: 2),
            Text(timeAgo(context, message.createdAt), style: theme.textTheme.bodySmall?.copyWith(color: muted)),
          ],
        ),
        trailing: message.read
            ? null
            : Semantics(
                label: context.tr(fr: 'Non lu', en: 'Unread'),
                child: Container(
                  key: ValueKey('unread-${message.id}'),
                  width: 10,
                  height: 10,
                  decoration: BoxDecoration(color: color, shape: BoxShape.circle),
                ),
              ),
      ),
    );
  }
}
