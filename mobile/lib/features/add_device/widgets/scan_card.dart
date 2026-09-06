import 'package:flutter/material.dart';

import '../../../core/i18n.dart';
import '../../../core/theme.dart';

/// Highlighted "Scan a QR code" entry at the top of the catalogue.
class ScanQrCard extends StatelessWidget {
  const ScanQrCard({super.key, this.onTap});

  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      color: SafeRColors.primary.withValues(alpha: theme.brightness == Brightness.dark ? 0.22 : 0.10),
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Row(
            children: [
              Container(
                width: 48,
                height: 48,
                decoration: BoxDecoration(color: SafeRColors.primary, borderRadius: BorderRadius.circular(14)),
                child: const Icon(Icons.qr_code_scanner, color: Colors.white, size: 26),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      context.tr(fr: 'Scanner un code QR (Matter, Tuya)', en: 'Scan a QR code (Matter, Tuya)'),
                      style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      context.tr(fr: "Le moyen le plus rapide d'ajouter un appareil", en: 'The fastest way to add a device'),
                      style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                    ),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right, color: SafeRColors.primary),
            ],
          ),
        ),
      ),
    );
  }
}
