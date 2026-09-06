/// One controllable/readable property of a device (mirrors the hub's Capability).
class Capability {
  const Capability({
    required this.code,
    required this.type,
    this.writable = false,
    this.unit,
    this.min,
    this.max,
    this.step,
    this.values = const [],
    this.label,
  });

  final String code;
  final String type; // bool|int|float|enum|string|json|color
  final bool writable;
  final String? unit;
  final num? min;
  final num? max;
  final num? step;
  final List<String> values;
  final String? label;

  factory Capability.fromJson(Map<String, dynamic> json) => Capability(
        code: json['code'] as String,
        type: (json['type'] as String?) ?? 'string',
        writable: json['writable'] == true,
        unit: json['unit'] as String?,
        min: json['min'] as num?,
        max: json['max'] as num?,
        step: json['step'] as num?,
        values: (json['values'] as List?)?.map((e) => e.toString()).toList() ?? const [],
        label: json['label'] as String?,
      );

  Map<String, dynamic> toJson() => {
        'code': code,
        'type': type,
        'writable': writable,
        if (unit != null) 'unit': unit,
        if (min != null) 'min': min,
        if (max != null) 'max': max,
        if (step != null) 'step': step,
        if (values.isNotEmpty) 'values': values,
        if (label != null) 'label': label,
      };
}

/// Unified device (any brand).
class Device {
  const Device({
    required this.id,
    required this.homeId,
    required this.name,
    required this.brand,
    required this.protocol,
    required this.category,
    required this.externalId,
    this.roomId,
    this.integrationId,
    this.parentId,
    this.model,
    this.manufacturer,
    this.firmware,
    this.online = true,
    this.icon,
    this.capabilities = const [],
    this.state = const {},
    this.config = const {},
    this.createdAt,
    this.updatedAt,
    this.lastSeenAt,
  });

  final String id;
  final String homeId;
  final String? roomId;
  final String? integrationId;
  final String? parentId;
  final String name;
  final String brand;
  final String protocol;
  final String category;
  final String? model;
  final String? manufacturer;
  final String? firmware;
  final String externalId;
  final bool online;
  final String? icon;
  final List<Capability> capabilities;
  final Map<String, dynamic> state;
  final Map<String, dynamic> config;
  final DateTime? createdAt;
  final DateTime? updatedAt;
  final DateTime? lastSeenAt;

  factory Device.fromJson(Map<String, dynamic> json) => Device(
        id: json['id'] as String,
        homeId: json['home_id'] as String,
        roomId: json['room_id'] as String?,
        integrationId: json['integration_id'] as String?,
        parentId: json['parent_id'] as String?,
        name: (json['name'] as String?) ?? '',
        brand: (json['brand'] as String?) ?? 'generic',
        protocol: (json['protocol'] as String?) ?? '',
        category: (json['category'] as String?) ?? 'generic',
        model: json['model'] as String?,
        manufacturer: json['manufacturer'] as String?,
        firmware: json['firmware'] as String?,
        externalId: (json['external_id'] as String?) ?? '',
        online: json['online'] != false,
        icon: json['icon'] as String?,
        capabilities: (json['capabilities'] as List?)
                ?.whereType<Map>()
                .map((e) => Capability.fromJson(Map<String, dynamic>.from(e)))
                .toList() ??
            const [],
        state: Map<String, dynamic>.from((json['state'] as Map?) ?? const {}),
        config: Map<String, dynamic>.from((json['config'] as Map?) ?? const {}),
        createdAt: _date(json['created_at']),
        updatedAt: _date(json['updated_at']),
        lastSeenAt: _date(json['last_seen_at']),
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'home_id': homeId,
        'room_id': roomId,
        'integration_id': integrationId,
        'parent_id': parentId,
        'name': name,
        'brand': brand,
        'protocol': protocol,
        'category': category,
        'model': model,
        'manufacturer': manufacturer,
        'firmware': firmware,
        'external_id': externalId,
        'online': online,
        'icon': icon,
        'capabilities': capabilities.map((c) => c.toJson()).toList(),
        'state': state,
        'config': config,
        'created_at': createdAt?.toIso8601String(),
        'updated_at': updatedAt?.toIso8601String(),
        'last_seen_at': lastSeenAt?.toIso8601String(),
      };

  Device copyWith({
    String? name,
    String? roomId,
    bool clearRoom = false,
    bool? online,
    String? icon,
    Map<String, dynamic>? state,
    List<Capability>? capabilities,
    DateTime? lastSeenAt,
  }) =>
      Device(
        id: id,
        homeId: homeId,
        roomId: clearRoom ? null : (roomId ?? this.roomId),
        integrationId: integrationId,
        parentId: parentId,
        name: name ?? this.name,
        brand: brand,
        protocol: protocol,
        category: category,
        model: model,
        manufacturer: manufacturer,
        firmware: firmware,
        externalId: externalId,
        online: online ?? this.online,
        icon: icon ?? this.icon,
        capabilities: capabilities ?? this.capabilities,
        state: state ?? this.state,
        config: config,
        createdAt: createdAt,
        updatedAt: updatedAt,
        lastSeenAt: lastSeenAt ?? this.lastSeenAt,
      );

  /// Merge a partial state update (from a command or a WebSocket event).
  ///
  /// An `online: false` report is not a contact with the device: `lastSeenAt` keeps the last real
  /// sighting so the offline banner can show when the device was actually reachable.
  Device withState(Map<String, dynamic> partial, {bool? online}) => copyWith(
        state: {...state, ...partial},
        online: online,
        lastSeenAt: online == false ? lastSeenAt : DateTime.now(),
      );

  Capability? capability(String code) {
    for (final c in capabilities) {
      if (c.code == code) return c;
    }
    return null;
  }

  bool hasCapability(String code) => capability(code) != null;

  bool? boolValue(String code) {
    final v = state[code];
    if (v is bool) return v;
    if (v is num) return v != 0;
    if (v is String) return v == 'true' || v == 'on' || v == '1';
    return null;
  }

  num? numValue(String code) {
    final v = state[code];
    if (v is num) return v;
    if (v is String) return num.tryParse(v);
    return null;
  }

  String? stringValue(String code) {
    final v = state[code];
    return v?.toString();
  }

  /// Primary on/off code for quick toggles on tiles (switch, switch_1, locked, siren...).
  String? get primaryToggleCode {
    for (final code in const ['switch', 'switch_1', 'siren']) {
      final cap = capability(code);
      if (cap != null && cap.writable && cap.type == 'bool') return code;
    }
    return null;
  }

  bool get isOn => primaryToggleCode != null && (boolValue(primaryToggleCode!) ?? false);

  bool get isCamera => category == 'camera' || category == 'doorbell' || category == 'nvr';
  bool get isSensor => category.startsWith('sensor_');
  bool get isSecurity => category == 'alarm_panel' || category == 'alarm_zone' || category == 'lock' || category == 'siren';

  /// Short human summary of the current state for tiles ("On · 80%", "Fermé", "26.5 °C").
  String get stateSummary {
    switch (category) {
      case 'light':
        final on = boolValue('switch') ?? false;
        final b = numValue('brightness');
        return on ? (b != null ? 'ON · ${b.round()}%' : 'ON') : 'OFF';
      case 'switch':
      case 'plug':
      case 'siren':
        final code = primaryToggleCode;
        if (code == null) return '';
        final on = boolValue(code) ?? false;
        final p = numValue('power');
        return on ? (p != null ? 'ON · ${p.toStringAsFixed(0)} W' : 'ON') : 'OFF';
      case 'cover':
        final p = numValue('position');
        return p == null ? '' : '${p.round()}%';
      case 'thermostat':
        final t = numValue('temp_current');
        final s = numValue('temp_set');
        return [if (t != null) '${t.toStringAsFixed(1)} °C', if (s != null) '→ ${s.toStringAsFixed(1)} °C'].join(' ');
      case 'sensor_contact':
        return (boolValue('contact') ?? false) ? 'OUVERT' : 'FERMÉ';
      case 'sensor_motion':
        return (boolValue('motion') ?? false) ? 'MOUVEMENT' : 'CALME';
      case 'sensor_temperature':
        final t = numValue('temperature');
        final h = numValue('humidity');
        return [if (t != null) '${t.toStringAsFixed(1)} °C', if (h != null) '${h.round()}%'].join(' · ');
      case 'sensor_humidity':
        final h = numValue('humidity');
        return h == null ? '' : '${h.round()}%';
      case 'sensor_smoke':
        return (boolValue('smoke') ?? false) ? 'FUMÉE !' : 'OK';
      case 'sensor_water':
        return (boolValue('water_leak') ?? false) ? 'FUITE !' : 'OK';
      case 'sensor_gas':
        return (boolValue('gas') ?? false) ? 'GAZ !' : 'OK';
      case 'lock':
        return (boolValue('locked') ?? false) ? 'VERROUILLÉE' : 'OUVERTE';
      case 'alarm_panel':
        return (boolValue('alarm') ?? false) ? 'ALARME !' : (stringValue('arm_mode') ?? '').toUpperCase();
      case 'alarm_zone':
        return (boolValue('alarm') ?? false) ? 'ALARME !' : ((boolValue('open') ?? false) ? 'OUVERT' : 'OK');
      case 'camera':
      case 'doorbell':
      case 'nvr':
        return (boolValue('motion') ?? false) ? 'MOUVEMENT' : (online ? 'EN LIGNE' : 'HORS LIGNE');
      default:
        return online ? '' : 'HORS LIGNE';
    }
  }

  /// True when the device is in an "alert" state (used to highlight tiles).
  bool get isAlerting =>
      (boolValue('alarm') ?? false) ||
      (boolValue('smoke') ?? false) ||
      (boolValue('water_leak') ?? false) ||
      (boolValue('gas') ?? false) ||
      (boolValue('co') ?? false);
}

/// Notable event recorded by the hub (motion, contact, alarm...).
class DeviceEvent {
  const DeviceEvent({required this.id, required this.deviceId, required this.type, this.payload = const {}, this.createdAt});

  final String id;
  final String deviceId;
  final String type;
  final Map<String, dynamic> payload;
  final DateTime? createdAt;

  factory DeviceEvent.fromJson(Map<String, dynamic> json) => DeviceEvent(
        id: (json['id'] as String?) ?? '',
        deviceId: (json['device_id'] as String?) ?? '',
        type: (json['type'] as String?) ?? 'event',
        payload: Map<String, dynamic>.from((json['payload'] as Map?) ?? const {}),
        createdAt: _date(json['created_at']),
      );
}

/// How to play a camera stream.
class StreamInfo {
  const StreamInfo({required this.url, this.type = 'rtsp', this.headers = const {}, this.username, this.password});

  final String url;
  final String type;
  final Map<String, String> headers;
  final String? username;
  final String? password;

  factory StreamInfo.fromJson(Map<String, dynamic> json) => StreamInfo(
        url: json['url'] as String,
        type: (json['type'] as String?) ?? 'rtsp',
        headers: Map<String, String>.from((json['headers'] as Map?) ?? const {}),
        username: json['username'] as String?,
        password: json['password'] as String?,
      );

  /// URL with embedded credentials for players that cannot send auth headers.
  String get authenticatedUrl {
    if (username == null || username!.isEmpty) return url;
    final uri = Uri.tryParse(url);
    if (uri == null || uri.userInfo.isNotEmpty) return url;
    final user = Uri.encodeComponent(username!);
    final pass = Uri.encodeComponent(password ?? '');
    return uri.replace(userInfo: '$user:$pass').toString();
  }
}

DateTime? _date(dynamic value) {
  if (value == null) return null;
  if (value is DateTime) return value;
  final parsed = DateTime.tryParse(value.toString());
  if (parsed == null) return null;
  // The hub stores naive UTC timestamps; treat values without offset as UTC.
  return parsed.isUtc || value.toString().endsWith('Z') || value.toString().contains('+')
      ? parsed
      : DateTime.utc(parsed.year, parsed.month, parsed.day, parsed.hour, parsed.minute, parsed.second, parsed.millisecond);
}

/// Shared parser for ISO timestamps from the hub.
DateTime? parseHubDate(dynamic value) => _date(value);
