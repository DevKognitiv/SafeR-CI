import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/config.dart';
import '../../../core/i18n.dart';
import '../../../core/providers/providers.dart';
import '../../../core/theme.dart';
import '../../../core/widgets/widgets.dart';
import 'auth_validators.dart';

/// Subtle `Hub : <url>` footer with a gear to change the hub URL.
class HubFooter extends StatelessWidget {
  const HubFooter({super.key, required this.url, required this.onEdit});

  final String url;
  final VoidCallback onEdit;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final muted = theme.colorScheme.onSurfaceVariant;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 24),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.dns_outlined, size: 14, color: muted),
          const SizedBox(width: 6),
          Flexible(
            child: Text(
              context.tr(fr: 'Hub : $url', en: 'Hub: $url'),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: theme.textTheme.bodySmall?.copyWith(color: muted),
            ),
          ),
          IconButton(
            onPressed: onEdit,
            tooltip: context.tr(fr: "Changer l'URL du hub", en: 'Change hub URL'),
            iconSize: 18,
            icon: Icon(Icons.settings_outlined, color: muted),
          ),
        ],
      ),
    );
  }
}

/// Opens the hub URL sheet. "Tester la connexion" applies the URL so the shared
/// client can probe it; if the sheet is dismissed without saving, the previous URL is restored.
Future<void> showHubUrlSheet(BuildContext context, WidgetRef ref) async {
  final original = ref.read(hubUrlProvider);
  final saved = await showModalBottomSheet<bool>(
    context: context,
    isScrollControlled: true,
    useSafeArea: true,
    builder: (_) => const HubUrlSheet(),
  );
  if (!context.mounted) return;
  if (saved == true) {
    showSnack(context, context.tr(fr: 'URL du hub enregistrée', en: 'Hub URL saved'));
    return;
  }
  if (ref.read(hubUrlProvider) != original) await ref.read(hubUrlProvider.notifier).set(original);
}

/// Bottom sheet editing `hubUrlProvider` with a connection test.
class HubUrlSheet extends ConsumerStatefulWidget {
  const HubUrlSheet({super.key});

  @override
  ConsumerState<HubUrlSheet> createState() => _HubUrlSheetState();
}

class _HubUrlSheetState extends ConsumerState<HubUrlSheet> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _controller;
  bool _testing = false;
  bool _saving = false;
  bool? _reachable;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: ref.read(hubUrlProvider));
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  bool get _busy => _testing || _saving;

  String get _url => AuthValidators.normalizeHubUrl(_controller.text);

  Future<void> _test() async {
    if (_busy || !(_formKey.currentState?.validate() ?? false)) return;
    setState(() {
      _testing = true;
      _reachable = null;
    });
    await ref.read(hubUrlProvider.notifier).set(_url);
    if (!mounted) return;
    final ok = await ref.read(hubClientProvider).health();
    if (!mounted) return;
    setState(() {
      _testing = false;
      _reachable = ok;
    });
  }

  Future<void> _save() async {
    if (_busy || !(_formKey.currentState?.validate() ?? false)) return;
    setState(() => _saving = true);
    await ref.read(hubUrlProvider.notifier).set(_url);
    if (!mounted) return;
    Navigator.of(context).pop(true);
  }

  void _restoreDefault() {
    _controller.text = AppConfig.defaultHubUrl;
    setState(() => _reachable = null);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final reachable = _reachable;
    return Padding(
      padding: EdgeInsets.fromLTRB(20, 12, 20, 20 + MediaQuery.viewInsetsOf(context).bottom),
      child: Form(
        key: _formKey,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Center(
              child: Container(
                width: 36,
                height: 4,
                decoration: BoxDecoration(color: theme.colorScheme.outlineVariant, borderRadius: BorderRadius.circular(2)),
              ),
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                Icon(Icons.dns_outlined, color: theme.colorScheme.primary),
                const SizedBox(width: 10),
                Text(context.tr(fr: 'Hub SafeR', en: 'SafeR hub'), style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700)),
              ],
            ),
            const SizedBox(height: 6),
            Text(
              context.tr(
                fr: "Adresse du hub auquel l'application se connecte (ex. http://192.168.1.20:8000).",
                en: 'Address of the hub the app connects to (e.g. http://192.168.1.20:8000).',
              ),
              style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
            ),
            const SizedBox(height: 16),
            TextFormField(
              key: const Key('hub-url-field'),
              controller: _controller,
              keyboardType: TextInputType.url,
              textInputAction: TextInputAction.done,
              autocorrect: false,
              enableSuggestions: false,
              validator: (v) => AuthValidators.hubUrl(context, v),
              onChanged: (_) {
                if (_reachable != null) setState(() => _reachable = null);
              },
              onFieldSubmitted: (_) => _save(),
              decoration: InputDecoration(
                labelText: context.tr(fr: 'URL du hub', en: 'Hub URL'),
                prefixIcon: const Icon(Icons.link),
                suffixIcon: IconButton(
                  onPressed: _busy ? null : _restoreDefault,
                  tooltip: context.tr(fr: 'Rétablir la valeur par défaut', en: 'Restore default'),
                  icon: const Icon(Icons.restart_alt),
                ),
              ),
            ),
            if (reachable != null) ...[
              const SizedBox(height: 12),
              Row(
                children: [
                  Icon(reachable ? Icons.check_circle : Icons.error, size: 18, color: reachable ? SafeRColors.success : SafeRColors.danger),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      reachable ? context.tr(fr: 'Hub joignable', en: 'Hub reachable') : context.tr(fr: 'Hub injoignable', en: 'Hub unreachable'),
                      style: theme.textTheme.bodyMedium?.copyWith(color: reachable ? SafeRColors.success : SafeRColors.danger, fontWeight: FontWeight.w600),
                    ),
                  ),
                ],
              ),
            ],
            const SizedBox(height: 20),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: _busy ? null : _test,
                    style: OutlinedButton.styleFrom(minimumSize: const Size.fromHeight(48), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12))),
                    icon: _testing
                        ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                        : const Icon(Icons.wifi_tethering),
                    label: Text(context.tr(fr: 'Tester la connexion', en: 'Test connection')),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: FilledButton(
                    onPressed: _busy ? null : _save,
                    child: Text(context.tr(fr: 'Enregistrer', en: 'Save')),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 4),
            TextButton(
              onPressed: _busy ? null : () => Navigator.of(context).pop(false),
              child: Text(context.tr(fr: 'Annuler', en: 'Cancel')),
            ),
          ],
        ),
      ),
    );
  }
}
