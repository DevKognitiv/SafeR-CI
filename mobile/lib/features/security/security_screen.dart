import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/config.dart';
import '../../core/i18n.dart';
import '../../core/models/models.dart';
import '../../core/providers/providers.dart';
import '../../core/routes.dart';
import '../../core/widgets/widgets.dart';
import 'widgets/alarm_banner_card.dart';
import 'widgets/alarm_history_list.dart';
import 'widgets/phone_dialer.dart';
import 'widgets/security_device_rows.dart';
import 'widgets/security_hero_card.dart';
import 'widgets/sos_card.dart';

/// Tuya-style Security tab: arm modes, alarm banner, panels / zones / sensors,
/// alarm history and the SafeR CI SOS entry point.
class SecurityScreen extends ConsumerStatefulWidget {
  const SecurityScreen({super.key});

  @override
  ConsumerState<SecurityScreen> createState() => _SecurityScreenState();
}

class _SecurityScreenState extends ConsumerState<SecurityScreen> {
  bool _busy = false;

  static String get _policeNumber => AppConfig.emergencyNumbers.firstWhere((n) => n.label == 'Police', orElse: () => AppConfig.emergencyNumbers.first).number;

  Future<void> _refresh(String homeId) async {
    await Future.wait([
      ref.read(securityProvider(homeId).notifier).refresh(),
      ref.read(devicesProvider(homeId).notifier).refresh(),
      ref.read(messagesProvider(homeId).notifier).refresh(),
    ]);
  }

  Future<void> _setMode(String homeId, SecurityState security, String mode, List<Device> openDevices) async {
    if (mode == security.mode || _busy) return;
    if (mode != 'disarmed' && openDevices.isNotEmpty) {
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          icon: const Icon(Icons.door_front_door, color: Colors.orange),
          title: Text(context.tr(fr: 'Ouvertures détectées', en: 'Openings detected')),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(context.tr(fr: 'Des ouvertures sont détectées, armer quand même ?', en: 'Some openings are detected, arm anyway?')),
              const SizedBox(height: 12),
              for (final d in openDevices.take(5)) Text('• ${d.name}', style: Theme.of(context).textTheme.bodySmall),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.of(context).pop(false), child: Text(context.tr(fr: 'Annuler', en: 'Cancel'))),
            FilledButton(onPressed: () => Navigator.of(context).pop(true), child: Text(context.tr(fr: 'Armer quand même', en: 'Arm anyway'))),
          ],
        ),
      );
      if (confirmed != true || !mounted) return;
    }
    setState(() => _busy = true);
    try {
      await ref.read(securityProvider(homeId).notifier).setMode(mode);
      if (!mounted) return;
      final label = securityModeLabel(context, mode);
      showSnack(context, context.tr(fr: 'Mode « $label » activé', en: '"$label" mode enabled'));
    } catch (e) {
      if (mounted) showErrorSnack(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _clearAlarm(String homeId) async {
    setState(() => _busy = true);
    try {
      await ref.read(securityProvider(homeId).notifier).clearAlarm();
      if (mounted) showSnack(context, context.tr(fr: 'Alarme acquittée', en: 'Alarm acknowledged'));
    } catch (e) {
      if (mounted) showErrorSnack(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final homes = ref.watch(homesProvider);
    final home = ref.watch(currentHomeProvider);
    if (home == null) return _NoHomeScaffold(homes: homes);

    final homeId = home.id;
    final securityAsync = ref.watch(securityProvider(homeId));
    final unread = ref.watch(unreadCountProvider(homeId)).valueOrNull;

    return Scaffold(
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(context.tr(fr: 'Sécurité', en: 'Security')),
            Text(home.name, style: Theme.of(context).textTheme.bodySmall?.copyWith(color: Theme.of(context).colorScheme.onSurfaceVariant)),
          ],
        ),
        actions: [
          IconButton(
            tooltip: context.tr(fr: 'Notifications d\'alarme', en: 'Alarm notifications'),
            onPressed: () => context.go('${Routes.messages}?kind=alarm'),
            icon: Badge(
              isLabelVisible: (unread?.alarm ?? 0) > 0,
              label: Text('${unread?.alarm ?? 0}'),
              child: const Icon(Icons.notifications_outlined),
            ),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () => _refresh(homeId),
        child: securityAsync.when(
          loading: () => const _FillScroll(child: LoadingView()),
          error: (error, _) => _FillScroll(child: ErrorView(error: error, onRetry: () => ref.read(securityProvider(homeId).notifier).refresh())),
          data: (security) => _SecurityBody(
            homeId: homeId,
            security: security,
            busy: _busy,
            policeNumber: _policeNumber,
            onSelectMode: (mode, open) => _setMode(homeId, security, mode, open),
            onClearAlarm: () => _clearAlarm(homeId),
            onCallPolice: () => dialNumber(context, ref, _policeNumber),
          ),
        ),
      ),
    );
  }
}

/// Scrollable content of the tab once the security state is known.
class _SecurityBody extends ConsumerWidget {
  const _SecurityBody({
    required this.homeId,
    required this.security,
    required this.busy,
    required this.policeNumber,
    required this.onSelectMode,
    required this.onClearAlarm,
    required this.onCallPolice,
  });

  final String homeId;
  final SecurityState security;
  final bool busy;
  final String policeNumber;
  final void Function(String mode, List<Device> openDevices) onSelectMode;
  final VoidCallback onClearAlarm;
  final VoidCallback onCallPolice;

  /// Prefer the live device list (patched by realtime events) over the snapshot in the security payload.
  static List<Device> _live(List<Device> snapshot, Map<String, Device> byId, Iterable<Device> fallback) {
    if (snapshot.isEmpty) return fallback.toList();
    return [for (final d in snapshot) byId[d.id] ?? d];
  }

  static bool _isOpen(Device d) =>
      d.online &&
      ((d.boolValue('contact') ?? false) ||
          (d.category == 'alarm_zone' && (d.boolValue('open') ?? false)) ||
          (d.category == 'lock' && (d.boolValue('door') ?? false)));

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final devices = ref.watch(devicesProvider(homeId)).valueOrNull ?? const <Device>[];
    final byId = {for (final d in devices) d.id: d};
    final panels = _live(security.panels, byId, devices.where((d) => d.category == 'alarm_panel'));
    final zones = _live(security.zones, byId, devices.where((d) => d.category == 'alarm_zone'));
    final sensors = _live(security.sensors, byId, devices.where((d) => d.isSensor || d.category == 'lock' || d.category == 'siren'));
    final all = {for (final d in [...panels, ...zones, ...sensors, ...devices]) d.id: d};
    final openDevices = all.values.where(_isOpen).toList();
    final alarmDevice = security.alarmDeviceId == null ? null : all[security.alarmDeviceId!];
    final messagesAsync = ref.watch(messagesProvider(homeId));

    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.only(bottom: 24),
      children: [
        if (security.alarmActive)
          SecurityAlarmBanner(
            deviceName: alarmDevice?.name,
            policeNumber: policeNumber,
            busy: busy,
            onAcknowledge: onClearAlarm,
            onCallPolice: onCallPolice,
          ),
        SecurityHeroCard(security: security, openCount: openDevices.length, busy: busy, onSelected: (mode) => onSelectMode(mode, openDevices)),
        SectionHeader(title: context.tr(fr: 'Centrales', en: 'Panels')),
        if (panels.isEmpty)
          SectionEmptyCard(
            icon: Icons.shield_outlined,
            text: context.tr(fr: 'Aucune centrale d\'alarme', en: 'No alarm panel'),
            actionLabel: context.tr(fr: 'Ajouter', en: 'Add'),
            onAction: () => context.push(Routes.addDevice),
          )
        else
          SecurityListCard(children: [
            for (final d in panels)
              SecurityDeviceRow(
                device: d,
                chips: panelChips(context, d),
                subtitle: d.brand == 'demo' ? categoryLabel(context, d.category) : '${categoryLabel(context, d.category)} · ${d.brand}',
                onTap: () => context.push(Routes.device(d.id)),
              ),
          ]),
        SectionHeader(title: context.tr(fr: 'Zones', en: 'Zones')),
        if (zones.isEmpty)
          SectionEmptyCard(icon: Icons.radar, text: context.tr(fr: 'Aucune zone configurée', en: 'No zone configured'))
        else
          SecurityListCard(children: [
            for (final d in zones)
              SecurityDeviceRow(device: d, chips: zoneChips(context, d), subtitle: _parentName(d, all), onTap: () => context.push(Routes.device(d.id))),
          ]),
        SectionHeader(title: context.tr(fr: 'Capteurs & serrures', en: 'Sensors & locks')),
        if (sensors.isEmpty)
          SectionEmptyCard(
            icon: Icons.sensors,
            text: context.tr(fr: 'Aucun capteur ni serrure', en: 'No sensor or lock yet'),
            actionLabel: context.tr(fr: 'Ajouter', en: 'Add'),
            onAction: () => context.push(Routes.addDevice),
          )
        else
          SecurityListCard(children: [
            for (final d in sensors)
              SecurityDeviceRow(device: d, chips: sensorChips(context, d), subtitle: _roomName(context, ref, d), onTap: () => context.push(Routes.device(d.id))),
          ]),
        SectionHeader(
          title: context.tr(fr: 'Historique des alarmes', en: 'Alarm history'),
          trailing: TextButton(
            onPressed: () => context.go('${Routes.messages}?kind=alarm'),
            child: Text(context.tr(fr: 'Voir tout', en: 'See all')),
          ),
        ),
        messagesAsync.when(
          loading: () => const SizedBox(height: 72, child: LoadingView()),
          error: (error, _) => SectionEmptyCard(
            icon: Icons.cloud_off,
            text: context.tr(fr: 'Historique indisponible', en: 'History unavailable'),
            actionLabel: context.tr(fr: 'Réessayer', en: 'Retry'),
            onAction: () => ref.read(messagesProvider(homeId).notifier).refresh(),
          ),
          data: (messages) {
            final alarms = messages.where((m) => m.kind == 'alarm').take(5).toList();
            if (alarms.isEmpty) {
              return SectionEmptyCard(icon: Icons.notifications_none, text: context.tr(fr: 'Aucune alarme récente', en: 'No recent alarm'));
            }
            return AlarmHistoryCard(
              messages: alarms,
              onTap: (m) => m.deviceId == null ? context.go('${Routes.messages}?kind=alarm') : context.push(Routes.device(m.deviceId!)),
            );
          },
        ),
        SosCard(onTap: () => context.push(Routes.sos)),
      ],
    );
  }

  String? _parentName(Device zone, Map<String, Device> all) {
    final parent = zone.parentId == null ? null : all[zone.parentId!];
    return parent?.name;
  }

  String? _roomName(BuildContext context, WidgetRef ref, Device device) {
    if (device.roomId == null) return null;
    for (final room in ref.watch(roomsProvider(homeId))) {
      if (room.id == device.roomId) return '${categoryLabel(context, device.category)} · ${room.name}';
    }
    return null;
  }
}

/// A non-scrolling child inside a scrollable so pull-to-refresh keeps working.
class _FillScroll extends StatelessWidget {
  const _FillScroll({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) => CustomScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        slivers: [SliverFillRemaining(hasScrollBody: false, child: child)],
      );
}

/// Shown while homes load, on error, or when the user has no home yet.
class _NoHomeScaffold extends ConsumerWidget {
  const _NoHomeScaffold({required this.homes});

  final AsyncValue<List<Home>> homes;

  @override
  Widget build(BuildContext context, WidgetRef ref) => Scaffold(
        appBar: AppBar(title: Text(context.tr(fr: 'Sécurité', en: 'Security'))),
        body: homes.when(
          loading: () => const LoadingView(),
          error: (error, _) => ErrorView(error: error, onRetry: () => ref.read(homesProvider.notifier).refresh()),
          data: (_) => EmptyState(
            icon: Icons.home_work_outlined,
            title: context.tr(fr: 'Créez votre première maison', en: 'Create your first home'),
            subtitle: context.tr(fr: 'La sécurité se configure par maison : centrale, zones et capteurs.', en: 'Security is set up per home: panel, zones and sensors.'),
            actionLabel: context.tr(fr: 'Créer une maison', en: 'Create a home'),
            onAction: () => context.push(Routes.homes),
          ),
        ),
      );
}
