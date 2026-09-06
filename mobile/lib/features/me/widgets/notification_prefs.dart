import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Preference key of the "realtime alerts" toggle (informational, kept on device).
const String kRealtimeAlertsPrefKey = 'safer.me.realtime_alerts';

/// Whether the app should surface realtime alerts (alarms, events) from the hub.
///
/// Stored in SharedPreferences; defaults to on.
class RealtimeAlertsNotifier extends AsyncNotifier<bool> {
  @override
  Future<bool> build() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(kRealtimeAlertsPrefKey) ?? true;
  }

  Future<void> set(bool enabled) async {
    state = AsyncData(enabled);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(kRealtimeAlertsPrefKey, enabled);
  }
}

final realtimeAlertsProvider = AsyncNotifierProvider<RealtimeAlertsNotifier, bool>(RealtimeAlertsNotifier.new);
