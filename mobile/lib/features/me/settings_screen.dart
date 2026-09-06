import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/config.dart';
import '../../core/i18n.dart';
import '../../core/providers/providers.dart';
import '../../core/router.dart';
import 'widgets/me_common.dart';
import 'widgets/settings_widgets.dart';

/// App settings: language, theme, hub URL, notifications and version.
class SettingsScreen extends ConsumerWidget {
  const SettingsScreen({super.key});

  static const _system = 'system';

  String _languageLabel(BuildContext context, Locale? locale) {
    switch (locale?.languageCode) {
      case 'fr':
        return 'Français';
      case 'en':
        return 'English';
      default:
        return context.tr(fr: 'Système', en: 'System');
    }
  }

  String _themeLabel(BuildContext context, ThemeMode mode) {
    switch (mode) {
      case ThemeMode.light:
        return context.tr(fr: 'Clair', en: 'Light');
      case ThemeMode.dark:
        return context.tr(fr: 'Sombre', en: 'Dark');
      case ThemeMode.system:
        return context.tr(fr: 'Système', en: 'System');
    }
  }

  Future<void> _pickLanguage(BuildContext context, WidgetRef ref) async {
    final current = ref.read(localeProvider)?.languageCode ?? _system;
    final picked = await showOptionSheet<String>(
      context,
      title: context.tr(fr: 'Langue', en: 'Language'),
      selected: current,
      options: [
        OptionItem(value: _system, label: context.tr(fr: 'Système', en: 'System'), subtitle: context.tr(fr: 'Suivre la langue du téléphone', en: 'Follow the phone language'), icon: Icons.phone_android),
        const OptionItem(value: 'fr', label: 'Français', icon: Icons.language),
        const OptionItem(value: 'en', label: 'English', icon: Icons.translate),
      ],
    );
    if (picked == null) return;
    await ref.read(localeProvider.notifier).set(picked == _system ? null : Locale(picked));
  }

  Future<void> _pickTheme(BuildContext context, WidgetRef ref) async {
    final picked = await showOptionSheet<ThemeMode>(
      context,
      title: context.tr(fr: 'Thème', en: 'Theme'),
      selected: ref.read(themeModeProvider),
      options: [
        OptionItem(value: ThemeMode.system, label: context.tr(fr: 'Système', en: 'System'), icon: Icons.brightness_auto),
        OptionItem(value: ThemeMode.light, label: context.tr(fr: 'Clair', en: 'Light'), icon: Icons.light_mode_outlined),
        OptionItem(value: ThemeMode.dark, label: context.tr(fr: 'Sombre', en: 'Dark'), icon: Icons.dark_mode_outlined),
      ],
    );
    if (picked == null) return;
    await ref.read(themeModeProvider.notifier).set(picked);
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final locale = ref.watch(localeProvider);
    final themeMode = ref.watch(themeModeProvider);
    final hubUrl = ref.watch(hubUrlProvider);
    final realtime = ref.watch(realtimeAlertsProvider);
    return Scaffold(
      appBar: AppBar(title: Text(context.tr(fr: 'Paramètres', en: 'Settings'))),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 0, 16, 32),
        children: [
          SettingsGroup(
            title: context.tr(fr: 'Général', en: 'General'),
            children: [
              SettingsTile(
                key: const Key('settings-language'),
                icon: Icons.language,
                title: context.tr(fr: 'Langue', en: 'Language'),
                value: _languageLabel(context, locale),
                onTap: () => _pickLanguage(context, ref),
              ),
              SettingsTile(
                key: const Key('settings-theme'),
                icon: Icons.dark_mode_outlined,
                title: context.tr(fr: 'Thème', en: 'Theme'),
                value: _themeLabel(context, themeMode),
                onTap: () => _pickTheme(context, ref),
              ),
            ],
          ),
          SettingsGroup(
            title: context.tr(fr: 'Hub SafeR', en: 'SafeR hub'),
            children: [
              SettingsTile(
                key: const Key('settings-hub'),
                icon: Icons.router_outlined,
                title: context.tr(fr: 'URL du hub', en: 'Hub URL'),
                value: hubUrl,
                onTap: () => showHubUrlEditor(context, ref),
              ),
            ],
          ),
          SettingsGroup(
            title: context.tr(fr: 'Notifications', en: 'Notifications'),
            children: [
              SwitchListTile(
                key: const Key('settings-realtime'),
                secondary: const IconBox(icon: Icons.notifications_active_outlined, size: 36),
                title: Text(context.tr(fr: 'Alertes en temps réel', en: 'Realtime alerts')),
                subtitle: Text(
                  context.tr(fr: 'Afficher les alarmes et événements dès leur réception', en: 'Show alarms and events as soon as they arrive'),
                  style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                ),
                value: realtime.valueOrNull ?? true,
                onChanged: realtime.isLoading ? null : (v) => ref.read(realtimeAlertsProvider.notifier).set(v),
              ),
              SettingsTile(
                icon: Icons.inbox_outlined,
                title: context.tr(fr: 'Centre de messages', en: 'Message center'),
                value: context.tr(fr: 'Alarmes, maison et notifications', en: 'Alarms, home and notices'),
                onTap: () => context.push(Routes.messages),
              ),
            ],
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(4, 8, 4, 0),
            child: Text(
              context.tr(
                fr: 'Les notifications push dépendent du hub SafeR et de votre téléphone. Ce réglage concerne uniquement les alertes affichées dans l\'application.',
                en: 'Push notifications depend on the SafeR hub and your phone. This setting only affects alerts shown inside the app.',
              ),
              style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
            ),
          ),
          SettingsGroup(
            title: context.tr(fr: 'À propos', en: 'About'),
            children: [
              SettingsTile(icon: Icons.verified_outlined, title: context.tr(fr: 'Version', en: 'Version'), value: '${AppConfig.appName} ${AppConfig.version}'),
              SettingsTile(icon: Icons.info_outline, title: context.tr(fr: 'À propos de SafeR', en: 'About SafeR'), onTap: () => context.push(Routes.about)),
            ],
          ),
        ],
      ),
    );
  }
}
