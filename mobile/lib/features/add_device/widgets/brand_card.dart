import 'package:flutter/material.dart';

import '../../../core/models/brand.dart';
import '../../../core/widgets/widgets.dart';
import 'brand_color.dart';

/// Rounded tinted square with the brand icon.
class BrandAvatar extends StatelessWidget {
  const BrandAvatar({super.key, required this.brand, this.size = 48});

  final BrandInfo brand;
  final double size;

  @override
  Widget build(BuildContext context) {
    final color = colorFromHex(brand.color);
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(color: color.withValues(alpha: 0.14), borderRadius: BorderRadius.circular(size * 0.3)),
      child: Icon(iconFromName(brand.icon, fallback: Icons.devices), color: color, size: size * 0.5),
    );
  }
}

/// Tuya-style brand row: colour avatar, name, vendor and protocol chips.
class BrandCard extends StatelessWidget {
  const BrandCard({super.key, required this.brand, this.onTap});

  final BrandInfo brand;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final color = colorFromHex(brand.color);
    return Card(
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Row(
            children: [
              BrandAvatar(brand: brand),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(brand.name, maxLines: 1, overflow: TextOverflow.ellipsis, style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w600)),
                    if (brand.vendor.isNotEmpty) ...[
                      const SizedBox(height: 2),
                      Text(brand.vendor, maxLines: 1, overflow: TextOverflow.ellipsis, style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
                    ],
                    if (brand.protocols.isNotEmpty) ...[
                      const SizedBox(height: 8),
                      Wrap(
                        spacing: 6,
                        runSpacing: 4,
                        children: [for (final protocol in brand.protocols) StateChip(label: protocol, color: color)],
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
