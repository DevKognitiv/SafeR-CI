import 'package:flutter/material.dart';

import '../../../core/i18n.dart';
import '../../../core/models/home.dart';
import '../../../core/theme.dart';
import '../../../core/widgets/widgets.dart';
import 'me_common.dart';

/// "Maison actuelle" card: name, role, counts, security mode and shortcuts.
class CurrentHomeCard extends StatelessWidget {
  const CurrentHomeCard({super.key, required this.home, required this.onMembers, required this.onManage});

  final Home home;
  final VoidCallback onMembers;
  final VoidCallback onManage;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final muted = theme.colorScheme.onSurfaceVariant;
    final address = home.address?.trim() ?? '';
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const IconBox(icon: Icons.home_rounded, size: 44),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(home.name, maxLines: 1, overflow: TextOverflow.ellipsis, style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
                      Text(
                        address.isEmpty ? context.tr(fr: 'Adresse non renseignée', en: 'No address') : address,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: theme.textTheme.bodySmall?.copyWith(color: muted),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 8),
                RoleChip(role: home.role),
              ],
            ),
            const SizedBox(height: 14),
            Wrap(
              spacing: 16,
              runSpacing: 8,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                _Stat(icon: Icons.people_outline, label: membersLabel(context, home.memberCount)),
                _Stat(icon: Icons.devices_other, label: devicesLabel(context, home.deviceCount)),
                StateChip(
                  label: securityModeLabel(context, home.securityMode),
                  color: SafeRColors.forSecurityMode(home.securityMode),
                  icon: Icons.shield_outlined,
                ),
              ],
            ),
            const SizedBox(height: 14),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    style: OutlinedButton.styleFrom(minimumSize: const Size.fromHeight(44), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12))),
                    onPressed: onMembers,
                    icon: const Icon(Icons.people_outline, size: 18),
                    label: Text(context.tr(fr: 'Membres', en: 'Members')),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: FilledButton.tonalIcon(
                    style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(44), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12))),
                    onPressed: onManage,
                    icon: const Icon(Icons.home_work_outlined, size: 18),
                    label: Text(context.tr(fr: 'Gérer', en: 'Manage')),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _Stat extends StatelessWidget {
  const _Stat({required this.icon, required this.label});

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 16, color: theme.colorScheme.onSurfaceVariant),
        const SizedBox(width: 4),
        Text(label, style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant, fontWeight: FontWeight.w600)),
      ],
    );
  }
}
