import 'device.dart' show parseHubDate;

class Room {
  const Room({required this.id, required this.homeId, required this.name, this.icon, this.sortOrder = 0, this.deviceCount = 0});

  final String id;
  final String homeId;
  final String name;
  final String? icon;
  final int sortOrder;
  final int deviceCount;

  factory Room.fromJson(Map<String, dynamic> json) => Room(
        id: json['id'] as String,
        homeId: (json['home_id'] as String?) ?? '',
        name: (json['name'] as String?) ?? '',
        icon: json['icon'] as String?,
        sortOrder: (json['sort_order'] as num?)?.toInt() ?? 0,
        deviceCount: (json['device_count'] as num?)?.toInt() ?? 0,
      );
}

class Home {
  const Home({
    required this.id,
    required this.name,
    this.lat,
    this.lon,
    this.address,
    this.securityMode = 'disarmed',
    this.alarmActive = false,
    this.role = 'member',
    this.rooms = const [],
    this.memberCount = 0,
    this.deviceCount = 0,
    this.createdAt,
  });

  final String id;
  final String name;
  final double? lat;
  final double? lon;
  final String? address;
  final String securityMode;
  final bool alarmActive;
  final String role;
  final List<Room> rooms;
  final int memberCount;
  final int deviceCount;
  final DateTime? createdAt;

  bool get canManage => role == 'owner' || role == 'admin';
  bool get isOwner => role == 'owner';

  factory Home.fromJson(Map<String, dynamic> json) => Home(
        id: json['id'] as String,
        name: (json['name'] as String?) ?? '',
        lat: (json['lat'] as num?)?.toDouble(),
        lon: (json['lon'] as num?)?.toDouble(),
        address: json['address'] as String?,
        securityMode: (json['security_mode'] as String?) ?? 'disarmed',
        alarmActive: json['alarm_active'] == true,
        role: (json['role'] as String?) ?? 'member',
        rooms: (json['rooms'] as List?)?.whereType<Map>().map((e) => Room.fromJson(Map<String, dynamic>.from(e))).toList() ?? const [],
        memberCount: (json['member_count'] as num?)?.toInt() ?? 0,
        deviceCount: (json['device_count'] as num?)?.toInt() ?? 0,
        createdAt: parseHubDate(json['created_at']),
      );

  Home copyWith({String? name, String? securityMode, bool? alarmActive, List<Room>? rooms}) => Home(
        id: id,
        name: name ?? this.name,
        lat: lat,
        lon: lon,
        address: address,
        securityMode: securityMode ?? this.securityMode,
        alarmActive: alarmActive ?? this.alarmActive,
        role: role,
        rooms: rooms ?? this.rooms,
        memberCount: memberCount,
        deviceCount: deviceCount,
        createdAt: createdAt,
      );
}

class Member {
  const Member({required this.userId, required this.email, required this.name, required this.role, this.avatarUrl, this.joinedAt});

  final String userId;
  final String email;
  final String name;
  final String role;
  final String? avatarUrl;
  final DateTime? joinedAt;

  factory Member.fromJson(Map<String, dynamic> json) => Member(
        userId: json['user_id'] as String,
        email: (json['email'] as String?) ?? '',
        name: (json['name'] as String?) ?? '',
        role: (json['role'] as String?) ?? 'member',
        avatarUrl: json['avatar_url'] as String?,
        joinedAt: parseHubDate(json['joined_at']),
      );
}

class Weather {
  const Weather({this.temperature, this.humidity, this.condition = 'unknown', this.icon = 'cloud', this.windKmh, this.available = false});

  final double? temperature;
  final double? humidity;
  final String condition;
  final String icon;
  final double? windKmh;
  final bool available;

  factory Weather.fromJson(Map<String, dynamic> json) => Weather(
        temperature: (json['temperature'] as num?)?.toDouble(),
        humidity: (json['humidity'] as num?)?.toDouble(),
        condition: (json['condition'] as String?) ?? 'unknown',
        icon: (json['icon'] as String?) ?? 'cloud',
        windKmh: (json['wind_kmh'] as num?)?.toDouble(),
        available: json['available'] == true,
      );
}

class Integration {
  const Integration({required this.id, required this.homeId, required this.brand, required this.key, required this.name, this.config = const {}, this.createdAt});

  final String id;
  final String homeId;
  final String brand;
  final String key;
  final String name;
  final Map<String, dynamic> config;
  final DateTime? createdAt;

  factory Integration.fromJson(Map<String, dynamic> json) => Integration(
        id: json['id'] as String,
        homeId: (json['home_id'] as String?) ?? '',
        brand: (json['brand'] as String?) ?? '',
        key: (json['key'] as String?) ?? '',
        name: (json['name'] as String?) ?? '',
        config: Map<String, dynamic>.from((json['config'] as Map?) ?? const {}),
        createdAt: parseHubDate(json['created_at']),
      );
}
