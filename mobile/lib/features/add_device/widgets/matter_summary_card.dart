import 'package:flutter/material.dart';

import '../../../core/i18n.dart';
import '../../../core/theme.dart';
import '../matter_payload.dart';

/// Client-side decoding of a Matter code: "Matter device detected: vendor
/// 0xFFF1, product 0x8001, discriminator 3840" (or an inline error).
class MatterSummaryCard extends StatelessWidget {
  const MatterSummaryCard({super.key, required this.code});

  final String code;

  @override
  Widget build(BuildContext context) {
    if (code.trim().isEmpty) return const SizedBox.shrink();
    final theme = Theme.of(context);
    final payload = tryParseMatterCode(code);
    if (payload == null) {
      return _Banner(
        color: SafeRColors.danger,
        icon: Icons.error_outline,
        title: context.tr(fr: 'Code Matter invalide', en: 'Invalid Matter code'),
        body: context.tr(
          fr: 'Le code doit commencer par « MT: » ou comporter 11 (ou 21) chiffres avec un chiffre de contrôle valide.',
          en: 'The code must start with "MT:" or contain 11 (or 21) digits with a valid check digit.',
        ),
      );
    }
    final transports = [
      if (payload.supportsBle) 'Bluetooth LE',
      if (payload.supportsSoftAp) 'Wi-Fi (Soft-AP)',
      if (payload.supportsOnNetwork) context.tr(fr: 'Réseau IP', en: 'IP network'),
    ];
    final String detail;
    if (payload.isShortDiscriminator) {
      detail = [
        context.tr(fr: 'Discriminant court ${payload.shortDiscriminator}', en: 'Short discriminator ${payload.shortDiscriminator}'),
        if (payload.hasVendorProduct) context.tr(fr: 'Fabricant ${payload.vendorIdHex} · Produit ${payload.productIdHex}', en: 'Vendor ${payload.vendorIdHex} · Product ${payload.productIdHex}'),
        context.tr(fr: "Code d'appairage valide", en: 'Valid pairing code'),
      ].join(' · ');
    } else {
      detail = context.tr(
        fr: 'Fabricant ${payload.vendorIdHex} · Produit ${payload.productIdHex} · Discriminant ${payload.discriminator}',
        en: 'Vendor ${payload.vendorIdHex} · Product ${payload.productIdHex} · Discriminator ${payload.discriminator}',
      );
    }
    return _Banner(
      color: SafeRColors.primary,
      icon: Icons.hub,
      title: context.tr(fr: 'Appareil Matter détecté', en: 'Matter device detected'),
      body: detail,
      footer: transports.isEmpty ? null : Text(transports.join(', '), style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
    );
  }
}

class _Banner extends StatelessWidget {
  const _Banner({required this.color, required this.icon, required this.title, required this.body, this.footer});

  final Color color;
  final IconData icon;
  final String title;
  final String body;
  final Widget? footer;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(color: color.withValues(alpha: 0.10), borderRadius: BorderRadius.circular(16)),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: color),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700, color: color)),
                const SizedBox(height: 4),
                Text(body, style: theme.textTheme.bodySmall),
                if (footer != null) ...[const SizedBox(height: 4), footer!],
              ],
            ),
          ),
        ],
      ),
    );
  }
}
