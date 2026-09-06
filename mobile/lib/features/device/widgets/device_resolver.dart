import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/i18n.dart';
import '../../../core/models/device.dart';
import '../../../core/providers/providers.dart';
import '../../../core/routes.dart';
import '../../../core/widgets/widgets.dart';
import 'device_providers.dart';

/// Resolves a device for the device screens: current home -> cached list -> fallback fetch.
/// Handles the "no home", loading and error states so screens only deal with a [Device].
class DeviceResolver extends ConsumerWidget {
  const DeviceResolver({super.key, required this.deviceId, required this.builder, this.title});

  final String deviceId;
  final Widget Function(BuildContext context, Device device) builder;
  final String? title;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final homes = ref.watch(homesProvider);
    final home = ref.watch(currentHomeProvider);
    if (home == null) {
      return _Frame(
        title: title,
        child: homes.when(
          loading: () => const LoadingView(),
          error: (error, _) => ErrorView(error: error, onRetry: () => ref.read(homesProvider.notifier).refresh()),
          data: (_) => EmptyState(
            icon: Icons.home_work_outlined,
            title: context.tr(fr: 'Aucune maison', en: 'No home'),
            subtitle: context.tr(fr: 'Créez une maison pour gérer vos appareils', en: 'Create a home to manage your devices'),
            actionLabel: context.tr(fr: 'Créer une maison', en: 'Create a home'),
            onAction: () => context.push(Routes.homes),
          ),
        ),
      );
    }
    final cached = ref.watch(deviceProvider((homeId: home.id, deviceId: deviceId)));
    if (cached != null) return builder(context, cached);
    final devices = ref.watch(devicesProvider(home.id));
    return devices.when(
      loading: () => _Frame(title: title, child: const LoadingView()),
      error: (error, _) => _Frame(title: title, child: ErrorView(error: error, onRetry: () => ref.read(devicesProvider(home.id).notifier).refresh())),
      data: (_) => ref.watch(fetchedDeviceProvider(deviceId)).when(
            loading: () => _Frame(title: title, child: const LoadingView()),
            error: (error, _) => _Frame(title: title, child: ErrorView(error: error, onRetry: () => ref.invalidate(fetchedDeviceProvider(deviceId)))),
            data: (device) => _AdoptDevice(homeId: home.id, device: device, child: builder(context, device)),
          ),
    );
  }
}

class _Frame extends StatelessWidget {
  const _Frame({required this.child, this.title});

  final Widget child;
  final String? title;

  @override
  Widget build(BuildContext context) => Scaffold(appBar: AppBar(title: Text(title ?? '')), body: child);
}

/// Adds a freshly fetched device to the cached list of its home so commands and
/// realtime updates flow through the normal notifier.
class _AdoptDevice extends ConsumerStatefulWidget {
  const _AdoptDevice({required this.homeId, required this.device, required this.child});

  final String homeId;
  final Device device;
  final Widget child;

  @override
  ConsumerState<_AdoptDevice> createState() => _AdoptDeviceState();
}

class _AdoptDeviceState extends ConsumerState<_AdoptDevice> {
  @override
  void initState() {
    super.initState();
    if (widget.device.homeId == widget.homeId) {
      Future.microtask(() {
        if (mounted) ref.read(devicesProvider(widget.homeId).notifier).addAll([widget.device]);
      });
    }
  }

  @override
  Widget build(BuildContext context) => widget.child;
}
