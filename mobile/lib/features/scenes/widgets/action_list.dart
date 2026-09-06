import 'package:flutter/material.dart';

import '../../../core/i18n.dart';
import '../../../core/models/models.dart';
import 'labels.dart';

/// Apply a drag reorder to [items] (new list). Follows the Flutter contract of
/// `ReorderableList.onReorder`: [newIndex] is the drop slot *before* the item
/// is removed, so it is decremented when the item moves down the list.
List<T> reorderedList<T>(List<T> items, int oldIndex, int newIndex) {
  final list = List.of(items);
  if (oldIndex < 0 || oldIndex >= list.length) return list;
  final target = (oldIndex < newIndex ? newIndex - 1 : newIndex).clamp(0, list.length - 1);
  final item = list.removeAt(oldIndex);
  list.insert(target, item);
  return list;
}

/// Reorderable list of actions (sliver) with a delete button per row.
class SliverActionList extends StatelessWidget {
  const SliverActionList({super.key, required this.actions, required this.devices, this.scenes = const [], required this.onReorder, required this.onRemove});

  final List<SceneAction> actions;
  final List<Device> devices;
  final List<Scene> scenes;
  final void Function(int oldIndex, int newIndex) onReorder;
  final ValueChanged<int> onRemove;

  @override
  Widget build(BuildContext context) => SliverPadding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        sliver: SliverReorderableList(
          itemCount: actions.length,
          onReorderItem: onReorder,
          itemBuilder: (context, index) => Padding(
            key: ObjectKey(actions[index]),
            padding: const EdgeInsets.only(bottom: 8),
            child: ActionTile(index: index, action: actions[index], devices: devices, scenes: scenes, onRemove: () => onRemove(index)),
          ),
        ),
      );
}

/// One action row: drag handle, icon, summary and delete.
class ActionTile extends StatelessWidget {
  const ActionTile({super.key, required this.index, required this.action, required this.devices, this.scenes = const [], this.onRemove});

  final int index;
  final SceneAction action;
  final List<Device> devices;
  final List<Scene> scenes;
  final VoidCallback? onRemove;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      child: ListTile(
        minTileHeight: 56,
        leading: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            ReorderableDragStartListener(
              index: index,
              child: Semantics(
                label: context.tr(fr: 'Déplacer', en: 'Move'),
                child: const Padding(padding: EdgeInsets.only(right: 6), child: Icon(Icons.drag_indicator)),
              ),
            ),
            CircleAvatar(radius: 18, backgroundColor: scheme.primary.withValues(alpha: 0.12), child: Icon(actionIcon(action.type), size: 20, color: scheme.primary)),
          ],
        ),
        title: Text(actionSummary(context, action, devices: devices, scenes: scenes), maxLines: 2, overflow: TextOverflow.ellipsis),
        subtitle: Text(actionTypeLabel(context, action.type)),
        trailing: IconButton(
          icon: const Icon(Icons.delete_outline),
          tooltip: context.tr(fr: 'Supprimer', en: 'Delete'),
          onPressed: onRemove,
        ),
      ),
    );
  }
}

/// One trigger / condition row.
class RuleTile extends StatelessWidget {
  const RuleTile({super.key, required this.rule, required this.devices, this.onRemove});

  final Rule rule;
  final List<Device> devices;
  final VoidCallback? onRemove;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
      child: Card(
        child: ListTile(
          minTileHeight: 56,
          leading: CircleAvatar(radius: 18, backgroundColor: scheme.tertiary.withValues(alpha: 0.12), child: Icon(ruleIcon(rule.type), size: 20, color: scheme.tertiary)),
          title: Text(ruleSummary(context, rule, devices: devices), maxLines: 2, overflow: TextOverflow.ellipsis),
          subtitle: Text(ruleTypeLabel(context, rule.type)),
          trailing: IconButton(
            icon: const Icon(Icons.delete_outline),
            tooltip: context.tr(fr: 'Supprimer', en: 'Delete'),
            onPressed: onRemove,
          ),
        ),
      ),
    );
  }
}

/// Full-width outlined "Ajouter …" button.
class AddItemButton extends StatelessWidget {
  const AddItemButton({super.key, required this.label, required this.onPressed});

  final String label;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
        child: OutlinedButton.icon(
          style: OutlinedButton.styleFrom(minimumSize: const Size.fromHeight(48), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12))),
          onPressed: onPressed,
          icon: const Icon(Icons.add),
          label: Text(label),
        ),
      );
}

/// Sticky bottom bar with the primary save button.
class SaveBar extends StatelessWidget {
  const SaveBar({super.key, required this.label, required this.onPressed, this.busy = false});

  final String label;
  final VoidCallback? onPressed;
  final bool busy;

  @override
  Widget build(BuildContext context) => SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
          child: FilledButton(
            onPressed: busy ? null : onPressed,
            child: busy ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2)) : Text(label),
          ),
        ),
      );
}
