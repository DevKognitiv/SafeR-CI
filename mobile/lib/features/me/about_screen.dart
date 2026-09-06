import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/config.dart';
import '../../core/i18n.dart';
import '../../core/providers/providers.dart';
import '../../core/widgets/widgets.dart';
import 'widgets/me_common.dart';
import 'widgets/safer_logo.dart';
import 'widgets/settings_widgets.dart';

/// About SafeR: logo, version, description, supported brands, licences and credits.
class AboutScreen extends ConsumerWidget {
  const AboutScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final muted = theme.colorScheme.onSurfaceVariant;
    final brands = ref.watch(brandsProvider);
    return Scaffold(
      appBar: AppBar(title: Text(context.tr(fr: 'À propos', en: 'About'))),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
        children: [
          const Center(child: SafeRLogo()),
          const SizedBox(height: 16),
          Text(AppConfig.appName, textAlign: TextAlign.center, style: theme.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800)),
          const SizedBox(height: 4),
          Text(
            context.tr(fr: 'Version ${AppConfig.version}', en: 'Version ${AppConfig.version}'),
            key: const Key('about-version'),
            textAlign: TextAlign.center,
            style: theme.textTheme.bodyMedium?.copyWith(color: muted),
          ),
          const SizedBox(height: 16),
          Text(
            context.tr(
              fr: 'SafeR réunit vos caméras, alarmes, capteurs et prises connectées dans une seule application, quelle que soit la marque, avec le bouton SOS de SafeR CI pour alerter vos proches en cas d\'urgence.',
              en: 'SafeR brings your cameras, alarms, sensors and smart plugs together in one app, whatever the brand, with the SafeR CI SOS button to alert your relatives in an emergency.',
            ),
            textAlign: TextAlign.center,
            style: theme.textTheme.bodyMedium,
          ),
          SectionHeader(title: context.tr(fr: 'Marques compatibles', en: 'Supported brands'), padding: const EdgeInsets.fromLTRB(4, 24, 4, 8)),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: brands.when(
                loading: () => const SizedBox(height: 56, child: LoadingView()),
                error: (error, _) => Column(
                  children: [
                    Text(errorMessage(error), style: theme.textTheme.bodySmall?.copyWith(color: muted), textAlign: TextAlign.center),
                    const SizedBox(height: 8),
                    OutlinedButton.icon(onPressed: () => ref.invalidate(brandsProvider), icon: const Icon(Icons.refresh), label: Text(context.tr(fr: 'Réessayer', en: 'Retry'))),
                  ],
                ),
                data: (list) => list.isEmpty
                    ? Text(context.tr(fr: 'Aucune marque disponible sur ce hub.', en: 'No brand available on this hub.'), style: theme.textTheme.bodySmall?.copyWith(color: muted))
                    : Wrap(
                        spacing: 8,
                        runSpacing: 8,
                        children: [
                          for (final brand in list)
                            Chip(
                              avatar: Icon(iconFromName(brand.icon, fallback: Icons.devices_other), size: 18, color: colorFromHex(brand.color)),
                              label: Text(brand.name),
                              backgroundColor: colorFromHex(brand.color).withValues(alpha: 0.10),
                            ),
                        ],
                      ),
              ),
            ),
          ),
          SectionHeader(title: context.tr(fr: 'Liens', en: 'Links'), padding: const EdgeInsets.fromLTRB(4, 24, 4, 8)),
          GroupedCard(children: [
            SettingsTile(
              icon: Icons.code,
              title: context.tr(fr: 'Code source', en: 'Source code'),
              value: 'github.com/DevKognitiv/SafeR-CI',
              onTap: () => openExternalLink(context, ref, kSafeRRepoUrl),
            ),
            SettingsTile(
              icon: Icons.bug_report_outlined,
              title: context.tr(fr: 'Signaler un problème', en: 'Report an issue'),
              onTap: () => openExternalLink(context, ref, kSafeRIssuesUrl),
            ),
            SettingsTile(
              key: const Key('about-licenses'),
              icon: Icons.description_outlined,
              title: context.tr(fr: 'Licences open source', en: 'Open source licences'),
              value: context.tr(fr: 'Bibliothèques utilisées par l\'application', en: 'Libraries used by the app'),
              onTap: () => showLicensePage(context: context, applicationName: AppConfig.appName, applicationVersion: AppConfig.version),
            ),
          ]),
          const SizedBox(height: 28),
          Text(
            context.tr(fr: 'Conçu avec ❤ par SafeR CI · Abidjan, Côte d\'Ivoire', en: 'Made with ❤ by SafeR CI · Abidjan, Côte d\'Ivoire'),
            textAlign: TextAlign.center,
            style: theme.textTheme.bodySmall?.copyWith(color: muted),
          ),
          const SizedBox(height: 4),
          Text('© ${DateTime.now().year} SafeR CI', textAlign: TextAlign.center, style: theme.textTheme.bodySmall?.copyWith(color: muted)),
        ],
      ),
    );
  }
}
