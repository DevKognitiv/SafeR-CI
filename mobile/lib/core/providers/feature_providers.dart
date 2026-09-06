import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/models.dart';
import 'app_providers.dart';
import 'homes_provider.dart';
import 'ws_provider.dart';

// ---------------------------------------------------------------- scenes
class ScenesNotifier extends FamilyAsyncNotifier<List<Scene>, String> {
  @override
  Future<List<Scene>> build(String arg) => ref.read(hubClientProvider).scenes(arg);

  Future<void> refresh() async => state = await AsyncValue.guard(() => ref.read(hubClientProvider).scenes(arg));

  Future<Scene> create(Map<String, dynamic> body) async {
    final scene = await ref.read(hubClientProvider).createScene(arg, body);
    await refresh();
    return scene;
  }

  Future<Scene> updateScene(String sceneId, Map<String, dynamic> body) async {
    final scene = await ref.read(hubClientProvider).updateScene(sceneId, body);
    await refresh();
    return scene;
  }

  Future<void> delete(String sceneId) async {
    await ref.read(hubClientProvider).deleteScene(sceneId);
    state = AsyncData((state.valueOrNull ?? const []).where((s) => s.id != sceneId).toList());
  }

  Future<Map<String, dynamic>> run(String sceneId) async {
    final result = await ref.read(hubClientProvider).runScene(sceneId);
    await refresh();
    return result;
  }
}

final scenesProvider = AsyncNotifierProvider.family<ScenesNotifier, List<Scene>, String>(ScenesNotifier.new);

// ---------------------------------------------------------------- automations
class AutomationsNotifier extends FamilyAsyncNotifier<List<Automation>, String> {
  @override
  Future<List<Automation>> build(String arg) => ref.read(hubClientProvider).automations(arg);

  Future<void> refresh() async => state = await AsyncValue.guard(() => ref.read(hubClientProvider).automations(arg));

  Future<Automation> create(Map<String, dynamic> body) async {
    final automation = await ref.read(hubClientProvider).createAutomation(arg, body);
    await refresh();
    return automation;
  }

  Future<Automation> updateAutomation(String id, Map<String, dynamic> body) async {
    final automation = await ref.read(hubClientProvider).updateAutomation(id, body);
    await refresh();
    return automation;
  }

  Future<void> delete(String id) async {
    await ref.read(hubClientProvider).deleteAutomation(id);
    state = AsyncData((state.valueOrNull ?? const []).where((a) => a.id != id).toList());
  }

  Future<void> setEnabled(String id, bool enabled) async {
    final updated = await ref.read(hubClientProvider).setAutomationEnabled(id, enabled);
    state = AsyncData([for (final a in state.valueOrNull ?? const <Automation>[]) a.id == id ? updated : a]);
  }

  Future<Map<String, dynamic>> trigger(String id) => ref.read(hubClientProvider).triggerAutomation(id);
}

final automationsProvider = AsyncNotifierProvider.family<AutomationsNotifier, List<Automation>, String>(AutomationsNotifier.new);

// ---------------------------------------------------------------- security
class SecurityNotifier extends FamilyAsyncNotifier<SecurityState, String> {
  @override
  Future<SecurityState> build(String arg) async {
    ref.listen<AsyncValue<HubEvent>>(hubEventsProvider(arg), (_, next) {
      final event = next.valueOrNull;
      if (event == null) return;
      final current = state.valueOrNull;
      if (event.type == HubEvent.securityMode && event.mode != null) {
        if (current != null) state = AsyncData(current.copyWith(mode: event.mode, alarmActive: event.mode == 'disarmed' ? false : null));
        ref.read(homesProvider.notifier).patch(arg, (h) => h.copyWith(securityMode: event.mode));
      } else if (event.type == HubEvent.securityAlarm) {
        final active = event.active ?? true;
        if (current != null) state = AsyncData(current.copyWith(alarmActive: active, alarmDeviceId: event.deviceId));
        ref.read(homesProvider.notifier).patch(arg, (h) => h.copyWith(alarmActive: active));
      } else if (event.type == HubEvent.deviceState || event.type == HubEvent.deviceAdded || event.type == HubEvent.deviceRemoved) {
        refresh();
      }
    });
    return ref.read(hubClientProvider).security(arg);
  }

  Future<void> refresh() async => state = await AsyncValue.guard(() => ref.read(hubClientProvider).security(arg));

  Future<void> setMode(String mode) async {
    final previous = state.valueOrNull;
    if (previous != null) state = AsyncData(previous.copyWith(mode: mode));
    try {
      state = AsyncData(await ref.read(hubClientProvider).setSecurityMode(arg, mode));
      ref.read(homesProvider.notifier).patch(arg, (h) => h.copyWith(securityMode: mode, alarmActive: mode == 'disarmed' ? false : null));
    } catch (_) {
      if (previous != null) state = AsyncData(previous);
      rethrow;
    }
  }

  Future<void> clearAlarm() async {
    state = AsyncData(await ref.read(hubClientProvider).clearAlarm(arg));
    ref.read(homesProvider.notifier).patch(arg, (h) => h.copyWith(alarmActive: false));
  }

  Future<SosAlert> raiseSos({double? lat, double? lon, String? note}) async {
    final alert = await ref.read(hubClientProvider).raiseSos(arg, lat: lat, lon: lon, note: note);
    await refresh();
    return alert;
  }
}

final securityProvider = AsyncNotifierProvider.family<SecurityNotifier, SecurityState, String>(SecurityNotifier.new);

// ---------------------------------------------------------------- messages
class MessagesNotifier extends FamilyAsyncNotifier<List<HubMessage>, String> {
  @override
  Future<List<HubMessage>> build(String arg) async {
    ref.listen<AsyncValue<HubEvent>>(hubEventsProvider(arg), (_, next) {
      final event = next.valueOrNull;
      if (event?.type == HubEvent.messageNew && event?.message != null) {
        final message = HubMessage.fromJson(event!.message!);
        final current = state.valueOrNull ?? const <HubMessage>[];
        if (!current.any((m) => m.id == message.id)) state = AsyncData([message, ...current]);
        ref.invalidate(unreadCountProvider(arg));
      }
    });
    return ref.read(hubClientProvider).messages(arg);
  }

  Future<void> refresh() async {
    state = await AsyncValue.guard(() => ref.read(hubClientProvider).messages(arg));
    ref.invalidate(unreadCountProvider(arg));
  }

  Future<void> markRead(String id) async {
    await ref.read(hubClientProvider).markRead(id);
    state = AsyncData([for (final m in state.valueOrNull ?? const <HubMessage>[]) m.id == id ? m.copyWith(read: true) : m]);
    ref.invalidate(unreadCountProvider(arg));
  }

  Future<void> markAllRead({String? kind}) async {
    await ref.read(hubClientProvider).markAllRead(arg, kind: kind);
    state = AsyncData([for (final m in state.valueOrNull ?? const <HubMessage>[]) (kind == null || m.kind == kind) ? m.copyWith(read: true) : m]);
    ref.invalidate(unreadCountProvider(arg));
  }

  Future<void> delete(String id) async {
    await ref.read(hubClientProvider).deleteMessage(id);
    state = AsyncData((state.valueOrNull ?? const <HubMessage>[]).where((m) => m.id != id).toList());
    ref.invalidate(unreadCountProvider(arg));
  }

  Future<void> clear({String? kind}) async {
    await ref.read(hubClientProvider).clearMessages(arg, kind: kind);
    await refresh();
  }
}

final messagesProvider = AsyncNotifierProvider.family<MessagesNotifier, List<HubMessage>, String>(MessagesNotifier.new);

final unreadCountProvider = FutureProvider.family<UnreadCount, String>((ref, homeId) => ref.read(hubClientProvider).unreadCount(homeId));

// ---------------------------------------------------------------- onboarding catalogue & weather
final brandsProvider = FutureProvider<List<BrandInfo>>((ref) => ref.read(hubClientProvider).brands());

final brandProvider = Provider.family<BrandInfo?, String>((ref, id) {
  for (final b in ref.watch(brandsProvider).valueOrNull ?? const <BrandInfo>[]) {
    if (b.id == id) return b;
  }
  return null;
});

final categoriesProvider = FutureProvider<List<CategoryGroup>>((ref) => ref.read(hubClientProvider).categories());

final weatherProvider = FutureProvider.family<Weather, String>((ref, homeId) => ref.read(hubClientProvider).weather(homeId));

final integrationsProvider = FutureProvider.family<List<Integration>, String>((ref, homeId) => ref.read(hubClientProvider).integrations(homeId));

final membersProvider = FutureProvider.family<List<Member>, String>((ref, homeId) => ref.read(hubClientProvider).members(homeId));

final deviceEventsProvider = FutureProvider.family<List<DeviceEvent>, String>((ref, deviceId) => ref.read(hubClientProvider).deviceEvents(deviceId));

final sosAlertsProvider = FutureProvider.family<List<SosAlert>, String>((ref, homeId) => ref.read(hubClientProvider).sosAlerts(homeId));
