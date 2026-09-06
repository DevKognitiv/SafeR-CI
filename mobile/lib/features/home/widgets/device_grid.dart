import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/models/device.dart';
import '../../../core/models/home.dart';
import '../../../core/providers/providers.dart';
import '../../../core/router.dart';
import '../../../core/widgets/widgets.dart';
import 'device_actions_sheet.dart';

/// 2-column grid of [DeviceTile]s (as a sliver so the whole Home tab scrolls together).
class DeviceGridSliver extends ConsumerWidget {
  const DeviceGridSliver({super.key, required this.homeId, required this.devices, required this.rooms});

  final String homeId;
  final List<Device> devices;
  final List<Room> rooms;

  /// Fixed tile height keeps [DeviceTile] from overflowing on narrow screens.
  static const double tileHeight = 140;

  Future<void> _toggle(BuildContext context, WidgetRef ref, Device device, bool value) async {
    final code = device.primaryToggleCode;
    if (code == null) return;
    try {
      await ref.read(devicesProvider(homeId).notifier).sendCommand(device.id, code, value);
    } catch (e) {
      if (context.mounted) showErrorSnack(context, e);
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) => SliverPadding(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
        sliver: SliverGrid(
          gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(crossAxisCount: 2, mainAxisSpacing: 12, crossAxisSpacing: 12, mainAxisExtent: tileHeight),
          delegate: SliverChildBuilderDelegate(
            (context, index) {
              final device = devices[index];
              return GestureDetector(
                key: ValueKey('device-tile-${device.id}'),
                onLongPress: () => showDeviceActions(context, ref, device: device, rooms: rooms),
                child: DeviceTile(
                  device: device,
                  onTap: () => context.push(Routes.device(device.id)),
                  onToggle: device.primaryToggleCode == null ? null : (value) => _toggle(context, ref, device, value),
                ),
              );
            },
            childCount: devices.length,
          ),
        ),
      );
}
