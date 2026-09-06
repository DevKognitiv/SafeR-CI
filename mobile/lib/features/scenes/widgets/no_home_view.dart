import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/i18n.dart';
import '../../../core/models/home.dart';
import '../../../core/providers/providers.dart';
import '../../../core/router.dart';
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
