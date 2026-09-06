import 'package:flutter/material.dart';

import '../../../core/i18n.dart';
import '../../../core/models/brand.dart';
import '../../../core/theme.dart';
import '../../../core/widgets/widgets.dart';

/// Icon for a pairing method (hub icon name, else guessed from its id).
IconData iconForMethod(PairingMethod method) {
  final id = method.id.toLowerCase();
  IconData fallback;
  if (id.contains('qr')) {
    fallback = Icons.qr_code_scanner;
  } else if (id.contains('cloud') || id.contains('project') || id.contains('account') || id.contains('api')) {
    fallback = Icons.cloud_outlined;
  } else if (id.contains('local') || id.contains('ip') || id.contains('host') || id.contains('lan')) {
    fallback = Icons.router_outlined;
  } else if (id.contains('manual') || id.contains('code') || id.contains('pin')) {
    fallback = Icons.dialpad;
  } else if (id.contains('discover') || id.contains('scan') || id.contains('virtual')) {
    fallback = Icons.search;
  } else if (id.contains('sia') || id.contains('webhook')) {
    fallback = Icons.cell_tower;
  } else {
    fallback = Icons.link;
  }
  return iconFromName(method.icon, fallback: fallback);
}

/// Step 1 of the wizard: pick how to connect the device.
class MethodChooser extends StatelessWidget {
  const MethodChooser({super.key, required this.methods, required this.onSelected, this.color = SafeRColors.primary});

  final List<PairingMethod> methods;
  final ValueChanged<PairingMethod> onSelected;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
      children: [
        Text(context.tr(fr: "Comment souhaitez-vous ajouter l'appareil ?", en: 'How do you want to add the device?'), style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
        const SizedBox(height: 4),
        Text(context.tr(fr: 'Choisissez une méthode de connexion.', en: 'Choose a connection method.'), style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
        const SizedBox(height: 16),
        for (final method in methods) ...[
          MethodCard(method: method, color: color, onTap: () => onSelected(method)),
          const SizedBox(height: 10),
        ],
      ],
    );
  }
}

class MethodCard extends StatelessWidget {
  const MethodCard({super.key, required this.method, this.onTap, this.color = SafeRColors.primary});

  final PairingMethod method;
  final VoidCallback? onTap;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              Container(
                width: 48,
                height: 48,
                decoration: BoxDecoration(color: color.withValues(alpha: 0.14), borderRadius: BorderRadius.circular(14)),
                child: Icon(iconForMethod(method), color: color),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(method.title, style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w600)),
                    if (method.description.isNotEmpty) ...[
                      const SizedBox(height: 2),
                      Text(method.description, style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
                    ],
                    if (method.supportsDiscovery || method.requiresIntegration) ...[
                      const SizedBox(height: 8),
                      Wrap(
                        spacing: 6,
                        runSpacing: 4,
                        children: [
                          if (method.supportsDiscovery) StateChip(label: context.tr(fr: 'Détection automatique', en: 'Auto discovery'), icon: Icons.radar, color: SafeRColors.success),
                          if (method.requiresIntegration) StateChip(label: context.tr(fr: 'Compte requis', en: 'Account required'), icon: Icons.account_circle_outlined),
                        ],
                      ),
                    ],
                  ],
                ),
              ),
              const SizedBox(width: 8),
              Icon(Icons.chevron_right, color: theme.colorScheme.onSurfaceVariant),
            ],
          ),
        ),
      ),
    );
  }
}
