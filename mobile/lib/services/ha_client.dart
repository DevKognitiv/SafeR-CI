import 'dart:async';
import 'dart:convert';

import 'package:web_socket_channel/web_socket_channel.dart';

/// A minimal Home Assistant WebSocket + REST client.
///
/// Implements the slice of the public HA API needed for a dashboard:
/// long-lived-token auth, `get_states`, `subscribe_events:state_changed`,
/// `config/area_registry/list`, `config/entity_registry/list`, and
/// `call_service`. Exposes a [Stream] that fires the full entity map
/// whenever any state changes.
///
/// Docs:
///  - https://developers.home-assistant.io/docs/api/websocket/
///  - https://developers.home-assistant.io/docs/api/rest/
class HaClient {
  /// e.g. `wss://homeassistant.local:8123/api/websocket`
  final String wsUrl;

  /// Long-lived access token (Profile → Security → Long-lived access tokens).
  final String token;

  WebSocketChannel? _channel;
  int _msgId = 1;
  final Map<int, Completer<dynamic>> _pending = {};
  Completer<void>? _connectCompleter;
  bool _authed = false;

  final Map<String, HaState> _states = {};
  final Map<String, HaArea> _areas = {};
  final Map<String, String?> _entityArea = {};

  final StreamController<Map<String, HaState>> _statesController =
      StreamController<Map<String, HaState>>.broadcast();

  HaClient({required this.wsUrl, required this.token});

  Stream<Map<String, HaState>> get states => _statesController.stream;
  Map<String, HaState> get currentStates => Map.unmodifiable(_states);
  Map<String, HaArea> get areas => Map.unmodifiable(_areas);
  String? areaForEntity(String entityId) => _entityArea[entityId];
  bool get isConnected => _channel != null && _authed;

  Future<void> connect() async {
    if (_connectCompleter != null && !_connectCompleter!.isCompleted) {
      return _connectCompleter!.future;
    }
    final completer = Completer<void>();
    _connectCompleter = completer;
    try {
      _channel = WebSocketChannel.connect(Uri.parse(wsUrl));
    } catch (e) {
      completer.completeError(HaException('connect failed: $e'));
      return completer.future;
    }
    _channel!.stream.listen(
      _onRawMessage,
      onError: (Object e, StackTrace _) {
        if (!completer.isCompleted) {
          completer.completeError(HaException('socket error: $e'));
        }
        _teardown();
      },
      onDone: () {
        if (!completer.isCompleted) {
          completer.completeError(
              HaException('socket closed before auth_ok'));
        }
        _teardown();
      },
    );
    return completer.future;
  }

  Future<void> disconnect() async {
    await _channel?.sink.close();
    _teardown();
  }

  void _teardown() {
    _channel = null;
    _authed = false;
    for (final c in _pending.values) {
      if (!c.isCompleted) c.completeError(HaException('disconnected'));
    }
    _pending.clear();
  }

  Future<void> dispose() async {
    await disconnect();
    await _statesController.close();
  }

  /// Call a HA service, e.g. `callService('light', 'turn_on', entityId: 'light.x')`.
  Future<void> callService(
    String domain,
    String service, {
    String? entityId,
    Map<String, dynamic>? data,
  }) async {
    await _request({
      'type': 'call_service',
      'domain': domain,
      'service': service,
      if (data != null) 'service_data': data,
      if (entityId != null) 'target': {'entity_id': entityId},
    });
  }

  Future<void> toggle(String entityId) {
    final state = _states[entityId];
    final domain = entityId.split('.').first;
    final service = (state?.isOn ?? false) ? 'turn_off' : 'turn_on';
    return callService(domain, service, entityId: entityId);
  }

  // --- internals --------------------------------------------------------

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
        _connectCompleter?.completeError(
            HaException(msg['message']?.toString() ?? 'auth invalid'));
        _teardown();
        break;

      case 'result':
        final id = msg['id'] as int?;
        if (id == null) return;
        final completer = _pending.remove(id);
        if (completer == null || completer.isCompleted) return;
        if (msg['success'] == true) {
          completer.complete(msg['result']);
        } else {
          completer.completeError(HaException(
              msg['error']?['message']?.toString() ?? 'request failed'));
        }
        break;

      case 'event':
        final ev = msg['event'] as Map<String, dynamic>?;
        if (ev?['event_type'] == 'state_changed') {
          _applyStateChange(ev!['data'] as Map<String, dynamic>);
        }
        break;
    }
  }

  Future<void> _bootstrap() async {
    try {
      final areas = await _request({'type': 'config/area_registry/list'});
      for (final a in (areas as List).cast<Map>().map((m) =>
          m.cast<String, dynamic>())) {
        final area = HaArea.fromJson(a);
        _areas[area.areaId] = area;
      }

      final entReg = await _request({'type': 'config/entity_registry/list'});
      for (final e in (entReg as List).cast<Map>().map((m) =>
          m.cast<String, dynamic>())) {
        _entityArea[e['entity_id'] as String] = e['area_id'] as String?;
      }

      final states = await _request({'type': 'get_states'});
      for (final s in (states as List).cast<Map>().map((m) =>
          m.cast<String, dynamic>())) {
        final st = HaState.fromJson(s);
        _states[st.entityId] = st;
      }

      await _request({
        'type': 'subscribe_events',
        'event_type': 'state_changed',
      });

      _statesController.add(currentStates);
      _connectCompleter?.complete();
    } catch (e) {
      _connectCompleter?.completeError(
          e is HaException ? e : HaException('bootstrap failed: $e'));
      await disconnect();
    }
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
}

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
        lastChanged:
            DateTime.tryParse(j['last_changed']?.toString() ?? ''),
      );

  String get domain => entityId.split('.').first;
  String get friendlyName =>
      attributes['friendly_name']?.toString() ?? entityId;
  String? get unit => attributes['unit_of_measurement']?.toString();

  /// True for the common "on-ish" states across HA domains.
  bool get isOn {
    switch (state) {
      case 'on':
      case 'open':
      case 'home':
      case 'playing':
      case 'unlocked':
      case 'cleaning':
        return true;
    }
    return false;
  }

  /// 0..255 brightness for `light.*` entities, or null.
  int? get brightness {
    final v = attributes['brightness'];
    return v is num ? v.toInt() : null;
  }
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
