import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/i18n.dart';
import '../../../core/models/device.dart';
import '../../../core/theme.dart';
import '../../../core/widgets/widgets.dart';
import '../widgets/capability_format.dart';
import '../widgets/device_events_list.dart';
import '../widgets/generic_controls.dart';
import '../widgets/info_rows.dart';
import '../widgets/panel_card.dart';
import '../widgets/status_chips.dart';

class _Status {
  const _Status({required this.label, required this.description, required this.color, required this.icon});

  final String label;
  final String description;
  final Color color;
  final IconData icon;
}

/// Sensors and alarm zones: status hero, gauges, battery/signal chips and history.
class SensorPanel extends ConsumerWidget {
  const SensorPanel({super.key, required this.device});

  final Device device;

  static const _alertCodes = <String, (String, String, IconData)>{
    'smoke': ('FUMÉE !', 'SMOKE!', Icons.local_fire_department),
    'co': ('CO !', 'CO!', Icons.gas_meter),
    'water_leak': ('FUITE !', 'LEAK!', Icons.water),
    'gas': ('GAZ !', 'GAS!', Icons.gas_meter),
    'alarm': ('ALARME !', 'ALARM!', Icons.notifications_active),
  };

  _Status? _status(BuildContext context) {
    for (final entry in _alertCodes.entries) {
      if (device.hasCapability(entry.key) && (device.boolValue(entry.key) ?? false)) {
        return _Status(
          label: context.tr(fr: entry.value.$1, en: entry.value.$2),
          description: context.tr(fr: 'Alerte en cours — vérifiez immédiatement', en: 'Alert in progress — check immediately'),
          color: SafeRColors.danger,
          icon: entry.value.$3,
        );
      }
    }
    final contactCode = device.hasCapability('contact') ? 'contact' : (device.hasCapability('open') ? 'open' : null);
    if (contactCode != null) {
      final open = device.boolValue(contactCode) ?? false;
      return _Status(
        label: open ? context.tr(fr: 'OUVERT', en: 'OPEN') : context.tr(fr: 'FERMÉ', en: 'CLOSED'),
        description: open ? context.tr(fr: "L'ouverture est détectée", en: 'Opening detected') : context.tr(fr: 'Tout est en ordre', en: 'All good'),
        color: open ? SafeRColors.warning : SafeRColors.success,
        icon: open ? Icons.door_front_door : Icons.door_front_door_outlined,
      );
    }
    if (device.hasCapability('motion')) {
      final motion = device.boolValue('motion') ?? false;
      return _Status(
        label: motion ? context.tr(fr: 'MOUVEMENT', en: 'MOTION') : context.tr(fr: 'CALME', en: 'CLEAR'),
        description: motion ? context.tr(fr: 'Un mouvement est détecté', en: 'Motion detected') : context.tr(fr: 'Aucun mouvement récent', en: 'No recent motion'),
        color: motion ? SafeRColors.warning : SafeRColors.success,
        icon: motion ? Icons.directions_run : Icons.motion_photos_off_outlined,
      );
    }
    if (_alertCodes.keys.any(device.hasCapability)) {
      return _Status(
        label: 'OK',
        description: context.tr(fr: 'Aucune alerte', en: 'No alert'),
        color: SafeRColors.success,
        icon: Icons.verified_outlined,
      );
    }
    return null;
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final status = _status(context);
    final temperature = device.hasCapability('temperature') ? device.numValue('temperature') : null;
    final humidity = device.hasCapability('humidity') ? device.numValue('humidity') : null;
    final illuminance = device.hasCapability('illuminance') ? device.numValue('illuminance') : null;
    final battery = device.hasCapability('battery') ? device.numValue('battery') : null;
    final signal = device.hasCapability('signal') ? device.numValue('signal') : null;
    final tamper = device.hasCapability('tamper') ? (device.boolValue('tamper') ?? false) : null;
    final hasGauges = temperature != null || humidity != null || illuminance != null;
    final lastSeen = device.lastSeenAt ?? device.updatedAt;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (status != null)
          PanelCard(
            padding: const EdgeInsets.symmetric(vertical: 28, horizontal: 16),
            child: Column(
              children: [
                Container(
                  width: 112,
                  height: 112,
                  decoration: BoxDecoration(shape: BoxShape.circle, color: status.color.withValues(alpha: 0.14)),
                  child: Icon(status.icon, size: 56, color: status.color),
                ),
                const SizedBox(height: 16),
                Text(status.label, style: theme.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w900, color: status.color, letterSpacing: 1.5)),
                const SizedBox(height: 4),
                Text(status.description, style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant), textAlign: TextAlign.center),
                if (lastSeen != null) ...[
                  const SizedBox(height: 4),
                  Text(context.tr(fr: 'Mis à jour ${timeAgo(context, lastSeen).toLowerCase()}', en: 'Updated ${timeAgo(context, lastSeen).toLowerCase()}'),
                      style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
                ],
              ],
            ),
          ),
        if (hasGauges) ...[
          if (status != null) const SizedBox(height: 12),
          PanelCard(
            title: context.tr(fr: 'Mesures', en: 'Readings'),
            child: Wrap(
              alignment: WrapAlignment.spaceEvenly,
              spacing: 16,
              runSpacing: 16,
              children: [
                if (temperature != null)
                  GaugeTile(
                    value: temperature.toDouble(),
                    min: -10,
                    max: 50,
                    label: context.tr(fr: 'Température', en: 'Temperature'),
                    text: formatNumber(temperature, unit: device.capability('temperature')?.unit ?? '°C'),
                    icon: Icons.device_thermostat,
                    color: SafeRColors.warning,
                  ),
                if (humidity != null)
                  GaugeTile(
                    value: humidity.toDouble(),
                    min: 0,
                    max: 100,
                    label: context.tr(fr: 'Humidité', en: 'Humidity'),
                    text: formatNumber(humidity, unit: device.capability('humidity')?.unit ?? '%', decimals: 0),
                    icon: Icons.water_drop_outlined,
                    color: SafeRColors.primary,
                  ),
                if (illuminance != null)
                  GaugeTile(
                    value: illuminance.toDouble(),
                    min: 0,
                    max: 1000,
                    label: context.tr(fr: 'Luminosité', en: 'Illuminance'),
                    text: formatNumber(illuminance, unit: device.capability('illuminance')?.unit ?? 'lx', decimals: 0),
                    icon: Icons.wb_sunny_outlined,
                    color: const Color(0xFFF59E0B),
                  ),
              ],
            ),
          ),
        ],
        if (battery != null || signal != null || tamper != null) ...[
          const SizedBox(height: 12),
          PanelCard(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            child: Wrap(
              spacing: 8,
              runSpacing: 8,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                if (battery != null) BatteryChip(level: battery),
                if (signal != null) SignalChip(level: signal),
                if (tamper != null)
                  BoolChip(
                    active: tamper,
                    activeLabel: context.tr(fr: 'SABOTAGE', en: 'TAMPER'),
                    inactiveLabel: context.tr(fr: 'Boîtier OK', en: 'Case OK'),
                    activeColor: SafeRColors.danger,
                    icon: tamper ? Icons.report_gmailerrorred : Icons.verified_user_outlined,
                  ),
                OnlineChip(online: device.online),
              ],
            ),
          ),
        ],
        GenericControls(
          device: device,
          exclude: const {'contact', 'open', 'motion', 'smoke', 'co', 'water_leak', 'gas', 'alarm', 'temperature', 'humidity', 'illuminance', 'battery', 'signal', 'tamper'},
        ),
        SectionHeader(title: context.tr(fr: 'Historique', en: 'History'), padding: const EdgeInsets.fromLTRB(4, 20, 4, 8)),
        DeviceEventsList(deviceId: device.id),
      ],
    );
  }
}
