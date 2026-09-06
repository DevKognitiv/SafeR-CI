import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/i18n.dart';
import '../../core/providers/providers.dart';
import '../../core/theme.dart';

/// Bottom navigation shell: Home · Scenes · Security · Me (Tuya-style).
class MainShell extends ConsumerWidget {
  const MainShell({super.key, required this.navigationShell});

  final StatefulNavigationShell navigationShell;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final home = ref.watch(currentHomeProvider);
    final unread = home == null ? null : ref.watch(unreadCountProvider(home.id)).valueOrNull;
    final alarm = home?.alarmActive ?? false;
    return Scaffold(
      body: navigationShell,
      bottomNavigationBar: NavigationBar(
        selectedIndex: navigationShell.currentIndex,
        onDestinationSelected: (index) => navigationShell.goBranch(index, initialLocation: index == navigationShell.currentIndex),
        destinations: [
          NavigationDestination(icon: const Icon(Icons.home_outlined), selectedIcon: const Icon(Icons.home), label: context.tr(fr: 'Accueil', en: 'Home')),
          NavigationDestination(icon: const Icon(Icons.auto_awesome_outlined), selectedIcon: const Icon(Icons.auto_awesome), label: context.tr(fr: 'Scènes', en: 'Scenes')),
          NavigationDestination(
            icon: Badge(isLabelVisible: alarm, backgroundColor: SafeRColors.danger, child: const Icon(Icons.shield_outlined)),
            selectedIcon: Badge(isLabelVisible: alarm, backgroundColor: SafeRColors.danger, child: const Icon(Icons.shield)),
            label: context.tr(fr: 'Sécurité', en: 'Security'),
          ),
          NavigationDestination(
            icon: Badge(isLabelVisible: (unread?.total ?? 0) > 0, label: Text('${unread?.total ?? 0}'), child: const Icon(Icons.person_outline)),
            selectedIcon: Badge(isLabelVisible: (unread?.total ?? 0) > 0, label: Text('${unread?.total ?? 0}'), child: const Icon(Icons.person)),
            label: context.tr(fr: 'Moi', en: 'Me'),
          ),
        ],
      ),
    );
  }
}
