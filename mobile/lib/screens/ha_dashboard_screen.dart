import 'dart:async';

import 'package:flutter/material.dart';

import '../services/ha_client.dart';
import '../services/ha_connection_settings.dart';
import 'ha_settings_sheet.dart';

/// Live Home Assistant dashboard.
///
/// Loads connection settings from [HaConnectionSettings], opens a HA
/// WebSocket via [HaClient], and renders a status-chip + per-area
/// dashboard against real HA entities. Tapping a tile toggles the
/// underlying entity via `call_service`.
class HaDashboardScreen extends StatefulWidget {
  const HaDashboardScreen({super.key});

  @override
  State<HaDashboardScreen> createState() => _HaDashboardScreenState();
}

class _HaDashboardScreenState extends State<HaDashboardScreen> {
  HaClient? _client;
  StreamSubscription<Map<String, HaState>>? _sub;
  Map<String, HaState> _states = {};
  Map<String, HaArea> _areas = {};
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
    _sub?.cancel();
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
    final client = HaClient(wsUrl: settings.wsUrl, token: settings.token);
    try {
      await client.connect();
      _client = client;
      _states = client.currentStates;
      _areas = client.areas;
      _sub = client.states.listen((s) {
        if (!mounted) return;
        setState(() => _states = s);
      });
      setState(() => _connecting = false);
    } catch (e) {
      await client.dispose();
      if (!mounted) return;
      setState(() {
        _connecting = false;
        _connectionError = '$e';
      });
    }
  }

  Future<void> _openSettings() async {
    final result = await showModalBottomSheet<HaConnectionSettings>(
      context: context,
      isScrollControlled: true,
      builder: (_) => HaSettingsSheet(
        initial: _settings ?? const HaConnectionSettings(baseUrl: '', token: ''),
      ),
    );
    if (result == null) return;
    await _sub?.cancel();
    await _client?.dispose();
    _client = null;
    await _connect(result);
  }

  Future<void> _onTileTap(HaState entity) async {
    final client = _client;
    if (client == null) return;
    if (!_isToggleable(entity.domain)) return;
    try {
      await client.toggle(entity.entityId);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Toggle failed: $e')),
      );
    }
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
            _ConnectionDot(connected: _client?.isConnected ?? false),
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
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_settings == null || !_settings!.isComplete) {
      return _NoSettings(onOpen: _openSettings);
    }
    if (_connecting) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_connectionError != null) {
      return _ErrorState(
        error: _connectionError!,
        onRetry: () => _connect(_settings!),
        onSettings: _openSettings,
      );
    }
    if (_states.isEmpty) {
      return const Center(child: Text('No entities available.'));
    }

    final chips = _statusChips(_states);
    final byArea = _groupByArea(_states, _areas, _client!);

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
            isToggleable: _isToggleable,
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

/// Domains we surface on the dashboard. Keeps the noise down (HA exposes
/// dozens of housekeeping entities like `sensor.last_boot` we don't want).
const _renderableDomains = {
  'light',
  'switch',
  'cover',
  'climate',
  'media_player',
  'fan',
  'lock',
  'binary_sensor',
  'sensor',
  'vacuum',
};

const _toggleableDomains = {
  'light',
  'switch',
  'fan',
  'media_player',
  'cover',
  'lock',
};

bool _isToggleable(String domain) => _toggleableDomains.contains(domain);

/// Returns area-name → entities, plus an "Other" bucket for entities with no
/// area. Areas with zero renderable entities are skipped.
Map<String, List<HaState>> _groupByArea(
  Map<String, HaState> states,
  Map<String, HaArea> areas,
  HaClient client,
) {
  final out = <String, List<HaState>>{};
  for (final s in states.values) {
    if (!_renderableDomains.contains(s.domain)) continue;
    if (s.domain == 'sensor' && _isNoisySensor(s)) continue;
    final areaId = client.areaForEntity(s.entityId);
    final areaName = areaId != null ? areas[areaId]?.name : null;
    final bucket = areaName ?? 'Other';
    out.putIfAbsent(bucket, () => []).add(s);
  }
  // Stable sort: real areas first (by name), "Other" last.
  final keys = out.keys.toList()
    ..sort((a, b) {
      if (a == 'Other') return 1;
      if (b == 'Other') return -1;
      return a.compareTo(b);
    });
  return {for (final k in keys) k: out[k]!..sort(_entityCompare)};
}

int _entityCompare(HaState a, HaState b) {
  // Toggleable first, then alphabetic.
  final at = _toggleableDomains.contains(a.domain) ? 0 : 1;
  final bt = _toggleableDomains.contains(b.domain) ? 0 : 1;
  if (at != bt) return at - bt;
  return a.friendlyName.toLowerCase().compareTo(b.friendlyName.toLowerCase());
}

bool _isNoisySensor(HaState s) {
  // Skip diagnostic / housekeeping sensors that flood the dashboard.
  const skipUnits = {'°', null, ''};
  if (s.attributes['device_class'] == null && skipUnits.contains(s.unit)) {
    return true;
  }
  return false;
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
  if (temp != null) {
    chips.add(_ChipData(
      icon: Icons.thermostat,
      color: Colors.redAccent,
      label: '${temp.state}${temp.unit ?? ''}',
    ));
  }
  final hum = firstByDeviceClass('humidity', 'sensor');
  if (hum != null) {
    chips.add(_ChipData(
      icon: Icons.water_drop,
      color: Colors.blueAccent,
      label: '${hum.state}${hum.unit ?? ''}',
    ));
  }
  for (final s in states.values) {
    if (s.domain == 'person') {
      chips.add(_ChipData(
        icon: Icons.person_pin_circle,
        color: Colors.grey,
        label: '${s.friendlyName}: ${s.state}',
      ));
      if (chips.length >= 4) break;
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
  final bool Function(String) isToggleable;
  const _AreaSection({
    required this.area,
    required this.entities,
    required this.onTap,
    required this.isToggleable,
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
                onTap: isToggleable(e.domain) ? () => onTap(e) : null,
              ),
          ],
        ),
      ],
    );
  }
}

class _EntityTile extends StatelessWidget {
  final HaState entity;
  final VoidCallback? onTap;
  const _EntityTile({required this.entity, this.onTap});

  @override
  Widget build(BuildContext context) {
    final accent = _domainColor(entity.domain);
    final on = entity.isOn;
    return Material(
      color: Colors.white,
      borderRadius: BorderRadius.circular(14),
      elevation: 0,
      child: InkWell(
        onTap: onTap,
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
                child: Icon(_domainIcon(entity.domain),
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
                    Text(_stateLabel(entity),
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
    );
  }
}

class _ConnectionDot extends StatelessWidget {
  final bool connected;
  const _ConnectionDot({required this.connected});
  @override
  Widget build(BuildContext context) {
    return Container(
      width: 8,
      height: 8,
      decoration: BoxDecoration(
        color: connected ? Colors.amber : Colors.grey,
        shape: BoxShape.circle,
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

// ---------------------------------------------------------------------------
// Domain → icon / color / label
// ---------------------------------------------------------------------------

IconData _domainIcon(String domain) {
  switch (domain) {
    case 'light':
      return Icons.lightbulb;
    case 'switch':
      return Icons.toggle_on;
    case 'cover':
      return Icons.blinds;
    case 'climate':
      return Icons.thermostat;
    case 'media_player':
      return Icons.speaker;
    case 'fan':
      return Icons.air;
    case 'lock':
      return Icons.lock;
    case 'binary_sensor':
      return Icons.sensors;
    case 'sensor':
      return Icons.show_chart;
    case 'vacuum':
      return Icons.cleaning_services;
    default:
      return Icons.circle;
  }
}

Color _domainColor(String domain) {
  switch (domain) {
    case 'light':
      return Colors.amber;
    case 'switch':
    case 'fan':
      return Colors.blueAccent;
    case 'cover':
      return Colors.purple;
    case 'climate':
      return Colors.redAccent;
    case 'media_player':
      return Colors.deepPurple;
    case 'lock':
      return Colors.brown;
    case 'binary_sensor':
    case 'sensor':
      return Colors.green;
    case 'vacuum':
      return Colors.teal;
    default:
      return Colors.indigo;
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

String _stateLabel(HaState e) {
  final unit = e.unit;
  if (e.domain == 'light' && e.isOn && e.brightness != null) {
    final pct = (e.brightness! / 255 * 100).round();
    return '$pct%';
  }
  if (unit != null && unit.isNotEmpty) return '${e.state} $unit';
  return e.state;
}
