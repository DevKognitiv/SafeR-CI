/// Realtime event pushed by the hub over the WebSocket.
class HubEvent {
  const HubEvent({required this.type, this.homeId, this.deviceId, this.data = const {}});

  final String type;
  final String? homeId;
  final String? deviceId;
  final Map<String, dynamic> data;

  static const deviceState = 'device.state';
  static const deviceEvent = 'device.event';
  static const deviceAdded = 'device.added';
  static const deviceRemoved = 'device.removed';
  static const messageNew = 'message.new';
  static const securityMode = 'security.mode';
  static const securityAlarm = 'security.alarm';
  static const sceneRan = 'scene.ran';
  static const sosRaised = 'sos.raised';
  static const hello = 'hello';
  static const pong = 'pong';

  factory HubEvent.fromJson(Map<String, dynamic> json) => HubEvent(
        type: (json['type'] as String?) ?? 'unknown',
        homeId: json['home_id'] as String?,
        deviceId: json['device_id'] as String?,
        data: Map<String, dynamic>.from(json)..removeWhere((k, _) => k == 'type' || k == 'home_id' || k == 'device_id'),
      );

  Map<String, dynamic>? get state => (data['state'] as Map?)?.cast<String, dynamic>();
  bool? get online => data['online'] as bool?;
  String? get mode => data['mode'] as String?;
  bool? get active => data['active'] as bool?;
  Map<String, dynamic>? get message => (data['message'] as Map?)?.cast<String, dynamic>();
  Map<String, dynamic>? get device => (data['device'] as Map?)?.cast<String, dynamic>();
}
