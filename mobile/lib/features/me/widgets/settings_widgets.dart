import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/config.dart';
import '../../../core/i18n.dart';
import '../../../core/providers/providers.dart';
import '../../../core/theme.dart';
import '../../../core/widgets/widgets.dart';
import 'me_common.dart';

/// Titled group of settings rows.
class SettingsGroup extends StatelessWidget {
  const SettingsGroup({super.key, required this.title, required this.children});

  final String title;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SectionHeader(title: title, padding: const EdgeInsets.fromLTRB(4, 20, 4, 8)),
          GroupedCard(children: children),
        ],
      );
}

/// Row with icon, label, current value and a chevron.
class SettingsTile extends StatelessWidget {
  const SettingsTile({super.key, required this.icon, required this.title, this.value, this.onTap, this.trailing});

  final IconData icon;
  final String title;
  final String? value;
  final VoidCallback? onTap;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListTile(
      leading: IconBox(icon: icon, size: 36),
      title: Text(title),
      subtitle: value == null ? null : Text(value!, maxLines: 1, overflow: TextOverflow.ellipsis, style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
      trailing: trailing ?? (onTap == null ? null : Icon(Icons.chevron_right, color: theme.colorScheme.onSurfaceVariant)),
      onTap: onTap,
    );
  }
}

/// One choice of [showOptionSheet].
class OptionItem<T> {
  const OptionItem({required this.value, required this.label, this.subtitle, this.icon});

  final T value;
  final String label;
  final String? subtitle;
  final IconData? icon;
}

/// Bottom sheet listing options with a check on the selected one. Resolves with the picked value.
Future<T?> showOptionSheet<T>(BuildContext context, {required String title, required List<OptionItem<T>> options, T? selected}) => showModalBottomSheet<T>(
      context: context,
      showDragHandle: true,
      builder: (sheetContext) {
        final theme = Theme.of(sheetContext);
        return SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 0, 20, 8),
                child: Text(title, style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
              ),
              for (final option in options)
                ListTile(
                  leading: option.icon == null ? null : Icon(option.icon),
                  title: Text(option.label),
                  subtitle: option.subtitle == null ? null : Text(option.subtitle!),
                  trailing: Icon(
                    option.value == selected ? Icons.check_circle : Icons.circle_outlined,
                    color: option.value == selected ? theme.colorScheme.primary : theme.colorScheme.outline,
                  ),
                  selected: option.value == selected,
                  onTap: () => Navigator.of(sheetContext).pop(option.value),
                ),
              const SizedBox(height: 8),
            ],
          ),
        );
      },
    );

/// Basic hub URL validation (http/https + host).
String? validateHubUrl(BuildContext context, String? value) {
  final v = (value ?? '').trim();
  if (v.isEmpty) return context.tr(fr: "Saisissez l'URL du hub", en: 'Enter the hub URL');
  final uri = Uri.tryParse(v);
  if (uri == null || (uri.scheme != 'http' && uri.scheme != 'https') || uri.host.isEmpty) {
    return context.tr(fr: 'URL invalide (ex. http://192.168.1.20:8000)', en: 'Invalid URL (e.g. http://192.168.1.20:8000)');
  }
  return null;
}

String normalizeHubUrl(String value) => value.trim().replaceAll(RegExp(r'/+$'), '');

/// Opens the hub URL editor. "Tester" applies the URL so the shared client probes it;
/// when the sheet is dismissed without saving, the previous URL is restored.
Future<void> showHubUrlEditor(BuildContext context, WidgetRef ref) async {
  final original = ref.read(hubUrlProvider);
  final saved = await showModalBottomSheet<bool>(
    context: context,
    isScrollControlled: true,
    useSafeArea: true,
    showDragHandle: true,
    builder: (_) => const HubUrlEditorSheet(),
  );
  if (!context.mounted) return;
  if (saved == true) {
    showSnack(context, context.tr(fr: 'URL du hub enregistrée', en: 'Hub URL saved'));
    return;
  }
  if (ref.read(hubUrlProvider) != original) await ref.read(hubUrlProvider.notifier).set(original);
}

/// Sheet editing `hubUrlProvider` with a connection test.
class HubUrlEditorSheet extends ConsumerStatefulWidget {
  const HubUrlEditorSheet({super.key});

  @override
  ConsumerState<HubUrlEditorSheet> createState() => _HubUrlEditorSheetState();
}

class _HubUrlEditorSheetState extends ConsumerState<HubUrlEditorSheet> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _controller = TextEditingController(text: ref.read(hubUrlProvider));
  bool _testing = false;
  bool? _reachable;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _test() async {
    if (_testing || !(_formKey.currentState?.validate() ?? false)) return;
    setState(() {
      _testing = true;
      _reachable = null;
    });
    await ref.read(hubUrlProvider.notifier).set(normalizeHubUrl(_controller.text));
    if (!mounted) return;
    final ok = await ref.read(hubClientProvider).health();
    if (!mounted) return;
    setState(() {
      _testing = false;
      _reachable = ok;
    });
  }

  Future<void> _save() async {
    if (_testing || !(_formKey.currentState?.validate() ?? false)) return;
    await ref.read(hubUrlProvider.notifier).set(normalizeHubUrl(_controller.text));
    if (!mounted) return;
    Navigator.of(context).pop(true);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final reachable = _reachable;
    return Padding(
      padding: EdgeInsets.fromLTRB(20, 0, 20, 20 + MediaQuery.viewInsetsOf(context).bottom),
      child: Form(
        key: _formKey,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(context.tr(fr: 'Hub SafeR', en: 'SafeR hub'), style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700)),
            const SizedBox(height: 6),
            Text(
              context.tr(fr: "Adresse du hub auquel l'application se connecte.", en: 'Address of the hub the app connects to.'),
              style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
            ),
            const SizedBox(height: 16),
            TextFormField(
              key: const Key('settings-hub-url'),
              controller: _controller,
              keyboardType: TextInputType.url,
              textInputAction: TextInputAction.done,
              autocorrect: false,
              enableSuggestions: false,
              validator: (v) => validateHubUrl(context, v),
              onChanged: (_) {
                if (_reachable != null) setState(() => _reachable = null);
              },
              onFieldSubmitted: (_) => _save(),
              decoration: InputDecoration(
                labelText: context.tr(fr: 'URL du hub', en: 'Hub URL'),
                hintText: AppConfig.defaultHubUrl,
                prefixIcon: const Icon(Icons.link),
                suffixIcon: IconButton(
                  tooltip: context.tr(fr: 'Rétablir la valeur par défaut', en: 'Restore default'),
                  onPressed: _testing
                      ? null
                      : () {
                          _controller.text = AppConfig.defaultHubUrl;
                          setState(() => _reachable = null);
                        },
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
                    style: OutlinedButton.styleFrom(minimumSize: const Size.fromHeight(48), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12))),
                    onPressed: _testing ? null : _test,
                    icon: _testing
                        ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                        : const Icon(Icons.wifi_tethering),
                    label: Text(context.tr(fr: 'Tester la connexion', en: 'Test connection')),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: FilledButton(onPressed: _testing ? null : _save, child: Text(context.tr(fr: 'Enregistrer', en: 'Save'))),
                ),
              ],
            ),
            const SizedBox(height: 4),
            TextButton(
              onPressed: _testing ? null : () => Navigator.of(context).pop(false),
              child: Text(context.tr(fr: 'Annuler', en: 'Cancel')),
            ),
          ],
        ),
      ),
    );
  }
}
