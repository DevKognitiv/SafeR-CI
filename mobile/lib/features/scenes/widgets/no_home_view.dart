import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/i18n.dart';
import '../../../core/models/home.dart';
import '../../../core/providers/providers.dart';
import '../../../core/routes.dart';
import '../../../core/widgets/widgets.dart';

/// Shown while homes load, on error, or when the user has no home yet.
class NoHomeView extends ConsumerWidget {
  const NoHomeView({super.key, required this.homes});

  final AsyncValue<List<Home>> homes;

  @override
  Widget build(BuildContext context, WidgetRef ref) => homes.when(
        loading: () => const LoadingView(),
        error: (error, _) => ErrorView(error: error, onRetry: () => ref.read(homesProvider.notifier).refresh()),
        data: (_) => EmptyState(
          icon: Icons.home_work_outlined,
          title: context.tr(fr: 'Créez votre première maison', en: 'Create your first home'),
          subtitle: context.tr(fr: 'Les scènes et automatisations sont liées à une maison.', en: 'Scenes and automations belong to a home.'),
          actionLabel: context.tr(fr: 'Créer une maison', en: 'Create a home'),
          onAction: () => context.push(Routes.homes),
        ),
      );
}

/// Shown when a plain member opens "new scene / new automation" (admin-only on the hub).
class AdminOnlyEditorView extends StatelessWidget {
  const AdminOnlyEditorView({super.key});

  @override
  Widget build(BuildContext context) => EmptyState(
        key: const Key('scenes-admin-only'),
        icon: Icons.lock_outline,
        title: context.tr(fr: 'Réservé aux administrateurs', en: 'Administrators only'),
        subtitle: context.tr(
          fr: 'Seuls les administrateurs et le propriétaire peuvent créer des scènes et des automatisations.',
          en: 'Only administrators and the owner can create scenes and automations.',
        ),
        actionLabel: context.tr(fr: 'Retour', en: 'Back'),
        onAction: () => context.canPop() ? context.pop() : context.go(Routes.scenes),
      );
}

/// Replaces the Save bar for members: the editor is read-only.
class ReadOnlyEditorBar extends StatelessWidget {
  const ReadOnlyEditorBar({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return SafeArea(
      minimum: const EdgeInsets.fromLTRB(16, 8, 16, 16),
      child: Row(
        key: const Key('scenes-read-only'),
        children: [
          Icon(Icons.lock_outline, size: 18, color: theme.colorScheme.onSurfaceVariant),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              context.tr(fr: 'Lecture seule : seuls les administrateurs peuvent modifier.', en: 'Read-only: only administrators can edit.'),
              style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
            ),
          ),
        ],
      ),
    );
  }
}
