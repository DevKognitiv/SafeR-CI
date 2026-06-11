import 'dart:async';

import 'package:flutter/material.dart';

import '../services/ha_client.dart';
import '../services/ha_connection_settings.dart';
import '../widgets/entity_detail_sheet.dart';
import '../widgets/ha_entity_visuals.dart';
import 'ha_settings_sheet.dart';

/// Live Home Assistant dashboard.
///
/// Renders *every* visible entity HA exposes, grouped by area: known domains
/// get dedicated tiles and controls, unknown domains fall back to a generic
/// tile + attribute sheet, so any device from any protocol HA bridges
/// (Matter, Zigbee, Z-Wave, Thread, WiFi, BLE, KNX, MQTT, …) shows up.
///
/// Tap = the domain's primary action (toggle, open/close, lock/unlock,
/// play/pause, start/dock…). Long-press (or tap, for domains that need
/// richer input like alarms and thermostats) opens [EntityDetailSheet].
class HaDashboardScreen extends StatefulWidget {
  const HaDashboardScreen({super.key});

  @override
  State<HaDashboardScreen> createState() => _HaDashboardScreenState();
}

class _HaDashboardScreenState extends State<HaDashboardScreen> {
  HaClient? _client;
  StreamSubscription<Map<String, HaState>>? _statesSub;
  StreamSubscription<HaConnectionState>? _connSub;
  Map<String, HaState> _states = {};
  HaConnectionState _connection = HaConnectionState.disconnected;
  String? _connectionError;
  bool _connecting = false;
  HaConnectionSettings? _settings;

  @override
  void initState() {
    super.initState();
    _bootstrap();
  }

  @override
  void dispose() {
    _statesSub?.cancel();
    _connSub?.cancel();
    _client?.dispose();
    super.dispose();
  }

  Future<void> _bootstrap() async {
    final settings = await HaConnectionSettings.load();
    if (!settings.isComplete) {
      setState(() => _settings = settings);
      return;
    }
    await _connect(settings);
  }

  Future<void> _connect(HaConnectionSettings settings) async {
    setState(() {
      _connecting = true;
      _connectionError = null;
      _settings = settings;
    });
    final client = HaClient(
      wsUrl: settings.wsUrl,
      restBase: settings.restBase,
      token: settings.token,
    );
    _client = client;
    _connSub = client.connectionStates.listen((s) {
      if (!mounted) return;
      setState(() => _connection = s);
    });
    _statesSub = client.states.listen((s) {
      if (!mounted) return;
      setState(() => _states = s);
    });
    try {
      await client.connect();
      if (!mounted) return;
      setState(() {
        _states = client.currentStates;
        _connecting = false;
      });
    } catch (e) {
      if (!mounted) return;
      // autoReconnect keeps retrying in the background; surface the first
      // error so the user can fix settings if it's an auth problem.
      setState(() {
        _connecting = false;
        _connectionError = '$e';
      });
    }
  }

  Future<void> _teardownClient() async {
    await _statesSub?.cancel();
    await _connSub?.cancel();
    _statesSub = null;
    _connSub = null;
    await _client?.dispose();
    _client = null;
  }

  Future<void> _openSettings() async {
    final result = await showModalBottomSheet<HaConnectionSettings>(
      context: context,
      isScrollControlled: true,
      builder: (_) => HaSettingsSheet(
        initial:
            _settings ?? const HaConnectionSettings(baseUrl: '', token: ''),
      ),
    );
    if (result == null) return;
    await _teardownClient();
    await _connect(result);
  }

  /// Domains that need richer input than a tap (codes, temperatures,
  /// option lists), so tapping the tile opens the detail sheet instead of
  /// firing a service.
  static const Set<String> _detailFirstDomains = {
    'alarm_control_panel',
    'climate',
    'select',
    'input_select',
    'number',
    'input_number',
    'camera',
    'water_heater',
  };

  Future<void> _onTileTap(HaState entity) async {
    final client = _client;
    if (client == null) return;
    final domain = entity.domain;
    if (_detailFirstDomains.contains(domain) ||
        !client.isPrimaryActionable(domain)) {
      await EntityDetailSheet.show(context, client, entity.entityId);
      return;
    }
    try {
      await client.primaryAction(entity.entityId);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Command failed: $e')),
      );
    }
  }

  Future<void> _onTileLongPress(HaState entity) async {
    final client = _client;
    if (client == null) return;
    await EntityDetailSheet.show(context, client, entity.entityId);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF2F4F7),
      appBar: AppBar(
        backgroundColor: Colors.white,
        foregroundColor: Colors.black87,
        elevation: 0,
        leading: const Icon(Icons.menu),
        title: Row(
          children: [
            const Text('Home Assistant',
                style: TextStyle(fontWeight: FontWeight.w600)),
            const SizedBox(width: 8),
            _ConnectionDot(state: _connection),
          ],
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.settings_outlined),
            onPressed: _openSettings,
          ),
          const Icon(Icons.more_vert),
          const SizedBox(width: 8),
        ],
      ),
      body: Column(
        children: [
          if (_connection == HaConnectionState.reconnecting)
            const _ReconnectingBanner(),
          Expanded(child: _buildBody()),
        ],
      ),
    );
  }

  Widget _buildBody() {
    if (_settings == null || !_settings!.isComplete) {
      return _NoSettings(onOpen: _openSettings);
    }
    if (_connecting && _states.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_connectionError != null && _states.isEmpty) {
      return _ErrorState(
        error: _connectionError!,
        onRetry: () async {
          await _teardownClient();
          await _connect(_settings!);
        },
        onSettings: _openSettings,
      );
    }
    if (_states.isEmpty) {
      return const Center(child: Text('No entities available.'));
    }

    final client = _client!;
    final chips = _statusChips(_states);
    final byArea = _groupByArea(_states, client);

    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
      children: [
        if (chips.isNotEmpty) _ChipsRow(chips: chips),
        const SizedBox(height: 16),
        for (final entry in byArea.entries) ...[
          _AreaSection(
            area: entry.key,
            entities: entry.value,
            onTap: _onTileTap,
            onLongPress: _onTileLongPress,
          ),
          const SizedBox(height: 16),
        ],
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// Grouping & filtering
// ---------------------------------------------------------------------------

/// Housekeeping domains that never belong on a device dashboard. Everything
/// else renders — including domains this app has no special handling for.
const _excludedDomains = {
  'persistent_notification',
  'sun',
  'zone',
  'person', // surfaced in the chips row instead
  'device_tracker',
  'tts',
  'stt',
  'conversation',
  'update',
  'event',
  'tag',
  'todo',
  'calendar',
};

/// area-name → entities; "Other" bucket last. Diagnostic/config/hidden/
/// disabled entities are filtered through the entity registry.
Map<String, List<HaState>> _groupByArea(
  Map<String, HaState> states,
  HaClient client,
) {
  final out = <String, List<HaState>>{};
  for (final s in states.values) {
    if (_excludedDomains.contains(s.domain)) continue;
    if (!client.isVisible(s.entityId)) continue;
    final areaId = client.areaForEntity(s.entityId);
    final areaName = areaId != null ? client.areas[areaId]?.name : null;
    final bucket = areaName ?? 'Other';
    out.putIfAbsent(bucket, () => []).add(s);
  }
  final keys = out.keys.toList()
    ..sort((a, b) {
      if (a == 'Other') return 1;
      if (b == 'Other') return -1;
      return a.compareTo(b);
    });
  return {for (final k in keys) k: out[k]!..sort(_entityCompare)};
}

int _entityCompare(HaState a, HaState b) {
  final at = HaClient.primaryActionDomains.contains(a.domain) ? 0 : 1;
  final bt = HaClient.primaryActionDomains.contains(b.domain) ? 0 : 1;
  if (at != bt) return at - bt;
  return a.friendlyName.toLowerCase().compareTo(b.friendlyName.toLowerCase());
}

List<_ChipData> _statusChips(Map<String, HaState> states) {
  final chips = <_ChipData>[];

  HaState? firstByDeviceClass(String dc, String domain) {
    for (final s in states.values) {
      if (s.domain == domain && s.attributes['device_class'] == dc) return s;
    }
    return null;
  }

  final temp = firstByDeviceClass('temperature', 'sensor');
  if (temp != null && !temp.isUnavailable) {
    chips.add(_ChipData(
      icon: Icons.thermostat,
      color: Colors.redAccent,
      label: '${temp.state}${temp.unit ?? ''}',
    ));
  }
  final hum = firstByDeviceClass('humidity', 'sensor');
  if (hum != null && !hum.isUnavailable) {
    chips.add(_ChipData(
      icon: Icons.water_drop,
      color: Colors.blueAccent,
      label: '${hum.state}${hum.unit ?? ''}',
    ));
  }
  for (final s in states.values) {
    if (s.domain == 'alarm_control_panel') {
      chips.add(_ChipData(
        icon: Icons.shield,
        color: s.isOn ? Colors.red : Colors.green,
        label: s.state.replaceAll('_', ' '),
      ));
      break;
    }
  }
  for (final s in states.values) {
    if (s.domain == 'person') {
      chips.add(_ChipData(
        icon: Icons.person_pin_circle,
        color: Colors.grey,
        label: '${s.friendlyName}: ${s.state}',
      ));
      if (chips.length >= 6) break;
    }
  }
  return chips;
}

// ---------------------------------------------------------------------------
// UI primitives
// ---------------------------------------------------------------------------

class _ChipData {
  final IconData icon;
  final Color color;
  final String label;
  _ChipData({required this.icon, required this.color, required this.label});
}

class _ChipsRow extends StatelessWidget {
  final List<_ChipData> chips;
  const _ChipsRow({required this.chips});

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Row(
        children: [
          for (final c in chips) ...[
            _StatusChip(chip: c),
            const SizedBox(width: 8),
          ],
        ],
      ),
    );
  }
}

class _StatusChip extends StatelessWidget {
  final _ChipData chip;
  const _StatusChip({required this.chip});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(999),
        boxShadow: const [
          BoxShadow(color: Colors.black12, blurRadius: 2, offset: Offset(0, 1)),
        ],
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(chip.icon, size: 16, color: chip.color),
          const SizedBox(width: 6),
          Text(chip.label, style: const TextStyle(fontWeight: FontWeight.w500)),
        ],
      ),
    );
  }
}

class _AreaSection extends StatelessWidget {
  final String area;
  final List<HaState> entities;
  final Future<void> Function(HaState) onTap;
  final Future<void> Function(HaState) onLongPress;
  const _AreaSection({
    required this.area,
    required this.entities,
    required this.onTap,
    required this.onLongPress,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 6),
          child: Row(
            children: [
              Icon(_areaIcon(area), size: 18, color: Colors.black54),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  area,
                  style: const TextStyle(
                      fontSize: 16, fontWeight: FontWeight.w600),
                ),
              ),
              Text('${entities.length}',
                  style: const TextStyle(color: Colors.black45, fontSize: 12)),
            ],
          ),
        ),
        GridView.count(
          crossAxisCount: 2,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          childAspectRatio: 2.6,
          crossAxisSpacing: 12,
          mainAxisSpacing: 12,
          children: [
            for (final e in entities)
              _EntityTile(
                entity: e,
                onTap: () => onTap(e),
                onLongPress: () => onLongPress(e),
              ),
          ],
        ),
      ],
    );
  }
}

class _EntityTile extends StatelessWidget {
  final HaState entity;
  final VoidCallback onTap;
  final VoidCallback onLongPress;
  const _EntityTile({
    required this.entity,
    required this.onTap,
    required this.onLongPress,
  });

  @override
  Widget build(BuildContext context) {
    final accent = haDomainColor(entity.domain);
    final on = entity.isOn;
    final unavailable = entity.isUnavailable;
    return Opacity(
      opacity: unavailable ? 0.45 : 1,
      child: Material(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        elevation: 0,
        child: InkWell(
          onTap: unavailable ? null : onTap,
          onLongPress: onLongPress,
          borderRadius: BorderRadius.circular(14),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(14),
              boxShadow: const [
                BoxShadow(
                    color: Colors.black12, blurRadius: 2, offset: Offset(0, 1)),
              ],
            ),
            child: Row(
              children: [
                Container(
                  width: 36,
                  height: 36,
                  decoration: BoxDecoration(
                    color: on ? accent.withOpacity(0.18) : Colors.black12,
                    shape: BoxShape.circle,
                  ),
                  child: Icon(haDomainIcon(entity.domain),
                      size: 18, color: on ? accent : Colors.black45),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Text(entity.friendlyName,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontWeight: FontWeight.w600)),
                      Text(haStateLabel(entity),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                              color: Colors.black54, fontSize: 12)),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _ConnectionDot extends StatelessWidget {
  final HaConnectionState state;
  const _ConnectionDot({required this.state});

  @override
  Widget build(BuildContext context) {
    final color = switch (state) {
      HaConnectionState.connected => Colors.green,
      HaConnectionState.reconnecting => Colors.orange,
      HaConnectionState.connecting => Colors.orange,
      HaConnectionState.disconnected => Colors.grey,
    };
    return Container(
      width: 8,
      height: 8,
      decoration: BoxDecoration(color: color, shape: BoxShape.circle),
    );
  }
}

class _ReconnectingBanner extends StatelessWidget {
  const _ReconnectingBanner();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      color: Colors.orange.shade700,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      child: const Row(
        children: [
          SizedBox(
            width: 12,
            height: 12,
            child: CircularProgressIndicator(
                strokeWidth: 2, color: Colors.white),
          ),
          SizedBox(width: 10),
          Text('Reconnecting to Home Assistant…',
              style: TextStyle(color: Colors.white, fontSize: 12)),
        ],
      ),
    );
  }
}

class _NoSettings extends StatelessWidget {
  final VoidCallback onOpen;
  const _NoSettings({required this.onOpen});
  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.settings_remote, size: 64, color: Colors.black26),
            const SizedBox(height: 12),
            const Text('No Home Assistant configured',
                style: TextStyle(fontSize: 16)),
            const SizedBox(height: 16),
            FilledButton(onPressed: onOpen, child: const Text('Configure HA')),
          ],
        ),
      ),
    );
  }
}

class _ErrorState extends StatelessWidget {
  final String error;
  final VoidCallback onRetry;
  final VoidCallback onSettings;
  const _ErrorState({
    required this.error,
    required this.onRetry,
    required this.onSettings,
  });

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline, size: 56, color: Colors.redAccent),
            const SizedBox(height: 12),
            Text(error,
                textAlign: TextAlign.center,
                style: const TextStyle(color: Colors.black54)),
            const SizedBox(height: 16),
            Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                OutlinedButton(
                  onPressed: onSettings,
                  child: const Text('Settings'),
                ),
                const SizedBox(width: 12),
                FilledButton(onPressed: onRetry, child: const Text('Retry')),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

IconData _areaIcon(String name) {
  final n = name.toLowerCase();
  if (n.contains('living')) return Icons.weekend;
  if (n.contains('kitchen')) return Icons.kitchen;
  if (n.contains('bed')) return Icons.king_bed;
  if (n.contains('bath')) return Icons.bathtub;
  if (n.contains('garage')) return Icons.garage;
  if (n.contains('office')) return Icons.work;
  if (n.contains('outside') || n.contains('garden')) return Icons.park;
  return Icons.home;
}
