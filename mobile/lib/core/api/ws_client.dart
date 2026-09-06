import 'dart:async';
import 'dart:convert';

import 'package:web_socket_channel/web_socket_channel.dart';

import '../models/hub_event.dart';

/// Realtime connection to the hub with automatic reconnection.
class HubSocket {
  HubSocket({required this.url, this.pingInterval = const Duration(seconds: 25)});

  final String url;
  final Duration pingInterval;

  final _controller = StreamController<HubEvent>.broadcast();
  final _statusController = StreamController<bool>.broadcast();
  WebSocketChannel? _channel;
  StreamSubscription? _subscription;
  Timer? _pingTimer;
  Timer? _reconnectTimer;
  int _attempt = 0;
  bool _closed = false;
  bool _connected = false;

  Stream<HubEvent> get events => _controller.stream;
  Stream<bool> get status => _statusController.stream;
  bool get isConnected => _connected;

  void connect() {
    if (_closed) return;
    _reconnectTimer?.cancel();
    try {
      final channel = WebSocketChannel.connect(Uri.parse(url));
      _channel = channel;
      _subscription = channel.stream.listen(_onData, onError: (_) => _scheduleReconnect(), onDone: _scheduleReconnect, cancelOnError: true);
      _pingTimer?.cancel();
      _pingTimer = Timer.periodic(pingInterval, (_) => send({'type': 'ping'}));
    } catch (_) {
      _scheduleReconnect();
    }
  }

  void send(Map<String, dynamic> message) {
    try {
      _channel?.sink.add(jsonEncode(message));
    } catch (_) {
      // ignore: connection will be re-established by the reconnect loop
    }
  }

  void _onData(dynamic raw) {
    try {
      final decoded = jsonDecode(raw as String);
      if (decoded is Map<String, dynamic>) {
        final event = HubEvent.fromJson(decoded);
        if (event.type == HubEvent.hello) {
          _attempt = 0;
          _setConnected(true);
        }
        if (event.type != HubEvent.pong) _controller.add(event);
      }
    } catch (_) {
      // ignore malformed frames
    }
  }

  void _setConnected(bool value) {
    if (_connected == value) return;
    _connected = value;
    if (!_statusController.isClosed) _statusController.add(value);
  }

  void _scheduleReconnect() {
    _setConnected(false);
    _pingTimer?.cancel();
    if (_closed) return;
    _attempt += 1;
    final seconds = _attempt < 6 ? (1 << _attempt) : 60; // 2,4,8,16,32,60
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(Duration(seconds: seconds), connect);
  }

  Future<void> close() async {
    _closed = true;
    _pingTimer?.cancel();
    _reconnectTimer?.cancel();
    await _subscription?.cancel();
    await _channel?.sink.close();
    _setConnected(false);
    await _controller.close();
    await _statusController.close();
  }
}
