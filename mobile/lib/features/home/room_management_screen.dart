import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/i18n.dart';
import '../../core/models/home.dart';
import '../../core/providers/providers.dart';
import '../../core/router.dart';
import '../../core/widgets/widgets.dart';
import 'widgets/text_input_dialog.dart';

/// Tuya "Room management": list, add, rename, delete and reorder the rooms of the current home.
class RoomManagementScreen extends ConsumerStatefulWidget {
  const RoomManagementScreen({super.key});

  @override
  ConsumerState<RoomManagementScreen> createState() => _RoomManagementScreenState();
}

class _RoomManagementScreenState extends ConsumerState<RoomManagementScreen> {
  /// Local order shown while a reorder request is in flight.
  List<Room>? _pendingOrder;

  Future<void> _reload() => ref.read(homesProvider.notifier).refresh();

  Future<void> _add(String homeId) async {
    final name = await showTextInputDialog(
      context,
      title: context.tr(fr: 'Ajouter une pièce', en: 'Add a room'),
      confirmLabel: context.tr(fr: 'Ajouter', en: 'Add'),
      hint: context.tr(fr: 'Nom de la pièce', en: 'Room name'),
    );
    if (name == null || !mounted) return;
    try {
      await ref.read(hubClientProvider).createRoom(homeId, name);
      await _reload();
      if (mounted) showSnack(context, context.tr(fr: 'Pièce ajoutée', en: 'Room added'));
    } catch (e) {
      if (mounted) showErrorSnack(context, e);
    }
  }

  Future<void> _rename(Room room) async {
    final name = await showTextInputDialog(
      context,
      title: context.tr(fr: 'Renommer la pièce', en: 'Rename room'),
      confirmLabel: context.tr(fr: 'Enregistrer', en: 'Save'),
      initialValue: room.name,
      hint: context.tr(fr: 'Nom de la pièce', en: 'Room name'),
    );
    if (name == null || name == room.name || !mounted) return;
    try {
      await ref.read(hubClientProvider).updateRoom(room.id, name: name);
      await _reload();
      if (mounted) showSnack(context, context.tr(fr: 'Pièce renommée', en: 'Room renamed'));
    } catch (e) {
      if (mounted) showErrorSnack(context, e);
    }
  }

  Future<void> _delete(Room room) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(context.tr(fr: 'Supprimer « ${room.name} » ?', en: 'Delete "${room.name}"?')),
        content: Text(context.tr(fr: 'Les appareils de cette pièce ne seront pas supprimés.', en: 'Devices in this room will not be deleted.')),
        actions: [
          TextButton(onPressed: () => Navigator.of(dialogContext).pop(false), child: Text(context.tr(fr: 'Annuler', en: 'Cancel'))),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: Theme.of(context).colorScheme.error, minimumSize: const Size(88, 44)),
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: Text(context.tr(fr: 'Supprimer', en: 'Delete')),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    try {
      await ref.read(hubClientProvider).deleteRoom(room.id);
      await _reload();
      if (mounted) showSnack(context, context.tr(fr: 'Pièce supprimée', en: 'Room deleted'));
    } catch (e) {
      if (mounted) showErrorSnack(context, e);
    }
  }

  /// [newIndex] is already adjusted for the removed item (ReorderableListView.onReorderItem semantics).
  Future<void> _reorder(String homeId, List<Room> rooms, int oldIndex, int newIndex) async {
    final list = List.of(rooms);
    final moved = list.removeAt(oldIndex);
    list.insert(newIndex, moved);
    setState(() => _pendingOrder = list);
    try {
      await ref.read(hubClientProvider).reorderRooms(homeId, list.map((r) => r.id).toList());
      await _reload();
    } catch (e) {
      if (mounted) showErrorSnack(context, e);
    } finally {
      if (mounted) setState(() => _pendingOrder = null);
    }
  }

  Future<void> _showActions(Room room) async {
    final action = await showModalBottomSheet<_RoomAction>(
      context: context,
      showDragHandle: true,
      builder: (sheetContext) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: Icon(iconFromName(room.icon, fallback: Icons.meeting_room_outlined)),
              title: Text(room.name, style: const TextStyle(fontWeight: FontWeight.w700)),
            ),
            const Divider(),
            ListTile(
              leading: const Icon(Icons.edit_outlined),
              title: Text(sheetContext.tr(fr: 'Renommer', en: 'Rename')),
              onTap: () => Navigator.of(sheetContext).pop(_RoomAction.rename),
            ),
            ListTile(
              leading: Icon(Icons.delete_outline, color: Theme.of(sheetContext).colorScheme.error),
              title: Text(sheetContext.tr(fr: 'Supprimer', en: 'Delete'), style: TextStyle(color: Theme.of(sheetContext).colorScheme.error)),
              onTap: () => Navigator.of(sheetContext).pop(_RoomAction.delete),
            ),
            const SizedBox(height: 8),
          ],
        ),
      ),
    );
    if (action == null || !mounted) return;
    switch (action) {
      case _RoomAction.rename:
        await _rename(room);
      case _RoomAction.delete:
        await _delete(room);
    }
  }

  @override
  Widget build(BuildContext context) {
    final homes = ref.watch(homesProvider);
    final home = ref.watch(currentHomeProvider);
    final title = Text(context.tr(fr: 'Gérer les pièces', en: 'Manage rooms'));
    if (home == null) {
      return Scaffold(
        appBar: AppBar(title: title),
        body: homes.isLoading
            ? const LoadingView()
            : EmptyState(
                icon: Icons.home_work_outlined,
                title: context.tr(fr: 'Créez votre première maison', en: 'Create your first home'),
                actionLabel: context.tr(fr: 'Créer une maison', en: 'Create a home'),
                onAction: () => context.push(Routes.homes),
              ),
      );
    }

    final List<Room> rooms = _pendingOrder ?? ref.watch(roomsProvider(home.id));
    final devices = ref.watch(devicesProvider(home.id)).value;
    int countFor(Room room) => devices == null ? room.deviceCount : devices.where((d) => d.roomId == room.id).length;
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: title),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _add(home.id),
        icon: const Icon(Icons.add),
        label: Text(context.tr(fr: 'Ajouter une pièce', en: 'Add a room')),
      ),
      body: rooms.isEmpty
          ? EmptyState(
              icon: Icons.meeting_room_outlined,
              title: context.tr(fr: 'Aucune pièce', en: 'No rooms'),
              subtitle: context.tr(fr: 'Créez des pièces pour organiser vos appareils.', en: 'Create rooms to organise your devices.'),
              actionLabel: context.tr(fr: 'Ajouter une pièce', en: 'Add a room'),
              onAction: () => _add(home.id),
            )
          : Column(
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
                  child: Row(
                    children: [
                      Icon(Icons.info_outline, size: 16, color: theme.colorScheme.onSurfaceVariant),
                      const SizedBox(width: 6),
                      Expanded(
                        child: Text(
                          context.tr(fr: 'Appuyez sur une pièce pour la modifier, glissez la poignée pour réorganiser.', en: 'Tap a room to edit it, drag the handle to reorder.'),
                          style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                        ),
                      ),
                    ],
                  ),
                ),
                Expanded(
                  child: ReorderableListView.builder(
                    padding: const EdgeInsets.fromLTRB(16, 8, 16, 96),
                    buildDefaultDragHandles: false,
                    itemCount: rooms.length,
                    onReorderItem: (oldIndex, newIndex) => _reorder(home.id, rooms, oldIndex, newIndex),
                    proxyDecorator: (child, _, __) => Material(color: Colors.transparent, elevation: 4, borderRadius: BorderRadius.circular(16), child: child),
                    itemBuilder: (context, index) {
                      final room = rooms[index];
                      return Padding(
                        key: ValueKey('room-${room.id}'),
                        padding: const EdgeInsets.only(bottom: 10),
                        child: _RoomCard(
                          room: room,
                          deviceCount: countFor(room),
                          index: index,
                          onTap: () => _showActions(room),
                        ),
                      );
                    },
                  ),
                ),
              ],
            ),
    );
  }
}

enum _RoomAction { rename, delete }

class _RoomCard extends StatelessWidget {
  const _RoomCard({required this.room, required this.deviceCount, required this.index, required this.onTap});

  final Room room;
  final int deviceCount;
  final int index;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final countLabel = context.tr(fr: deviceCount == 1 ? '1 appareil' : '$deviceCount appareils', en: deviceCount == 1 ? '1 device' : '$deviceCount devices');
    return Card(
      child: ListTile(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        leading: Container(
          width: 44,
          height: 44,
          decoration: BoxDecoration(color: theme.colorScheme.primary.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(12)),
          child: Icon(iconFromName(room.icon, fallback: Icons.meeting_room_outlined), color: theme.colorScheme.primary),
        ),
        title: Text(room.name, style: const TextStyle(fontWeight: FontWeight.w600)),
        subtitle: Text(countLabel),
        trailing: ReorderableDragStartListener(
          index: index,
          child: Semantics(
            label: context.tr(fr: 'Réorganiser ${room.name}', en: 'Reorder ${room.name}'),
            child: const SizedBox(width: 44, height: 44, child: Icon(Icons.drag_handle)),
          ),
        ),
        onTap: onTap,
      ),
    );
  }
}
