import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/config.dart';
import '../../core/i18n.dart';
import '../../core/models/home.dart';
import '../../core/providers/providers.dart';
import '../../core/routes.dart';
import '../../core/widgets/widgets.dart';
import 'widgets/alarm_banner.dart';
import 'widgets/device_grid.dart';
import 'widgets/home_app_bar.dart';
import 'widgets/offline_banner.dart';
import 'widgets/room_tabs.dart';
import 'widgets/weather_header.dart';

/// Tuya-style Home tab: status header, room tabs and the device grid of the current home.
class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});

  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen> {
  /// Selected room filter: null = all, [kUnassignedRoomId] = devices without a room.
  String? _roomId;

  Future<void> _refresh(String homeId) async {
    ref.invalidate(weatherProvider(homeId));
    ref.invalidate(unreadCountProvider(homeId));
    await ref.read(devicesProvider(homeId).notifier).refresh();
  }

  /// Keep the filter valid when rooms change (deleted room, no more unassigned devices).
  String? _effectiveRoom(List<Room> rooms, bool hasUnassigned) {
    final id = _roomId;
    if (id == null) return null;
    if (id == kUnassignedRoomId) return hasUnassigned ? id : null;
    return rooms.any((r) => r.id == id) ? id : null;
  }

  @override
  Widget build(BuildContext context) {
    ref.listen<String?>(currentHomeIdProvider, (previous, next) {
      if (previous != next && _roomId != null) setState(() => _roomId = null);
    });
    final homes = ref.watch(homesProvider);
    final home = ref.watch(currentHomeProvider);
    if (home == null) return _NoHomeScaffold(homes: homes);

    final homeId = home.id;
    final rooms = ref.watch(roomsProvider(homeId));
    final devicesAsync = ref.watch(devicesProvider(homeId));
    final unassigned = ref.watch(roomDevicesProvider((homeId: homeId, roomId: kUnassignedRoomId)));
    final selectedRoom = _effectiveRoom(rooms, unassigned.isNotEmpty);
    final visible = ref.watch(roomDevicesProvider((homeId: homeId, roomId: selectedRoom)));
    // Only meaningful when a socket is supposed to be open (build flag + user preference).
    final realtime = ref.watch(realtimeActiveProvider);
    final offline = realtime && ref.watch(hubConnectedProvider(homeId)).valueOrNull == false;
    final canManage = home.canManage;

    return Scaffold(
      appBar: HomeAppBar(home: home),
      body: RefreshIndicator(
        onRefresh: () => _refresh(homeId),
        child: CustomScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          slivers: [
            if (offline) const SliverToBoxAdapter(child: OfflineBanner()),
            if (home.alarmActive) SliverToBoxAdapter(child: AlarmBanner(onTap: () => context.go(Routes.security))),
            SliverToBoxAdapter(child: WeatherHeaderCard(home: home, devices: devicesAsync.valueOrNull)),
            SliverPersistentHeader(
              pinned: true,
              delegate: _PinnedHeaderDelegate(
                height: RoomTabBar.height,
                child: RoomTabBar(
                  rooms: rooms,
                  selected: selectedRoom,
                  showUnassigned: unassigned.isNotEmpty,
                  onSelected: (id) => setState(() => _roomId = id),
                ),
              ),
            ),
            devicesAsync.when(
              loading: () => const SliverFillRemaining(hasScrollBody: false, child: LoadingView()),
              error: (error, _) => SliverFillRemaining(
                hasScrollBody: false,
                child: ErrorView(error: error, onRetry: () => ref.read(devicesProvider(homeId).notifier).refresh()),
              ),
              data: (_) => visible.isEmpty
                  ? SliverFillRemaining(
                      hasScrollBody: false,
                      child: EmptyState(
                        icon: Icons.devices_other,
                        title: context.tr(fr: 'Aucun appareil', en: 'No devices'),
                        subtitle: selectedRoom != null
                            ? context.tr(fr: 'Aucun appareil dans cette pièce', en: 'No devices in this room')
                            : canManage
                                ? context.tr(fr: 'Ajoutez votre premier appareil pour commencer', en: 'Add your first device to get started')
                                : context.tr(fr: "Demandez à un administrateur d'ajouter des appareils", en: 'Ask an administrator to add devices'),
                        // Pairing is admin/owner only on the hub: members get no dead-end action.
                        actionLabel: canManage ? context.tr(fr: 'Ajouter un appareil', en: 'Add device') : null,
                        onAction: canManage ? () => context.push(Routes.addDevice) : null,
                      ),
                    )
                  : DeviceGridSliver(homeId: homeId, devices: visible, rooms: rooms),
            ),
          ],
        ),
      ),
    );
  }
}

/// Shown while homes load, on error, or when the user has no home yet.
class _NoHomeScaffold extends ConsumerWidget {
  const _NoHomeScaffold({required this.homes});

  final AsyncValue<List<Home>> homes;

  @override
  Widget build(BuildContext context, WidgetRef ref) => Scaffold(
        appBar: AppBar(title: const Text(AppConfig.appName)),
        body: homes.when(
          loading: () => const LoadingView(),
          error: (error, _) => ErrorView(error: error, onRetry: () => ref.read(homesProvider.notifier).refresh()),
          data: (_) => EmptyState(
            icon: Icons.home_work_outlined,
            title: context.tr(fr: 'Créez votre première maison', en: 'Create your first home'),
            subtitle: context.tr(fr: 'Une maison regroupe vos pièces et vos appareils.', en: 'A home groups your rooms and devices.'),
            actionLabel: context.tr(fr: 'Créer une maison', en: 'Create a home'),
            onAction: () => context.push(Routes.homes),
          ),
        ),
      );
}

class _PinnedHeaderDelegate extends SliverPersistentHeaderDelegate {
  const _PinnedHeaderDelegate({required this.child, required this.height});

  final Widget child;
  final double height;

  @override
  double get minExtent => height;

  @override
  double get maxExtent => height;

  @override
  Widget build(BuildContext context, double shrinkOffset, bool overlapsContent) =>
      ColoredBox(color: Theme.of(context).scaffoldBackgroundColor, child: SizedBox.expand(child: child));

  @override
  bool shouldRebuild(covariant _PinnedHeaderDelegate oldDelegate) => oldDelegate.child != child || oldDelegate.height != height;
}
