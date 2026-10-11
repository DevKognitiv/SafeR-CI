import '../api/api_exception.dart';
import '../models/models.dart';
import 'demo_options.dart';
import 'fake_hub_client.dart';

/// The hub the demo build talks to: [FakeHubClient]'s "Maison Cocody" with
/// every forced state the widget-test fakes know (offline, no home, alarm,
/// member role, weather unavailable, empty devices, protected streams...)
/// behind one set of switches, plus in-memory implementations of the calls
/// the shared fake leaves to the network (room CRUD, home update/delete,
/// member roles, SOS status) so the whole app stays usable without a hub.
///
/// Switches are plain mutable fields so a running demo (or a test) can flip
/// them; [DemoHubClient.fromStates] maps the `?state=` names of the capture
/// harness onto them.
class DemoHubClient extends FakeHubClient {
  DemoHubClient({
    bool offline = false,
    this.noHomes = false,
    this.noDevices = false,
    this.weatherAvailable = true,
    this.role = 'owner',
    String securityMode = 'disarmed',
    bool alarmActive = false,
    this.alarmDeviceId,
    this.openIds = const {},
    this.offlineIds = const {},
    this.noScenes = false,
    this.noAutomations = false,
    this.noMessages = false,
    this.protectedStreams = false,
    this.failDevices = false,
    this.failWeather = false,
    this.failSecurity = false,
    this.failScenes = false,
    this.failUnread = false,
    List<SosAlert> seededAlerts = const [],
  })  : seeded = List.of(seededAlerts),
        super(failNetwork: offline) {
    this.securityMode = securityMode;
    this.alarmActive = alarmActive;
  }

  /// Maps the documented `?state=` names onto the switches.
  factory DemoHubClient.fromStates(Set<DemoState> states) {
    bool has(DemoState s) => states.contains(s);
    final mode = has(DemoState.armedAway)
        ? 'armed_away'
        : has(DemoState.armedNight)
            ? 'armed_night'
            : has(DemoState.armedHome)
                ? 'armed_home'
                : 'disarmed';
    return DemoHubClient(
      offline: has(DemoState.offline),
      noHomes: has(DemoState.noHomes),
      noDevices: has(DemoState.noDevices),
      weatherAvailable: !has(DemoState.noWeather),
      role: has(DemoState.member) ? 'member' : 'owner',
      securityMode: has(DemoState.alarm) && mode == 'disarmed' ? 'armed_away' : mode,
      alarmActive: has(DemoState.alarm),
      alarmDeviceId: has(DemoState.alarm) ? alarmDevice : null,
      openIds: has(DemoState.openings) ? openDevices : const {},
      offlineIds: has(DemoState.offlineDevices) ? offlineDevices : const {},
      noScenes: has(DemoState.noScenes),
      noAutomations: has(DemoState.noAutomations),
      noMessages: has(DemoState.noMessages),
      protectedStreams: has(DemoState.protectedStreams),
      failDevices: has(DemoState.failDevices),
      failWeather: has(DemoState.failWeather),
      failSecurity: has(DemoState.failSecurity),
      failScenes: has(DemoState.failScenes),
      failUnread: has(DemoState.failUnread),
      seededAlerts: has(DemoState.sosAlerts) ? demoSosAlerts() : const [],
    );
  }

  /// Demo device ids used by the capture routes and the forced states.
  static const String lightDevice = 'dev-light';
  static const String cameraDevice = 'dev-cam';
  static const String alarmDevice = 'dev-pir';
  static const Set<String> openDevices = {'dev-door', 'dev-zone'};
  static const Set<String> offlineDevices = {lightDevice, cameraDevice};

  /// When true, the user has no home at all.
  bool noHomes;

  /// When true, the home has no device.
  bool noDevices;

  /// When false, the weather endpoint reports `available: false`.
  bool weatherAvailable;

  /// Role of the signed-in user in the demo home.
  String role;

  /// Device blamed for the active alarm.
  String? alarmDeviceId;

  /// Devices reported open (contact / zone / lock door).
  Set<String> openIds;

  /// Devices reported offline.
  Set<String> offlineIds;

  bool noScenes;
  bool noAutomations;
  bool noMessages;

  /// Stream descriptors follow the protected-camera contract (`auth_required`
  /// without credentials) so the player never starts.
  bool protectedStreams;

  bool failDevices;
  bool failWeather;
  bool failSecurity;
  bool failScenes;
  bool failUnread;

  /// Alerts listed before the ones raised through the client.
  final List<SosAlert> seeded;

  /// Rooms of the demo home (the shared fake has no room CRUD).
  List<Room> rooms_ = List.of(FakeHubClient.demoRooms);

  /// Member roles changed through [updateMember].
  final Map<String, String> memberRoles = {};

  /// SOS statuses changed through [updateSos].
  final Map<String, String> sosStatus = {};

  String? _homeName;
  String? _homeAddress;
  double? _homeLat;
  double? _homeLon;
  bool _homeDeleted = false;

  /// Two alerts for the `sosAlerts` state: one still open, one resolved.
  static List<SosAlert> demoSosAlerts() => [
        SosAlert(id: 'sos-demo-2', homeId: FakeHubClient.homeId, userId: FakeHubClient.userId, lat: 5.36, lon: -4.0, note: 'Bruit suspect côté jardin', forwarded: true, createdAt: DateTime.now().subtract(const Duration(minutes: 25))),
        SosAlert(id: 'sos-demo-1', homeId: FakeHubClient.homeId, userId: 'user-2', status: 'resolved', createdAt: DateTime.now().subtract(const Duration(days: 2))),
      ];

  void _network() {
    if (failNetwork) throw ApiException('Impossible de joindre le hub', status: null);
  }

  Device _apply(Device d) {
    var device = d;
    if (offlineIds.contains(device.id)) device = device.copyWith(online: false);
    if (openIds.contains(device.id)) {
      device = switch (device.category) {
        'alarm_zone' => device.withState({'open': true}),
        'lock' => device.withState({'door': true}),
        _ => device.withState({'contact': true}),
      };
    }
    return device;
  }

  Home _home(Home h) => Home(
        id: h.id,
        name: _homeName ?? h.name,
        lat: _homeLat ?? h.lat,
        lon: _homeLon ?? h.lon,
        address: _homeAddress ?? h.address,
        securityMode: h.securityMode,
        alarmActive: h.alarmActive,
        role: role,
        rooms: rooms_,
        memberCount: h.memberCount,
        deviceCount: noDevices ? 0 : h.deviceCount,
        createdAt: h.createdAt ?? DateTime.now().subtract(const Duration(days: 40)),
      );

  // ---- homes & rooms
  @override
  Future<List<Home>> homes() async {
    _network();
    if (noHomes || _homeDeleted) return const [];
    return [for (final h in await super.homes()) _home(h)];
  }

  @override
  Future<Home> home(String homeId) async => _home(await super.home(homeId));

  @override
  Future<Home> updateHome(String homeId, {String? name, double? lat, double? lon, String? address}) async {
    _network();
    if (name != null) _homeName = name;
    if (address != null) _homeAddress = address;
    if (lat != null) _homeLat = lat;
    if (lon != null) _homeLon = lon;
    return home(homeId);
  }

  @override
  Future<void> deleteHome(String homeId) async {
    _network();
    if (homeId == FakeHubClient.homeId) _homeDeleted = true;
  }

  @override
  Future<void> registerPushToken(String platform, String token) async {}

  @override
  Future<List<Room>> rooms(String homeId) async => rooms_;

  @override
  Future<Room> createRoom(String homeId, String name, {String? icon}) async {
    _network();
    final room = Room(id: 'room-${rooms_.length + 1}', homeId: homeId, name: name, icon: icon, sortOrder: rooms_.length);
    rooms_ = [...rooms_, room];
    return room;
  }

  @override
  Future<Room> updateRoom(String roomId, {String? name, String? icon}) async {
    _network();
    final index = rooms_.indexWhere((r) => r.id == roomId);
    if (index < 0) throw ApiException('Room not found', status: 404);
    final old = rooms_[index];
    final updated = Room(id: old.id, homeId: old.homeId, name: name ?? old.name, icon: icon ?? old.icon, sortOrder: old.sortOrder, deviceCount: old.deviceCount);
    rooms_ = [for (final r in rooms_) r.id == roomId ? updated : r];
    return updated;
  }

  @override
  Future<void> deleteRoom(String roomId) async {
    _network();
    rooms_ = rooms_.where((r) => r.id != roomId).toList();
  }

  @override
  Future<List<Room>> reorderRooms(String homeId, List<String> ids) async {
    _network();
    rooms_ = [for (final id in ids) rooms_.firstWhere((r) => r.id == id)];
    return rooms_;
  }

  // ---- members
  @override
  Future<List<Member>> members(String homeId) async => [
        for (final m in await super.members(homeId))
          Member(userId: m.userId, email: m.email, name: m.name, role: memberRoles[m.userId] ?? (m.userId == FakeHubClient.userId ? role : m.role), joinedAt: m.joinedAt),
      ];

  @override
  Future<Member> updateMember(String homeId, String userId, String role) async {
    _network();
    memberRoles[userId] = role;
    final all = await members(homeId);
    return all.firstWhere((m) => m.userId == userId, orElse: () => throw ApiException('Member not found', status: 404));
  }

  // ---- weather
  @override
  Future<Weather> weather(String homeId) async {
    if (failWeather) throw ApiException('Service météo indisponible', status: 502);
    if (!weatherAvailable) return const Weather(available: false);
    return super.weather(homeId);
  }

  // ---- devices
  @override
  Future<List<Device>> devices(String homeId, {String? roomId, String? category, String? brand}) async {
    if (failDevices) throw ApiException('Impossible de joindre le hub', status: null);
    if (noDevices) {
      _network();
      return const [];
    }
    return (await super.devices(homeId, roomId: roomId, category: category, brand: brand)).map(_apply).toList();
  }

  @override
  Future<Device> device(String deviceId) async => _apply(await super.device(deviceId));

  @override
  Future<Device> refreshDevice(String deviceId) async => _apply(await super.refreshDevice(deviceId));

  @override
  Future<Device> updateDevice(String deviceId, {String? name, String? roomId, bool clearRoom = false, String? icon}) async =>
      _apply(await super.updateDevice(deviceId, name: name, roomId: roomId, clearRoom: clearRoom, icon: icon));

  @override
  Future<Device> sendCommands(String deviceId, List<({String code, dynamic value})> commands) async {
    if (offlineIds.contains(deviceId)) throw ApiException('Appareil hors ligne', status: 409, code: 'device_offline');
    return _apply(await super.sendCommands(deviceId, commands));
  }

  @override
  Future<List<Device>> children(String deviceId) async => (await super.children(deviceId)).map(_apply).toList();

  @override
  Future<StreamInfo> stream(String deviceId, {String quality = 'main'}) async {
    final info = await super.stream(deviceId, quality: quality);
    if (!protectedStreams) return info;
    return StreamInfo(url: info.url, type: info.type, headers: info.headers, authRequired: true);
  }

  // ---- scenes & automations
  @override
  Future<List<Scene>> scenes(String homeId) async {
    if (failScenes) throw ApiException('scenes down', status: 500);
    if (noScenes) {
      _network();
      return const [];
    }
    return super.scenes(homeId);
  }

  @override
  Future<List<Automation>> automations(String homeId) async {
    if (noAutomations) {
      _network();
      return const [];
    }
    return super.automations(homeId);
  }

  // ---- security & SOS
  @override
  Future<SecurityState> security(String homeId) async {
    if (failSecurity) throw ApiException('Impossible de joindre le hub', status: null);
    final base = await super.security(homeId);
    List<Device> fix(List<Device> list) => noDevices ? const [] : list.map(_apply).toList();
    return SecurityState(
      homeId: base.homeId,
      mode: base.mode,
      alarmActive: base.alarmActive,
      alarmDeviceId: base.alarmActive ? alarmDeviceId : null,
      changedAt: DateTime.now().subtract(const Duration(minutes: 12)),
      panels: fix(base.panels),
      zones: fix(base.zones),
      sensors: fix(base.sensors),
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

  SosAlert _withStatus(SosAlert a) {
    final status = sosStatus[a.id];
    if (status == null) return a;
    return SosAlert(id: a.id, homeId: a.homeId, userId: a.userId, lat: a.lat, lon: a.lon, note: a.note, status: status, forwarded: a.forwarded, incidentId: a.incidentId, createdAt: a.createdAt);
  }

  @override
  Future<List<SosAlert>> sosAlerts(String homeId) async => [...await super.sosAlerts(homeId), ...seeded].map(_withStatus).toList();

  @override
  Future<SosAlert> updateSos(String homeId, String sosId, String status) async {
    _network();
    sosStatus[sosId] = status;
    final all = await sosAlerts(homeId);
    return all.firstWhere((a) => a.id == sosId, orElse: () => throw ApiException('SOS not found', status: 404));
  }

  // ---- messages
  @override
  Future<List<HubMessage>> messages(String homeId, {String? kind, bool unreadOnly = false, int limit = 50}) async {
    if (noMessages) {
      _network();
      return const [];
    }
    return super.messages(homeId, kind: kind, unreadOnly: unreadOnly, limit: limit);
  }

  @override
  Future<UnreadCount> unreadCount(String homeId) async {
    if (failUnread) throw ApiException('hub down', status: 503);
    if (noMessages) {
      _network();
      return const UnreadCount();
    }
    return super.unreadCount(homeId);
  }
}
