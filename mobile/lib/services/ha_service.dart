import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:mqtt_client/mqtt_client.dart';
import 'package:mqtt_client/mqtt_server_client.dart';

/// Home Assistant MQTT bridge for the SafeR CI mobile app.
///
/// Connects to the HA MQTT broker, subscribes to the channels used by the
/// SafeR HA automations, and exposes a unified [Stream] of decoded payloads
/// the UI can listen to. Also publishes SOS pings to `safer/mobile/sos`.
class HomeAssistantService {
  static const String topicUpdates = 'safer/app/updates';
  static const String topicStatus = 'safer/app/status';
  static const String topicSos = 'safer/mobile/sos';

  final String host;
  final int port;
  final String clientId;
  final String? username;
  final String? password;

  MqttServerClient? _client;
  final StreamController<Map<String, dynamic>> _alertController =
      StreamController<Map<String, dynamic>>.broadcast();
  StreamSubscription<List<MqttReceivedMessage<MqttMessage>>>? _updatesSub;

  HomeAssistantService({
    required this.host,
    this.port = 1883,
    String? clientId,
    this.username,
    this.password,
  }) : clientId = clientId ?? 'safer-mobile-${DateTime.now().millisecondsSinceEpoch}';

  /// Stream of incoming messages from `safer/app/updates` and
  /// `safer/app/status`. Each event includes the raw `topic` and the parsed
  /// `payload` (JSON-decoded when possible, otherwise the raw string).
  Stream<Map<String, dynamic>> get alerts => _alertController.stream;

  bool get isConnected =>
      _client?.connectionStatus?.state == MqttConnectionState.connected;

  Future<void> connect() async {
    final client = MqttServerClient.withPort(host, clientId, port)
      ..logging(on: false)
      ..keepAlivePeriod = 30
      ..autoReconnect = true
      ..onDisconnected = _onDisconnected
      ..onConnected = _onConnected;

    final connMess = MqttConnectMessage()
        .withClientIdentifier(clientId)
        .withWillTopic('safer/app/status')
        .withWillMessage(jsonEncode({
          'client_id': clientId,
          'state': 'offline',
        }))
        .withWillQos(MqttQos.atLeastOnce)
        .startClean();
    client.connectionMessage = connMess;

    try {
      await client.connect(username, password);
    } on NoConnectionException catch (e) {
      client.disconnect();
      throw HomeAssistantException('MQTT connection failed: $e');
    } on SocketException catch (e) {
      client.disconnect();
      throw HomeAssistantException('MQTT socket error: $e');
    }

    if (client.connectionStatus?.state != MqttConnectionState.connected) {
      final state = client.connectionStatus?.state;
      client.disconnect();
      throw HomeAssistantException('MQTT not connected (state=$state)');
    }

    _client = client;
    client.subscribe(topicUpdates, MqttQos.atLeastOnce);
    client.subscribe(topicStatus, MqttQos.atLeastOnce);

    _updatesSub = client.updates?.listen(_onMessages);
  }

  void _onMessages(List<MqttReceivedMessage<MqttMessage>> events) {
    for (final event in events) {
      final recMess = event.payload as MqttPublishMessage;
      final raw = MqttPublishPayload.bytesToStringAsString(
        recMess.payload.message,
      );

      dynamic parsed;
      try {
        parsed = jsonDecode(raw);
      } catch (_) {
        parsed = raw;
      }

      _alertController.add({
        'topic': event.topic,
        'payload': parsed,
        'received_at': DateTime.now().toIso8601String(),
      });
    }
  }

  /// Publish an SOS event to `safer/mobile/sos`.
  Future<void> sendSOS(double lat, double lng, {Map<String, dynamic>? extra}) async {
    final client = _client;
    if (client == null || !isConnected) {
      throw HomeAssistantException('MQTT not connected; cannot send SOS');
    }
    final payload = <String, dynamic>{
      'lat': lat,
      'lng': lng,
      'client_id': clientId,
      'timestamp': DateTime.now().toUtc().toIso8601String(),
      if (extra != null) ...extra,
    };
    final builder = MqttClientPayloadBuilder()..addString(jsonEncode(payload));
    client.publishMessage(
      topicSos,
      MqttQos.atLeastOnce,
      builder.payload!,
      retain: false,
    );
  }

  Future<void> disconnect() async {
    await _updatesSub?.cancel();
    _updatesSub = null;
    _client?.disconnect();
    _client = null;
  }

  Future<void> dispose() async {
    await disconnect();
    await _alertController.close();
  }

  void _onConnected() {}
  void _onDisconnected() {}
}

class HomeAssistantException implements Exception {
  final String message;
  HomeAssistantException(this.message);
  @override
  String toString() => 'HomeAssistantException: $message';
}
