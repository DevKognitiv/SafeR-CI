import 'package:flutter/material.dart';

import '../../../core/i18n.dart';
import '../../../core/theme.dart';

/// Thin banner shown when the realtime connection to the hub is down.
class OfflineBanner extends StatelessWidget {
  const OfflineBanner({super.key});

  @override
  Widget build(BuildContext context) => Container(
        width: double.infinity,
        color: SafeRColors.warning.withValues(alpha: 0.14),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        child: Row(
          children: [
            const Icon(Icons.cloud_off, size: 18, color: SafeRColors.warning),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                context.tr(fr: 'Hors ligne — reconnexion au hub…', en: 'Offline — reconnecting to the hub…'),
                style: const TextStyle(color: SafeRColors.warning, fontSize: 12, fontWeight: FontWeight.w600),
              ),
            ),
          ],
        ),
      );
}
