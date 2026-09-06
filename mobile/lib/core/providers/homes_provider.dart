import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/home.dart';
import 'app_providers.dart';
import 'auth_provider.dart';

/// All homes of the signed-in user.
class HomesNotifier extends AsyncNotifier<List<Home>> {
  @override
  Future<List<Home>> build() async {
    final auth = ref.watch(authProvider);
    if (!auth.isAuthenticated) return const [];
    final homes = await ref.read(hubClientProvider).homes();
    _ensureCurrent(homes);
    return homes;
  }

  void _ensureCurrent(List<Home> homes) {
    final current = ref.read(currentHomeIdProvider);
    if (homes.isEmpty) return;
    if (current == null || !homes.any((h) => h.id == current)) {
      ref.read(currentHomeIdProvider.notifier).set(homes.first.id);
    }
  }

  Future<void> refresh() async {
    state = const AsyncLoading<List<Home>>().copyWithPrevious(state);
    state = await AsyncValue.guard(() async {
      final homes = await ref.read(hubClientProvider).homes();
      _ensureCurrent(homes);
      return homes;
    });
  }

  Future<Home> create({required String name, double? lat, double? lon, String? address, List<String> rooms = const []}) async {
    final home = await ref.read(hubClientProvider).createHome(name: name, lat: lat, lon: lon, address: address, rooms: rooms);
    await refresh();
    ref.read(currentHomeIdProvider.notifier).set(home.id);
    return home;
  }

  Future<void> updateHome(String homeId, {String? name, double? lat, double? lon, String? address}) async {
    await ref.read(hubClientProvider).updateHome(homeId, name: name, lat: lat, lon: lon, address: address);
    await refresh();
  }

  Future<void> delete(String homeId) async {
    await ref.read(hubClientProvider).deleteHome(homeId);
    if (ref.read(currentHomeIdProvider) == homeId) ref.read(currentHomeIdProvider.notifier).set(null);
    await refresh();
  }

  /// Patch a home locally (used by realtime security events).
  void patch(String homeId, Home Function(Home) update) {
    final homes = state.value;
    if (homes == null) return;
    state = AsyncData([for (final h in homes) h.id == homeId ? update(h) : h]);
  }
}

final homesProvider = AsyncNotifierProvider<HomesNotifier, List<Home>>(HomesNotifier.new);

class CurrentHomeIdNotifier extends Notifier<String?> {
  @override
  String? build() => ref.watch(storageProvider).currentHomeId;

  void set(String? id) {
    state = id;
    ref.read(storageProvider).setCurrentHomeId(id);
  }
}

final currentHomeIdProvider = NotifierProvider<CurrentHomeIdNotifier, String?>(CurrentHomeIdNotifier.new);

/// The selected home (null while loading or when the user has none).
final currentHomeProvider = Provider<Home?>((ref) {
  final id = ref.watch(currentHomeIdProvider);
  final homes = ref.watch(homesProvider).value ?? const [];
  if (homes.isEmpty) return null;
  return homes.firstWhere((h) => h.id == id, orElse: () => homes.first);
});

/// Rooms of a home (from the home payload; refreshed with homesProvider).
final roomsProvider = Provider.family<List<Room>, String>((ref, homeId) {
  final homes = ref.watch(homesProvider).value ?? const [];
  for (final h in homes) {
    if (h.id == homeId) return h.rooms;
  }
  return const [];
});
