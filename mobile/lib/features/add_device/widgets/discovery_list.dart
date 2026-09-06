import 'package:flutter/material.dart';

import '../../../core/i18n.dart';
import '../../../core/models/brand.dart';
import '../../../core/widgets/widgets.dart';

/// Discovery step: selectable list of devices found by the hub.
class DiscoveryList extends StatelessWidget {
  const DiscoveryList({
    super.key,
    required this.devices,
    required this.selected,
    required this.onToggle,
    required this.onSelectAll,
    required this.onContinue,
    this.onBack,
  });

  final List<DiscoveredDevice> devices;
  final Set<String> selected;
  final void Function(String externalId, bool selected) onToggle;
  final ValueChanged<bool> onSelectAll;
  final VoidCallback onContinue;
  final VoidCallback? onBack;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final allSelected = selected.length == devices.length;
    final count = selected.length;
    return Column(
      children: [
        Expanded(
          child: ListView(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      context.tr(fr: '${devices.length} appareil${devices.length > 1 ? 's' : ''} trouvé${devices.length > 1 ? 's' : ''}', en: '${devices.length} device${devices.length > 1 ? 's' : ''} found'),
                      style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700),
                    ),
                  ),
                  TextButton(
                    onPressed: () => onSelectAll(!allSelected),
                    child: Text(allSelected ? context.tr(fr: 'Tout désélectionner', en: 'Deselect all') : context.tr(fr: 'Tout sélectionner', en: 'Select all')),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Card(
                clipBehavior: Clip.antiAlias,
                child: Column(
                  children: [
                    for (var i = 0; i < devices.length; i++) ...[
                      if (i > 0) const Divider(height: 1),
                      _DiscoveredTile(device: devices[i], selected: selected.contains(devices[i].externalId), onChanged: (v) => onToggle(devices[i].externalId, v)),
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
                FilledButton.icon(
                  onPressed: count == 0 ? null : onContinue,
                  icon: const Icon(Icons.add),
                  label: Text(context.tr(fr: 'Ajouter les appareils sélectionnés', en: 'Add selected devices')),
                ),
                if (onBack != null) TextButton(onPressed: onBack, child: Text(context.tr(fr: 'Modifier les paramètres', en: 'Edit settings'))),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _DiscoveredTile extends StatelessWidget {
  const _DiscoveredTile({required this.device, required this.selected, required this.onChanged});

  final DiscoveredDevice device;
  final bool selected;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final details = [
      categoryLabel(context, device.category),
      if (device.model != null && device.model!.isNotEmpty) device.model!,
      if (device.address != null && device.address!.isNotEmpty) device.address!,
    ].join(' · ');
    return CheckboxListTile(
      value: selected,
      onChanged: (v) => onChanged(v ?? false),
      controlAffinity: ListTileControlAffinity.trailing,
      secondary: Container(
        width: 40,
        height: 40,
        decoration: BoxDecoration(color: theme.colorScheme.primary.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(12)),
        child: Icon(categoryIcon(device.category), color: theme.colorScheme.primary, size: 22),
      ),
      title: Text(device.name.isEmpty ? device.externalId : device.name, maxLines: 1, overflow: TextOverflow.ellipsis),
      subtitle: Text(details, maxLines: 2, overflow: TextOverflow.ellipsis),
    );
  }
}
