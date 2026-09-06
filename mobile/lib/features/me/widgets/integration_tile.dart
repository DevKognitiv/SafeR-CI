import 'package:flutter/material.dart';

import '../../../core/i18n.dart';
import '../../../core/models/brand.dart';
import '../../../core/models/home.dart';
import '../../../core/widgets/widgets.dart';
import 'me_common.dart';

/// Card of the integrations list: brand icon/colour, name, key and creation time.
class IntegrationTile extends StatelessWidget {
  const IntegrationTile({super.key, required this.integration, this.brand, required this.onDelete});

  final Integration integration;
  final BrandInfo? brand;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final muted = theme.colorScheme.onSurfaceVariant;
    final color = colorFromHex(brand?.color);
    final ago = timeAgo(context, integration.createdAt);
    // "Il y a 3 j" -> "il y a 3 j" so it reads naturally after "Ajoutée".
    final created = ago.isEmpty ? '' : ago[0].toLowerCase() + ago.substring(1);
    final brandName = brand?.name ?? integration.brand;
    return Card(
      key: ValueKey('integration-${integration.id}'),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 4, 12),
        child: Row(
          children: [
            IconBox(icon: iconFromName(brand?.icon, fallback: Icons.extension_outlined), color: color, size: 44),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(integration.name.isEmpty ? brandName : integration.name, maxLines: 1, overflow: TextOverflow.ellipsis, style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
                  const SizedBox(height: 2),
                  Text(brandName, style: theme.textTheme.bodySmall?.copyWith(color: color, fontWeight: FontWeight.w600)),
                  const SizedBox(height: 2),
                  Text(integration.key, maxLines: 1, overflow: TextOverflow.ellipsis, style: theme.textTheme.bodySmall?.copyWith(color: muted, fontFamily: 'monospace')),
                  if (created.isNotEmpty)
                    Text(context.tr(fr: 'Ajoutée $created', en: 'Added $created'), style: theme.textTheme.bodySmall?.copyWith(color: muted)),
                ],
              ),
            ),
            IconButton(
              tooltip: context.tr(fr: 'Supprimer', en: 'Delete'),
              onPressed: onDelete,
              icon: Icon(Icons.delete_outline, color: theme.colorScheme.error),
            ),
          ],
        ),
      ),
    );
  }
}
