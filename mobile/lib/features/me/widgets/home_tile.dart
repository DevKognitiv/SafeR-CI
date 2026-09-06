import 'package:flutter/material.dart';

import '../../../core/i18n.dart';
import '../../../core/models/home.dart';
import 'me_common.dart';

/// Card of the "Gestion des maisons" list: name, address, role, counts and a check on the current home.
class HomeTile extends StatelessWidget {
  const HomeTile({
    super.key,
    required this.home,
    required this.selected,
    required this.onTap,
    required this.onMembers,
    this.onEdit,
    this.onDelete,
  });

  final Home home;
  final bool selected;
  final VoidCallback onTap;
  final VoidCallback onMembers;
  final VoidCallback? onEdit;
  final VoidCallback? onDelete;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final muted = theme.colorScheme.onSurfaceVariant;
    final address = home.address?.trim() ?? '';
    final subtitle = [
      if (address.isNotEmpty) address,
      '${membersLabel(context, home.memberCount)} · ${devicesLabel(context, home.deviceCount)}',
    ].join('\n');
    return Card(
      key: ValueKey('home-tile-${home.id}'),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: selected ? BorderSide(color: theme.colorScheme.primary, width: 1.5) : BorderSide.none,
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 14, 8, 14),
          child: Row(
            children: [
              IconBox(icon: selected ? Icons.home_rounded : Icons.home_outlined, size: 44),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Flexible(
                          child: Text(home.name, maxLines: 1, overflow: TextOverflow.ellipsis, style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
                        ),
                        const SizedBox(width: 8),
                        RoleChip(role: home.role),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(subtitle, style: theme.textTheme.bodySmall?.copyWith(color: muted)),
                  ],
                ),
              ),
              const SizedBox(width: 4),
              if (selected)
                Semantics(
                  label: context.tr(fr: 'Maison actuelle', en: 'Current home'),
                  child: Icon(Icons.check_circle, color: theme.colorScheme.primary, key: ValueKey('home-check-${home.id}')),
                ),
              PopupMenuButton<_HomeAction>(
                tooltip: context.tr(fr: 'Options de la maison', en: 'Home options'),
                onSelected: (action) {
                  switch (action) {
                    case _HomeAction.members:
                      onMembers();
                    case _HomeAction.edit:
                      onEdit?.call();
                    case _HomeAction.delete:
                      onDelete?.call();
                  }
                },
                itemBuilder: (context) => [
                  PopupMenuItem(
                    value: _HomeAction.members,
                    child: ListTile(leading: const Icon(Icons.people_outline), title: Text(context.tr(fr: 'Membres', en: 'Members')), contentPadding: EdgeInsets.zero),
                  ),
                  if (onEdit != null)
                    PopupMenuItem(
                      value: _HomeAction.edit,
                      child: ListTile(leading: const Icon(Icons.edit_outlined), title: Text(context.tr(fr: 'Modifier', en: 'Edit')), contentPadding: EdgeInsets.zero),
                    ),
                  if (onDelete != null)
                    PopupMenuItem(
                      value: _HomeAction.delete,
                      child: ListTile(
                        leading: Icon(Icons.delete_outline, color: theme.colorScheme.error),
                        title: Text(context.tr(fr: 'Supprimer', en: 'Delete'), style: TextStyle(color: theme.colorScheme.error)),
                        contentPadding: EdgeInsets.zero,
                      ),
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

enum _HomeAction { members, edit, delete }
