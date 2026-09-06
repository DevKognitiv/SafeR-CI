import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/i18n.dart';
import '../../../core/models/models.dart';
import '../../../core/providers/providers.dart';
import '../../../core/widgets/widgets.dart';
import 'labels.dart';
import 'sheet_scaffold.dart';

/// Pick a device of the home, grouped by room. With [writableOnly] only controllable devices are listed.
Future<Device?> showDevicePicker(BuildContext context, {required String homeId, bool writableOnly = false}) =>
    showSafeRSheet<Device>(context, builder: (_) => _DevicePickerSheet(homeId: homeId, writableOnly: writableOnly));

/// Pick one capability of [device] (writable ones only when [writableOnly]).
Future<Capability?> showCapabilityPicker(BuildContext context, {required Device device, bool writableOnly = false}) =>
    showSafeRSheet<Capability>(context, builder: (_) => _CapabilityPickerSheet(device: device, writableOnly: writableOnly));

bool _eligible(Device device, bool writableOnly) =>
    writableOnly ? device.capabilities.any((c) => c.writable) : device.capabilities.isNotEmpty;

class _DevicePickerSheet extends ConsumerWidget {
  const _DevicePickerSheet({required this.homeId, required this.writableOnly});

  final String homeId;
  final bool writableOnly;

  List<({String name, List<Device> devices})> _group(BuildContext context, List<Device> devices, List<Room> rooms) {
    final sorted = [...rooms]..sort((a, b) => a.sortOrder.compareTo(b.sortOrder));
    final groups = <({String name, List<Device> devices})>[];
    for (final room in sorted) {
      final inRoom = devices.where((d) => d.roomId == room.id).toList();
      if (inRoom.isNotEmpty) groups.add((name: room.name, devices: inRoom));
    }
    final roomIds = rooms.map((r) => r.id).toSet();
    final rest = devices.where((d) => d.roomId == null || !roomIds.contains(d.roomId)).toList();
    if (rest.isNotEmpty) groups.add((name: context.tr(fr: 'Non assignés', en: 'Unassigned'), devices: rest));
    return groups;
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final devicesAsync = ref.watch(devicesProvider(homeId));
    final rooms = ref.watch(roomsProvider(homeId));
    final scheme = Theme.of(context).colorScheme;
    return SheetScaffold(
      title: context.tr(fr: 'Choisir un appareil', en: 'Choose a device'),
      scrollable: false,
      child: devicesAsync.when(
        loading: () => const SizedBox(height: 180, child: LoadingView()),
        error: (error, _) => SizedBox(height: 260, child: ErrorView(error: error, onRetry: () => ref.read(devicesProvider(homeId).notifier).refresh())),
        data: (all) {
          final devices = all.where((d) => _eligible(d, writableOnly)).toList();
          if (devices.isEmpty) {
            return SizedBox(
              height: 260,
              child: EmptyState(
                icon: Icons.devices_other,
                title: context.tr(fr: 'Aucun appareil compatible', en: 'No compatible device'),
                subtitle: context.tr(fr: "Ajoutez d'abord un appareil à cette maison.", en: 'Add a device to this home first.'),
              ),
            );
          }
          final groups = _group(context, devices, rooms);
          return ListView(
            shrinkWrap: true,
            padding: const EdgeInsets.only(bottom: 16),
            children: [
              for (final group in groups) ...[
                SectionHeader(title: group.name, padding: const EdgeInsets.fromLTRB(20, 12, 20, 4)),
                for (final device in group.devices)
                  ListTile(
                    minTileHeight: 56,
                    leading: CircleAvatar(
                      backgroundColor: scheme.primary.withValues(alpha: 0.12),
                      child: Icon(iconFromName(device.icon, fallback: categoryIcon(device.category)), color: scheme.primary),
                    ),
                    title: Text(device.name),
                    subtitle: Text(categoryLabel(context, device.category)),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => Navigator.of(context).pop(device),
                  ),
              ],
            ],
          );
        },
      ),
    );
  }
}

class _CapabilityPickerSheet extends StatelessWidget {
  const _CapabilityPickerSheet({required this.device, required this.writableOnly});

  final Device device;
  final bool writableOnly;

  IconData _typeIcon(String type) {
    switch (type) {
      case 'bool':
        return Icons.toggle_on_outlined;
      case 'int':
      case 'float':
        return Icons.tune;
      case 'enum':
        return Icons.list;
      case 'color':
        return Icons.palette_outlined;
      default:
        return Icons.text_fields;
    }
  }

  @override
  Widget build(BuildContext context) {
    final caps = device.capabilities.where((c) => !writableOnly || c.writable).toList();
    return SheetScaffold(
      title: device.name,
      subtitle: context.tr(fr: 'Choisir une fonction', en: 'Choose a function'),
      scrollable: false,
      child: caps.isEmpty
          ? SizedBox(height: 200, child: EmptyState(icon: Icons.block, title: context.tr(fr: 'Aucune fonction disponible', en: 'No function available')))
          : ListView(
              shrinkWrap: true,
              padding: const EdgeInsets.only(bottom: 16),
              children: [
                for (final cap in caps)
                  ListTile(
                    minTileHeight: 56,
                    leading: Icon(_typeIcon(cap.type)),
                    title: Text(capabilityLabel(context, cap.code, capability: cap)),
                    subtitle: device.state.containsKey(cap.code)
                        ? Text(valueLabel(context, code: cap.code, value: device.state[cap.code], capability: cap))
                        : null,
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => Navigator.of(context).pop(cap),
                  ),
              ],
            ),
    );
  }
}
