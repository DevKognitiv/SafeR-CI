import 'package:flutter/material.dart';

import '../../../core/i18n.dart';
import '../../../core/models/security.dart';
import '../../../core/theme.dart';
import '../../../core/widgets/widgets.dart';

/// Status label + colour for an SOS alert.
({String label, Color color}) sosStatusSpec(BuildContext context, String status) {
  switch (status) {
    case 'resolved':
    case 'closed':
      return (label: context.tr(fr: 'Résolue', en: 'Resolved'), color: SafeRColors.success);
    case 'acknowledged':
    case 'in_progress':
      return (label: context.tr(fr: 'Prise en compte', en: 'Acknowledged'), color: SafeRColors.warning);
    case 'open':
      return (label: context.tr(fr: 'Ouverte', en: 'Open'), color: SafeRColors.danger);
    default:
      return (label: status, color: SafeRColors.primary);
  }
}

/// One recent SOS alert (dark card) with a "mark resolved" action.
class SosAlertTile extends StatelessWidget {
  const SosAlertTile({super.key, required this.alert, this.onResolve, this.busy = false});

  final SosAlert alert;
  final VoidCallback? onResolve;
  final bool busy;

  @override
  Widget build(BuildContext context) {
    final spec = sosStatusSpec(context, alert.status);
    final resolved = alert.status == 'resolved' || alert.status == 'closed';
    final lat = alert.lat;
    final lon = alert.lon;
    final details = <String>[
      if (lat != null && lon != null) '${lat.toStringAsFixed(4)}, ${lon.toStringAsFixed(4)}' else context.tr(fr: 'Position non disponible', en: 'Location unavailable'),
      if (alert.forwarded) context.tr(fr: 'Transmise aux secours', en: 'Forwarded to responders'),
    ];
    return Card(
      color: SafeRColors.cardDark,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(14, 12, 14, 8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.sos, color: SafeRColors.danger, size: 20),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(timeAgo(context, alert.createdAt), style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700)),
                ),
                StateChip(label: spec.label, color: spec.color),
              ],
            ),
            if (alert.note != null && alert.note!.isNotEmpty) ...[
              const SizedBox(height: 6),
              Text(alert.note!, style: const TextStyle(color: Colors.white), maxLines: 2, overflow: TextOverflow.ellipsis),
            ],
            const SizedBox(height: 4),
            Text(details.join(' · '), style: const TextStyle(color: Colors.white60, fontSize: 12)),
            if (!resolved && onResolve != null)
              Align(
                alignment: Alignment.centerRight,
                child: TextButton.icon(
                  onPressed: busy ? null : onResolve,
                  style: TextButton.styleFrom(foregroundColor: SafeRColors.success, minimumSize: const Size(44, 44)),
                  icon: const Icon(Icons.task_alt, size: 18),
                  label: Text(context.tr(fr: 'Marquer résolu', en: 'Mark resolved')),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
