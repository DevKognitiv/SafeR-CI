import 'package:flutter/material.dart';

import '../../../core/i18n.dart';
import '../../../core/models/device.dart';
import '../../../core/theme.dart';
import '../../../core/widgets/widgets.dart';

/// Final step: the devices that were added.
class PairingSuccessView extends StatelessWidget {
  const PairingSuccessView({super.key, required this.devices, required this.onDone, required this.onAddAnother, this.message = '', this.roomName});

  final List<Device> devices;
  final String message;
  final String? roomName;
  final VoidCallback onDone;
  final VoidCallback onAddAnother;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final n = devices.length;
    final title = n == 1 ? context.tr(fr: 'Appareil ajouté', en: 'Device added') : context.tr(fr: '$n appareils ajoutés', en: '$n devices added');
    return Column(
      children: [
        Expanded(
          child: ListView(
            padding: const EdgeInsets.fromLTRB(16, 24, 16, 16),
            children: [
              Center(
                child: Container(
                  width: 88,
                  height: 88,
                  decoration: BoxDecoration(shape: BoxShape.circle, color: SafeRColors.success.withValues(alpha: 0.14)),
                  child: const Icon(Icons.check_rounded, size: 48, color: SafeRColors.success),
                ),
              ),
              const SizedBox(height: 20),
              Text(title, textAlign: TextAlign.center, style: theme.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w700)),
              if (message.isNotEmpty) ...[
                const SizedBox(height: 6),
                Text(message, textAlign: TextAlign.center, style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
              ],
              const SizedBox(height: 24),
              if (devices.isEmpty)
                Text(
                  context.tr(fr: 'Aucun nouvel appareil (déjà présent ou aucune sélection).', en: 'No new device (already present or nothing selected).'),
                  textAlign: TextAlign.center,
                  style: theme.textTheme.bodySmall,
                )
              else
                Card(
                  clipBehavior: Clip.antiAlias,
                  child: Column(
                    children: [
                      for (var i = 0; i < devices.length; i++) ...[
                        if (i > 0) const Divider(height: 1),
                        _PairedTile(device: devices[i], roomName: roomName),
                      ],
                    ],
                  ),
                ),
            ],
          ),
        ),
        SafeArea(
          top: false,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                FilledButton(onPressed: onDone, child: Text(context.tr(fr: 'Terminer', en: 'Done'))),
                const SizedBox(height: 8),
                OutlinedButton.icon(
                  onPressed: onAddAnother,
                  style: OutlinedButton.styleFrom(minimumSize: const Size.fromHeight(48), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12))),
                  icon: const Icon(Icons.add),
                  label: Text(context.tr(fr: 'Ajouter un autre', en: 'Add another')),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _PairedTile extends StatelessWidget {
  const _PairedTile({required this.device, this.roomName});

  final Device device;
  final String? roomName;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final subtitle = [categoryLabel(context, device.category), if (roomName != null && roomName!.isNotEmpty) roomName!].join(' · ');
    return ListTile(
      leading: Container(
        width: 40,
        height: 40,
        decoration: BoxDecoration(color: SafeRColors.primary.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(12)),
        child: Icon(iconFromName(device.icon, fallback: categoryIcon(device.category)), color: SafeRColors.primary, size: 22),
      ),
      title: Text(device.name, maxLines: 1, overflow: TextOverflow.ellipsis, style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w600)),
      subtitle: Text(subtitle, maxLines: 1, overflow: TextOverflow.ellipsis),
      trailing: device.online
          ? StateChip(label: context.tr(fr: 'En ligne', en: 'Online'), color: SafeRColors.success, icon: Icons.wifi)
          : StateChip(label: context.tr(fr: 'Hors ligne', en: 'Offline'), color: theme.colorScheme.onSurfaceVariant, icon: Icons.wifi_off),
    );
  }
}
