import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../../core/i18n.dart';
import '../../../core/models/device.dart';
import '../../../core/providers/providers.dart';
import '../../../core/theme.dart';
import '../../../core/widgets/widgets.dart';
import 'capability_format.dart';

/// Human label for a hub device event ("Mouvement détecté", "Fermé"...).
String deviceEventLabel(BuildContext context, DeviceEvent event) {
  final raw = event.payload['value'];
  final on = raw == true || raw == 1 || raw == 'true' || raw == 'on';
  switch (event.type) {
    case 'motion':
      return on ? context.tr(fr: 'Mouvement détecté', en: 'Motion detected') : context.tr(fr: 'Fin du mouvement', en: 'Motion ended');
    case 'contact':
    case 'open':
      return on ? context.tr(fr: 'Ouvert', en: 'Opened') : context.tr(fr: 'Fermé', en: 'Closed');
    case 'smoke':
      return on ? context.tr(fr: 'Fumée détectée', en: 'Smoke detected') : context.tr(fr: 'Fumée dissipée', en: 'Smoke cleared');
    case 'water_leak':
      return on ? context.tr(fr: 'Fuite détectée', en: 'Leak detected') : context.tr(fr: 'Fuite terminée', en: 'Leak cleared');
    case 'gas':
      return on ? context.tr(fr: 'Gaz détecté', en: 'Gas detected') : context.tr(fr: 'Gaz dissipé', en: 'Gas cleared');
    case 'co':
      return on ? context.tr(fr: 'Monoxyde détecté', en: 'CO detected') : context.tr(fr: 'Monoxyde dissipé', en: 'CO cleared');
    case 'alarm':
      return on ? context.tr(fr: 'Alarme déclenchée', en: 'Alarm triggered') : context.tr(fr: 'Alarme terminée', en: 'Alarm cleared');
    case 'tamper':
      return on ? context.tr(fr: 'Sabotage détecté', en: 'Tamper detected') : context.tr(fr: 'Sabotage terminé', en: 'Tamper cleared');
    case 'doorbell_pressed':
      return context.tr(fr: 'Sonnette pressée', en: 'Doorbell pressed');
    case 'locked':
      return on ? context.tr(fr: 'Verrouillée', en: 'Locked') : context.tr(fr: 'Déverrouillée', en: 'Unlocked');
    case 'door':
      return on ? context.tr(fr: 'Porte ouverte', en: 'Door opened') : context.tr(fr: 'Porte fermée', en: 'Door closed');
    case 'arm_mode':
      return securityModeLabel(context, raw?.toString() ?? '');
    case 'online':
      return on ? context.tr(fr: 'En ligne', en: 'Online') : context.tr(fr: 'Hors ligne', en: 'Offline');
    default:
      final label = humanize(event.type);
      return raw == null ? label : '$label: $raw';
  }
}

bool _isAlert(DeviceEvent event) {
  final raw = event.payload['value'];
  final on = raw == true || raw == 1 || raw == 'true';
  return on && const {'smoke', 'water_leak', 'gas', 'co', 'alarm', 'tamper', 'doorbell_pressed'}.contains(event.type);
}

IconData _iconFor(DeviceEvent event) {
  switch (event.type) {
    case 'motion':
      return Icons.directions_run;
    case 'contact':
    case 'open':
    case 'door':
      return Icons.door_front_door_outlined;
    case 'smoke':
      return Icons.local_fire_department_outlined;
    case 'water_leak':
      return Icons.water_outlined;
    case 'gas':
    case 'co':
      return Icons.gas_meter_outlined;
    case 'alarm':
      return Icons.notifications_active_outlined;
    case 'tamper':
      return Icons.report_gmailerrorred;
    case 'doorbell_pressed':
      return Icons.doorbell_outlined;
    case 'locked':
      return Icons.lock_outline;
    case 'arm_mode':
      return Icons.shield_outlined;
    case 'online':
      return Icons.cloud_outlined;
    default:
      return Icons.history;
  }
}

/// "Historique" list backed by [deviceEventsProvider] (loading / empty / error states included).
class DeviceEventsList extends ConsumerWidget {
  const DeviceEventsList({super.key, required this.deviceId, this.limit = 20});

  final String deviceId;
  final int limit;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final events = ref.watch(deviceEventsProvider(deviceId));
    return events.when(
      loading: () => const Padding(padding: EdgeInsets.all(24), child: LoadingView()),
      error: (error, _) => ErrorView(error: error, onRetry: () => ref.invalidate(deviceEventsProvider(deviceId))),
      data: (list) {
        if (list.isEmpty) {
          return EmptyState(
            icon: Icons.history,
            title: context.tr(fr: 'Aucun événement', en: 'No events'),
            subtitle: context.tr(fr: 'Les événements notables apparaîtront ici', en: 'Notable events will appear here'),
          );
        }
        final shown = list.take(limit).toList();
        return Card(
          child: Column(
            children: [
              for (var i = 0; i < shown.length; i++) ...[
                if (i > 0) const Divider(indent: 56),
                Builder(builder: (context) {
                  final event = shown[i];
                  final alert = _isAlert(event);
                  final color = alert ? SafeRColors.danger : theme.colorScheme.primary;
                  final time = event.createdAt?.toLocal();
                  return ListTile(
                    leading: Container(
                      width: 40,
                      height: 40,
                      decoration: BoxDecoration(color: color.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(12)),
                      child: Icon(_iconFor(event), color: color, size: 20),
                    ),
                    title: Text(deviceEventLabel(context, event),
                        style: TextStyle(fontWeight: alert ? FontWeight.w700 : FontWeight.w500, color: alert ? SafeRColors.danger : null)),
                    subtitle: time == null ? null : Text(timeAgo(context, time)),
                    trailing: time == null
                        ? null
                        : Text(DateFormat('dd/MM HH:mm').format(time), style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
                  );
                }),
              ],
            ],
          ),
        );
      },
    );
  }
}
