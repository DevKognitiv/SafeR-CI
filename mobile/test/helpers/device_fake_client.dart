import 'package:safer_ci/core/api/api_exception.dart';
import 'package:safer_ci/core/models/models.dart';

import 'fake_hub_client.dart';

/// FakeHubClient variant for the device screens: offline devices, extra devices
/// (generic + gateway with children), a "no home" mode and refresh counting.
class DeviceFakeHubClient extends FakeHubClient {
  DeviceFakeHubClient({this.offlineIds = const {}, this.noHomes = false, List<Device>? extras}) : extras = extras ?? demoExtras(FakeHubClient.homeId);

  /// Devices reported offline.
  final Set<String> offlineIds;

  /// When true, the user has no home at all.
  final bool noHomes;

  /// Additional devices (kept outside the shared fake's private list).
  List<Device> extras;

  /// Number of POST /devices/{id}/refresh calls.
  int refreshCalls = 0;

  /// Qualities requested through GET /devices/{id}/stream.
  final List<String> streamQualities = [];

  static List<Device> demoExtras(String homeId) => [
        Device(
          id: 'dev-generic',
          homeId: homeId,
          name: 'Ventilateur',
          brand: 'home_assistant',
          protocol: 'ha_rest',
          category: 'generic',
          externalId: 'fan.bureau',
          capabilities: const [
            Capability(code: 'fan_switch', type: 'bool', writable: true),
            Capability(code: 'speed', type: 'enum', writable: true, values: ['low', 'medium', 'high']),
            Capability(code: 'level', type: 'int', writable: true, min: 0, max: 10, step: 1),
            Capability(code: 'raw_status', type: 'string'),
          ],
          state: const {'fan_switch': false, 'speed': 'low', 'level': 3, 'raw_status': 'idle'},
        ),
        Device(
          id: 'dev-gw',
          homeId: homeId,
          name: 'Passerelle Zigbee',
          brand: 'tuya',
          protocol: 'tuya_cloud',
          category: 'gateway',
          externalId: 'gw-1',
          capabilities: const [Capability(code: 'child_count', type: 'int')],
          state: const {'child_count': 1},
        ),
        Device(
          id: 'dev-gw-child-1',
          homeId: homeId,
          name: 'Capteur porte garage',
          brand: 'tuya',
          protocol: 'tuya_cloud',
          category: 'sensor_contact',
          externalId: 'gw-1:1',
          parentId: 'dev-gw',
          capabilities: const [Capability(code: 'contact', type: 'bool'), Capability(code: 'battery', type: 'int', unit: '%')],
          state: const {'contact': true, 'battery': 55},
        ),
      ];

  Device _apply(Device device) => offlineIds.contains(device.id) ? device.copyWith(online: false) : device;

  Device? _extra(String id) => extras.where((d) => d.id == id).firstOrNull;

  @override
  Future<List<Home>> homes() async {
    if (noHomes) {
      if (failNetwork) throw ApiException('Impossible de joindre le hub', status: null);
      return [];
    }
    return super.homes();
  }

  @override
  Future<List<Device>> devices(String homeId, {String? roomId, String? category, String? brand}) async {
    final base = await super.devices(homeId, roomId: roomId, category: category, brand: brand);
    final matching = extras.where((d) => (roomId == null || d.roomId == roomId) && (category == null || d.category == category) && (brand == null || d.brand == brand));
    return [...base, ...matching].map(_apply).toList();
  }

  @override
  Future<Device> device(String deviceId) async {
    final extra = _extra(deviceId);
    return _apply(extra ?? await super.device(deviceId));
  }

  @override
  Future<Device> refreshDevice(String deviceId) async {
    refreshCalls += 1;
    return device(deviceId);
  }

  @override
  Future<Device> sendCommands(String deviceId, List<({String code, dynamic value})> commands) async {
    var extra = _extra(deviceId);
    if (extra == null) return _apply(await super.sendCommands(deviceId, commands));
    for (final c in commands) {
      final cap = extra!.capability(c.code);
      if (cap == null || !cap.writable) throw ApiException("Capability '${c.code}' is not writable", status: 400, code: 'invalid_input');
      this.commands.add((deviceId: deviceId, code: c.code, value: c.value));
      extra = extra.withState({c.code: c.value});
    }
    extras = [for (final d in extras) d.id == deviceId ? extra! : d];
    return _apply(extra!);
  }

  @override
  Future<List<Device>> children(String deviceId) async {
    final base = await super.children(deviceId);
    return [...base, ...extras.where((d) => d.parentId == deviceId)].map(_apply).toList();
  }

  @override
  Future<StreamInfo> stream(String deviceId, {String quality = 'main'}) {
    streamQualities.add(quality);
    return super.stream(deviceId, quality: quality);
  }
}
