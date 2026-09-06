import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/i18n.dart';
import '../../../core/models/device.dart';
import '../../../core/theme.dart';
import '../../../core/widgets/widgets.dart';
import '../widgets/big_power_button.dart';
import '../widgets/device_command.dart';
import '../widgets/device_events_list.dart';
import '../widgets/dialogs.dart';
import '../widgets/generic_controls.dart';
import '../widgets/panel_card.dart';
import '../widgets/status_chips.dart';

/// Lock: big lock/unlock button with confirmation, door state, battery and history.
class LockPanel extends ConsumerWidget {
  const LockPanel({super.key, required this.device});

  final Device device;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final locked = device.boolValue('locked') ?? false;
    final lockCap = writableCapability(device, 'locked', type: 'bool');
    final door = device.hasCapability('door') ? (device.boolValue('door') ?? false) : null;
    final battery = device.hasCapability('battery') ? device.numValue('battery') : null;

    Future<void> toggle() async {
      final unlocking = locked;
      final confirmed = await showConfirmDialog(
        context,
        icon: unlocking ? Icons.lock_open : Icons.lock,
        title:
            unlocking ? context.tr(fr: 'Déverrouiller la serrure ?', en: 'Unlock the door?') : context.tr(fr: 'Verrouiller la serrure ?', en: 'Lock the door?'),
        message: unlocking
            ? context.tr(fr: '${device.name} sera déverrouillée immédiatement.', en: '${device.name} will be unlocked immediately.')
            : context.tr(fr: '${device.name} sera verrouillée immédiatement.', en: '${device.name} will be locked immediately.'),
        confirmLabel: unlocking ? context.tr(fr: 'Déverrouiller', en: 'Unlock') : context.tr(fr: 'Verrouiller', en: 'Lock'),
        destructive: unlocking,
      );
      if (!confirmed || !context.mounted) return;
      final ok = await sendDeviceCommand(context, ref, device, 'locked', !locked);
      if (ok && context.mounted) {
        showSnack(context, unlocking ? context.tr(fr: 'Serrure déverrouillée', en: 'Door unlocked') : context.tr(fr: 'Serrure verrouillée', en: 'Door locked'));
      }
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        PanelCard(
          padding: const EdgeInsets.symmetric(vertical: 28, horizontal: 16),
          child: Column(
            children: [
              BigPowerButton(
                active: locked,
                icon: locked ? Icons.lock : Icons.lock_open,
                activeColor: SafeRColors.success,
                semanticsLabel: locked ? context.tr(fr: 'Déverrouiller', en: 'Unlock') : context.tr(fr: 'Verrouiller', en: 'Lock'),
                caption: locked ? context.tr(fr: 'VERROUILLÉE', en: 'LOCKED') : context.tr(fr: 'OUVERTE', en: 'UNLOCKED'),
                onPressed: device.online && lockCap != null ? toggle : null,
              ),
              const SizedBox(height: 8),
              Text(
                locked ? context.tr(fr: 'Appuyez pour déverrouiller', en: 'Tap to unlock') : context.tr(fr: 'Appuyez pour verrouiller', en: 'Tap to lock'),
                style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
              ),
            ],
          ),
        ),
        const SizedBox(height: 12),
        PanelCard(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          child: Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              if (door != null)
                BoolChip(
                  active: door,
                  activeLabel: context.tr(fr: 'Porte ouverte', en: 'Door open'),
                  inactiveLabel: context.tr(fr: 'Porte fermée', en: 'Door closed'),
                  activeColor: SafeRColors.warning,
                  inactiveColor: SafeRColors.success,
                  icon: door ? Icons.door_front_door : Icons.door_front_door_outlined,
                ),
              if (battery != null) BatteryChip(level: battery),
              OnlineChip(online: device.online),
            ],
          ),
        ),
        GenericControls(device: device, exclude: const {'locked', 'door', 'battery'}),
        SectionHeader(title: context.tr(fr: 'Historique', en: 'History'), padding: const EdgeInsets.fromLTRB(4, 20, 4, 8)),
        DeviceEventsList(deviceId: device.id),
      ],
    );
  }
}
