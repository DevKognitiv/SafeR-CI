import 'device.dart' show parseHubDate;

class User {
  const User({required this.id, required this.email, this.name = '', this.phone, this.locale = 'fr', this.avatarUrl, this.isAdmin = false, this.createdAt});

  final String id;
  final String email;
  final String name;
  final String? phone;
  final String locale;
  final String? avatarUrl;
  final bool isAdmin;
  final DateTime? createdAt;

  String get displayName => name.isNotEmpty ? name : email.split('@').first;
  String get initials {
    final source = displayName.trim();
    if (source.isEmpty) return '?';
    final parts = source.split(RegExp(r'\s+'));
    return parts.length >= 2 ? '${parts[0][0]}${parts[1][0]}'.toUpperCase() : source[0].toUpperCase();
  }

  factory User.fromJson(Map<String, dynamic> json) => User(
        id: json['id'] as String,
        email: (json['email'] as String?) ?? '',
        name: (json['name'] as String?) ?? '',
        phone: json['phone'] as String?,
        locale: (json['locale'] as String?) ?? 'fr',
        avatarUrl: json['avatar_url'] as String?,
        isAdmin: json['is_admin'] == true,
        createdAt: parseHubDate(json['created_at']),
      );
}

class AuthResult {
  const AuthResult({required this.token, required this.user});

  final String token;
  final User user;

  factory AuthResult.fromJson(Map<String, dynamic> json) =>
      AuthResult(token: json['token'] as String, user: User.fromJson(Map<String, dynamic>.from(json['user'] as Map)));
}
