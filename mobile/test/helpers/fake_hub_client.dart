import 'dart:typed_data';

import 'package:safer_ci/core/api/api_exception.dart';
import 'package:safer_ci/core/api/hub_client.dart';
import 'package:safer_ci/core/models/models.dart';

/// In-memory HubClient for widget tests. Mirrors the hub's demo adapter data.
class FakeHubClient extends HubClient {
  FakeHubClient({this.authenticated = true, this.failNetwork = false}) : super(baseUrl: 'http://test.local', tokenProvider: () => 'test-token') {
    _devices = demoDevices(homeId);
  }

  static const homeId = 'home-1';
  static const userId = 'user-1';

  bool authenticated;
  bool failNetwork;

  late List<Device> _devices;
  final List<({String deviceId, String code, dynamic value})> commands = [];
  final List<Scene> _scenes = [
    Scene(id: 'scene-1', homeId: homeId, name: 'Bonne nuit', icon: 'bedtime', color: '#7C3AED', actions: [SceneAction.deviceCommand('dev-light', 'switch', false), SceneAction.securityMode('armed_night')]),
    Scene(id: 'scene-2', homeId: homeId, name: 'Je pars', icon: 'flight_takeoff', color: '#DC2626', actions: [SceneAction.securityMode('armed_away')]),
  ];
  final List<Automation> _automations = [
    Automation(id: 'auto-1', homeId: homeId, name: 'Lumière si mouvement', triggers: [Rule.deviceState('dev-pir', 'motion', 'eq', true)], conditions: [Rule.timeRange('19:00', '06:00')], actions: [SceneAction.deviceCommand('dev-light', 'switch', true)]),
  ];
  final List<HubMessage> _messages = [
    HubMessage(id: 'msg-1', homeId: homeId, kind: 'alarm', title: 'Mouvement détecté — Détecteur couloir', body: 'Un mouvement a été détecté.', severity: 'warning', createdAt: DateTime.now().subtract(const Duration(minutes: 5))),
    HubMessage(id: 'msg-2', homeId: homeId, kind: 'home', title: 'Nouvel appareil: Lampe salon', body: '', read: true, createdAt: DateTime.now().subtract(const Duration(hours: 2))),
    HubMessage(id: 'msg-3', homeId: homeId, kind: 'notice', title: 'Bienvenue sur SafeR', body: 'Ajoutez vos appareils.', createdAt: DateTime.now().subtract(const Duration(days: 1))),
  ];
  String securityMode = 'disarmed';
  bool alarmActive = false;
  final List<SosAlert> _sos = [];
  final List<Member> _members = [
    Member(userId: userId, email: 'alice@safer.ci', name: 'Alice', role: 'owner', joinedAt: DateTime.now()),
    Member(userId: 'user-2', email: 'bob@safer.ci', name: 'Bob', role: 'member', joinedAt: DateTime.now()),
  ];

  User get user => const User(id: userId, email: 'alice@safer.ci', name: 'Alice Kouassi', locale: 'fr');

  Home get demoHome => Home(
        id: homeId,
        name: 'Maison Cocody',
        lat: 5.36,
        lon: -4.0,
        address: 'Cocody, Abidjan',
        securityMode: securityMode,
        alarmActive: alarmActive,
        role: 'owner',
        rooms: demoRooms,
        memberCount: 2,
        deviceCount: _devices.length,
      );

  static const demoRooms = [
    Room(id: 'room-1', homeId: homeId, name: 'Salon', icon: 'weekend', sortOrder: 0, deviceCount: 3),
    Room(id: 'room-2', homeId: homeId, name: 'Chambre', icon: 'bed', sortOrder: 1, deviceCount: 1),
    Room(id: 'room-3', homeId: homeId, name: 'Entrée', icon: 'door_front_door', sortOrder: 2, deviceCount: 2),
  ];

  void _check() {
    if (failNetwork) throw ApiException('Impossible de joindre le hub', status: null);
    if (!authenticated) throw ApiException('Not authenticated', status: 401);
  }

  Device _find(String id) => _devices.firstWhere((d) => d.id == id, orElse: () => throw ApiException('Device not found', status: 404));

  void _replace(Device device) => _devices = [for (final d in _devices) d.id == device.id ? device : d];

  // ---- auth
  @override
  Future<AuthResult> login({required String email, required String password}) async {
    if (failNetwork) throw ApiException('Impossible de joindre le hub', status: null);
    if (password != 'secret123') throw ApiException('Invalid credentials', status: 401);
    authenticated = true;
    return AuthResult(token: 'test-token', user: user);
  }

  @override
  Future<AuthResult> register({required String email, required String password, required String name, String? phone, String locale = 'fr'}) async {
    if (email == 'taken@safer.ci') throw ApiException('E-mail already registered', status: 409);
    authenticated = true;
    return AuthResult(token: 'test-token', user: User(id: userId, email: email, name: name, locale: locale));
  }

  @override
  Future<User> me() async {
    _check();
    return user;
  }

  @override
  Future<User> updateMe({String? name, String? phone, String? locale, String? avatarUrl}) async {
    _check();
    return User(id: userId, email: user.email, name: name ?? user.name, phone: phone ?? user.phone, locale: locale ?? user.locale, avatarUrl: avatarUrl);
  }

  @override
  Future<bool> health() async => !failNetwork;

  // ---- homes
  @override
  Future<List<Home>> homes() async {
    _check();
    return [demoHome];
  }

  @override
  Future<Home> home(String homeId) async => demoHome;

  @override
  Future<Home> createHome({required String name, double? lat, double? lon, String? address, List<String> rooms = const []}) async {
    _check();
    return Home(id: 'home-new', name: name, lat: lat, lon: lon, address: address, role: 'owner', rooms: [for (var i = 0; i < rooms.length; i++) Room(id: 'r$i', homeId: 'home-new', name: rooms[i], sortOrder: i)]);
  }

  @override
  Future<List<Room>> rooms(String homeId) async => demoRooms;

  @override
  Future<List<Member>> members(String homeId) async {
    _check();
    return _members;
  }

  @override
  Future<Member> addMember(String homeId, String email, {String role = 'member'}) async {
    _check();
    if (email == 'nobody@safer.ci') throw ApiException('User not found', status: 404);
    final member = Member(userId: 'user-${_members.length + 1}', email: email, name: email.split('@').first, role: role, joinedAt: DateTime.now());
    _members.add(member);
    return member;
  }

  @override
  Future<void> removeMember(String homeId, String userId) async {
    _members.removeWhere((m) => m.userId == userId);
  }

  @override
  Future<Weather> weather(String homeId) async {
    _check();
    return const Weather(temperature: 29.5, humidity: 74, condition: 'partly_cloudy', icon: 'cloud_queue', windKmh: 12, available: true);
  }

  // ---- devices
  @override
  Future<List<Device>> devices(String homeId, {String? roomId, String? category, String? brand}) async {
    _check();
    return _devices.where((d) => (roomId == null || d.roomId == roomId) && (category == null || d.category == category) && (brand == null || d.brand == brand)).toList();
  }

  @override
  Future<Device> device(String deviceId) async {
    _check();
    return _find(deviceId);
  }

  @override
  Future<Device> updateDevice(String deviceId, {String? name, String? roomId, bool clearRoom = false, String? icon}) async {
    _check();
    final updated = _find(deviceId).copyWith(name: name, roomId: roomId, clearRoom: clearRoom, icon: icon);
    _replace(updated);
    return updated;
  }

  @override
  Future<void> deleteDevice(String deviceId) async {
    _check();
    _devices = _devices.where((d) => d.id != deviceId && d.parentId != deviceId).toList();
  }

  @override
  Future<Device> refreshDevice(String deviceId) async {
    _check();
    return _find(deviceId);
  }

  @override
  Future<Device> sendCommands(String deviceId, List<({String code, dynamic value})> commands) async {
    _check();
    var device = _find(deviceId);
    for (final c in commands) {
      final cap = device.capability(c.code);
      if (cap == null) throw ApiException("Unknown capability '${c.code}'", status: 400, code: 'invalid_input');
      if (!cap.writable) throw ApiException("Capability '${c.code}' is read-only", status: 400, code: 'invalid_input');
      this.commands.add((deviceId: deviceId, code: c.code, value: c.value));
      final partial = <String, dynamic>{c.code: c.value};
      if (c.code == 'control') partial['position'] = c.value == 'open' ? 100 : (c.value == 'close' ? 0 : device.numValue('position'));
      if (c.code == 'arm_mode') partial['alarm'] = false;
      device = device.withState(partial, online: true);
    }
    _replace(device);
    return device;
  }

  @override
  Future<StreamInfo> stream(String deviceId, {String quality = 'main'}) async {
    _check();
    final device = _find(deviceId);
    if (!device.isCamera) throw ApiException('No stream for this device', status: 404);
    return StreamInfo(url: device.stringValue(quality == 'sub' ? 'stream_sub' : 'stream_main') ?? 'rtsp://demo/main', type: 'rtsp');
  }

  @override
  Future<Uint8List> snapshot(String deviceId) async {
    _check();
    return Uint8List.fromList(const [0xFF, 0xD8, 0xFF, 0xD9]);
  }

  @override
  Future<List<DeviceEvent>> deviceEvents(String deviceId, {int limit = 50}) async {
    _check();
    return [DeviceEvent(id: 'ev-1', deviceId: deviceId, type: 'motion', payload: const {'value': true}, createdAt: DateTime.now().subtract(const Duration(minutes: 3)))];
  }

  @override
  Future<List<Device>> children(String deviceId) async {
    _check();
    return _devices.where((d) => d.parentId == deviceId).toList();
  }

  // ---- onboarding
  static final List<BrandInfo> demoBrands = [
    const BrandInfo(id: 'demo', name: 'Appareils de démonstration', vendor: 'SafeR', description: 'Appareils virtuels', protocols: ['demo'], categories: ['light', 'plug', 'camera', 'alarm_panel'], icon: 'science', color: '#7C3AED', methods: [
      PairingMethod(id: 'virtual', title: 'Ajouter la maison de démonstration', description: 'Crée des appareils virtuels', supportsDiscovery: true, fields: [FormFieldSpec(name: 'prefix', label: 'Préfixe', required: false)]),
    ]),
    const BrandInfo(id: 'tuya', name: 'Tuya / Smart Life', vendor: 'Tuya Inc.', description: 'Appareils Tuya via le cloud ou en local', protocols: ['tuya_cloud', 'tuya_local'], categories: ['switch', 'plug', 'light', 'sensor_contact', 'camera'], icon: 'cloud', color: '#FF4800', methods: [
      PairingMethod(id: 'cloud_project', title: 'Projet Tuya Cloud', description: 'Access ID / Secret du projet IoT', requiresIntegration: true, supportsDiscovery: true, fields: [
        FormFieldSpec(name: 'region', label: 'Région', type: 'select', options: [(value: 'eu', label: 'Europe'), (value: 'us', label: 'Amériques')], defaultValue: 'eu'),
        FormFieldSpec(name: 'access_id', label: 'Access ID'),
        FormFieldSpec(name: 'access_secret', label: 'Access Secret', type: 'password'),
      ]),
      PairingMethod(id: 'local_key', title: 'Clé locale', description: 'Contrôle local sans cloud', fields: [FormFieldSpec(name: 'device_id', label: 'Device ID'), FormFieldSpec(name: 'local_key', label: 'Local key', type: 'password'), FormFieldSpec(name: 'host', label: 'Adresse IP')]),
    ]),
    const BrandInfo(id: 'hikvision', name: 'Hikvision', vendor: 'Hikvision', description: 'Caméras, NVR et centrales AX PRO (ISAPI)', protocols: ['isapi'], categories: ['camera', 'nvr', 'alarm_panel'], icon: 'videocam', color: '#E30613', methods: [
      PairingMethod(id: 'ip_credentials', title: 'Adresse IP + identifiants', fields: [FormFieldSpec(name: 'host', label: 'Adresse IP'), FormFieldSpec(name: 'port', label: 'Port', type: 'number', defaultValue: 80), FormFieldSpec(name: 'https', label: 'HTTPS', type: 'toggle', required: false, defaultValue: false), FormFieldSpec(name: 'username', label: 'Utilisateur'), FormFieldSpec(name: 'password', label: 'Mot de passe', type: 'password')]),
    ]),
    const BrandInfo(id: 'matter', name: 'Matter', vendor: 'CSA', description: 'Appareils Matter (Wi-Fi / Thread)', protocols: ['matter'], categories: ['light', 'plug', 'lock', 'sensor_contact', 'thermostat'], icon: 'hub', color: '#2563EB', methods: [
      PairingMethod(id: 'qr_code', title: 'Scanner le code QR Matter', requiresIntegration: true, fields: [FormFieldSpec(name: 'code', label: 'Code QR', type: 'qr'), FormFieldSpec(name: 'wifi_ssid', label: 'Wi-Fi SSID', required: false), FormFieldSpec(name: 'wifi_password', label: 'Mot de passe Wi-Fi', type: 'password', required: false)]),
      PairingMethod(id: 'manual_code', title: 'Code d\'appairage manuel', requiresIntegration: true, fields: [FormFieldSpec(name: 'code', label: 'Code à 11 chiffres')]),
    ]),
  ];

  @override
  Future<List<BrandInfo>> brands() async {
    _check();
    return demoBrands;
  }

  @override
  Future<BrandInfo> brand(String brandId) async {
    _check();
    return demoBrands.firstWhere((b) => b.id == brandId, orElse: () => throw ApiException('Unknown brand', status: 404));
  }

  @override
  Future<List<CategoryGroup>> categories() async {
    _check();
    return const [
      CategoryGroup(id: 'lighting', name: 'Éclairage', nameEn: 'Lighting', icon: 'light', categories: [DeviceCategoryInfo(id: 'light', name: 'Éclairage', nameEn: 'Lighting', icon: 'lightbulb', group: 'lighting', brands: ['tuya', 'matter', 'demo'])]),
      CategoryGroup(id: 'cameras', name: 'Caméras & vidéo', nameEn: 'Cameras & video', icon: 'videocam', categories: [DeviceCategoryInfo(id: 'camera', name: 'Caméra', nameEn: 'Camera', icon: 'videocam', group: 'cameras', brands: ['hikvision', 'tuya', 'demo'])]),
      CategoryGroup(id: 'security', name: 'Sécurité', nameEn: 'Security', icon: 'security', categories: [DeviceCategoryInfo(id: 'alarm_panel', name: 'Centrale d\'alarme', nameEn: 'Alarm panel', icon: 'shield', group: 'security', brands: ['hikvision', 'demo'])]),
    ];
  }

  @override
  Future<ParsedCode> parseCode(String code) async {
    _check();
    if (code.startsWith('MT:')) {
      return const ParsedCode(kind: 'matter_qr', brand: 'matter', method: 'qr_code', data: {'vendor_id': 65521, 'product_id': 32769, 'discriminator': 3840, 'passcode': 20202021});
    }
    return const ParsedCode(kind: 'unknown');
  }

  @override
  Future<List<DiscoveredDevice>> discover(String brandId, {required String homeId, required String method, Map<String, dynamic> payload = const {}}) async {
    _check();
    return const [
      DiscoveredDevice(externalId: 'disc-1', name: 'Lampe découverte', category: 'light', model: 'X1', address: '192.168.1.10'),
      DiscoveredDevice(externalId: 'disc-2', name: 'Prise découverte', category: 'plug', model: 'P1', address: '192.168.1.11'),
    ];
  }

  @override
  Future<({List<Device> devices, String? integrationId, String message})> pair(String brandId, {required String homeId, required String method, Map<String, dynamic> payload = const {}, String? roomId, List<String>? selectedExternalIds}) async {
    _check();
    if (payload['host'] == '10.0.0.99') throw ApiException('Connexion impossible', status: 502, code: 'unreachable');
    final paired = Device(id: 'dev-new-${_devices.length}', homeId: homeId, name: 'Nouvel appareil $brandId', brand: brandId, protocol: method, category: 'light', externalId: 'ext-${_devices.length}', roomId: roomId, capabilities: const [Capability(code: 'switch', type: 'bool', writable: true)], state: const {'switch': false});
    _devices = [..._devices, paired];
    return (devices: [paired], integrationId: null, message: '1 appareil ajouté');
  }

  @override
  Future<List<Integration>> integrations(String homeId) async {
    _check();
    return [Integration(id: 'int-1', homeId: homeId, brand: 'tuya', key: 'tuya_cloud:abc', name: 'Tuya Cloud (eu)', config: const {'region': 'eu'})];
  }

  @override
  Future<void> deleteIntegration(String integrationId) async {}

  // ---- scenes & automations
  @override
  Future<List<Scene>> scenes(String homeId) async {
    _check();
    return List.of(_scenes);
  }

  @override
  Future<Scene> createScene(String homeId, Map<String, dynamic> body) async {
    _check();
    final scene = Scene.fromJson({...body, 'id': 'scene-${_scenes.length + 1}', 'home_id': homeId});
    _scenes.add(scene);
    return scene;
  }

  @override
  Future<Scene> updateScene(String sceneId, Map<String, dynamic> body) async {
    _check();
    final index = _scenes.indexWhere((s) => s.id == sceneId);
    final existing = _scenes[index];
    final scene = Scene.fromJson({...existing.toJson(), ...body, 'id': sceneId, 'home_id': existing.homeId});
    _scenes[index] = scene;
    return scene;
  }

  @override
  Future<void> deleteScene(String sceneId) async => _scenes.removeWhere((s) => s.id == sceneId);

  @override
  Future<Map<String, dynamic>> runScene(String sceneId) async {
    _check();
    return {'scene_id': sceneId, 'results': []};
  }

  @override
  Future<List<Automation>> automations(String homeId) async {
    _check();
    return List.of(_automations);
  }

  @override
  Future<Automation> createAutomation(String homeId, Map<String, dynamic> body) async {
    _check();
    final automation = Automation.fromJson({...body, 'id': 'auto-${_automations.length + 1}', 'home_id': homeId});
    _automations.add(automation);
    return automation;
  }

  @override
  Future<Automation> updateAutomation(String automationId, Map<String, dynamic> body) async {
    _check();
    final index = _automations.indexWhere((a) => a.id == automationId);
    final existing = _automations[index];
    final automation = Automation.fromJson({...existing.toJson(), ...body, 'id': automationId, 'home_id': existing.homeId});
    _automations[index] = automation;
    return automation;
  }

  @override
  Future<void> deleteAutomation(String automationId) async => _automations.removeWhere((a) => a.id == automationId);

  @override
  Future<Automation> setAutomationEnabled(String automationId, bool enabled) async {
    final index = _automations.indexWhere((a) => a.id == automationId);
    final a = _automations[index];
    final updated = Automation(id: a.id, homeId: a.homeId, name: a.name, enabled: enabled, match: a.match, triggers: a.triggers, conditions: a.conditions, actions: a.actions);
    _automations[index] = updated;
    return updated;
  }

  @override
  Future<Map<String, dynamic>> triggerAutomation(String automationId) async => {'automation_id': automationId, 'results': []};

  // ---- security
  SecurityState get _security => SecurityState(
        homeId: homeId,
        mode: securityMode,
        alarmActive: alarmActive,
        panels: _devices.where((d) => d.category == 'alarm_panel').toList(),
        zones: _devices.where((d) => d.category == 'alarm_zone').toList(),
        sensors: _devices.where((d) => d.isSensor || d.category == 'lock' || d.category == 'siren').toList(),
      );

  @override
  Future<SecurityState> security(String homeId) async {
    _check();
    return _security;
  }

  @override
  Future<SecurityState> setSecurityMode(String homeId, String mode) async {
    _check();
    securityMode = mode;
    if (mode == 'disarmed') alarmActive = false;
    return _security;
  }

  @override
  Future<SecurityState> clearAlarm(String homeId) async {
    alarmActive = false;
    return _security;
  }

  @override
  Future<SosAlert> raiseSos(String homeId, {double? lat, double? lon, String? note, String incidentType = 'panic'}) async {
    _check();
    final alert = SosAlert(id: 'sos-${_sos.length + 1}', homeId: homeId, userId: userId, lat: lat, lon: lon, note: note, createdAt: DateTime.now());
    _sos.insert(0, alert);
    alarmActive = true;
    return alert;
  }

  @override
  Future<List<SosAlert>> sosAlerts(String homeId) async => List.of(_sos);

  // ---- messages
  @override
  Future<List<HubMessage>> messages(String homeId, {String? kind, bool unreadOnly = false, int limit = 50}) async {
    _check();
    return _messages.where((m) => (kind == null || m.kind == kind) && (!unreadOnly || !m.read)).toList();
  }

  @override
  Future<UnreadCount> unreadCount(String homeId) async {
    _check();
    final unread = _messages.where((m) => !m.read);
    return UnreadCount(total: unread.length, alarm: unread.where((m) => m.kind == 'alarm').length, home: unread.where((m) => m.kind == 'home').length, notice: unread.where((m) => m.kind == 'notice').length);
  }

  @override
  Future<HubMessage> markRead(String messageId) async {
    final index = _messages.indexWhere((m) => m.id == messageId);
    _messages[index] = _messages[index].copyWith(read: true);
    return _messages[index];
  }

  @override
  Future<void> markAllRead(String homeId, {String? kind}) async {
    for (var i = 0; i < _messages.length; i++) {
      if (kind == null || _messages[i].kind == kind) _messages[i] = _messages[i].copyWith(read: true);
    }
  }

  @override
  Future<void> deleteMessage(String messageId) async => _messages.removeWhere((m) => m.id == messageId);

  @override
  Future<void> clearMessages(String homeId, {String? kind}) async => _messages.removeWhere((m) => kind == null || m.kind == kind);

  /// Demo devices matching the hub's demo adapter.
  static List<Device> demoDevices(String homeId) {
    Device d(String id, String name, String category, List<Capability> caps, Map<String, dynamic> state, {String? roomId, String? parentId}) =>
        Device(id: id, homeId: homeId, name: name, brand: 'demo', protocol: 'demo', category: category, externalId: id, roomId: roomId, parentId: parentId, capabilities: caps, state: state, model: 'SafeR Virtual', manufacturer: 'SafeR', firmware: '1.0.0');
    const bool_ = 'bool';
    return [
      d('dev-light', 'Lampe salon', 'light', const [Capability(code: 'switch', type: bool_, writable: true), Capability(code: 'brightness', type: 'int', writable: true, min: 0, max: 100, unit: '%'), Capability(code: 'color_temp', type: 'int', writable: true, min: 2700, max: 6500, unit: 'K'), Capability(code: 'color', type: 'color', writable: true), Capability(code: 'work_mode', type: 'enum', writable: true, values: ['white', 'colour', 'scene'])], {'switch': true, 'brightness': 80, 'color_temp': 4000, 'color': {'h': 30, 's': 40, 'v': 100}, 'work_mode': 'white'}, roomId: 'room-1'),
      d('dev-plug', 'Prise TV', 'plug', const [Capability(code: 'switch', type: bool_, writable: true), Capability(code: 'power', type: 'float', unit: 'W')], {'switch': false, 'power': 0.0}, roomId: 'room-1'),
      d('dev-switch', 'Interrupteur cuisine', 'switch', const [Capability(code: 'switch_1', type: bool_, writable: true), Capability(code: 'switch_2', type: bool_, writable: true)], {'switch_1': true, 'switch_2': false}),
      d('dev-cover', 'Volet chambre', 'cover', const [Capability(code: 'position', type: 'int', writable: true, min: 0, max: 100, unit: '%'), Capability(code: 'control', type: 'enum', writable: true, values: ['open', 'close', 'stop'])], {'position': 100, 'control': 'stop'}, roomId: 'room-2'),
      d('dev-thermo', 'Climatisation', 'thermostat', const [Capability(code: 'temp_current', type: 'float', unit: '°C'), Capability(code: 'temp_set', type: 'float', writable: true, min: 5, max: 35, step: 0.5, unit: '°C'), Capability(code: 'mode', type: 'enum', writable: true, values: ['off', 'heat', 'cool', 'auto']), Capability(code: 'humidity_current', type: 'float', unit: '%')], {'temp_current': 27.5, 'temp_set': 24.0, 'mode': 'cool', 'humidity_current': 71}, roomId: 'room-1'),
      d('dev-door', "Porte d'entrée", 'sensor_contact', const [Capability(code: 'contact', type: bool_), Capability(code: 'battery', type: 'int', unit: '%')], {'contact': false, 'battery': 92}, roomId: 'room-3'),
      d('dev-pir', 'Détecteur couloir', 'sensor_motion', const [Capability(code: 'motion', type: bool_), Capability(code: 'battery', type: 'int', unit: '%')], {'motion': false, 'battery': 78}),
      d('dev-smoke', 'Détecteur fumée cuisine', 'sensor_smoke', const [Capability(code: 'smoke', type: bool_), Capability(code: 'battery', type: 'int', unit: '%')], {'smoke': false, 'battery': 100}),
      d('dev-cam', 'Caméra entrée', 'camera', const [Capability(code: 'stream_main', type: 'string'), Capability(code: 'stream_sub', type: 'string'), Capability(code: 'snapshot', type: 'string'), Capability(code: 'motion', type: bool_), Capability(code: 'recording', type: bool_), Capability(code: 'ptz', type: 'enum', writable: true, values: ['up', 'down', 'left', 'right', 'zoom_in', 'zoom_out', 'stop']), Capability(code: 'siren', type: bool_, writable: true), Capability(code: 'light', type: bool_, writable: true)], {'motion': false, 'recording': true, 'siren': false, 'light': false, 'stream_main': 'rtsp://demo.safer.local:554/cam1/main', 'stream_sub': 'rtsp://demo.safer.local:554/cam1/sub', 'snapshot': 'https://demo.safer.local/cam1/snapshot.jpg'}, roomId: 'room-3'),
      d('dev-lock', 'Serrure entrée', 'lock', const [Capability(code: 'locked', type: bool_, writable: true), Capability(code: 'door', type: bool_), Capability(code: 'battery', type: 'int', unit: '%')], {'locked': true, 'door': false, 'battery': 65}),
      d('dev-panel', "Centrale d'alarme", 'alarm_panel', const [Capability(code: 'arm_mode', type: 'enum', writable: true, values: ['disarmed', 'armed_home', 'armed_away', 'armed_night']), Capability(code: 'alarm', type: bool_), Capability(code: 'triggered_zone', type: 'string'), Capability(code: 'ready', type: bool_)], {'arm_mode': 'disarmed', 'alarm': false, 'triggered_zone': '', 'ready': true}),
      d('dev-zone', 'Zone salon', 'alarm_zone', const [Capability(code: 'open', type: bool_), Capability(code: 'alarm', type: bool_), Capability(code: 'bypass', type: bool_, writable: true), Capability(code: 'tamper', type: bool_), Capability(code: 'battery', type: 'int', unit: '%'), Capability(code: 'signal', type: 'int', unit: '%')], {'open': false, 'alarm': false, 'bypass': false, 'tamper': false, 'battery': 90, 'signal': 80}, parentId: 'dev-panel'),
    ];
  }
}
