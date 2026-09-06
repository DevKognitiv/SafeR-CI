import 'package:safer_ci/core/api/api_exception.dart';
import 'package:safer_ci/core/models/models.dart';

import 'fake_hub_client.dart';

/// FakeHubClient with mutable rooms (the shared fake has no room CRUD) and an optional "no home" mode.
class HomeFakeHubClient extends FakeHubClient {
  HomeFakeHubClient({this.noHomes = false, this.weatherAvailable = true});

  /// When true, the user has no home at all.
  final bool noHomes;

  /// When false, the weather endpoint reports `available: false`.
  final bool weatherAvailable;

  List<Room> rooms_ = List.of(FakeHubClient.demoRooms);
  final List<List<String>> reorders = [];

  /// Number of device-list fetches (pull-to-refresh assertions).
  int devicesCalls = 0;

  void _check() {
    if (failNetwork) throw ApiException('Impossible de joindre le hub', status: null);
  }

  @override
  Future<List<Device>> devices(String homeId, {String? roomId, String? category, String? brand}) {
    devicesCalls += 1;
    return super.devices(homeId, roomId: roomId, category: category, brand: brand);
  }

  @override
  Future<List<Home>> homes() async {
    if (noHomes) {
      _check();
      return [];
    }
    final base = await super.homes();
    return [for (final h in base) h.copyWith(rooms: rooms_)];
  }

  @override
  Future<List<Room>> rooms(String homeId) async => rooms_;

  @override
  Future<Room> createRoom(String homeId, String name, {String? icon}) async {
    _check();
    final room = Room(id: 'room-${rooms_.length + 1}', homeId: homeId, name: name, icon: icon, sortOrder: rooms_.length);
    rooms_ = [...rooms_, room];
    return room;
  }

  @override
  Future<Room> updateRoom(String roomId, {String? name, String? icon}) async {
    _check();
    final index = rooms_.indexWhere((r) => r.id == roomId);
    if (index < 0) throw ApiException('Room not found', status: 404);
    final old = rooms_[index];
    final updated = Room(id: old.id, homeId: old.homeId, name: name ?? old.name, icon: icon ?? old.icon, sortOrder: old.sortOrder, deviceCount: old.deviceCount);
    rooms_ = [for (final r in rooms_) r.id == roomId ? updated : r];
    return updated;
  }

  @override
  Future<void> deleteRoom(String roomId) async {
    _check();
    rooms_ = rooms_.where((r) => r.id != roomId).toList();
  }

  @override
  Future<List<Room>> reorderRooms(String homeId, List<String> ids) async {
    _check();
    reorders.add(ids);
    rooms_ = [for (final id in ids) rooms_.firstWhere((r) => r.id == id)];
    return rooms_;
  }

  @override
  Future<Weather> weather(String homeId) async {
    if (!weatherAvailable) return const Weather(available: false);
    return super.weather(homeId);
  }
}
