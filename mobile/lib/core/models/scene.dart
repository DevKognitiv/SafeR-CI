import 'device.dart' show parseHubDate;

/// Action shared by scenes and automations (kept as a loose map to mirror the hub).
class SceneAction {
  const SceneAction(this.data);

  final Map<String, dynamic> data;

  String get type => (data['type'] as String?) ?? 'device_command';
  String? get deviceId => data['device_id'] as String?;
  String? get code => data['code'] as String?;
  dynamic get value => data['value'];
  num? get seconds => data['seconds'] as num?;
  String? get mode => data['mode'] as String?;
  String? get sceneId => data['scene_id'] as String?;
  String? get title => data['title'] as String?;
  String? get body => data['body'] as String?;

  static SceneAction deviceCommand(String deviceId, String code, dynamic value) =>
      SceneAction({'type': 'device_command', 'device_id': deviceId, 'code': code, 'value': value});
  static SceneAction delay(num seconds) => SceneAction({'type': 'delay', 'seconds': seconds});
  static SceneAction securityMode(String mode) => SceneAction({'type': 'security_mode', 'mode': mode});
  static SceneAction notify(String title, String body) => SceneAction({'type': 'notify', 'title': title, 'body': body});
  static SceneAction runScene(String sceneId) => SceneAction({'type': 'run_scene', 'scene_id': sceneId});

  Map<String, dynamic> toJson() => Map<String, dynamic>.from(data);
}

class Scene {
  const Scene({
    required this.id,
    required this.homeId,
    required this.name,
    this.icon,
    this.color,
    this.actions = const [],
    this.enabled = true,
    this.sortOrder = 0,
    this.lastRunAt,
  });

  final String id;
  final String homeId;
  final String name;
  final String? icon;
  final String? color;
  final List<SceneAction> actions;
  final bool enabled;
  final int sortOrder;
  final DateTime? lastRunAt;

  factory Scene.fromJson(Map<String, dynamic> json) => Scene(
        id: json['id'] as String,
        homeId: (json['home_id'] as String?) ?? '',
        name: (json['name'] as String?) ?? '',
        icon: json['icon'] as String?,
        color: json['color'] as String?,
        actions: (json['actions'] as List?)?.whereType<Map>().map((e) => SceneAction(Map<String, dynamic>.from(e))).toList() ?? const [],
        enabled: json['enabled'] != false,
        sortOrder: (json['sort_order'] as num?)?.toInt() ?? 0,
        lastRunAt: parseHubDate(json['last_run_at']),
      );

  Map<String, dynamic> toJson() => {
        'name': name,
        'icon': icon,
        'color': color,
        'actions': actions.map((a) => a.toJson()).toList(),
        'enabled': enabled,
      };
}
