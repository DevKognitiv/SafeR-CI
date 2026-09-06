import 'package:flutter/material.dart';

import '../../../core/i18n.dart';
import '../../../core/models/security.dart';
import '../../../core/theme.dart';
import 'arm_mode_selector.dart';

/// Hero card: current mode, last change, open sensors hint and the four arm buttons.
class SecurityHeroCard extends StatelessWidget {
  const SecurityHeroCard({
    super.key,
    required this.security,
    required this.openCount,
    required this.onSelected,
    this.busy = false,
  });

  final SecurityState security;
  final int openCount;
  final ValueChanged<String> onSelected;
  final bool busy;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final color = SafeRColors.forSecurityMode(security.mode);
    final changed = timeAgo(context, security.changedAt);
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
      child: Card(
        child: Container(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(16),
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [color.withValues(alpha: 0.18), color.withValues(alpha: 0.02)],
            ),
          ),
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Container(
                    width: 56,
                    height: 56,
                    decoration: BoxDecoration(color: color, shape: BoxShape.circle, boxShadow: [BoxShadow(color: color.withValues(alpha: 0.35), blurRadius: 16, offset: const Offset(0, 6))]),
                    child: Icon(security.isArmed ? Icons.shield : Icons.shield_outlined, color: Colors.white, size: 30),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          context.tr(fr: 'Mode actuel', en: 'Current mode'),
                          style: theme.textTheme.labelMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                        ),
                        Text(
                          securityModeLabel(context, security.mode),
                          key: const Key('security-current-mode'),
                          style: theme.textTheme.headlineSmall?.copyWith(color: color, fontWeight: FontWeight.w800),
                        ),
                        if (changed.isNotEmpty)
                          Text(
                            context.tr(fr: 'Modifié $changed', en: 'Changed $changed').replaceFirst('Modifié Il y a', 'Modifié il y a'),
                            style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                          ),
                      ],
                    ),
                  ),
                  if (busy) const SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2.5)),
                ],
              ),
              const SizedBox(height: 12),
              _ReadinessRow(openCount: openCount, armed: security.isArmed),
              const SizedBox(height: 14),
              ArmModeSelector(mode: security.mode, onSelected: onSelected, enabled: !busy),
            ],
          ),
        ),
      ),
    );
  }
}

/// "Système prêt" / "2 ouvertures détectées" hint under the mode title.
class _ReadinessRow extends StatelessWidget {
  const _ReadinessRow({required this.openCount, required this.armed});

  final int openCount;
  final bool armed;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final ready = openCount == 0;
    final color = ready ? SafeRColors.success : SafeRColors.warning;
    final text = ready
        ? (armed
            ? context.tr(fr: 'Système armé · toutes les ouvertures sont fermées', en: 'System armed · all openings are closed')
            : context.tr(fr: 'Système prêt · toutes les ouvertures sont fermées', en: 'System ready · all openings are closed'))
        : context.tr(
            fr: openCount == 1 ? '1 ouverture détectée' : '$openCount ouvertures détectées',
            en: openCount == 1 ? '1 opening detected' : '$openCount openings detected',
          );
    return Row(
      children: [
        Icon(ready ? Icons.check_circle : Icons.error_outline, size: 18, color: color),
        const SizedBox(width: 6),
        Expanded(child: Text(text, style: theme.textTheme.bodySmall?.copyWith(color: color, fontWeight: FontWeight.w600))),
      ],
    );
  }
}
