import 'package:flutter/material.dart';

import '../../../core/i18n.dart';
import '../../../core/models/home.dart';
import '../../../core/theme.dart';
import '../../../core/widgets/widgets.dart';

/// Room step: optional room for the new device(s).
class RoomPicker extends StatelessWidget {
  const RoomPicker({super.key, required this.rooms, required this.selectedId, required this.onSelected, required this.onConfirm, required this.confirmLabel});

  final List<Room> rooms;
  final String? selectedId;
  final ValueChanged<String?> onSelected;
  final VoidCallback onConfirm;
  final String confirmLabel;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      children: [
        Expanded(
          child: ListView(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
            children: [
              Text(context.tr(fr: "Dans quelle pièce se trouve l'appareil ?", en: 'Which room is the device in?'), style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
              const SizedBox(height: 4),
              Text(context.tr(fr: 'Facultatif — vous pourrez la changer plus tard.', en: 'Optional — you can change it later.'), style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
              const SizedBox(height: 16),
              Card(
                clipBehavior: Clip.antiAlias,
                child: Column(
                  children: [
                    _RoomTile(icon: Icons.home_outlined, name: context.tr(fr: 'Aucune pièce', en: 'No room'), selected: selectedId == null, onTap: () => onSelected(null)),
                    for (final room in rooms) ...[
                      const Divider(height: 1),
                      _RoomTile(
                        icon: iconFromName(room.icon, fallback: Icons.meeting_room_outlined),
                        name: room.name,
                        selected: room.id == selectedId,
                        onTap: () => onSelected(room.id),
                      ),
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
            child: FilledButton(onPressed: onConfirm, child: Text(confirmLabel)),
          ),
        ),
      ],
    );
  }
}

class _RoomTile extends StatelessWidget {
  const _RoomTile({required this.icon, required this.name, required this.selected, required this.onTap});

  final IconData icon;
  final String name;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => ListTile(
        onTap: onTap,
        selected: selected,
        leading: Icon(icon, color: selected ? SafeRColors.primary : null),
        title: Text(name),
        trailing: selected ? const Icon(Icons.check_circle, color: SafeRColors.primary) : const Icon(Icons.radio_button_unchecked),
      );
}
