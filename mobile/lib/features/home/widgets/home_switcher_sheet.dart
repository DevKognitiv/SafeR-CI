import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/i18n.dart';
import '../../../core/models/home.dart';
import '../../../core/providers/providers.dart';
import '../../../core/router.dart';
import '../../../core/widgets/widgets.dart';

/// Tuya-style home switcher: bottom sheet listing the user's homes + "Manage homes".
Future<void> showHomeSwitcher(BuildContext context) async {
  final result = await showModalBottomSheet<_SwitcherResult>(
    context: context,
    showDragHandle: true,
    builder: (_) => const _HomeSwitcherSheet(),
  );
  if (result == null || !context.mounted) return;
  if (result.manage) context.push(Routes.homes);
}

class _SwitcherResult {
  const _SwitcherResult({this.manage = false});

  final bool manage;
}

class _HomeSwitcherSheet extends ConsumerWidget {
  const _HomeSwitcherSheet();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final homes = ref.watch(homesProvider);
    final currentId = ref.watch(currentHomeProvider)?.id;
    final theme = Theme.of(context);
    return SafeArea(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 0, 20, 8),
            child: Text(context.tr(fr: 'Mes maisons', en: 'My homes'), style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
          ),
          Flexible(
            child: homes.when(
              loading: () => const Padding(padding: EdgeInsets.all(24), child: LoadingView()),
              error: (e, _) => ErrorView(error: e, onRetry: () => ref.read(homesProvider.notifier).refresh()),
              data: (list) => list.isEmpty
                  ? Padding(
                      padding: const EdgeInsets.all(24),
                      child: Text(context.tr(fr: 'Aucune maison pour le moment', en: 'No home yet'), textAlign: TextAlign.center),
                    )
                  : ListView(
                      shrinkWrap: true,
                      children: [for (final home in list) _HomeRow(home: home, selected: home.id == currentId)],
                    ),
            ),
          ),
          const Divider(),
          ListTile(
            leading: const Icon(Icons.home_work_outlined),
            title: Text(context.tr(fr: 'Gérer les maisons', en: 'Manage homes')),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => Navigator.of(context).pop(const _SwitcherResult(manage: true)),
          ),
          const SizedBox(height: 8),
        ],
      ),
    );
  }
}

class _HomeRow extends ConsumerWidget {
  const _HomeRow({required this.home, required this.selected});

  final Home home;
  final bool selected;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final count = home.deviceCount;
    final subtitle = home.address?.isNotEmpty == true
        ? home.address!
        : context.tr(fr: count == 1 ? '1 appareil' : '$count appareils', en: count == 1 ? '1 device' : '$count devices');
    return ListTile(
      leading: CircleAvatar(
        backgroundColor: theme.colorScheme.primary.withValues(alpha: 0.12),
        child: Icon(Icons.home_rounded, color: theme.colorScheme.primary),
      ),
      title: Text(home.name, style: TextStyle(fontWeight: selected ? FontWeight.w700 : FontWeight.w500)),
      subtitle: Text(subtitle, maxLines: 1, overflow: TextOverflow.ellipsis),
      trailing: selected ? Icon(Icons.check_circle, color: theme.colorScheme.primary) : null,
      selected: selected,
      onTap: () {
        ref.read(currentHomeIdProvider.notifier).set(home.id);
        Navigator.of(context).pop(const _SwitcherResult());
      },
    );
  }
}
