import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_exception.dart';
import '../models/device.dart';
import '../models/hub_event.dart';
import 'app_providers.dart';
import 'ws_provider.dart';

/// Devices of a home, patched live from WebSocket events.
class DevicesNotifier extends FamilyAsyncNotifier<List<Device>, String> {
  @override
  Future<List<Device>> build(String arg) async {
    ref.listen<AsyncValue<HubEvent>>(hubEventsProvider(arg), (_, next) {
      final event = next.value;
      if (event != null) _onEvent(event);
    });
    return ref.read(hubClientProvider).devices(arg);
  }

  void _onEvent(HubEvent event) {
    final devices = state.value;
    if (devices == null) return;
    switch (event.type) {
      case HubEvent.deviceState:
        final id = event.deviceId;
        final partial = event.state;
        if (id == null || partial == null) return;
        state = AsyncData([for (final d in devices) d.id == id ? d.withState(partial, online: event.online) : d]);
      case HubEvent.deviceAdded:
        final json = event.device;
        if (json == null || json['id'] == null) return;
        // The realtime payload is a summary; fetch the full record.
        ref.read(hubClientProvider).device(json['id'] as String).then((device) {
          final current = state.value ?? const <Device>[];
          if (current.any((d) => d.id == device.id)) return;
          state = AsyncData([...current, device]);
        }).catchError((_) {});
      case HubEvent.deviceRemoved:
        state = AsyncData(devices.where((d) => d.id != event.deviceId).toList());
    }
  }

  Future<void> refresh() async {
    state = await AsyncValue.guard(() => ref.read(hubClientProvider).devices(arg));
  }

  Device? byId(String id) {
    for (final d in state.value ?? const <Device>[]) {
      if (d.id == id) return d;
    }
    return null;
  }

  void _replace(Device device) {
    final devices = state.value;
    if (devices == null) return;
    state = AsyncData([for (final d in devices) d.id == device.id ? device : d]);
  }

  /// Send a command with an optimistic local update; rolls back on failure.
  Future<Device> sendCommand(String deviceId, String code, dynamic value) async {
    final previous = byId(deviceId);
    if (previous != null) _replace(previous.withState({code: value}));
    try {
      final updated = await ref.read(hubClientProvider).sendCommand(deviceId, code, value);
      _replace(updated);
      return updated;
    } on ApiException {
      if (previous != null) _replace(previous);
      rethrow;
    }
  }

  Future<Device> toggle(Device device) {
    final code = device.primaryToggleCode;
    if (code == null) throw ApiException('Cet appareil ne peut pas être allumé/éteint', status: 400);
    return sendCommand(device.id, code, !(device.boolValue(code) ?? false));
  }

  Future<Device> refreshDevice(String deviceId) async {
    final device = await ref.read(hubClientProvider).refreshDevice(deviceId);
    _replace(device);
    return device;
  }

  Future<Device> updateDevice(String deviceId, {String? name, String? roomId, bool clearRoom = false, String? icon}) async {
    final device = await ref.read(hubClientProvider).updateDevice(deviceId, name: name, roomId: roomId, clearRoom: clearRoom, icon: icon);
    _replace(device);
    return device;
  }

  Future<void> remove(String deviceId) async {
    await ref.read(hubClientProvider).deleteDevice(deviceId);
    final devices = state.value ?? const <Device>[];
    state = AsyncData(devices.where((d) => d.id != deviceId && d.parentId != deviceId).toList());
  }

  /// Add freshly paired devices without a round-trip.
  void addAll(List<Device> devices) {
    final current = state.value ?? const <Device>[];
    final ids = current.map((d) => d.id).toSet();
    state = AsyncData([...current, ...devices.where((d) => !ids.contains(d.id))]);
  }
}

final devicesProvider = AsyncNotifierProvider.family<DevicesNotifier, List<Device>, String>(DevicesNotifier.new);

/// A single device from the cached list (falls back to a fetch when unknown).
final deviceProvider = Provider.family<Device?, ({String homeId, String deviceId})>((ref, key) {
  final devices = ref.watch(devicesProvider(key.homeId)).value ?? const [];
  for (final d in devices) {
    if (d.id == key.deviceId) return d;
  }
  return null;
});

/// Devices filtered by room (null room = all, 'none' = unassigned).
final roomDevicesProvider = Provider.family<List<Device>, ({String homeId, String? roomId})>((ref, key) {
  final devices = ref.watch(devicesProvider(key.homeId)).value ?? const [];
  final visible = devices.where((d) => d.parentId == null || d.category == 'camera' || d.category == 'alarm_zone' || d.isSensor);
  if (key.roomId == null) return visible.toList();
  if (key.roomId == 'none') return visible.where((d) => d.roomId == null).toList();
  return visible.where((d) => d.roomId == key.roomId).toList();
});
