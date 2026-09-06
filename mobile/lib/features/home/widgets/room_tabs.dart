import 'package:flutter/material.dart';

import '../../../core/i18n.dart';
import '../../../core/models/home.dart';

/// Room filter used by the device grid: null = all rooms, 'none' = unassigned devices.
const String kUnassignedRoomId = 'none';

/// Horizontal room tab bar ("Tous" · rooms · "Non assignés").
class RoomTabBar extends StatelessWidget {
  const RoomTabBar({
    super.key,
    required this.rooms,
    required this.selected,
    required this.onSelected,
    this.showUnassigned = false,
  });

  static const double height = 52;

  final List<Room> rooms;
  final String? selected;
  final ValueChanged<String?> onSelected;
  final bool showUnassigned;

  @override
  Widget build(BuildContext context) {
    final entries = <({String? id, String label})>[
      (id: null, label: context.tr(fr: 'Tous', en: 'All')),
      for (final room in rooms) (id: room.id, label: room.name),
      if (showUnassigned) (id: kUnassignedRoomId, label: context.tr(fr: 'Non assignés', en: 'Unassigned')),
    ];
    // Non-lazy row: a home has a handful of rooms and every pill stays reachable (scroll + ensureVisible).
    return SizedBox(
      height: height,
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
        child: Row(
          children: [
            for (var i = 0; i < entries.length; i++) ...[
              if (i > 0) const SizedBox(width: 8),
              _RoomPill(label: entries[i].label, selected: entries[i].id == selected, onTap: () => onSelected(entries[i].id)),
            ],
          ],
        ),
      ),
    );
  }
}

class _RoomPill extends StatelessWidget {
  const _RoomPill({required this.label, required this.selected, required this.onTap});

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final background = selected ? theme.colorScheme.primary : (theme.cardTheme.color ?? theme.colorScheme.surface);
    final foreground = selected ? theme.colorScheme.onPrimary : theme.colorScheme.onSurface;
    return Semantics(
      button: true,
      selected: selected,
      child: Material(
        color: background,
        borderRadius: BorderRadius.circular(22),
        child: InkWell(
          borderRadius: BorderRadius.circular(22),
          onTap: onTap,
          child: Container(
            constraints: const BoxConstraints(minHeight: 44, minWidth: 56),
            padding: const EdgeInsets.symmetric(horizontal: 16),
            alignment: Alignment.center,
            child: Text(label, style: TextStyle(color: foreground, fontWeight: selected ? FontWeight.w700 : FontWeight.w500, fontSize: 14)),
          ),
        ),
      ),
    );
  }
}
