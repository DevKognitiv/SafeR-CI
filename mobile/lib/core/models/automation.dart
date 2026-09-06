import 'device.dart' show parseHubDate;
import 'scene.dart';

/// Trigger or condition (loose map mirroring the hub schema).
class Rule {
  const Rule(this.data);

  final Map<String, dynamic> data;

  String get type => (data['type'] as String?) ?? 'device_state';
  String? get deviceId => data['device_id'] as String?;
  String? get code => data['code'] as String?;
  String get op => (data['op'] as String?) ?? 'eq';
  dynamic get value => data['value'];
  String? get time => data['time'] as String?;
  List<int> get days => (data['days'] as List?)?.map((e) => (e as num).toInt()).toList() ?? const [0, 1, 2, 3, 4, 5, 6];
  String? get mode => data['mode'] as String?;
  String? get start => data['start'] as String?;
  String? get end => data['end'] as String?;

  static Rule deviceState(String deviceId, String code, String op, dynamic value) =>
      Rule({'type': 'device_state', 'device_id': deviceId, 'code': code, 'op': op, 'value': value});
  static Rule schedule(String time, List<int> days) => Rule({'type': 'schedule', 'time': time, 'days': days});
  static Rule securityMode(String mode) => Rule({'type': 'security_mode', 'mode': mode});
  static Rule timeRange(String start, String end) => Rule({'type': 'time_range', 'start': start, 'end': end});

  Map<String, dynamic> toJson() => Map<String, dynamic>.from(data);
}

class Automation {
  const Automation({
    required this.id,
    required this.homeId,
    required this.name,
    this.enabled = true,
    this.match = 'all',
    this.triggers = const [],
    this.conditions = const [],
    this.actions = const [],
    this.lastTriggeredAt,
  });

  final String id;
  final String homeId;
  final String name;
  final bool enabled;
  final String match;
  final List<Rule> triggers;
  final List<Rule> conditions;
  final List<SceneAction> actions;
  final DateTime? lastTriggeredAt;

  factory Automation.fromJson(Map<String, dynamic> json) => Automation(
        id: json['id'] as String,
        homeId: (json['home_id'] as String?) ?? '',
        name: (json['name'] as String?) ?? '',
        enabled: json['enabled'] != false,
        match: (json['match'] as String?) ?? 'all',
        triggers: (json['triggers'] as List?)?.whereType<Map>().map((e) => Rule(Map<String, dynamic>.from(e))).toList() ?? const [],
        conditions: (json['conditions'] as List?)?.whereType<Map>().map((e) => Rule(Map<String, dynamic>.from(e))).toList() ?? const [],
        actions: (json['actions'] as List?)?.whereType<Map>().map((e) => SceneAction(Map<String, dynamic>.from(e))).toList() ?? const [],
        lastTriggeredAt: parseHubDate(json['last_triggered_at']),
      );

  Map<String, dynamic> toJson() => {
        'name': name,
        'enabled': enabled,
        'match': match,
        'triggers': triggers.map((t) => t.toJson()).toList(),
        'conditions': conditions.map((c) => c.toJson()).toList(),
        'actions': actions.map((a) => a.toJson()).toList(),
      };
}
