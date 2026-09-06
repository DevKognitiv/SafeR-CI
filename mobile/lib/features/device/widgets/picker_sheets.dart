import 'package:flutter/material.dart';

import '../../../core/i18n.dart';
import '../../../core/models/home.dart';
import '../../../core/widgets/widgets.dart';

/// Result of the room picker: `roomId == null` means "no room".
class RoomChoice {
  const RoomChoice(this.roomId);

  final String? roomId;
}

/// Bottom sheet listing the rooms of the home (+ "no room").
Future<RoomChoice?> showRoomPickerSheet(BuildContext context, {required List<Room> rooms, required String? currentRoomId}) => showModalBottomSheet<RoomChoice>(
      context: context,
      showDragHandle: true,
      builder: (context) {
        final theme = Theme.of(context);
        return SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 0, 20, 8),
                child: Text(context.tr(fr: 'Choisir une pièce', en: 'Choose a room'), style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
              ),
              Flexible(
                child: ListView(
                  shrinkWrap: true,
                  children: [
                    for (final room in rooms)
                      ListTile(
                        leading: Icon(iconFromName(room.icon, fallback: Icons.meeting_room_outlined)),
                        title: Text(room.name),
                        trailing: room.id == currentRoomId ? Icon(Icons.check_circle, color: theme.colorScheme.primary) : null,
                        onTap: () => Navigator.of(context).pop(RoomChoice(room.id)),
                      ),
                    ListTile(
                      leading: const Icon(Icons.block_outlined),
                      title: Text(context.tr(fr: 'Aucune pièce', en: 'No room')),
                      trailing: currentRoomId == null ? Icon(Icons.check_circle, color: theme.colorScheme.primary) : null,
                      onTap: () => Navigator.of(context).pop(const RoomChoice(null)),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 8),
            ],
          ),
        );
      },
    );

/// Icon names understood by [iconFromName] that make sense for a device.
const List<String> kDeviceIconNames = [
  'lightbulb',
  'light',
  'toggle_on',
  'power',
  'electrical_services',
  'blinds',
  'thermostat',
  'ac_unit',
  'door_front_door',
  'motion_photos_on',
  'device_thermostat',
  'water_drop',
  'local_fire_department',
  'water',
  'gas_meter',
  'sensors',
  'videocam',
  'doorbell',
  'dns',
  'lock',
  'key',
  'campaign',
  'shield',
  'security',
  'radar',
  'hub',
  'router',
  'wifi',
  'settings_remote',
  'home',
  'devices_other',
];

/// Bottom sheet with a grid of device icons. Resolves with the icon name.
Future<String?> showIconPickerSheet(BuildContext context, {required String? current}) => showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      builder: (context) {
        final theme = Theme.of(context);
        return SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 0, 20, 12),
                child: Text(context.tr(fr: 'Choisir une icône', en: 'Choose an icon'), style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
              ),
              Flexible(
                child: GridView.count(
                  shrinkWrap: true,
                  crossAxisCount: 5,
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  mainAxisSpacing: 8,
                  crossAxisSpacing: 8,
                  children: [
                    for (final name in kDeviceIconNames)
                      Semantics(
                        button: true,
                        selected: name == current,
                        label: name.replaceAll('_', ' '),
                        child: InkWell(
                          borderRadius: BorderRadius.circular(14),
                          onTap: () => Navigator.of(context).pop(name),
                          child: Container(
                            decoration: BoxDecoration(
                              color: name == current ? theme.colorScheme.primary.withValues(alpha: 0.16) : theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.5),
                              borderRadius: BorderRadius.circular(14),
                              border: name == current ? Border.all(color: theme.colorScheme.primary, width: 2) : null,
                            ),
                            child: Icon(iconFromName(name), color: name == current ? theme.colorScheme.primary : theme.colorScheme.onSurfaceVariant),
                          ),
                        ),
                      ),
                  ],
                ),
              ),
              const SizedBox(height: 12),
            ],
          ),
        );
      },
    );
