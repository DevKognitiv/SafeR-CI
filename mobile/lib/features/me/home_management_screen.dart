import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/i18n.dart';
import '../../core/models/home.dart';
import '../../core/providers/providers.dart';
import '../../core/router.dart';
import '../../core/widgets/widgets.dart';
import 'widgets/home_form_sheet.dart';
import 'widgets/home_tile.dart';
import 'widgets/me_common.dart';

/// Tuya-style "Home management": list of homes, switch the current one, create/edit/delete.
class HomeManagementScreen extends ConsumerWidget {
  const HomeManagementScreen({super.key});

  Future<void> _create(BuildContext context, WidgetRef ref) async {
    final result = await showHomeFormSheet(context);
    if (result == null || !context.mounted) return;
    try {
      final home = await ref.read(homesProvider.notifier).create(name: result.name, address: result.address, lat: result.lat, lon: result.lon, rooms: result.rooms);
      if (!context.mounted) return;
      showSnack(context, context.tr(fr: 'Maison « ${home.name} » créée', en: 'Home "${home.name}" created'));
    } catch (e) {
      if (context.mounted) showErrorSnack(context, errorMessage(e));
    }
  }

  Future<void> _edit(BuildContext context, WidgetRef ref, Home home) async {
    final result = await showHomeFormSheet(context, initial: home);
    if (result == null || !context.mounted) return;
    try {
      await ref.read(homesProvider.notifier).updateHome(home.id, name: result.name, address: result.address ?? '', lat: result.lat, lon: result.lon);
      if (!context.mounted) return;
      showSnack(context, context.tr(fr: 'Maison mise à jour', en: 'Home updated'));
    } catch (e) {
      if (context.mounted) showErrorSnack(context, errorMessage(e));
    }
  }

  Future<void> _delete(BuildContext context, WidgetRef ref, Home home) async {
    final confirmed = await confirmDialog(
      context,
      title: context.tr(fr: 'Supprimer « ${home.name} » ?', en: 'Delete "${home.name}"?'),
      message: context.tr(
        fr: 'Les pièces, appareils, scènes et messages de cette maison seront supprimés. Cette action est irréversible.',
        en: 'Rooms, devices, scenes and messages of this home will be deleted. This cannot be undone.',
      ),
      confirmLabel: context.tr(fr: 'Supprimer', en: 'Delete'),
      destructive: true,
    );
    if (!confirmed || !context.mounted) return;
    try {
      await ref.read(homesProvider.notifier).delete(home.id);
      if (!context.mounted) return;
      showSnack(context, context.tr(fr: 'Maison supprimée', en: 'Home deleted'));
    } catch (e) {
      if (context.mounted) showErrorSnack(context, errorMessage(e));
    }
  }

  Future<void> _leave(BuildContext context, WidgetRef ref, Home home) async {
    final confirmed = await confirmDialog(
      context,
      title: context.tr(fr: 'Quitter « ${home.name} » ?', en: 'Leave "${home.name}"?'),
      message: context.tr(
        fr: "Vous n'aurez plus accès à cette maison ni à ses appareils. Un administrateur pourra vous réinviter.",
        en: 'You will lose access to this home and its devices. An administrator can invite you again.',
      ),
      confirmLabel: context.tr(fr: 'Quitter', en: 'Leave'),
      destructive: true,
    );
    if (!confirmed || !context.mounted) return;
    try {
      await ref.read(homesProvider.notifier).leave(home.id);
      if (!context.mounted) return;
      showSnack(context, context.tr(fr: 'Vous avez quitté « ${home.name} »', en: 'You left "${home.name}"'));
    } catch (e) {
      if (context.mounted) showErrorSnack(context, errorMessage(e));
    }
  }

  void _select(BuildContext context, WidgetRef ref, Home home) {
    if (ref.read(currentHomeIdProvider) == home.id) return;
    ref.read(currentHomeIdProvider.notifier).set(home.id);
    showSnack(context, context.tr(fr: '« ${home.name} » est maintenant la maison actuelle', en: '"${home.name}" is now the current home'));
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final homes = ref.watch(homesProvider);
    final currentId = ref.watch(currentHomeProvider)?.id;
    return Scaffold(
      appBar: AppBar(
        title: Text(context.tr(fr: 'Gestion des maisons', en: 'Home management')),
        actions: [
          IconButton(
            tooltip: context.tr(fr: 'Créer une maison', en: 'Create a home'),
            onPressed: () => _create(context, ref),
            icon: const Icon(Icons.add_home_outlined),
          ),
        ],
      ),
      body: homes.when(
        loading: () => const LoadingView(),
        error: (error, _) => ErrorView(error: error, onRetry: () => ref.read(homesProvider.notifier).refresh()),
        data: (list) {
          if (list.isEmpty) {
            return EmptyState(
              icon: Icons.home_work_outlined,
              title: context.tr(fr: 'Aucune maison', en: 'No home yet'),
              subtitle: context.tr(fr: 'Créez votre première maison pour y ajouter des pièces et des appareils.', en: 'Create your first home to add rooms and devices.'),
              actionLabel: context.tr(fr: 'Créer une maison', en: 'Create a home'),
              onAction: () => _create(context, ref),
            );
          }
          return RefreshIndicator(
            onRefresh: () => ref.read(homesProvider.notifier).refresh(),
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
                      context.tr(fr: 'Touchez une maison pour en faire la maison actuelle.', en: 'Tap a home to make it the current one.'),
                      textAlign: TextAlign.center,
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(color: Theme.of(context).colorScheme.onSurfaceVariant),
                    ),
                  );
                }
                final home = list[index];
                return HomeTile(
                  home: home,
                  selected: home.id == currentId,
                  onTap: () => _select(context, ref, home),
                  onMembers: () => context.push(Routes.members(home.id)),
                  onEdit: home.canManage ? () => _edit(context, ref, home) : null,
                  onDelete: home.isOwner ? () => _delete(context, ref, home) : null,
                  onLeave: home.isOwner ? null : () => _leave(context, ref, home),
                );
              },
            ),
          );
        },
      ),
      bottomNavigationBar: (homes.valueOrNull?.isEmpty ?? true)
          ? null
          : SafeArea(
              minimum: const EdgeInsets.fromLTRB(16, 8, 16, 16),
              child: FilledButton.icon(
                key: const Key('homes-create'),
                onPressed: () => _create(context, ref),
                icon: const Icon(Icons.add),
                label: Text(context.tr(fr: 'Créer une maison', en: 'Create a home')),
              ),
            ),
    );
  }
}
