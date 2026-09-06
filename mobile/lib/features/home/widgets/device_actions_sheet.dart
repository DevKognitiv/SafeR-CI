import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/i18n.dart';
import '../../../core/models/device.dart';
import '../../../core/models/home.dart';
import '../../../core/providers/providers.dart';
import '../../../core/routes.dart';
import '../../../core/widgets/widgets.dart';
import 'text_input_dialog.dart';

enum _DeviceAction { rename, move, settings }

/// Long-press menu of a device tile: rename · move to room · device settings.
Future<void> showDeviceActions(BuildContext context, WidgetRef ref, {required Device device, required List<Room> rooms}) async {
  final action = await showModalBottomSheet<_DeviceAction>(
    context: context,
    showDragHandle: true,
    builder: (_) => _DeviceActionsSheet(device: device, rooms: rooms),
  );
  if (action == null || !context.mounted) return;
  switch (action) {
    case _DeviceAction.rename:
      await _rename(context, ref, device);
    case _DeviceAction.move:
      await _move(context, ref, device, rooms);
    case _DeviceAction.settings:
      context.push(Routes.deviceSettings(device.id));
  }
}

Future<void> _rename(BuildContext context, WidgetRef ref, Device device) async {
  final name = await showTextInputDialog(
    context,
    title: context.tr(fr: 'Renommer l\'appareil', en: 'Rename device'),
    confirmLabel: context.tr(fr: 'Enregistrer', en: 'Save'),
    initialValue: device.name,
    hint: context.tr(fr: 'Nouveau nom', en: 'New name'),
  );
  if (name == null || name == device.name || !context.mounted) return;
  try {
    await ref.read(devicesProvider(device.homeId).notifier).updateDevice(device.id, name: name);
    if (context.mounted) showSnack(context, context.tr(fr: 'Appareil renommé', en: 'Device renamed'));
  } catch (e) {
    if (context.mounted) showErrorSnack(context, e);
  }
}

class _RoomChoice {
  const _RoomChoice(this.roomId);

  /// null = remove from its room.
  final String? roomId;
}

Future<void> _move(BuildContext context, WidgetRef ref, Device device, List<Room> rooms) async {
  final choice = await showModalBottomSheet<_RoomChoice>(
    context: context,
    showDragHandle: true,
    builder: (_) => _RoomPickerSheet(device: device, rooms: rooms),
  );
  if (choice == null || choice.roomId == device.roomId || !context.mounted) return;
  try {
    await ref.read(devicesProvider(device.homeId).notifier).updateDevice(device.id, roomId: choice.roomId, clearRoom: choice.roomId == null);
    if (context.mounted) showSnack(context, context.tr(fr: 'Appareil déplacé', en: 'Device moved'));
  } catch (e) {
    if (context.mounted) showErrorSnack(context, e);
  }
}

class _DeviceActionsSheet extends StatelessWidget {
  const _DeviceActionsSheet({required this.device, required this.rooms});

  final Device device;
  final List<Room> rooms;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final room = rooms.where((r) => r.id == device.roomId).firstOrNull;
    final subtitle = [categoryLabel(context, device.category), if (room != null) room.name].join(' · ');
    return SafeArea(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          ListTile(
            leading: Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(color: theme.colorScheme.primary.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(12)),
              child: Icon(iconFromName(device.icon, fallback: categoryIcon(device.category)), color: theme.colorScheme.primary),
            ),
            title: Text(device.name, style: const TextStyle(fontWeight: FontWeight.w700)),
            subtitle: Text(subtitle),
          ),
          const Divider(),
          ListTile(
            leading: const Icon(Icons.edit_outlined),
            title: Text(context.tr(fr: 'Renommer', en: 'Rename')),
            onTap: () => Navigator.of(context).pop(_DeviceAction.rename),
          ),
          ListTile(
            leading: const Icon(Icons.meeting_room_outlined),
            title: Text(context.tr(fr: 'Déplacer vers une pièce', en: 'Move to a room')),
            onTap: () => Navigator.of(context).pop(_DeviceAction.move),
          ),
          ListTile(
            leading: const Icon(Icons.settings_outlined),
            title: Text(context.tr(fr: 'Paramètres de l\'appareil', en: 'Device settings')),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => Navigator.of(context).pop(_DeviceAction.settings),
          ),
          const SizedBox(height: 8),
        ],
      ),
    );
  }
}

class _RoomPickerSheet extends StatelessWidget {
  const _RoomPickerSheet({required this.device, required this.rooms});

  final Device device;
  final List<Room> rooms;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return SafeArea(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 0, 20, 8),
            child: Text(context.tr(fr: 'Déplacer vers une pièce', en: 'Move to a room'), style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
          ),
          Flexible(
            child: ListView(
              shrinkWrap: true,
              children: [
                for (final room in rooms)
                  ListTile(
                    leading: Icon(iconFromName(room.icon, fallback: Icons.meeting_room_outlined)),
                    title: Text(room.name),
                    trailing: room.id == device.roomId ? Icon(Icons.check_circle, color: theme.colorScheme.primary) : null,
                    onTap: () => Navigator.of(context).pop(_RoomChoice(room.id)),
                  ),
                ListTile(
                  leading: const Icon(Icons.block_outlined),
                  title: Text(context.tr(fr: 'Aucune pièce', en: 'No room')),
                  trailing: device.roomId == null ? Icon(Icons.check_circle, color: theme.colorScheme.primary) : null,
                  onTap: () => Navigator.of(context).pop(const _RoomChoice(null)),
                ),
              ],
            ),
          ),
          const SizedBox(height: 8),
        ],
      ),
    );
  }
}
