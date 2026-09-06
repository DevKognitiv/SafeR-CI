import 'package:flutter/material.dart';

import '../../../core/i18n.dart';
import '../../../core/models/home.dart';
import 'me_common.dart';

/// Row of the members list: avatar initials, name, e-mail, role chip and an optional actions menu.
class MemberTile extends StatelessWidget {
  const MemberTile({super.key, required this.member, this.isMe = false, this.onChangeRole, this.onRemove, this.onLeave});

  final Member member;
  final bool isMe;
  final VoidCallback? onChangeRole;
  final VoidCallback? onRemove;

  /// Own row only: leave the home (self-removal).
  final VoidCallback? onLeave;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final hasActions = onChangeRole != null || onRemove != null || onLeave != null;
    final name = member.name.trim().isEmpty ? member.email.split('@').first : member.name;
    return ListTile(
      key: ValueKey('member-${member.userId}'),
      contentPadding: const EdgeInsets.fromLTRB(16, 6, 8, 6),
      leading: InitialsAvatar(name: member.name, email: member.email),
      title: Row(
        children: [
          Flexible(child: Text(name, maxLines: 1, overflow: TextOverflow.ellipsis, style: theme.textTheme.bodyLarge?.copyWith(fontWeight: FontWeight.w600))),
          if (isMe) ...[
            const SizedBox(width: 6),
            // Flexible too: a wide role chip + menu can leave the title very little room.
            Flexible(child: Text(context.tr(fr: '(moi)', en: '(me)'), maxLines: 1, overflow: TextOverflow.ellipsis, style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant))),
          ],
        ],
      ),
      subtitle: Text(member.email, maxLines: 1, overflow: TextOverflow.ellipsis),
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          RoleChip(role: member.role),
          if (hasActions)
            PopupMenuButton<_MemberAction>(
              tooltip: context.tr(fr: 'Options du membre', en: 'Member options'),
              onSelected: (action) {
                switch (action) {
                  case _MemberAction.role:
                    onChangeRole?.call();
                  case _MemberAction.remove:
                    onRemove?.call();
                  case _MemberAction.leave:
                    onLeave?.call();
                }
              },
              itemBuilder: (context) => [
                if (onChangeRole != null)
                  PopupMenuItem(
                    value: _MemberAction.role,
                    child: ListTile(leading: const Icon(Icons.manage_accounts_outlined), title: Text(context.tr(fr: 'Changer le rôle', en: 'Change role')), contentPadding: EdgeInsets.zero),
                  ),
                if (onRemove != null)
                  PopupMenuItem(
                    value: _MemberAction.remove,
                    child: ListTile(
                      leading: Icon(Icons.person_remove_outlined, color: theme.colorScheme.error),
                      title: Text(context.tr(fr: 'Retirer', en: 'Remove'), style: TextStyle(color: theme.colorScheme.error)),
                      contentPadding: EdgeInsets.zero,
                    ),
                  ),
                if (onLeave != null)
                  PopupMenuItem(
                    value: _MemberAction.leave,
                    child: ListTile(
                      leading: Icon(Icons.exit_to_app, color: theme.colorScheme.error),
                      title: Text(context.tr(fr: 'Quitter la maison', en: 'Leave home'), style: TextStyle(color: theme.colorScheme.error)),
                      contentPadding: EdgeInsets.zero,
                    ),
                  ),
              ],
            )
          else
            const SizedBox(width: 8),
        ],
      ),
    );
  }
}

enum _MemberAction { role, remove, leave }
