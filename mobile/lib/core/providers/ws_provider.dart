import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/ws_client.dart';
import '../models/hub_event.dart';
import 'app_providers.dart';

/// True when the realtime socket should be open: enabled by the build
/// ([realtimeEnabledProvider], off in widget tests) and not switched off by
/// the user (Settings > "Alertes en temps réel"). While the preference is
/// still loading it counts as on, and `select` keeps the socket from being
/// re-created when the stored value turns out to be the default.
final realtimeActiveProvider = Provider<bool>((ref) {
  final userEnabled = ref.watch(realtimeAlertsProvider.select((pref) => pref.valueOrNull ?? true));
  return ref.watch(realtimeEnabledProvider) && userEnabled;
});

/// One realtime socket per home, kept alive while something listens to it.
final hubSocketProvider = Provider.family<HubSocket, String>((ref, homeId) {
  final client = ref.watch(hubClientProvider);
  final token = ref.watch(tokenProvider) ?? '';
  final socket = HubSocket(url: client.wsUrl(homeId, token));
  if (ref.watch(realtimeActiveProvider) && token.isNotEmpty) socket.connect();
  ref.onDispose(socket.close);
  return socket;
});

/// Stream of realtime events for a home.
final hubEventsProvider = StreamProvider.family<HubEvent, String>((ref, homeId) => ref.watch(hubSocketProvider(homeId)).events);

/// Connection status for the banner.
final hubConnectedProvider = StreamProvider.family<bool, String>((ref, homeId) => ref.watch(hubSocketProvider(homeId)).status);
