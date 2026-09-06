import 'dart:typed_data';

import 'package:dio/dio.dart';

import '../config.dart';
import '../models/models.dart';
import 'api_exception.dart';

typedef TokenProvider = String? Function();

/// Typed client for the SafeR Hub API (`/api/v1/hub`).
class HubClient {
  HubClient({required String baseUrl, required TokenProvider tokenProvider, Dio? dio})
      : _tokenProvider = tokenProvider,
        _dio = dio ?? Dio() {
    this.baseUrl = baseUrl;
    _dio.options
      ..connectTimeout = const Duration(seconds: 10)
      ..receiveTimeout = const Duration(seconds: 30)
      ..responseType = ResponseType.json;
    _dio.interceptors.add(InterceptorsWrapper(onRequest: (options, handler) {
      final token = _tokenProvider();
      if (token != null && token.isNotEmpty) {
        options.headers['Authorization'] = 'Bearer $token';
      }
      handler.next(options);
    }));
  }

  final Dio _dio;
  final TokenProvider _tokenProvider;
  late String _baseUrl;

  String get baseUrl => _baseUrl;
  set baseUrl(String value) {
    _baseUrl = value.replaceAll(RegExp(r'/+$'), '');
    _dio.options.baseUrl = '$_baseUrl${AppConfig.apiPrefix}';
  }

  /// WebSocket URL for realtime events.
  String wsUrl(String homeId, String token) {
    final uri = Uri.parse(_baseUrl);
    final scheme = uri.scheme == 'https' ? 'wss' : 'ws';
    return uri.replace(scheme: scheme, path: '${AppConfig.apiPrefix}/ws', queryParameters: {'home_id': homeId, 'token': token}).toString();
  }

  // ------------------------------------------------------------------ core
  Future<T> _run<T>(Future<Response<dynamic>> Function() call, T Function(dynamic data) parse) async {
    try {
      final response = await call();
      return parse(response.data);
    } on DioException catch (e) {
      throw _toApiException(e);
    }
  }

  ApiException _toApiException(DioException e) {
    final status = e.response?.statusCode;
    final data = e.response?.data;
    String message = e.message ?? 'Network error';
    String? code;
    if (data is Map) {
      final detail = data['detail'];
      if (detail is String) {
        message = detail;
      } else if (detail is List && detail.isNotEmpty) {
        final first = detail.first;
        if (first is Map && first['msg'] != null) {
          final loc = (first['loc'] as List?)?.skip(1).join('.') ?? '';
          message = loc.isNotEmpty ? '$loc: ${first['msg']}' : first['msg'].toString();
        }
      }
      code = data['code'] as String?;
    } else if (status == null) {
      message = 'Impossible de joindre le hub SafeR ($_baseUrl)';
    }
    return ApiException(message, status: status, code: code);
  }

  static Map<String, dynamic> _map(dynamic data) => Map<String, dynamic>.from(data as Map);
  static List<Map<String, dynamic>> _list(dynamic data) =>
      (data as List).whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();

  Future<bool> health() async {
    try {
      final response = await _dio.get('/health');
      return response.statusCode == 200;
    } on DioException {
      return false;
    }
  }

  // ------------------------------------------------------------------ auth
  Future<AuthResult> register({required String email, required String password, required String name, String? phone, String locale = 'fr'}) =>
      _run(() => _dio.post('/auth/register', data: {'email': email, 'password': password, 'name': name, 'phone': phone, 'locale': locale}),
          (d) => AuthResult.fromJson(_map(d)));

  Future<AuthResult> login({required String email, required String password}) =>
      _run(() => _dio.post('/auth/login', data: {'email': email, 'password': password}), (d) => AuthResult.fromJson(_map(d)));

  Future<User> me() => _run(() => _dio.get('/auth/me'), (d) => User.fromJson(_map(d)));

  Future<User> updateMe({String? name, String? phone, String? locale, String? avatarUrl}) => _run(
      () => _dio.patch('/auth/me', data: {
            if (name != null) 'name': name,
            if (phone != null) 'phone': phone,
            if (locale != null) 'locale': locale,
            if (avatarUrl != null) 'avatar_url': avatarUrl,
          }),
      (d) => User.fromJson(_map(d)));

  Future<void> registerPushToken(String platform, String token) =>
      _run(() => _dio.post('/auth/push-token', data: {'platform': platform, 'token': token}), (_) {});

  // ------------------------------------------------------------------ homes
  Future<List<Home>> homes() => _run(() => _dio.get('/homes'), (d) => _list(d).map(Home.fromJson).toList());

  Future<Home> createHome({required String name, double? lat, double? lon, String? address, List<String> rooms = const []}) => _run(
      () => _dio.post('/homes', data: {'name': name, 'lat': lat, 'lon': lon, 'address': address, 'rooms': rooms}), (d) => Home.fromJson(_map(d)));

  Future<Home> home(String homeId) => _run(() => _dio.get('/homes/$homeId'), (d) => Home.fromJson(_map(d)));

  Future<Home> updateHome(String homeId, {String? name, double? lat, double? lon, String? address}) => _run(
      () => _dio.patch('/homes/$homeId', data: {
            if (name != null) 'name': name,
            if (lat != null) 'lat': lat,
            if (lon != null) 'lon': lon,
            if (address != null) 'address': address,
          }),
      (d) => Home.fromJson(_map(d)));

  Future<void> deleteHome(String homeId) => _run(() => _dio.delete('/homes/$homeId'), (_) {});

  Future<List<Room>> rooms(String homeId) => _run(() => _dio.get('/homes/$homeId/rooms'), (d) => _list(d).map(Room.fromJson).toList());

  Future<Room> createRoom(String homeId, String name, {String? icon}) =>
      _run(() => _dio.post('/homes/$homeId/rooms', data: {'name': name, 'icon': icon}), (d) => Room.fromJson(_map(d)));

  Future<Room> updateRoom(String roomId, {String? name, String? icon}) =>
      _run(() => _dio.patch('/rooms/$roomId', data: {if (name != null) 'name': name, if (icon != null) 'icon': icon}), (d) => Room.fromJson(_map(d)));

  Future<void> deleteRoom(String roomId) => _run(() => _dio.delete('/rooms/$roomId'), (_) {});

  Future<List<Room>> reorderRooms(String homeId, List<String> ids) =>
      _run(() => _dio.post('/homes/$homeId/rooms/reorder', data: {'ids': ids}), (d) => _list(d).map(Room.fromJson).toList());

  Future<List<Member>> members(String homeId) => _run(() => _dio.get('/homes/$homeId/members'), (d) => _list(d).map(Member.fromJson).toList());

  Future<Member> addMember(String homeId, String email, {String role = 'member'}) =>
      _run(() => _dio.post('/homes/$homeId/members', data: {'email': email, 'role': role}), (d) => Member.fromJson(_map(d)));

  Future<Member> updateMember(String homeId, String userId, String role) =>
      _run(() => _dio.patch('/homes/$homeId/members/$userId', data: {'role': role}), (d) => Member.fromJson(_map(d)));

  Future<void> removeMember(String homeId, String userId) => _run(() => _dio.delete('/homes/$homeId/members/$userId'), (_) {});

  Future<Weather> weather(String homeId) => _run(() => _dio.get('/homes/$homeId/weather'), (d) => Weather.fromJson(_map(d)));

  // ------------------------------------------------------------------ devices
  Future<List<Device>> devices(String homeId, {String? roomId, String? category, String? brand}) => _run(
      () => _dio.get('/homes/$homeId/devices', queryParameters: {
            if (roomId != null) 'room_id': roomId,
            if (category != null) 'category': category,
            if (brand != null) 'brand': brand,
          }),
      (d) => _list(d).map(Device.fromJson).toList());

  Future<Device> device(String deviceId) => _run(() => _dio.get('/devices/$deviceId'), (d) => Device.fromJson(_map(d)));

  Future<Device> updateDevice(String deviceId, {String? name, String? roomId, bool clearRoom = false, String? icon}) => _run(
      () => _dio.patch('/devices/$deviceId', data: {
            if (name != null) 'name': name,
            if (roomId != null) 'room_id': roomId,
            if (icon != null) 'icon': icon,
            'clear_room': clearRoom,
          }),
      (d) => Device.fromJson(_map(d)));

  Future<void> deleteDevice(String deviceId) => _run(() => _dio.delete('/devices/$deviceId'), (_) {});

  Future<Device> refreshDevice(String deviceId) => _run(() => _dio.post('/devices/$deviceId/refresh'), (d) => Device.fromJson(_map(d)));

  Future<Device> sendCommand(String deviceId, String code, dynamic value) => sendCommands(deviceId, [(code: code, value: value)]);

  Future<Device> sendCommands(String deviceId, List<({String code, dynamic value})> commands) => _run(
      () => _dio.post('/devices/$deviceId/commands', data: {
            'commands': commands.map((c) => {'code': c.code, 'value': c.value}).toList(),
          }),
      (d) => Device.fromJson(_map(d)));

  Future<StreamInfo> stream(String deviceId, {String quality = 'main'}) =>
      _run(() => _dio.get('/devices/$deviceId/stream', queryParameters: {'quality': quality}), (d) => StreamInfo.fromJson(_map(d)));

  Future<Uint8List> snapshot(String deviceId) => _run(
      () => _dio.get<List<int>>('/devices/$deviceId/snapshot', options: Options(responseType: ResponseType.bytes)),
      (d) => Uint8List.fromList((d as List).cast<int>()));

  /// Absolute snapshot URL (for Image.network with the bearer header).
  String snapshotUrl(String deviceId) => '$_baseUrl${AppConfig.apiPrefix}/devices/$deviceId/snapshot';

  Future<List<DeviceEvent>> deviceEvents(String deviceId, {int limit = 50}) =>
      _run(() => _dio.get('/devices/$deviceId/events', queryParameters: {'limit': limit}), (d) => _list(d).map(DeviceEvent.fromJson).toList());

  Future<List<Device>> children(String deviceId) => _run(() => _dio.get('/devices/$deviceId/children'), (d) => _list(d).map(Device.fromJson).toList());

  // ------------------------------------------------------------------ onboarding
  Future<List<BrandInfo>> brands() => _run(() => _dio.get('/onboarding/brands'), (d) => _list(d).map(BrandInfo.fromJson).toList());

  Future<BrandInfo> brand(String brandId) => _run(() => _dio.get('/onboarding/brands/$brandId'), (d) => BrandInfo.fromJson(_map(d)));

  Future<List<CategoryGroup>> categories() => _run(() => _dio.get('/onboarding/categories'), (d) => _list(d).map(CategoryGroup.fromJson).toList());

  Future<ParsedCode> parseCode(String code) => _run(() => _dio.post('/onboarding/parse-code', data: {'code': code}), (d) => ParsedCode.fromJson(_map(d)));

  Future<List<DiscoveredDevice>> discover(String brandId, {required String homeId, required String method, Map<String, dynamic> payload = const {}}) => _run(
      () => _dio.post('/onboarding/$brandId/discover', data: {'home_id': homeId, 'method': method, 'payload': payload}),
      (d) => _list(d).map(DiscoveredDevice.fromJson).toList());

  Future<({List<Device> devices, String? integrationId, String message})> pair(
    String brandId, {
    required String homeId,
    required String method,
    Map<String, dynamic> payload = const {},
    String? roomId,
    List<String>? selectedExternalIds,
  }) =>
      _run(
          () => _dio.post('/onboarding/$brandId/pair', data: {
                'home_id': homeId,
                'room_id': roomId,
                'method': method,
                'payload': payload,
                'selected_external_ids': selectedExternalIds,
              }), (d) {
        final map = _map(d);
        return (
          devices: _list(map['devices']).map(Device.fromJson).toList(),
          integrationId: map['integration_id'] as String?,
          message: (map['message'] as String?) ?? '',
        );
      });

  Future<List<Integration>> integrations(String homeId) =>
      _run(() => _dio.get('/homes/$homeId/integrations'), (d) => _list(d).map(Integration.fromJson).toList());

  Future<void> deleteIntegration(String integrationId) => _run(() => _dio.delete('/integrations/$integrationId'), (_) {});

  // ------------------------------------------------------------------ scenes & automations
  Future<List<Scene>> scenes(String homeId) => _run(() => _dio.get('/homes/$homeId/scenes'), (d) => _list(d).map(Scene.fromJson).toList());

  Future<Scene> createScene(String homeId, Map<String, dynamic> body) => _run(() => _dio.post('/homes/$homeId/scenes', data: body), (d) => Scene.fromJson(_map(d)));

  Future<Scene> updateScene(String sceneId, Map<String, dynamic> body) => _run(() => _dio.patch('/scenes/$sceneId', data: body), (d) => Scene.fromJson(_map(d)));

  Future<void> deleteScene(String sceneId) => _run(() => _dio.delete('/scenes/$sceneId'), (_) {});

  Future<Map<String, dynamic>> runScene(String sceneId) => _run(() => _dio.post('/scenes/$sceneId/run'), _map);

  Future<List<Automation>> automations(String homeId) =>
      _run(() => _dio.get('/homes/$homeId/automations'), (d) => _list(d).map(Automation.fromJson).toList());

  Future<Automation> createAutomation(String homeId, Map<String, dynamic> body) =>
      _run(() => _dio.post('/homes/$homeId/automations', data: body), (d) => Automation.fromJson(_map(d)));

  Future<Automation> updateAutomation(String automationId, Map<String, dynamic> body) =>
      _run(() => _dio.patch('/automations/$automationId', data: body), (d) => Automation.fromJson(_map(d)));

  Future<void> deleteAutomation(String automationId) => _run(() => _dio.delete('/automations/$automationId'), (_) {});

  Future<Automation> setAutomationEnabled(String automationId, bool enabled) =>
      _run(() => _dio.post('/automations/$automationId/${enabled ? 'enable' : 'disable'}'), (d) => Automation.fromJson(_map(d)));

  Future<Map<String, dynamic>> triggerAutomation(String automationId) => _run(() => _dio.post('/automations/$automationId/trigger'), _map);

  // ------------------------------------------------------------------ security / sos
  Future<SecurityState> security(String homeId) => _run(() => _dio.get('/homes/$homeId/security'), (d) => SecurityState.fromJson(_map(d)));

  Future<SecurityState> setSecurityMode(String homeId, String mode) =>
      _run(() => _dio.post('/homes/$homeId/security/mode', data: {'mode': mode}), (d) => SecurityState.fromJson(_map(d)));

  Future<SecurityState> clearAlarm(String homeId) => _run(() => _dio.post('/homes/$homeId/security/alarm/clear'), (d) => SecurityState.fromJson(_map(d)));

  Future<SosAlert> raiseSos(String homeId, {double? lat, double? lon, String? note, String incidentType = 'panic'}) => _run(
      () => _dio.post('/homes/$homeId/sos', data: {'lat': lat, 'lon': lon, 'note': note, 'incident_type': incidentType}), (d) => SosAlert.fromJson(_map(d)));

  Future<List<SosAlert>> sosAlerts(String homeId) => _run(() => _dio.get('/homes/$homeId/sos'), (d) => _list(d).map(SosAlert.fromJson).toList());

  Future<SosAlert> updateSos(String homeId, String sosId, String status) =>
      _run(() => _dio.patch('/homes/$homeId/sos/$sosId', data: {'status': status}), (d) => SosAlert.fromJson(_map(d)));

  // ------------------------------------------------------------------ messages
  Future<List<HubMessage>> messages(String homeId, {String? kind, bool unreadOnly = false, int limit = 50}) => _run(
      () => _dio.get('/homes/$homeId/messages', queryParameters: {if (kind != null) 'kind': kind, 'unread_only': unreadOnly, 'limit': limit}),
      (d) => _list(d).map(HubMessage.fromJson).toList());

  Future<UnreadCount> unreadCount(String homeId) => _run(() => _dio.get('/homes/$homeId/messages/unread-count'), (d) => UnreadCount.fromJson(_map(d)));

  Future<HubMessage> markRead(String messageId) => _run(() => _dio.post('/messages/$messageId/read'), (d) => HubMessage.fromJson(_map(d)));

  Future<void> markAllRead(String homeId, {String? kind}) =>
      _run(() => _dio.post('/homes/$homeId/messages/read-all', queryParameters: {if (kind != null) 'kind': kind}), (_) {});

  Future<void> deleteMessage(String messageId) => _run(() => _dio.delete('/messages/$messageId'), (_) {});

  Future<void> clearMessages(String homeId, {String? kind}) =>
      _run(() => _dio.delete('/homes/$homeId/messages', queryParameters: {if (kind != null) 'kind': kind}), (_) {});
}
