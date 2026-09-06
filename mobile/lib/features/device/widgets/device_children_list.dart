import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/i18n.dart';
import '../../../core/models/device.dart';
import '../../../core/providers/providers.dart';
import '../../../core/routes.dart';
import '../../../core/theme.dart';
import '../../../core/widgets/widgets.dart';
import 'device_command.dart';
import 'device_providers.dart';

/// Children of a parent device (zones, NVR channels, gateway nodes). Tap opens the child;
/// [showBypass] adds a bypass switch for alarm zones.
class DeviceChildrenList extends ConsumerWidget {
  const DeviceChildrenList({super.key, required this.parent, this.showBypass = false, this.emptyTitle, this.emptySubtitle});

  final Device parent;
  final bool showBypass;
  final String? emptyTitle;
  final String? emptySubtitle;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final children = ref.watch(deviceChildrenProvider(parent.id));
    return children.when(
      loading: () => const Padding(padding: EdgeInsets.all(24), child: LoadingView()),
      error: (error, _) => ErrorView(error: error, onRetry: () => ref.invalidate(deviceChildrenProvider(parent.id))),
      data: (list) {
        if (list.isEmpty) {
          return EmptyState(
            icon: Icons.device_hub_outlined,
            title: emptyTitle ?? context.tr(fr: 'Aucun appareil connecté', en: 'No connected device'),
            subtitle: emptySubtitle ?? context.tr(fr: 'Les appareils rattachés apparaîtront ici', en: 'Attached devices will appear here'),
          );
        }
        return Card(
          child: Column(
            children: [
              for (var i = 0; i < list.length; i++) ...[
                if (i > 0) const Divider(indent: 56),
                _ChildTile(homeId: parent.homeId, child: list[i], showBypass: showBypass),
              ],
            ],
          ),
        );
      },
    );
  }
}

class _ChildTile extends ConsumerWidget {
  const _ChildTile({required this.homeId, required this.child, required this.showBypass});

  final String homeId;
  final Device child;
  final bool showBypass;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    // Prefer the live cached record so realtime/optimistic updates are reflected.
    final device = ref.watch(deviceProvider((homeId: homeId, deviceId: child.id))) ?? child;
    final alerting = device.isAlerting;
    final accent = alerting ? SafeRColors.danger : (device.online ? SafeRColors.primary : theme.colorScheme.onSurfaceVariant);
    final bypassCap = showBypass ? writableCapability(device, 'bypass', type: 'bool') : null;
    final summary = device.online ? device.stateSummary : context.tr(fr: 'HORS LIGNE', en: 'OFFLINE');
    return ListTile(
      leading: Container(
        width: 40,
        height: 40,
        decoration: BoxDecoration(color: accent.withValues(alpha: 0.14), borderRadius: BorderRadius.circular(12)),
        child: Icon(iconFromName(device.icon, fallback: categoryIcon(device.category)), color: accent, size: 22),
      ),
      title: Text(device.name, maxLines: 1, overflow: TextOverflow.ellipsis),
      subtitle: Text(
        [categoryLabel(context, device.category), if (summary.isNotEmpty) summary].join(' · '),
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: TextStyle(color: alerting ? SafeRColors.danger : null, fontWeight: alerting ? FontWeight.w700 : null),
      ),
      trailing: bypassCap != null
          ? Semantics(
              label: context.tr(fr: 'Exclure ${device.name}', en: 'Bypass ${device.name}'),
              child: Switch.adaptive(
                value: device.boolValue('bypass') ?? false,
                onChanged: (v) => sendDeviceCommand(context, ref, device, 'bypass', v),
              ),
            )
          : const Icon(Icons.chevron_right),
      onTap: () => context.push(Routes.device(device.id)),
    );
  }
}
