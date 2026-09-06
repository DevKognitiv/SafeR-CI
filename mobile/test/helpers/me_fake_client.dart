import 'package:safer_ci/core/api/api_exception.dart';
import 'package:safer_ci/core/models/models.dart';

import 'fake_hub_client.dart';

/// FakeHubClient with mutable homes/members/integrations for the Me tab
/// (the shared fake has no home update/delete, member role update nor
/// integration removal).
class MeFakeHubClient extends FakeHubClient {
  MeFakeHubClient({this.noHomes = false, this.role = 'owner'});

  /// When true, the user has no home at all.
  final bool noHomes;

  /// Role of the signed-in user in the demo home.
  final String role;

  late List<Home> homes_ = noHomes ? <Home>[] : [_withRole(demoHome)];
  final List<Integration> integrations_ = [
    Integration(id: 'int-1', homeId: FakeHubClient.homeId, brand: 'tuya', key: 'tuya_cloud:abc', name: 'Tuya Cloud (eu)', config: const {'region': 'eu'}, createdAt: DateTime.now().subtract(const Duration(days: 3))),
    Integration(id: 'int-2', homeId: FakeHubClient.homeId, brand: 'matter', key: 'matter:server', name: 'Serveur Matter', createdAt: DateTime.now().subtract(const Duration(hours: 5))),
  ];

  final List<String> deletedIntegrations = [];
  final List<({String userId, String role})> roleUpdates = [];
  final List<({String homeId, String? name, String? address})> homeUpdates = [];
  final List<String> deletedHomes = [];
  int homesCalls = 0;

  Home _withRole(Home h) => Home(
        id: h.id,
        name: h.name,
        lat: h.lat,
        lon: h.lon,
        address: h.address,
        securityMode: h.securityMode,
        alarmActive: h.alarmActive,
        role: role,
        rooms: h.rooms,
        memberCount: h.memberCount,
        deviceCount: h.deviceCount,
        createdAt: h.createdAt,
      );

  void _guard() {
    if (failNetwork) throw ApiException('Impossible de joindre le hub', status: null);
    if (!authenticated) throw ApiException('Not authenticated', status: 401);
  }

  @override
  Future<List<Home>> homes() async {
    _guard();
    homesCalls += 1;
    return List.of(homes_);
  }

  @override
  Future<Home> createHome({required String name, double? lat, double? lon, String? address, List<String> rooms = const []}) async {
    final home = await super.createHome(name: name, lat: lat, lon: lon, address: address, rooms: rooms);
    homes_ = [...homes_, home];
    return home;
  }

  @override
  Future<Home> updateHome(String homeId, {String? name, double? lat, double? lon, String? address}) async {
    _guard();
    homeUpdates.add((homeId: homeId, name: name, address: address));
    final index = homes_.indexWhere((h) => h.id == homeId);
    if (index < 0) throw ApiException('Home not found', status: 404);
    final old = homes_[index];
    final updated = Home(
      id: old.id,
      name: name ?? old.name,
      lat: lat ?? old.lat,
      lon: lon ?? old.lon,
      address: address ?? old.address,
      securityMode: old.securityMode,
      alarmActive: old.alarmActive,
      role: old.role,
      rooms: old.rooms,
      memberCount: old.memberCount,
      deviceCount: old.deviceCount,
      createdAt: old.createdAt,
    );
    homes_ = [for (final h in homes_) h.id == homeId ? updated : h];
    return updated;
  }

  @override
  Future<void> deleteHome(String homeId) async {
    _guard();
    deletedHomes.add(homeId);
    homes_ = homes_.where((h) => h.id != homeId).toList();
  }

  @override
  Future<Member> updateMember(String homeId, String userId, String role) async {
    _guard();
    roleUpdates.add((userId: userId, role: role));
    final members = await super.members(homeId);
    final current = members.firstWhere((m) => m.userId == userId, orElse: () => throw ApiException('Member not found', status: 404));
    return Member(userId: current.userId, email: current.email, name: current.name, role: role, joinedAt: current.joinedAt);
  }

  /// Extra messages (e.g. one linked to a device) merged with the shared demo messages.
  List<HubMessage> extraMessages = [];

  @override
  Future<List<HubMessage>> messages(String homeId, {String? kind, bool unreadOnly = false, int limit = 50}) async {
    final base = await super.messages(homeId, kind: kind, unreadOnly: unreadOnly, limit: limit);
    final extras = extraMessages.where((m) => (kind == null || m.kind == kind) && (!unreadOnly || !m.read));
    return [...extras, ...base];
  }

  @override
  Future<HubMessage> markRead(String messageId) async {
    final index = extraMessages.indexWhere((m) => m.id == messageId);
    if (index < 0) return super.markRead(messageId);
    extraMessages[index] = extraMessages[index].copyWith(read: true);
    return extraMessages[index];
  }

  @override
  Future<void> deleteMessage(String messageId) async {
    extraMessages.removeWhere((m) => m.id == messageId);
    return super.deleteMessage(messageId);
  }

  @override
  Future<List<Integration>> integrations(String homeId) async {
    _guard();
    return List.of(integrations_);
  }

  @override
  Future<void> deleteIntegration(String integrationId) async {
    _guard();
    deletedIntegrations.add(integrationId);
    integrations_.removeWhere((i) => i.id == integrationId);
  }
}
