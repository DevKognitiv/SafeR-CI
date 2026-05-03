import 'dart:async';

import 'package:flutter/material.dart';

import '../services/ha_service.dart';

/// Home Assistant-style dashboard, mirroring the HA demo app layout
/// (status chips, rooms with entity tiles, energy panel) but driven by the
/// SafeR MQTT topics `safer/app/status` (full snapshot) and
/// `safer/app/updates` (live notifications).
///
/// Expected JSON shape on `safer/app/status`:
/// ```jsonc
/// {
///   "state": "online",
///   "chips": [{"icon":"thermometer","label":"10.5"}, ...],
///   "rooms": [{
///     "name":"Living Room","temperature":22.8,"humidity":57,
///     "entities":[{"name":"Floor lamp","icon":"lamp","state":"70%","on":true}, ...]
///   }],
///   "energy": {"title":"Energy","tiles":[{"name":"EV","icon":"car","state":"Unplugged"}, ...]}
/// }
/// ```
class HaDashboardScreen extends StatefulWidget {
  final HomeAssistantService haService;
  const HaDashboardScreen({super.key, required this.haService});

  @override
  State<HaDashboardScreen> createState() => _HaDashboardScreenState();
}

class _HaDashboardScreenState extends State<HaDashboardScreen> {
  StreamSubscription<Map<String, dynamic>>? _sub;
  HaStatus _status = const HaStatus.empty();
  final List<HaUpdate> _updates = [];
  HaUpdate? _toast;
  Timer? _toastTimer;

  int get _unreadCount => _updates.where((u) => !u.read).length;

  @override
  void initState() {
    super.initState();
    _sub = widget.haService.alerts.listen(_onMessage);
  }

  @override
  void dispose() {
    _sub?.cancel();
    _toastTimer?.cancel();
    super.dispose();
  }

  void _onMessage(Map<String, dynamic> event) {
    if (!mounted) return;
    final topic = event['topic'] as String?;
    final payload = event['payload'];
    if (topic == HomeAssistantService.topicStatus && payload is Map) {
      setState(() => _status = HaStatus.fromJson(payload.cast<String, dynamic>()));
    } else if (topic == HomeAssistantService.topicUpdates && payload is Map) {
      final update = HaUpdate.fromJson(payload.cast<String, dynamic>());
      setState(() {
        _updates.insert(0, update);
        _toast = update;
      });
      _toastTimer?.cancel();
      _toastTimer = Timer(const Duration(seconds: 6), () {
        if (mounted) setState(() => _toast = null);
      });
    }
  }

  void _openNotifications() {
    setState(() {
      for (final u in _updates) {
        u.read = true;
      }
    });
    showModalBottomSheet<void>(
      context: context,
      builder: (_) => _NotificationsPanel(updates: _updates),
    );
  }

  @override
  Widget build(BuildContext context) {
    final bg = const Color(0xFFF2F4F7);
    return Scaffold(
      backgroundColor: bg,
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
            if (widget.haService.isConnected)
              Container(
                width: 8,
                height: 8,
                decoration: const BoxDecoration(
                  color: Colors.amber,
                  shape: BoxShape.circle,
                ),
              ),
          ],
        ),
        actions: [
          Stack(
            alignment: Alignment.center,
            children: [
              IconButton(
                icon: const Icon(Icons.notifications_none),
                onPressed: _openNotifications,
              ),
              if (_unreadCount > 0)
                Positioned(
                  top: 10,
                  right: 10,
                  child: Container(
                    padding: const EdgeInsets.all(2),
                    decoration: const BoxDecoration(
                      color: Colors.redAccent,
                      shape: BoxShape.circle,
                    ),
                    constraints: const BoxConstraints(minWidth: 14, minHeight: 14),
                    child: Text(
                      '$_unreadCount',
                      style: const TextStyle(color: Colors.white, fontSize: 9),
                      textAlign: TextAlign.center,
                    ),
                  ),
                ),
            ],
          ),
          const Icon(Icons.more_vert),
          const SizedBox(width: 8),
        ],
      ),
      body: Stack(
        children: [
          ListView(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
            children: [
              if (_status.chips.isNotEmpty) _ChipsRow(chips: _status.chips),
              const SizedBox(height: 16),
              for (final room in _status.rooms) ...[
                _RoomSection(room: room),
                const SizedBox(height: 16),
              ],
              if (_status.energy != null) _EnergySection(energy: _status.energy!),
              if (_status.rooms.isEmpty &&
                  _status.chips.isEmpty &&
                  _status.energy == null)
                const _EmptyState(),
            ],
          ),
          if (_toast != null)
            Positioned(
              left: 12,
              right: 12,
              top: 12,
              child: _ToastBanner(
                update: _toast!,
                onDismiss: () => setState(() => _toast = null),
              ),
            ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Models
// ---------------------------------------------------------------------------

class HaStatus {
  final String state;
  final List<HaChip> chips;
  final List<HaRoom> rooms;
  final HaEnergy? energy;

  const HaStatus({
    required this.state,
    required this.chips,
    required this.rooms,
    required this.energy,
  });

  const HaStatus.empty()
      : state = 'unknown',
        chips = const [],
        rooms = const [],
        energy = null;

  factory HaStatus.fromJson(Map<String, dynamic> json) {
    return HaStatus(
      state: json['state']?.toString() ?? 'unknown',
      chips: (json['chips'] as List? ?? const [])
          .whereType<Map>()
          .map((e) => HaChip.fromJson(e.cast<String, dynamic>()))
          .toList(),
      rooms: (json['rooms'] as List? ?? const [])
          .whereType<Map>()
          .map((e) => HaRoom.fromJson(e.cast<String, dynamic>()))
          .toList(),
      energy: json['energy'] is Map
          ? HaEnergy.fromJson((json['energy'] as Map).cast<String, dynamic>())
          : null,
    );
  }
}

class HaChip {
  final String icon;
  final String label;
  const HaChip({required this.icon, required this.label});
  factory HaChip.fromJson(Map<String, dynamic> j) => HaChip(
        icon: j['icon']?.toString() ?? 'info',
        label: j['label']?.toString() ?? '',
      );
}

class HaRoom {
  final String name;
  final double? temperature;
  final double? humidity;
  final List<HaEntity> entities;

  const HaRoom({
    required this.name,
    required this.temperature,
    required this.humidity,
    required this.entities,
  });

  factory HaRoom.fromJson(Map<String, dynamic> j) => HaRoom(
        name: j['name']?.toString() ?? 'Room',
        temperature: (j['temperature'] as num?)?.toDouble(),
        humidity: (j['humidity'] as num?)?.toDouble(),
        entities: (j['entities'] as List? ?? const [])
            .whereType<Map>()
            .map((e) => HaEntity.fromJson(e.cast<String, dynamic>()))
            .toList(),
      );
}

class HaEntity {
  final String name;
  final String icon;
  final String state;
  final bool isOn;

  const HaEntity({
    required this.name,
    required this.icon,
    required this.state,
    required this.isOn,
  });

  factory HaEntity.fromJson(Map<String, dynamic> j) => HaEntity(
        name: j['name']?.toString() ?? '—',
        icon: j['icon']?.toString() ?? 'lightbulb',
        state: j['state']?.toString() ?? '',
        isOn: j['on'] == true,
      );
}

class HaEnergy {
  final String title;
  final List<HaEntity> tiles;
  const HaEnergy({required this.title, required this.tiles});
  factory HaEnergy.fromJson(Map<String, dynamic> j) => HaEnergy(
        title: j['title']?.toString() ?? 'Energy',
        tiles: (j['tiles'] as List? ?? const [])
            .whereType<Map>()
            .map((e) => HaEntity.fromJson(e.cast<String, dynamic>()))
            .toList(),
      );
}

class HaUpdate {
  final String title;
  final String body;
  final String severity;
  final DateTime receivedAt;
  bool read;

  HaUpdate({
    required this.title,
    required this.body,
    required this.severity,
    required this.receivedAt,
    this.read = false,
  });

  factory HaUpdate.fromJson(Map<String, dynamic> j) => HaUpdate(
        title: j['title']?.toString() ?? 'Notification',
        body: j['body']?.toString() ?? j['message']?.toString() ?? '',
        severity: j['severity']?.toString() ?? 'info',
        receivedAt: DateTime.tryParse(j['timestamp']?.toString() ?? '') ??
            DateTime.now(),
      );
}

// ---------------------------------------------------------------------------
// UI primitives
// ---------------------------------------------------------------------------

class _ChipsRow extends StatelessWidget {
  final List<HaChip> chips;
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
  final HaChip chip;
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
          Icon(_iconFor(chip.icon), size: 16, color: _colorFor(chip.icon)),
          const SizedBox(width: 6),
          Text(chip.label, style: const TextStyle(fontWeight: FontWeight.w500)),
        ],
      ),
    );
  }
}

class _RoomSection extends StatelessWidget {
  final HaRoom room;
  const _RoomSection({required this.room});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 6),
          child: Row(
            children: [
              const Icon(Icons.weekend, size: 18, color: Colors.black54),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  room.name,
                  style: const TextStyle(
                      fontSize: 16, fontWeight: FontWeight.w600),
                ),
              ),
              if (room.temperature != null) ...[
                const Icon(Icons.thermostat, size: 14, color: Colors.redAccent),
                const SizedBox(width: 2),
                Text('${room.temperature!.toStringAsFixed(1)}',
                    style: const TextStyle(color: Colors.black54)),
                const SizedBox(width: 8),
              ],
              if (room.humidity != null) ...[
                const Icon(Icons.water_drop, size: 14, color: Colors.blueAccent),
                const SizedBox(width: 2),
                Text('${room.humidity!.toStringAsFixed(0)}',
                    style: const TextStyle(color: Colors.black54)),
              ],
            ],
          ),
        ),
        _EntityGrid(entities: room.entities),
      ],
    );
  }
}

class _EnergySection extends StatelessWidget {
  final HaEnergy energy;
  const _EnergySection({required this.energy});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 6),
          child: Row(
            children: [
              const Icon(Icons.bolt, size: 18, color: Colors.black54),
              const SizedBox(width: 8),
              Text(energy.title,
                  style: const TextStyle(
                      fontSize: 16, fontWeight: FontWeight.w600)),
            ],
          ),
        ),
        _EntityGrid(entities: energy.tiles),
      ],
    );
  }
}

class _EntityGrid extends StatelessWidget {
  final List<HaEntity> entities;
  const _EntityGrid({required this.entities});

  @override
  Widget build(BuildContext context) {
    return GridView.count(
      crossAxisCount: 2,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      childAspectRatio: 2.6,
      crossAxisSpacing: 12,
      mainAxisSpacing: 12,
      children: [for (final e in entities) _EntityTile(entity: e)],
    );
  }
}

class _EntityTile extends StatelessWidget {
  final HaEntity entity;
  const _EntityTile({required this.entity});

  @override
  Widget build(BuildContext context) {
    final accent = _colorFor(entity.icon);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        boxShadow: const [
          BoxShadow(color: Colors.black12, blurRadius: 2, offset: Offset(0, 1)),
        ],
      ),
      child: Row(
        children: [
          Container(
            width: 36,
            height: 36,
            decoration: BoxDecoration(
              color: entity.isOn ? accent.withOpacity(0.18) : Colors.black12,
              shape: BoxShape.circle,
            ),
            child: Icon(_iconFor(entity.icon),
                size: 18,
                color: entity.isOn ? accent : Colors.black45),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(entity.name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontWeight: FontWeight.w600)),
                if (entity.state.isNotEmpty)
                  Text(entity.state,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                          color: Colors.black54, fontSize: 12)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ToastBanner extends StatelessWidget {
  final HaUpdate update;
  final VoidCallback onDismiss;
  const _ToastBanner({required this.update, required this.onDismiss});

  @override
  Widget build(BuildContext context) {
    return Material(
      elevation: 6,
      borderRadius: BorderRadius.circular(12),
      color: Colors.white,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        child: Row(
          children: [
            const Icon(Icons.notifications_active, color: Colors.amber),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(update.title,
                      style: const TextStyle(fontWeight: FontWeight.w600)),
                  if (update.body.isNotEmpty)
                    Text(update.body,
                        style: const TextStyle(color: Colors.black54)),
                ],
              ),
            ),
            TextButton(
              onPressed: onDismiss,
              child: const Text('Dismiss'),
            ),
          ],
        ),
      ),
    );
  }
}

class _NotificationsPanel extends StatelessWidget {
  final List<HaUpdate> updates;
  const _NotificationsPanel({required this.updates});

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Notifications',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600)),
            const SizedBox(height: 12),
            if (updates.isEmpty)
              const Text('No notifications yet.',
                  style: TextStyle(color: Colors.black54)),
            for (final u in updates.take(20))
              ListTile(
                leading: const Icon(Icons.notifications),
                title: Text(u.title),
                subtitle: Text(u.body),
                trailing: Text(_relative(u.receivedAt),
                    style: const TextStyle(color: Colors.black45, fontSize: 12)),
              ),
          ],
        ),
      ),
    );
  }

  static String _relative(DateTime t) {
    final d = DateTime.now().difference(t);
    if (d.inMinutes < 1) return 'now';
    if (d.inHours < 1) return '${d.inMinutes}m';
    if (d.inDays < 1) return '${d.inHours}h';
    return '${d.inDays}d';
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState();
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 64),
      child: Center(
        child: Column(
          children: const [
            Icon(Icons.cloud_off, size: 48, color: Colors.black26),
            SizedBox(height: 8),
            Text('Waiting for safer/app/status…',
                style: TextStyle(color: Colors.black45)),
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Icon / color mapping (kept inline so HA can send simple string keys)
// ---------------------------------------------------------------------------

IconData _iconFor(String key) {
  switch (key) {
    case 'thermometer':
      return Icons.thermostat;
    case 'humidity':
    case 'water':
      return Icons.water_drop;
    case 'presence':
    case 'car':
      return Icons.directions_car;
    case 'lamp':
    case 'lightbulb':
      return Icons.lightbulb;
    case 'spotlight':
      return Icons.flare;
    case 'blinds':
    case 'shutter':
      return Icons.blinds;
    case 'speaker':
      return Icons.speaker;
    case 'fridge':
      return Icons.kitchen;
    case 'battery':
      return Icons.battery_charging_full;
    case 'voltage':
      return Icons.electric_bolt;
    case 'power':
      return Icons.power;
    default:
      return Icons.circle;
  }
}

Color _colorFor(String key) {
  switch (key) {
    case 'thermometer':
      return Colors.redAccent;
    case 'humidity':
    case 'water':
      return Colors.blueAccent;
    case 'presence':
    case 'car':
      return Colors.grey;
    case 'lamp':
    case 'lightbulb':
    case 'spotlight':
      return Colors.amber;
    case 'blinds':
    case 'shutter':
      return Colors.purple;
    case 'fridge':
      return Colors.blueGrey;
    case 'battery':
    case 'voltage':
    case 'power':
      return Colors.green;
    default:
      return Colors.indigo;
  }
}
