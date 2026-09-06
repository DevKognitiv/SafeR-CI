import 'package:safer_ci/core/api/api_exception.dart';
import 'package:safer_ci/core/models/models.dart';

import 'fake_hub_client.dart';

/// FakeHubClient variant for the Security / SOS screens: forced-open sensors,
/// an alarm device id, a "no home" mode, a security failure toggle, seeded SOS
/// alerts and an in-memory `updateSos` (the shared fake has none).
class SecurityFakeHubClient extends FakeHubClient {
  SecurityFakeHubClient({this.noHomes = false, this.openIds = const {}, this.alarmDeviceId, List<SosAlert> seededAlerts = const []}) : seeded = List.of(seededAlerts);

  /// When true, the user has no home at all.
  final bool noHomes;

  /// Devices reported open (contact / zone open / lock door open).
  final Set<String> openIds;

  /// Device blamed for the active alarm.
  final String? alarmDeviceId;

  /// Extra alerts returned before the ones raised through the client.
  final List<SosAlert> seeded;

  /// When true, GET /security fails with a network error.
  bool failSecurity = false;

  /// Status overrides applied by [updateSos].
  final Map<String, String> sosStatus = {};
  final List<({String id, String status})> updateSosCalls = [];
  final List<({double? lat, double? lon, String? note})> sosCalls = [];

  Device _open(Device d) {
    if (!openIds.contains(d.id)) return d;
    switch (d.category) {
      case 'alarm_zone':
        return d.withState({'open': true});
      case 'lock':
        return d.withState({'door': true});
      default:
        return d.withState({'contact': true});
    }
  }

  SosAlert _withStatus(SosAlert a) {
    final status = sosStatus[a.id];
    if (status == null) return a;
    return SosAlert(id: a.id, homeId: a.homeId, userId: a.userId, lat: a.lat, lon: a.lon, note: a.note, status: status, forwarded: a.forwarded, incidentId: a.incidentId, createdAt: a.createdAt);
  }

  @override
  Future<List<Home>> homes() async {
    if (noHomes) {
      if (failNetwork) throw ApiException('Impossible de joindre le hub', status: null);
      return [];
    }
    return super.homes();
  }

  @override
  Future<List<Device>> devices(String homeId, {String? roomId, String? category, String? brand}) async =>
      (await super.devices(homeId, roomId: roomId, category: category, brand: brand)).map(_open).toList();

  @override
  Future<Device> device(String deviceId) async => _open(await super.device(deviceId));

  @override
  Future<SecurityState> security(String homeId) async {
    if (failSecurity) throw ApiException('Impossible de joindre le hub', status: null);
    final base = await super.security(homeId);
    return SecurityState(
      homeId: base.homeId,
      mode: base.mode,
      alarmActive: base.alarmActive,
      alarmDeviceId: base.alarmActive ? alarmDeviceId : null,
      changedAt: DateTime.now().subtract(const Duration(minutes: 12)),
      panels: base.panels.map(_open).toList(),
      zones: base.zones.map(_open).toList(),
      sensors: base.sensors.map(_open).toList(),
    );
  }

  @override
  Future<SecurityState> setSecurityMode(String homeId, String mode) async {
    await super.setSecurityMode(homeId, mode);
    return security(homeId);
  }

  @override
  Future<SecurityState> clearAlarm(String homeId) async {
    await super.clearAlarm(homeId);
    return security(homeId);
  }

  @override
  Future<SosAlert> raiseSos(String homeId, {double? lat, double? lon, String? note, String incidentType = 'panic'}) {
    sosCalls.add((lat: lat, lon: lon, note: note));
    return super.raiseSos(homeId, lat: lat, lon: lon, note: note, incidentType: incidentType);
  }

  @override
  Future<List<SosAlert>> sosAlerts(String homeId) async => [...await super.sosAlerts(homeId), ...seeded].map(_withStatus).toList();

  @override
  Future<SosAlert> updateSos(String homeId, String sosId, String status) async {
    updateSosCalls.add((id: sosId, status: status));
    sosStatus[sosId] = status;
    final all = await sosAlerts(homeId);
    return all.firstWhere((a) => a.id == sosId, orElse: () => throw ApiException('SOS not found', status: 404));
  }
}
