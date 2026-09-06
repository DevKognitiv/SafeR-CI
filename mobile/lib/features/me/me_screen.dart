import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/config.dart';
import '../../core/i18n.dart';
import '../../core/providers/providers.dart';
import '../../core/router.dart';
import '../../core/theme.dart';
import '../../core/widgets/widgets.dart';
import 'widgets/current_home_card.dart';
import 'widgets/me_common.dart';
import 'widgets/profile_header.dart';
import 'widgets/quick_grid.dart';
import 'widgets/settings_widgets.dart';

/// Tuya-style "Me" tab: profile header, quick grid, current home, help/about and sign out.
class MeScreen extends ConsumerWidget {
  const MeScreen({super.key});

  Future<void> _logout(BuildContext context, WidgetRef ref) async {
    final confirmed = await confirmDialog(
      context,
      title: context.tr(fr: 'Se déconnecter ?', en: 'Sign out?'),
      message: context.tr(fr: 'Vous devrez vous reconnecter pour accéder à vos appareils.', en: 'You will need to sign in again to access your devices.'),
      confirmLabel: context.tr(fr: 'Se déconnecter', en: 'Sign out'),
      destructive: true,
    );
    if (!confirmed) return;
    await ref.read(authProvider.notifier).logout();
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final user = ref.watch(authProvider).user;
    final home = ref.watch(currentHomeProvider);
    final unread = home == null ? 0 : (ref.watch(unreadCountProvider(home.id)).valueOrNull?.total ?? 0);
    return Scaffold(
      appBar: AppBar(title: Text(context.tr(fr: 'Moi', en: 'Me'))),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 4, 16, 32),
        children: [
          ProfileHeader(
            name: user?.displayName ?? context.tr(fr: 'Mon compte', en: 'My account'),
            email: user?.email ?? '',
            onTap: () => context.push(Routes.profile),
          ),
          const SizedBox(height: 16),
          QuickGrid(items: [
            QuickAction(icon: Icons.home_work_outlined, label: context.tr(fr: 'Gestion des maisons', en: 'Home management'), onTap: () => context.push(Routes.homes)),
            QuickAction(
              icon: Icons.notifications_outlined,
              label: context.tr(fr: 'Centre de messages', en: 'Message center'),
              badge: unread,
              color: SafeRColors.warning,
              onTap: () => context.push(Routes.messages),
            ),
            QuickAction(icon: Icons.extension_outlined, label: context.tr(fr: 'Intégrations', en: 'Integrations'), color: const Color(0xFF7C3AED), onTap: () => context.push(Routes.integrations)),
            QuickAction(icon: Icons.settings_outlined, label: context.tr(fr: 'Paramètres', en: 'Settings'), color: const Color(0xFF0891B2), onTap: () => context.push(Routes.settings)),
          ]),
          SectionHeader(title: context.tr(fr: 'Maison actuelle', en: 'Current home'), padding: const EdgeInsets.fromLTRB(4, 20, 4, 8)),
          if (home == null)
            NoHomeCard(onCreate: () => context.push(Routes.homes))
          else
            CurrentHomeCard(home: home, onMembers: () => context.push(Routes.members(home.id)), onManage: () => context.push(Routes.homes)),
          SectionHeader(title: context.tr(fr: 'Plus', en: 'More'), padding: const EdgeInsets.fromLTRB(4, 20, 4, 8)),
          GroupedCard(children: [
            SettingsTile(
              icon: Icons.help_outline,
              title: context.tr(fr: 'Aide & FAQ', en: 'Help & FAQ'),
              value: context.tr(fr: 'Guides et questions fréquentes', en: 'Guides and frequently asked questions'),
              onTap: () => openExternalLink(context, ref, kSafeRRepoUrl),
            ),
            SettingsTile(icon: Icons.info_outline, title: context.tr(fr: 'À propos', en: 'About'), value: 'SafeR ${AppConfig.version}', onTap: () => context.push(Routes.about)),
          ]),
          const SizedBox(height: 16),
          Card(
            clipBehavior: Clip.antiAlias,
            child: ListTile(
              key: const Key('me-logout'),
              leading: IconBox(icon: Icons.logout, color: theme.colorScheme.error, size: 36),
              title: Text(context.tr(fr: 'Se déconnecter', en: 'Sign out'), style: TextStyle(color: theme.colorScheme.error, fontWeight: FontWeight.w600)),
              onTap: () => _logout(context, ref),
            ),
          ),
          const SizedBox(height: 20),
          Center(
            child: Text(
              '${AppConfig.appName} · ${context.tr(fr: 'version', en: 'version')} ${AppConfig.version}',
              style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
            ),
          ),
        ],
      ),
    );
  }
}
