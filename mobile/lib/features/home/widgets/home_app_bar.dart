import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/i18n.dart';
import '../../../core/models/home.dart';
import '../../../core/providers/providers.dart';
import '../../../core/router.dart';
import 'home_switcher_sheet.dart';

/// Home tab app bar: home switcher · "+" menu · message-center bell.
class HomeAppBar extends StatelessWidget implements PreferredSizeWidget {
  const HomeAppBar({super.key, required this.home});

  final Home home;

  @override
  Size get preferredSize => const Size.fromHeight(kToolbarHeight);

  @override
  Widget build(BuildContext context) => AppBar(
        titleSpacing: 8,
        title: HomeSwitcherButton(home: home),
        actions: [
          const AddMenuButton(),
          MessageBell(homeId: home.id),
          const SizedBox(width: 4),
        ],
      );
}

/// Tapping the home name opens the home switcher sheet.
class HomeSwitcherButton extends StatelessWidget {
  const HomeSwitcherButton({super.key, required this.home});

  final Home home;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Align(
      alignment: AlignmentDirectional.centerStart,
      child: Semantics(
        button: true,
        label: context.tr(fr: 'Changer de maison', en: 'Switch home'),
        child: InkWell(
          borderRadius: BorderRadius.circular(12),
          onTap: () => showHomeSwitcher(context),
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: 44),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Flexible(
                    child: Text(
                      home.name,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700),
                    ),
                  ),
                  const SizedBox(width: 2),
                  const Icon(Icons.expand_more, size: 22),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

enum _AddAction { device, scan, rooms }

/// "+" menu: add device · scan code · manage rooms.
class AddMenuButton extends StatelessWidget {
  const AddMenuButton({super.key});

  @override
  Widget build(BuildContext context) => PopupMenuButton<_AddAction>(
        icon: const Icon(Icons.add),
        tooltip: context.tr(fr: 'Ajouter', en: 'Add'),
        position: PopupMenuPosition.under,
        onSelected: (action) {
          switch (action) {
            case _AddAction.device:
              context.push(Routes.addDevice);
            case _AddAction.scan:
              context.push(Routes.scan);
            case _AddAction.rooms:
              context.push(Routes.rooms);
          }
        },
        itemBuilder: (context) => [
          PopupMenuItem(
            value: _AddAction.device,
            child: ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.add_circle_outline),
              title: Text(context.tr(fr: 'Ajouter un appareil', en: 'Add device')),
            ),
          ),
          PopupMenuItem(
            value: _AddAction.scan,
            child: ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.qr_code_scanner),
              title: Text(context.tr(fr: 'Scanner un code', en: 'Scan a code')),
            ),
          ),
          PopupMenuItem(
            value: _AddAction.rooms,
            child: ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.meeting_room_outlined),
              title: Text(context.tr(fr: 'Gérer les pièces', en: 'Manage rooms')),
            ),
          ),
        ],
      );
}

/// Bell with the unread badge -> message center.
class MessageBell extends ConsumerWidget {
  const MessageBell({super.key, required this.homeId});

  final String homeId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final unread = ref.watch(unreadCountProvider(homeId)).value?.total ?? 0;
    return IconButton(
      tooltip: context.tr(fr: 'Centre de messages', en: 'Message center'),
      onPressed: () => context.push(Routes.messages),
      icon: Badge(
        isLabelVisible: unread > 0,
        label: Text(unread > 99 ? '99+' : '$unread'),
        child: const Icon(Icons.notifications_outlined),
      ),
    );
  }
}
