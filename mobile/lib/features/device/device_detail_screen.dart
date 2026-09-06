import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/i18n.dart';
import '../../core/models/device.dart';
import '../../core/providers/providers.dart';
import '../../core/router.dart';
import '../../core/widgets/widgets.dart';
import 'panels/device_panel.dart';
import 'widgets/device_offline_banner.dart';
import 'widgets/device_resolver.dart';

/// Tuya-style device page: app bar (name + "..." to settings), offline banner and
/// the control panel matching the device category.
class DeviceDetailScreen extends StatelessWidget {
  const DeviceDetailScreen({super.key, required this.deviceId});

  final String deviceId;

  @override
  Widget build(BuildContext context) => DeviceResolver(deviceId: deviceId, builder: (context, device) => _DeviceScaffold(device: device));
}

class _DeviceScaffold extends ConsumerStatefulWidget {
  const _DeviceScaffold({required this.device});

  final Device device;

  @override
  ConsumerState<_DeviceScaffold> createState() => _DeviceScaffoldState();
}

class _DeviceScaffoldState extends ConsumerState<_DeviceScaffold> {
  bool _refreshing = false;

  Future<void> _refresh() async {
    setState(() => _refreshing = true);
    try {
      final updated = await ref.read(devicesProvider(widget.device.homeId).notifier).refreshDevice(widget.device.id);
      if (!mounted) return;
      showSnack(context, updated.online ? context.tr(fr: 'Appareil de nouveau en ligne', en: 'Device back online') : context.tr(fr: 'Appareil toujours hors ligne', en: 'Device still offline'));
    } catch (e) {
      if (mounted) showErrorSnack(context, e);
    } finally {
      if (mounted) setState(() => _refreshing = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final device = widget.device;
    final rooms = ref.watch(roomsProvider(device.homeId));
    final room = rooms.where((r) => r.id == device.roomId).firstOrNull;
    final subtitle = [if (room != null) room.name, categoryLabel(context, device.category)].join(' · ');
    return Scaffold(
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(device.name, maxLines: 1, overflow: TextOverflow.ellipsis),
            Text(subtitle, style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant), maxLines: 1, overflow: TextOverflow.ellipsis),
          ],
        ),
        actions: [
          IconButton(
            tooltip: context.tr(fr: "Paramètres de l'appareil", en: 'Device settings'),
            onPressed: () => context.push(Routes.deviceSettings(device.id)),
            icon: const Icon(Icons.more_horiz),
          ),
        ],
      ),
      body: Column(
        children: [
          if (!device.online) DeviceOfflineBanner(onRefresh: _refresh, busy: _refreshing, lastSeen: device.lastSeenAt),
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
              child: panelForDevice(device),
            ),
          ),
        ],
      ),
    );
  }
}
