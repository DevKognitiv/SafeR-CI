import 'device.dart';

class SecurityState {
  const SecurityState({
    required this.homeId,
    required this.mode,
    this.alarmActive = false,
    this.alarmDeviceId,
    this.changedAt,
    this.panels = const [],
    this.zones = const [],
    this.sensors = const [],
  });

  final String homeId;
  final String mode;
  final bool alarmActive;
  final String? alarmDeviceId;
  final DateTime? changedAt;
  final List<Device> panels;
  final List<Device> zones;
  final List<Device> sensors;

  bool get isArmed => mode != 'disarmed';

  factory SecurityState.fromJson(Map<String, dynamic> json) => SecurityState(
        homeId: (json['home_id'] as String?) ?? '',
        mode: (json['mode'] as String?) ?? 'disarmed',
        alarmActive: json['alarm_active'] == true,
        alarmDeviceId: json['alarm_device_id'] as String?,
        changedAt: parseHubDate(json['changed_at']),
        panels: _devices(json['panels']),
        zones: _devices(json['zones']),
        sensors: _devices(json['sensors']),
      );

  SecurityState copyWith({String? mode, bool? alarmActive, String? alarmDeviceId}) => SecurityState(
        homeId: homeId,
        mode: mode ?? this.mode,
        alarmActive: alarmActive ?? this.alarmActive,
        alarmDeviceId: alarmDeviceId ?? this.alarmDeviceId,
        changedAt: changedAt,
        panels: panels,
        zones: zones,
        sensors: sensors,
      );

  static List<Device> _devices(dynamic list) =>
      (list as List?)?.whereType<Map>().map((e) => Device.fromJson(Map<String, dynamic>.from(e))).toList() ?? const [];
}

class SosAlert {
  const SosAlert({required this.id, required this.homeId, this.userId, this.lat, this.lon, this.note, this.status = 'open', this.forwarded = false, this.incidentId, this.createdAt});

  final String id;
  final String homeId;
  final String? userId;
  final double? lat;
  final double? lon;
  final String? note;
  final String status;
  final bool forwarded;
  final String? incidentId;
  final DateTime? createdAt;

  factory SosAlert.fromJson(Map<String, dynamic> json) => SosAlert(
        id: json['id'] as String,
        homeId: (json['home_id'] as String?) ?? '',
        userId: json['user_id'] as String?,
        lat: (json['lat'] as num?)?.toDouble(),
        lon: (json['lon'] as num?)?.toDouble(),
        note: json['note'] as String?,
        status: (json['status'] as String?) ?? 'open',
        forwarded: json['forwarded'] == true,
        incidentId: json['incident_id'] as String?,
        createdAt: parseHubDate(json['created_at']),
      );
}
