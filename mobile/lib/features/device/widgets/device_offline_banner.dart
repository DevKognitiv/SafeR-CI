import 'package:flutter/material.dart';

import '../../../core/i18n.dart';
import '../../../core/theme.dart';

/// Banner shown on the device screens when the device is offline, with a refresh action.
class DeviceOfflineBanner extends StatelessWidget {
  const DeviceOfflineBanner({super.key, required this.onRefresh, this.busy = false, this.lastSeen});

  final VoidCallback onRefresh;
  final bool busy;
  final DateTime? lastSeen;

  @override
  Widget build(BuildContext context) {
    final subtitle = lastSeen == null
        ? context.tr(fr: "L'appareil ne répond pas", en: 'The device is not responding')
        : context.tr(fr: 'Dernière activité ${timeAgo(context, lastSeen).toLowerCase()}', en: 'Last seen ${timeAgo(context, lastSeen).toLowerCase()}');
    return Material(
      color: SafeRColors.warning.withValues(alpha: 0.14),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 8, 8, 8),
        child: Row(
          children: [
            const Icon(Icons.cloud_off, size: 20, color: SafeRColors.warning),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(context.tr(fr: 'Appareil hors ligne', en: 'Device offline'),
                      style: const TextStyle(color: SafeRColors.warning, fontWeight: FontWeight.w700, fontSize: 13)),
                  Text(subtitle, style: TextStyle(color: SafeRColors.warning.withValues(alpha: 0.9), fontSize: 12)),
                ],
              ),
            ),
            TextButton.icon(
              onPressed: busy ? null : onRefresh,
              style: TextButton.styleFrom(foregroundColor: SafeRColors.warning, minimumSize: const Size(44, 44)),
              icon: busy
                  ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: SafeRColors.warning))
                  : const Icon(Icons.refresh, size: 18),
              label: Text(context.tr(fr: 'Actualiser', en: 'Refresh')),
            ),
          ],
        ),
      ),
    );
  }
}
