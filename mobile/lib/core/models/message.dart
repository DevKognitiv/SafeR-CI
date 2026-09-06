import 'device.dart' show parseHubDate;

/// Message-center entry (kind: alarm | home | notice).
class HubMessage {
  const HubMessage({
    required this.id,
    required this.homeId,
    required this.kind,
    required this.title,
    this.body = '',
    this.deviceId,
    this.severity = 'info',
    this.read = false,
    this.createdAt,
  });

  final String id;
  final String homeId;
  final String kind;
  final String title;
  final String body;
  final String? deviceId;
  final String severity;
  final bool read;
  final DateTime? createdAt;

  factory HubMessage.fromJson(Map<String, dynamic> json) => HubMessage(
        id: json['id'] as String,
        homeId: (json['home_id'] as String?) ?? '',
        kind: (json['kind'] as String?) ?? 'notice',
        title: (json['title'] as String?) ?? '',
        body: (json['body'] as String?) ?? '',
        deviceId: json['device_id'] as String?,
        severity: (json['severity'] as String?) ?? 'info',
        read: json['read'] == true,
        createdAt: parseHubDate(json['created_at']),
      );

  HubMessage copyWith({bool? read}) => HubMessage(
        id: id,
        homeId: homeId,
        kind: kind,
        title: title,
        body: body,
        deviceId: deviceId,
        severity: severity,
        read: read ?? this.read,
        createdAt: createdAt,
      );
}

class UnreadCount {
  const UnreadCount({this.total = 0, this.alarm = 0, this.home = 0, this.notice = 0});

  final int total;
  final int alarm;
  final int home;
  final int notice;

  factory UnreadCount.fromJson(Map<String, dynamic> json) => UnreadCount(
        total: (json['total'] as num?)?.toInt() ?? 0,
        alarm: (json['alarm'] as num?)?.toInt() ?? 0,
        home: (json['home'] as num?)?.toInt() ?? 0,
        notice: (json['notice'] as num?)?.toInt() ?? 0,
      );
}
