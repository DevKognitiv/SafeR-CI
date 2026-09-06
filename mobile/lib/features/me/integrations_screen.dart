import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/i18n.dart';
import '../../core/models/home.dart';
import '../../core/providers/providers.dart';
import '../../core/router.dart';
import '../../core/widgets/widgets.dart';
import 'widgets/integration_tile.dart';
import 'widgets/me_common.dart';

/// Cloud/bridge accounts linked to the current home (Tuya Cloud, Matter server, Home Assistant...).
class IntegrationsScreen extends ConsumerWidget {
  const IntegrationsScreen({super.key});

  Future<void> _delete(BuildContext context, WidgetRef ref, String homeId, Integration integration) async {
    final confirmed = await confirmDialog(
      context,
      title: context.tr(fr: 'Supprimer « ${integration.name} » ?', en: 'Delete "${integration.name}"?'),
      message: context.tr(
        fr: 'Les appareils liés à cette intégration ne seront plus mis à jour ni contrôlables.',
        en: 'Devices linked to this integration will no longer update or be controllable.',
      ),
      confirmLabel: context.tr(fr: 'Supprimer', en: 'Delete'),
      destructive: true,
    );
    if (!confirmed || !context.mounted) return;
    try {
      await ref.read(hubClientProvider).deleteIntegration(integration.id);
      ref.invalidate(integrationsProvider(homeId));
      ref.invalidate(devicesProvider(homeId));
      if (!context.mounted) return;
      showSnack(context, context.tr(fr: 'Intégration supprimée', en: 'Integration deleted'));
    } catch (e) {
      if (context.mounted) showErrorSnack(context, errorMessage(e));
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final home = ref.watch(currentHomeProvider);
    final title = Text(context.tr(fr: 'Intégrations', en: 'Integrations'));
    if (home == null) return Scaffold(appBar: AppBar(title: title), body: const NoHomeView());
    final homeId = home.id;
    final integrations = ref.watch(integrationsProvider(homeId));
    // Brand catalogue for icons/colours; the tiles rebuild once it arrives.
    ref.watch(brandsProvider);
    return Scaffold(
      appBar: AppBar(
        title: title,
        actions: [
          IconButton(
            key: const Key('integrations-add'),
            tooltip: context.tr(fr: 'Ajouter', en: 'Add'),
            onPressed: () => context.push(Routes.addDevice),
            icon: const Icon(Icons.add),
          ),
        ],
      ),
      body: integrations.when(
        loading: () => const LoadingView(),
        error: (error, _) => ErrorView(error: error, onRetry: () => ref.invalidate(integrationsProvider(homeId))),
        data: (list) {
          if (list.isEmpty) {
            return EmptyState(
              icon: Icons.extension_outlined,
              title: context.tr(fr: 'Aucune intégration', en: 'No integrations'),
              subtitle: context.tr(
                fr: 'Liez un compte Tuya Cloud, un serveur Matter ou Home Assistant en ajoutant un appareil.',
                en: 'Link a Tuya Cloud account, a Matter server or Home Assistant by adding a device.',
              ),
              actionLabel: context.tr(fr: 'Ajouter un appareil', en: 'Add a device'),
              onAction: () => context.push(Routes.addDevice),
            );
          }
          return RefreshIndicator(
            onRefresh: () async => ref.invalidate(integrationsProvider(homeId)),
            child: ListView.separated(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
              itemCount: list.length + 1,
              separatorBuilder: (_, __) => const SizedBox(height: 12),
              itemBuilder: (context, index) {
                if (index == list.length) {
                  return Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Text(
                      context.tr(fr: 'Les identifiants sont chiffrés sur le hub et ne sont jamais affichés.', en: 'Credentials are encrypted on the hub and never displayed.'),
                      textAlign: TextAlign.center,
                      style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                    ),
                  );
                }
                final integration = list[index];
                return IntegrationTile(
                  integration: integration,
                  brand: ref.watch(brandProvider(integration.brand)),
                  onDelete: () => _delete(context, ref, homeId, integration),
                );
              },
            ),
          );
        },
      ),
    );
  }
}
