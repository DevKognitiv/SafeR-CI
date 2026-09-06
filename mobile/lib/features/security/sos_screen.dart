import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/i18n.dart';
import '../../core/models/models.dart';
import '../../core/providers/providers.dart';
import '../../core/routes.dart';
import '../../core/theme.dart';
import '../../core/widgets/widgets.dart';
import 'widgets/emergency_numbers_row.dart';
import 'widgets/location_service.dart';
import 'widgets/phone_dialer.dart';
import 'widgets/sos_alert_list.dart';
import 'widgets/sos_button.dart';

enum _SosPhase { idle, locating, sending, sent, failed }

/// SafeR CI panic flow: locate, send the alert to the hub, show emergency numbers and recent alerts.
class SosScreen extends ConsumerStatefulWidget {
  const SosScreen({super.key});

  @override
  ConsumerState<SosScreen> createState() => _SosScreenState();
}

class _SosScreenState extends ConsumerState<SosScreen> {
  /// The SOS screen is always dark, whatever the app theme.
  static final ThemeData _darkTheme = SafeRTheme.darkTheme;

  _SosPhase _phase = _SosPhase.idle;
  String? _error;
  String? _resolvingId;
  final _note = TextEditingController();

  @override
  void dispose() {
    _note.dispose();
    super.dispose();
  }

  SosButtonState get _buttonState => switch (_phase) {
        _SosPhase.idle || _SosPhase.failed => SosButtonState.idle,
        _SosPhase.locating || _SosPhase.sending => SosButtonState.sending,
        _SosPhase.sent => SosButtonState.sent,
      };

  Future<void> _send(String homeId) async {
    if (_phase == _SosPhase.locating || _phase == _SosPhase.sending) return;
    setState(() {
      _phase = _SosPhase.locating;
      _error = null;
    });
    final point = await ref.read(locationServiceProvider).currentPosition();
    if (!mounted) return;
    setState(() => _phase = _SosPhase.sending);
    try {
      final note = _note.text.trim();
      await ref.read(securityProvider(homeId).notifier).raiseSos(lat: point?.lat, lon: point?.lon, note: note.isEmpty ? null : note);
      ref.invalidate(sosAlertsProvider(homeId));
      if (!mounted) return;
      setState(() => _phase = _SosPhase.sent);
      showSnack(context, context.tr(fr: 'Alerte SOS envoyée', en: 'SOS alert sent'));
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _phase = _SosPhase.failed;
        _error = e.toString().replaceFirst(RegExp(r'^ApiException\([^)]*\): '), '');
      });
      showErrorSnack(context, e);
    }
  }

  Future<void> _resolve(String homeId, SosAlert alert) async {
    setState(() => _resolvingId = alert.id);
    try {
      await ref.read(hubClientProvider).updateSos(homeId, alert.id, 'resolved');
      ref.invalidate(sosAlertsProvider(homeId));
      if (mounted) showSnack(context, context.tr(fr: 'Alerte marquée comme résolue', en: 'Alert marked as resolved'));
    } catch (e) {
      if (mounted) showErrorSnack(context, e);
    } finally {
      if (mounted) setState(() => _resolvingId = null);
    }
  }

  String _statusText(BuildContext context) => switch (_phase) {
        _SosPhase.idle => context.tr(fr: 'Appuyez sur le bouton en cas d\'urgence', en: 'Press the button in an emergency'),
        _SosPhase.locating => context.tr(fr: 'Localisation...', en: 'Locating...'),
        _SosPhase.sending => context.tr(fr: 'Envoi de l\'alerte...', en: 'Sending the alert...'),
        _SosPhase.sent => context.tr(fr: '✅ Alerte envoyée aux secours', en: '✅ Alert sent to emergency services'),
        _SosPhase.failed => context.tr(fr: 'Échec de l\'envoi, réessayez', en: 'Sending failed, try again'),
      };

  @override
  Widget build(BuildContext context) {
    final home = ref.watch(currentHomeProvider);
    return Theme(
      data: _darkTheme,
      child: Builder(builder: (context) => home == null ? _noHome(context) : _body(context, home)),
    );
  }

  Widget _noHome(BuildContext context) => Scaffold(
        backgroundColor: SafeRColors.surfaceDark,
        appBar: _appBar(context),
        body: EmptyState(
          icon: Icons.home_work_outlined,
          title: context.tr(fr: 'Créez votre première maison', en: 'Create your first home'),
          subtitle: context.tr(fr: 'Une alerte SOS est rattachée à une maison pour transmettre son adresse aux secours.', en: 'An SOS alert is linked to a home so its address reaches responders.'),
          actionLabel: context.tr(fr: 'Créer une maison', en: 'Create a home'),
          onAction: () => context.push(Routes.homes),
        ),
      );

  AppBar _appBar(BuildContext context) => AppBar(
        backgroundColor: SafeRColors.surfaceDark,
        foregroundColor: Colors.white,
        automaticallyImplyLeading: false,
        leading: IconButton(
          tooltip: context.tr(fr: 'Fermer', en: 'Close'),
          icon: const Icon(Icons.close),
          onPressed: () => context.canPop() ? context.pop() : context.go(Routes.security),
        ),
        title: const Text('SOS', style: TextStyle(fontWeight: FontWeight.w900, letterSpacing: 2)),
      );

  Widget _body(BuildContext context, Home home) {
    final theme = Theme.of(context);
    final homeId = home.id;
    final alertsAsync = ref.watch(sosAlertsProvider(homeId));
    final sent = _phase == _SosPhase.sent;
    final statusColor = switch (_phase) {
      _SosPhase.sent => SafeRColors.success,
      _SosPhase.failed => SafeRColors.danger,
      _ => Colors.white70,
    };
    return Scaffold(
      backgroundColor: SafeRColors.surfaceDark,
      appBar: _appBar(context),
      body: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(16, 4, 16, 32),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Icon(Icons.home_outlined, size: 16, color: Colors.white54),
                const SizedBox(width: 6),
                Flexible(
                  child: Text(
                    home.address == null || home.address!.isEmpty ? home.name : '${home.name} · ${home.address}',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: theme.textTheme.bodySmall?.copyWith(color: Colors.white54),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Center(child: SosButton(state: _buttonState, onPressed: () => _send(homeId))),
            Text(
              _statusText(context),
              key: const Key('sos-status'),
              textAlign: TextAlign.center,
              style: theme.textTheme.titleMedium?.copyWith(color: statusColor, fontWeight: FontWeight.w700),
            ),
            if (_error != null) ...[
              const SizedBox(height: 4),
              Text(_error!, textAlign: TextAlign.center, style: theme.textTheme.bodySmall?.copyWith(color: Colors.white54), maxLines: 3),
            ],
            if (sent) ...[
              const SizedBox(height: 6),
              Text(
                context.tr(fr: 'Restez en sécurité. Les secours et vos proches ont reçu votre position.', en: 'Stay safe. Responders and your contacts received your location.'),
                textAlign: TextAlign.center,
                style: theme.textTheme.bodySmall?.copyWith(color: Colors.white70),
              ),
              TextButton.icon(
                onPressed: () => setState(() {
                  _phase = _SosPhase.idle;
                  _note.clear();
                }),
                icon: const Icon(Icons.refresh, size: 18),
                label: Text(context.tr(fr: 'Nouvelle alerte', en: 'New alert')),
              ),
            ],
            const SizedBox(height: 12),
            TextField(
              controller: _note,
              enabled: !sent && _buttonState != SosButtonState.sending,
              maxLines: 2,
              minLines: 1,
              textInputAction: TextInputAction.done,
              decoration: InputDecoration(
                labelText: context.tr(fr: 'Note (facultatif)', en: 'Note (optional)'),
                hintText: context.tr(fr: 'Intrusion, incendie, malaise...', en: 'Intrusion, fire, medical...'),
                prefixIcon: const Icon(Icons.edit_note),
              ),
            ),
            SectionHeader(title: context.tr(fr: 'Numéros d\'urgence', en: 'Emergency numbers'), padding: const EdgeInsets.fromLTRB(0, 24, 0, 8)),
            EmergencyNumbersRow(onCall: (number) => dialNumber(context, ref, number)),
            SectionHeader(
              title: context.tr(fr: 'Alertes récentes', en: 'Recent alerts'),
              padding: const EdgeInsets.fromLTRB(0, 24, 0, 8),
              trailing: IconButton(
                tooltip: context.tr(fr: 'Actualiser', en: 'Refresh'),
                onPressed: () => ref.invalidate(sosAlertsProvider(homeId)),
                icon: const Icon(Icons.refresh, size: 20),
              ),
            ),
            alertsAsync.when(
              loading: () => const SizedBox(height: 80, child: LoadingView()),
              error: (error, _) => ErrorView(error: error, onRetry: () => ref.invalidate(sosAlertsProvider(homeId))),
              data: (alerts) => alerts.isEmpty
                  ? EmptyState(
                      icon: Icons.sos,
                      title: context.tr(fr: 'Aucune alerte récente', en: 'No recent alert'),
                      subtitle: context.tr(fr: 'Vos alertes SOS apparaîtront ici.', en: 'Your SOS alerts will show up here.'),
                    )
                  : Column(
                      children: [
                        for (final a in alerts.take(10)) ...[
                          SosAlertTile(alert: a, busy: _resolvingId == a.id, onResolve: () => _resolve(homeId, a)),
                          const SizedBox(height: 8),
                        ],
                      ],
                    ),
            ),
          ],
        ),
      ),
    );
  }
}
