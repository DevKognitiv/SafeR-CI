import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../../core/i18n.dart';
import '../../../core/routes.dart';
import '../../../core/widgets/widgets.dart';

/// Shown to plain members: adding devices is reserved to admins and the owner.
class AdminOnlyView extends StatelessWidget {
  const AdminOnlyView({super.key});

  @override
  Widget build(BuildContext context) => EmptyState(
        key: const Key('add-device-admin-only'),
        icon: Icons.lock_outline,
        title: context.tr(fr: 'Réservé aux administrateurs', en: 'Administrators only'),
        subtitle: context.tr(
          fr: "Seuls les administrateurs et le propriétaire peuvent ajouter des appareils à cette maison.",
          en: 'Only administrators and the owner can add devices to this home.',
        ),
        actionLabel: context.tr(fr: 'Retour', en: 'Back'),
        onAction: () => context.canPop() ? context.pop() : context.go(Routes.home),
      );
}

