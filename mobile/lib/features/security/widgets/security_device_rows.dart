import 'package:flutter/material.dart';

import '../../../core/i18n.dart';
import '../../../core/models/device.dart';
import '../../../core/theme.dart';
import '../../../core/widgets/widgets.dart';

/// A status chip descriptor (label + colour + icon).
typedef ChipSpec = ({String label, Color color, IconData? icon});

/// Chips describing an alarm panel: arm state, alarm, readiness.
List<ChipSpec> panelChips(BuildContext context, Device device) {
  if (!device.online) return [_offline(context)];
  final mode = device.stringValue('arm_mode') ?? 'disarmed';
  return [
    if (device.boolValue('alarm') ?? false) (label: context.tr(fr: 'Alarme', en: 'Alarm'), color: SafeRColors.danger, icon: Icons.notifications_active),
    (label: securityModeLabel(context, mode), color: SafeRColors.forSecurityMode(mode), icon: null),
    if (device.boolValue('ready') == false) (label: context.tr(fr: 'Non prête', en: 'Not ready'), color: SafeRColors.warning, icon: Icons.error_outline),
  ];
}

/// Chips describing an alarm zone: open / alarm / bypass / tamper.
List<ChipSpec> zoneChips(BuildContext context, Device device) {
  if (!device.online) return [_offline(context)];
  final open = device.boolValue('open') ?? false;
  return [
    if (device.boolValue('alarm') ?? false) (label: context.tr(fr: 'Alarme', en: 'Alarm'), color: SafeRColors.danger, icon: Icons.notifications_active),
    (
      label: open ? context.tr(fr: 'Ouverte', en: 'Open') : context.tr(fr: 'Fermée', en: 'Closed'),
      color: open ? SafeRColors.warning : SafeRColors.success,
      icon: open ? Icons.door_front_door : Icons.check,
    ),
    if (device.boolValue('bypass') ?? false) (label: context.tr(fr: 'Exclue', en: 'Bypassed'), color: Colors.grey, icon: Icons.block),
    if (device.boolValue('tamper') ?? false) (label: context.tr(fr: 'Sabotage', en: 'Tamper'), color: SafeRColors.danger, icon: Icons.warning),
  ];
}

/// Chips describing a sensor, a lock or a siren.
List<ChipSpec> sensorChips(BuildContext context, Device device) {
  if (!device.online) return [_offline(context)];
  final chips = <ChipSpec>[_sensorState(context, device)];
  final battery = device.numValue('battery');
  if (battery != null && battery <= 20) {
    chips.add((label: context.tr(fr: 'Pile ${battery.round()}%', en: 'Battery ${battery.round()}%'), color: SafeRColors.warning, icon: Icons.battery_alert));
  }
  return chips;
}

ChipSpec _offline(BuildContext context) => (label: context.tr(fr: 'Hors ligne', en: 'Offline'), color: Colors.grey, icon: Icons.cloud_off);

ChipSpec _sensorState(BuildContext context, Device device) {
  const ok = SafeRColors.success;
  const warn = SafeRColors.warning;
  const bad = SafeRColors.danger;
  switch (device.category) {
    case 'sensor_contact':
      final open = device.boolValue('contact') ?? false;
      return (label: open ? context.tr(fr: 'Ouvert', en: 'Open') : context.tr(fr: 'Fermé', en: 'Closed'), color: open ? warn : ok, icon: null);
    case 'sensor_motion':
      final motion = device.boolValue('motion') ?? false;
      return (label: motion ? context.tr(fr: 'Mouvement', en: 'Motion') : context.tr(fr: 'Calme', en: 'Clear'), color: motion ? warn : ok, icon: null);
    case 'sensor_smoke':
      return _alert(context, device.boolValue('smoke') ?? false, fr: 'Fumée !', en: 'Smoke!');
    case 'sensor_water':
      return _alert(context, device.boolValue('water_leak') ?? false, fr: 'Fuite !', en: 'Leak!');
    case 'sensor_gas':
      return _alert(context, (device.boolValue('gas') ?? false) || (device.boolValue('co') ?? false), fr: 'Gaz !', en: 'Gas!');
    case 'lock':
      final locked = device.boolValue('locked') ?? false;
      final door = device.boolValue('door') ?? false;
      if (door) return (label: context.tr(fr: 'Porte ouverte', en: 'Door open'), color: warn, icon: Icons.door_front_door);
      return (label: locked ? context.tr(fr: 'Verrouillée', en: 'Locked') : context.tr(fr: 'Déverrouillée', en: 'Unlocked'), color: locked ? ok : warn, icon: locked ? Icons.lock : Icons.lock_open);
    case 'siren':
      final on = device.boolValue('siren') ?? false;
      return (label: on ? context.tr(fr: 'Active', en: 'Sounding') : context.tr(fr: 'Silencieuse', en: 'Silent'), color: on ? bad : ok, icon: Icons.campaign);
    default:
      final summary = deviceStateSummary(context, device);
      return (label: summary.isEmpty ? 'OK' : summary, color: device.isAlerting ? bad : ok, icon: null);
  }
}

ChipSpec _alert(BuildContext context, bool active, {required String fr, required String en}) =>
    (label: active ? context.tr(fr: fr, en: en) : 'OK', color: active ? SafeRColors.danger : SafeRColors.success, icon: active ? Icons.warning : null);

/// Card grouping several [SecurityDeviceRow]s with thin dividers.
class SecurityListCard extends StatelessWidget {
  const SecurityListCard({super.key, required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: Card(
          clipBehavior: Clip.antiAlias,
          child: Column(
            children: [
              for (final (index, child) in children.indexed) ...[
                if (index > 0) const Divider(indent: 68),
                child,
              ],
            ],
          ),
        ),
      );
}

/// One device row: icon box, name, subtitle and trailing status chips.
class SecurityDeviceRow extends StatelessWidget {
  const SecurityDeviceRow({super.key, required this.device, required this.chips, this.subtitle, this.onTap});

  final Device device;
  final List<ChipSpec> chips;
  final String? subtitle;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final alerting = device.isAlerting;
    final accent = alerting ? SafeRColors.danger : (device.online ? SafeRColors.primary : theme.colorScheme.onSurfaceVariant);
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        child: Row(
          children: [
            Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(color: accent.withValues(alpha: 0.14), borderRadius: BorderRadius.circular(12)),
              child: Icon(iconFromName(device.icon, fallback: categoryIcon(device.category)), color: accent, size: 22),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(device.name, maxLines: 1, overflow: TextOverflow.ellipsis, style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w600)),
                  Text(subtitle ?? categoryLabel(context, device.category), maxLines: 1, overflow: TextOverflow.ellipsis, style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
                ],
              ),
            ),
            const SizedBox(width: 8),
            Wrap(
              spacing: 4,
              runSpacing: 4,
              alignment: WrapAlignment.end,
              children: [for (final c in chips) StateChip(label: c.label, color: c.color, icon: c.icon)],
            ),
          ],
        ),
      ),
    );
  }
}

/// Compact empty placeholder for a section (with an optional call to action).
class SectionEmptyCard extends StatelessWidget {
  const SectionEmptyCard({super.key, required this.icon, required this.text, this.actionLabel, this.onAction});

  final IconData icon;
  final String text;
  final String? actionLabel;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Card(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
          child: Row(
            children: [
              Icon(icon, color: theme.colorScheme.onSurfaceVariant),
              const SizedBox(width: 12),
              Expanded(child: Text(text, style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant))),
              if (actionLabel != null && onAction != null) TextButton(onPressed: onAction, child: Text(actionLabel!)),
            ],
          ),
        ),
      ),
    );
  }
}
