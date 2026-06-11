import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:http/http.dart' as http;
import 'package:web_socket_channel/web_socket_channel.dart';

/// Connection lifecycle exposed to the UI.
enum HaConnectionState { disconnected, connecting, connected, reconnecting }

/// A Home Assistant WebSocket client with a REST fallback.
///
/// Device/protocol compatibility note: the phone has no Zigbee, Z-Wave,
/// Thread or Matter radio. Universal device support is achieved by talking
/// to Home Assistant, which bridges every protocol through its integrations
/// and exposes all devices uniformly as entities. This client therefore aims
/// for *complete entity coverage* rather than per-protocol code:
///  - auth via long-lived token
///  - get_states + subscribe_events(state_changed)
///  - area / device / entity registries (kept in sync via registry events)
///  - call_service with correct per-domain semantics (cover/lock/vacuum/...)
///  - REST fallback for service calls when the socket is down
///  - automatic reconnect with exponential backoff and heartbeat pings
///
/// Docs: https://developers.home-assistant.io/docs/api/websocket/
///       https://developers.home-assistant.io/docs/api/rest/
class HaClient {
  /// e.g. `wss://homeassistant.local:8123/api/websocket`
  final String wsUrl;

  /// e.g. `https://homeassistant.local:8123` — enables REST fallback and
  /// connection tests. Optional; WS-only operation still works without it.
  final String? restBase;

  /// Long-lived access token (HA: Profile → Security).
  final String token;

  final bool autoReconnect;

  WebSocketChannel? _channel;
  int _msgId = 1;
  final Map<int, Completer<dynamic>> _pending = {};
  Completer<void>? _connectCompleter;
  bool _authed = false;
  bool _manualDisconnect = false;
  bool _disposed = false;
  int _reconnectAttempts = 0;
  Timer? _reconnectTimer;
  Timer? _heartbeatTimer;
  bool _refreshingRegistries = false;

  final Map<String, HaState> _states = {};
  final Map<String, HaArea> _areas = {};
  final Map<String, HaEntityMeta> _entityMeta = {};
  final Map<String, String?> _deviceArea = {};

  final StreamController<Map<String, HaState>> _statesController =
      StreamController<Map<String, HaState>>.broadcast();
  final StreamController<HaConnectionState> _connectionController =
      StreamController<HaConnectionState>.broadcast();
  HaConnectionState _connection = HaConnectionState.disconnected;

  HaClient({
    required this.wsUrl,
    required this.token,
    this.restBase,
    this.autoReconnect = true,
  });

  Stream<Map<String, HaState>> get states => _statesController.stream;
  Stream<HaConnectionState> get connectionStates =>
      _connectionController.stream;
  HaConnectionState get connectionState => _connection;
  Map<String, HaState> get currentStates => Map.unmodifiable(_states);
  Map<String, HaArea> get areas => Map.unmodifiable(_areas);
  bool get isConnected => _channel != null && _authed;

  HaEntityMeta? metaForEntity(String entityId) => _entityMeta[entityId];

  /// Area resolution the way HA does it: the entity's own area wins,
  /// otherwise the area of the device the entity belongs to.
  String? areaForEntity(String entityId) {
    final meta = _entityMeta[entityId];
    if (meta == null) return null;
    return meta.areaId ?? _deviceArea[meta.deviceId];
  }

  /// Whether the entity belongs on a dashboard: not disabled, not hidden,
  /// and not a diagnostic/config entity. Entities absent from the registry
  /// (some integrations) are shown.
  bool isVisible(String entityId) {
    final meta = _entityMeta[entityId];
    if (meta == null) return true;
    return meta.disabledBy == null &&
        meta.hiddenBy == null &&
        meta.entityCategory == null;
  }

  // -- connection lifecycle -------------------------------------------------

  Future<void> connect() {
    _manualDisconnect = false;
    return _openSocket();
  }

  Future<void> _openSocket() {
    if (_connectCompleter != null && !_connectCompleter!.isCompleted) {
      return _connectCompleter!.future;
    }
    final completer = Completer<void>();
    _connectCompleter = completer;
    _setConnection(_reconnectAttempts == 0
        ? HaConnectionState.connecting
        : HaConnectionState.reconnecting);
    try {
      _channel = WebSocketChannel.connect(Uri.parse(wsUrl));
    } catch (e) {
      _failConnect(completer, HaException('connect failed: $e'));
      _handleSocketClosed();
      return completer.future;
    }
    _channel!.stream.listen(
      _onRawMessage,
      onError: (Object e, StackTrace _) {
        _failConnect(completer, HaException('socket error: $e'));
        _handleSocketClosed();
      },
      onDone: () {
        _failConnect(completer, HaException('socket closed'));
        _handleSocketClosed();
      },
    );
    return completer.future;
  }

  void _failConnect(Completer<void> completer, HaException error) {
    if (!completer.isCompleted) completer.completeError(error);
  }

  void _handleSocketClosed() {
    _cleanupChannel();
    if (_disposed || _manualDisconnect) {
      _setConnection(HaConnectionState.disconnected);
      return;
    }
    _scheduleReconnect();
  }

  void _scheduleReconnect() {
    if (!autoReconnect) {
      _setConnection(HaConnectionState.disconnected);
      return;
    }
    if (_reconnectTimer != null) return;
    _setConnection(HaConnectionState.reconnecting);
    var seconds = 1 << min(_reconnectAttempts, 6); // 1,2,4,...,64
    if (seconds > 60) seconds = 60;
    final jitterMs = Random().nextInt(1000);
    _reconnectTimer =
        Timer(Duration(seconds: seconds, milliseconds: jitterMs), () {
      _reconnectTimer = null;
      _reconnectAttempts++;
      _openSocket().catchError((_) {});
    });
  }

  void _cleanupChannel() {
    _heartbeatTimer?.cancel();
    _heartbeatTimer = null;
    _channel = null;
    _authed = false;
    for (final c in _pending.values) {
      if (!c.isCompleted) c.completeError(HaException('disconnected'));
    }
    _pending.clear();
  }

  Future<void> disconnect() async {
    _manualDisconnect = true;
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    await _channel?.sink.close();
    _cleanupChannel();
    _setConnection(HaConnectionState.disconnected);
  }

  Future<void> dispose() async {
    _disposed = true;
    await disconnect();
    await _statesController.close();
    await _connectionController.close();
  }

  void _setConnection(HaConnectionState s) {
    if (_disposed || s == _connection) return;
    _connection = s;
    if (!_connectionController.isClosed) _connectionController.add(s);
  }

  // -- protocol ---------------------------------------------------------------

  Future<dynamic> _request(Map<String, dynamic> payload) {
    final ch = _channel;
    if (ch == null) {
      return Future.error(HaException('not connected'));
    }
    final id = _msgId++;
    final completer = Completer<dynamic>();
    _pending[id] = completer;
    ch.sink.add(jsonEncode({...payload, 'id': id}));
    return completer.future;
  }

  void _onRawMessage(dynamic raw) {
    final msg = jsonDecode(raw as String) as Map<String, dynamic>;
    switch (msg['type']) {
      case 'auth_required':
        _channel!.sink.add(jsonEncode({
          'type': 'auth',
          'access_token': token,
        }));
        break;

      case 'auth_ok':
        _authed = true;
        _bootstrap();
        break;

      case 'auth_invalid':
        if (_connectCompleter != null && !_connectCompleter!.isCompleted) {
          _connectCompleter!.completeError(
              HaException(msg['message']?.toString() ?? 'auth invalid'));
        }
        // A bad token won't fix itself — stop the reconnect loop.
        _manualDisconnect = true;
        _channel?.sink.close();
        break;

      case 'result':
      case 'pong':
        final id = msg['id'] as int?;
        if (id == null) return;
        final completer = _pending.remove(id);
        if (completer == null || completer.isCompleted) return;
        if (msg['type'] == 'pong' || msg['success'] == true) {
          completer.complete(msg['result']);
        } else {
          completer.completeError(HaException(
              msg['error']?['message']?.toString() ?? 'request failed'));
        }
        break;

      case 'event':
        final ev = msg['event'] as Map<String, dynamic>?;
        if (ev == null) return;
        final eventType = ev['event_type'];
        if (eventType == 'state_changed') {
          _applyStateChange(ev['data'] as Map<String, dynamic>);
        } else if (eventType == 'entity_registry_updated' ||
            eventType == 'area_registry_updated' ||
            eventType == 'device_registry_updated') {
          _refreshRegistries();
        }
        break;
    }
  }

  Future<void> _bootstrap() async {
    try {
      await _loadRegistries();

      final states = await _request({'type': 'get_states'});
      _states.clear();
      for (final s in (states as List)
          .cast<Map>()
          .map((m) => m.cast<String, dynamic>())) {
        final st = HaState.fromJson(s);
        _states[st.entityId] = st;
      }

      for (final eventType in [
        'state_changed',
        'entity_registry_updated',
        'area_registry_updated',
        'device_registry_updated',
      ]) {
        await _request({'type': 'subscribe_events', 'event_type': eventType});
      }

      _reconnectAttempts = 0;
      _setConnection(HaConnectionState.connected);
      _startHeartbeat();
      _statesController.add(currentStates);
      if (_connectCompleter != null && !_connectCompleter!.isCompleted) {
        _connectCompleter!.complete();
      }
    } catch (e) {
      final err = e is HaException ? e : HaException('bootstrap failed: $e');
      if (_connectCompleter != null && !_connectCompleter!.isCompleted) {
        _connectCompleter!.completeError(err);
      }
      // Closing the socket routes us through the reconnect path.
      _channel?.sink.close();
    }
  }

  Future<void> _loadRegistries() async {
    final areas = await _request({'type': 'config/area_registry/list'});
    _areas.clear();
    for (final a in (areas as List)
        .cast<Map>()
        .map((m) => m.cast<String, dynamic>())) {
      final area = HaArea.fromJson(a);
      _areas[area.areaId] = area;
    }

    final devices = await _request({'type': 'config/device_registry/list'});
    _deviceArea.clear();
    for (final d in (devices as List)
        .cast<Map>()
        .map((m) => m.cast<String, dynamic>())) {
      _deviceArea[d['id'] as String] = d['area_id'] as String?;
    }

    final entities = await _request({'type': 'config/entity_registry/list'});
    _entityMeta.clear();
    for (final e in (entities as List)
        .cast<Map>()
        .map((m) => m.cast<String, dynamic>())) {
      final meta = HaEntityMeta.fromJson(e);
      _entityMeta[meta.entityId] = meta;
    }
  }

  Future<void> _refreshRegistries() async {
    if (_refreshingRegistries || !isConnected) return;
    _refreshingRegistries = true;
    try {
      await _loadRegistries();
      // Areas / visibility may have changed; let the UI regroup.
      _statesController.add(currentStates);
    } catch (_) {
      // Transient — the next registry event or reconnect retries.
    } finally {
      _refreshingRegistries = false;
    }
  }

  void _startHeartbeat() {
    _heartbeatTimer?.cancel();
    _heartbeatTimer = Timer.periodic(const Duration(seconds: 25), (_) async {
      try {
        await _request({'type': 'ping'}).timeout(const Duration(seconds: 10));
      } catch (_) {
        // Dead link the TCP stack hasn't noticed — force the reconnect path.
        _channel?.sink.close();
      }
    });
  }

  void _applyStateChange(Map<String, dynamic> data) {
    final entityId = data['entity_id'] as String;
    final newState = data['new_state'];
    if (newState == null) {
      _states.remove(entityId);
    } else {
      _states[entityId] =
          HaState.fromJson((newState as Map).cast<String, dynamic>());
    }
    _statesController.add(currentStates);
  }

  // -- service calls (WS first, REST fallback) --------------------------------

  Future<void> callService(
    String domain,
    String service, {
    String? entityId,
    Map<String, dynamic>? data,
  }) async {
    if (isConnected) {
      await _request({
        'type': 'call_service',
        'domain': domain,
        'service': service,
        if (data != null) 'service_data': data,
        if (entityId != null) 'target': {'entity_id': entityId},
      });
      return;
    }
    if (restBase != null) {
      await _callServiceRest(domain, service, entityId: entityId, data: data);
      return;
    }
    throw HaException('not connected and no REST base configured');
  }

  Future<void> _callServiceRest(
    String domain,
    String service, {
    String? entityId,
    Map<String, dynamic>? data,
  }) async {
    final uri = Uri.parse('$restBase/api/services/$domain/$service');
    final body = <String, dynamic>{
      if (entityId != null) 'entity_id': entityId,
      ...?data,
    };
    final res = await http
        .post(
          uri,
          headers: {
            'Authorization': 'Bearer $token',
            'Content-Type': 'application/json',
          },
          body: jsonEncode(body),
        )
        .timeout(const Duration(seconds: 10));
    if (res.statusCode >= 400) {
      throw HaException('REST ${res.statusCode}: ${res.body}');
    }
  }

  /// Reachability + auth probe against `GET /api/` (true on HTTP 200).
  static Future<bool> testConnection(String restBase, String token) async {
    try {
      final res = await http.get(
        Uri.parse('$restBase/api/'),
        headers: {'Authorization': 'Bearer $token'},
      ).timeout(const Duration(seconds: 8));
      return res.statusCode == 200;
    } on SocketException {
      return false;
    } on Exception {
      return false;
    }
  }

  // -- per-domain actions ------------------------------------------------------

  /// Domains whose tile tap maps to a safe, obvious action.
  /// alarm_control_panel is deliberately excluded: arming/disarming
  /// must go through the detail sheet (it may need a code).
  static const Set<String> primaryActionDomains = {
    'light', 'switch', 'fan', 'input_boolean', 'siren', 'remote',
    'humidifier', 'automation', 'script', 'group', 'media_player',
    'cover', 'lock', 'vacuum', 'climate', 'scene', 'button', 'input_button',
    'valve', 'lawn_mower', 'water_heater',
  };

  bool isPrimaryActionable(String domain) =>
      primaryActionDomains.contains(domain);

  /// What tapping a tile should do, with correct per-domain semantics:
  /// covers/valves toggle open-close, locks lock/unlock, vacuums start/dock,
  /// media players play/pause, scenes activate, buttons press, and
  /// everything else goes through homeassistant.toggle.
  Future<void> primaryAction(String entityId) {
    final state = _states[entityId];
    final domain = entityId.split('.').first;
    switch (domain) {
      case 'cover':
        return callService('cover', 'toggle', entityId: entityId);
      case 'valve':
        return callService('valve', 'toggle', entityId: entityId);
      case 'lock':
        final unlocked = state?.state == 'unlocked';
        return callService('lock', unlocked ? 'lock' : 'unlock',
            entityId: entityId);
      case 'vacuum':
        final active =
            state?.state == 'cleaning' || state?.state == 'returning';
        return callService('vacuum', active ? 'return_to_base' : 'start',
            entityId: entityId);
      case 'lawn_mower':
        final mowing = state?.state == 'mowing';
        return callService('lawn_mower', mowing ? 'dock' : 'start_mowing',
            entityId: entityId);
      case 'media_player':
        return callService('media_player', 'media_play_pause',
            entityId: entityId);
      case 'climate':
        return callService('climate', 'toggle', entityId: entityId);
      case 'water_heater':
        final on = state != null && state.state != 'off';
        return callService('water_heater', on ? 'turn_off' : 'turn_on',
            entityId: entityId);
      case 'scene':
        return callService('scene', 'turn_on', entityId: entityId);
      case 'button':
      case 'input_button':
        return callService(domain, 'press', entityId: entityId);
      default:
        // homeassistant.toggle covers light/switch/fan/script/automation/…
        return callService('homeassistant', 'toggle', entityId: entityId);
    }
  }

  /// Backward-compatible alias for earlier call sites.
  Future<void> toggle(String entityId) => primaryAction(entityId);

  // Typed helpers used by the entity detail sheet.

  Future<void> setLightBrightness(String entityId, int brightness0to255) =>
      callService('light', 'turn_on',
          entityId: entityId, data: {'brightness': brightness0to255});

  Future<void> setFanPercentage(String entityId, int percentage) =>
      callService('fan', 'set_percentage',
          entityId: entityId, data: {'percentage': percentage});

  Future<void> coverCommand(String entityId, String command) =>
      callService('cover', command, entityId: entityId);

  Future<void> setCoverPosition(String entityId, int position0to100) =>
      callService('cover', 'set_cover_position',
          entityId: entityId, data: {'position': position0to100});

  Future<void> setClimateTemperature(String entityId, double temperature) =>
      callService('climate', 'set_temperature',
          entityId: entityId, data: {'temperature': temperature});

  Future<void> setClimateHvacMode(String entityId, String mode) =>
      callService('climate', 'set_hvac_mode',
          entityId: entityId, data: {'hvac_mode': mode});

  Future<void> mediaCommand(String entityId, String command) =>
      callService('media_player', command, entityId: entityId);

  Future<void> setMediaVolume(String entityId, double volume0to1) =>
      callService('media_player', 'volume_set',
          entityId: entityId, data: {'volume_level': volume0to1});

  Future<void> vacuumCommand(String entityId, String command) =>
      callService('vacuum', command, entityId: entityId);

  Future<void> lockCommand(String entityId, String command, {String? code}) =>
      callService('lock', command,
          entityId: entityId, data: code == null ? null : {'code': code});

  Future<void> selectOption(String entityId, String option) {
    final domain = entityId.split('.').first; // select | input_select
    return callService(domain, 'select_option',
        entityId: entityId, data: {'option': option});
  }

  Future<void> setNumberValue(String entityId, double value) {
    final domain = entityId.split('.').first; // number | input_number
    return callService(domain, 'set_value',
        entityId: entityId, data: {'value': value});
  }

  Future<void> alarmCommand(String entityId, String command,
          {String? code}) =>
      callService('alarm_control_panel', 'alarm_$command',
          entityId: entityId, data: code == null ? null : {'code': code});
}

/// One entity's live state, as delivered by HA.
class HaState {
  final String entityId;
  final String state;
  final Map<String, dynamic> attributes;
  final DateTime? lastChanged;

  const HaState({
    required this.entityId,
    required this.state,
    required this.attributes,
    this.lastChanged,
  });

  factory HaState.fromJson(Map<String, dynamic> j) => HaState(
        entityId: j['entity_id'] as String,
        state: j['state']?.toString() ?? '',
        attributes:
            (j['attributes'] as Map?)?.cast<String, dynamic>() ?? const {},
        lastChanged: DateTime.tryParse(j['last_changed']?.toString() ?? ''),
      );

  String get domain => entityId.split('.').first;
  String get friendlyName =>
      attributes['friendly_name']?.toString() ?? entityId;
  String? get unit => attributes['unit_of_measurement']?.toString();

  bool get isUnavailable => state == 'unavailable' || state == 'unknown';

  /// "Active" states across all HA domains (lights, covers, locks, climate,
  /// alarms, vacuums, cameras, mowers…). Drives tile highlighting.
  bool get isOn {
    switch (state) {
      case 'on':
      case 'open':
      case 'opening':
      case 'home':
      case 'playing':
      case 'buffering':
      case 'unlocked':
      case 'unlocking':
      case 'cleaning':
      case 'returning':
      case 'heat':
      case 'cool':
      case 'heat_cool':
      case 'auto':
      case 'dry':
      case 'fan_only':
      case 'armed_home':
      case 'armed_away':
      case 'armed_night':
      case 'armed_vacation':
      case 'armed_custom_bypass':
      case 'triggered':
      case 'streaming':
      case 'recording':
      case 'mowing':
      case 'running':
      case 'active':
        return true;
    }
    return false;
  }

  /// 0..255 brightness for `light.*`, or null.
  int? get brightness {
    final v = attributes['brightness'];
    return v is num ? v.toInt() : null;
  }

  double? get targetTemperature {
    final v = attributes['temperature'];
    return v is num ? v.toDouble() : null;
  }

  double? get volumeLevel {
    final v = attributes['volume_level'];
    return v is num ? v.toDouble() : null;
  }

  int? get coverPosition {
    final v = attributes['current_position'];
    return v is num ? v.toInt() : null;
  }
}

/// Entity registry entry — drives area grouping and dashboard visibility.
class HaEntityMeta {
  final String entityId;
  final String? areaId;
  final String? deviceId;
  final String? entityCategory; // 'diagnostic' | 'config' | null
  final String? hiddenBy;
  final String? disabledBy;

  const HaEntityMeta({
    required this.entityId,
    this.areaId,
    this.deviceId,
    this.entityCategory,
    this.hiddenBy,
    this.disabledBy,
  });

  factory HaEntityMeta.fromJson(Map<String, dynamic> j) => HaEntityMeta(
        entityId: j['entity_id'] as String,
        areaId: j['area_id'] as String?,
        deviceId: j['device_id'] as String?,
        entityCategory: j['entity_category'] as String?,
        hiddenBy: j['hidden_by'] as String?,
        disabledBy: j['disabled_by'] as String?,
      );
}

class HaArea {
  final String areaId;
  final String name;
  final String? icon;

  const HaArea({required this.areaId, required this.name, this.icon});

  factory HaArea.fromJson(Map<String, dynamic> j) => HaArea(
        areaId: j['area_id'] as String,
        name: j['name']?.toString() ?? 'Area',
        icon: j['icon']?.toString(),
      );
}

class HaException implements Exception {
  final String message;
  HaException(this.message);
  @override
  String toString() => 'HaException: $message';
}
