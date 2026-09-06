import 'package:safer_ci/core/api/api_exception.dart';
import 'package:safer_ci/core/models/models.dart';

import 'fake_hub_client.dart';

/// FakeHubClient for the Scenes tab: records runs/toggles/tests and can pretend to be empty.
class ScenesFakeHubClient extends FakeHubClient {
  ScenesFakeHubClient({this.noScenes = false, this.noAutomations = false, this.noHomes = false, this.role = 'owner'});

  /// Role of the signed-in user in the demo home.
  final String role;

  /// When true, GET /homes/{id}/devices fails with a 500.
  bool failDevices = false;

  /// When true, GET /homes/{id}/scenes fails with a 500.
  bool failScenes = false;

  /// When true, GET /homes/{id}/scenes returns nothing.
  final bool noScenes;

  /// When true, GET /homes/{id}/automations returns nothing.
  final bool noAutomations;

  /// When true, the user has no home at all.
  final bool noHomes;

  /// Scene ids passed to POST /scenes/{id}/run, in order.
  final List<String> runCalls = [];

  /// (automation id, enabled) pairs passed to /automations/{id}/enable|disable.
  final List<({String id, bool enabled})> enabledCalls = [];

  /// Automation ids passed to POST /automations/{id}/trigger.
  final List<String> triggerCalls = [];

  @override
  Future<List<Home>> homes() async {
    if (noHomes) return const [];
    return [
      for (final h in await super.homes())
        Home(id: h.id, name: h.name, lat: h.lat, lon: h.lon, address: h.address, securityMode: h.securityMode, alarmActive: h.alarmActive, role: role, rooms: h.rooms, memberCount: h.memberCount, deviceCount: h.deviceCount),
    ];
  }

  @override
  Future<List<Device>> devices(String homeId, {String? roomId, String? category, String? brand}) {
    if (failDevices) throw ApiException('devices down', status: 500);
    return super.devices(homeId, roomId: roomId, category: category, brand: brand);
  }

  @override
  Future<List<Scene>> scenes(String homeId) async {
    if (failScenes) throw ApiException('scenes down', status: 500);
    return noScenes ? const [] : super.scenes(homeId);
  }

  @override
  Future<List<Automation>> automations(String homeId) async => noAutomations ? const [] : super.automations(homeId);

  @override
  Future<Map<String, dynamic>> runScene(String sceneId) {
    runCalls.add(sceneId);
    return super.runScene(sceneId);
  }

  @override
  Future<Automation> setAutomationEnabled(String automationId, bool enabled) {
    enabledCalls.add((id: automationId, enabled: enabled));
    return super.setAutomationEnabled(automationId, enabled);
  }

  @override
  Future<Map<String, dynamic>> triggerAutomation(String automationId) {
    triggerCalls.add(automationId);
    return super.triggerAutomation(automationId);
  }
}
