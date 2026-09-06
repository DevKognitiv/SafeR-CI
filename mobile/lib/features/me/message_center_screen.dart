import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/i18n.dart';
import '../../core/models/message.dart';
import '../../core/providers/providers.dart';
import '../../core/router.dart';
import '../../core/widgets/widgets.dart';
import 'widgets/me_common.dart';
import 'widgets/message_tile.dart';

/// Tuya-style message center: Alarmes / Maison / Notifications tabs over the home's messages.
class MessageCenterScreen extends ConsumerStatefulWidget {
  const MessageCenterScreen({super.key, this.initialKind});

  /// `alarm` | `home` | `notice` — selects the initial tab.
  final String? initialKind;

  @override
  ConsumerState<MessageCenterScreen> createState() => _MessageCenterScreenState();
}

class _MessageCenterScreenState extends ConsumerState<MessageCenterScreen> with SingleTickerProviderStateMixin {
  late final TabController _tabs;

  @override
  void initState() {
    super.initState();
    final index = kMessageKinds.indexOf(widget.initialKind ?? '');
    _tabs = TabController(length: kMessageKinds.length, vsync: this, initialIndex: index < 0 ? 0 : index);
    _tabs.addListener(() {
      if (!_tabs.indexIsChanging) setState(() {});
    });
  }

  @override
  void dispose() {
    _tabs.dispose();
    super.dispose();
  }

  String get _kind => kMessageKinds[_tabs.index];

  Future<void> _open(String homeId, HubMessage message) async {
    if (!message.read) {
      try {
        await ref.read(messagesProvider(homeId).notifier).markRead(message.id);
      } catch (e) {
        if (mounted) showErrorSnack(context, errorMessage(e));
      }
    }
    final deviceId = message.deviceId;
    if (deviceId != null && deviceId.isNotEmpty && mounted) context.push(Routes.device(deviceId));
  }

  Future<void> _delete(String homeId, HubMessage message) async {
    try {
      await ref.read(messagesProvider(homeId).notifier).delete(message.id);
      if (mounted) showSnack(context, context.tr(fr: 'Message supprimé', en: 'Message deleted'));
    } catch (e) {
      if (mounted) showErrorSnack(context, errorMessage(e));
    }
  }

  Future<void> _markAllRead(String homeId) async {
    try {
      await ref.read(messagesProvider(homeId).notifier).markAllRead(kind: _kind);
      if (mounted) showSnack(context, context.tr(fr: 'Messages marqués comme lus', en: 'Messages marked as read'));
    } catch (e) {
      if (mounted) showErrorSnack(context, errorMessage(e));
    }
  }

  Future<void> _clear(String homeId) async {
    final label = messageKindLabel(context, _kind).toLowerCase();
    final confirmed = await confirmDialog(
      context,
      title: context.tr(fr: 'Effacer les messages ?', en: 'Clear messages?'),
      message: context.tr(fr: 'Tous les messages de l\'onglet « $label » seront supprimés.', en: 'All messages in the "$label" tab will be deleted.'),
      confirmLabel: context.tr(fr: 'Effacer', en: 'Clear'),
      destructive: true,
    );
    if (!confirmed || !mounted) return;
    try {
      await ref.read(messagesProvider(homeId).notifier).clear(kind: _kind);
      if (mounted) showSnack(context, context.tr(fr: 'Messages effacés', en: 'Messages cleared'));
    } catch (e) {
      if (mounted) showErrorSnack(context, errorMessage(e));
    }
  }

  @override
  Widget build(BuildContext context) {
    final home = ref.watch(currentHomeProvider);
    if (home == null) {
      return Scaffold(appBar: AppBar(title: Text(context.tr(fr: 'Centre de messages', en: 'Message center'))), body: const NoHomeView());
    }
    final homeId = home.id;
    final messages = ref.watch(messagesProvider(homeId));
    final all = messages.valueOrNull ?? const <HubMessage>[];
    final hasUnreadInTab = all.any((m) => m.kind == _kind && !m.read);
    final hasAnyInTab = all.any((m) => m.kind == _kind);
    return Scaffold(
      appBar: AppBar(
        title: Text(context.tr(fr: 'Centre de messages', en: 'Message center')),
        actions: [
          IconButton(
            key: const Key('messages-read-all'),
            tooltip: context.tr(fr: 'Tout marquer lu', en: 'Mark all as read'),
            onPressed: hasUnreadInTab ? () => _markAllRead(homeId) : null,
            icon: const Icon(Icons.done_all),
          ),
          IconButton(
            key: const Key('messages-clear'),
            tooltip: context.tr(fr: 'Effacer', en: 'Clear'),
            onPressed: hasAnyInTab ? () => _clear(homeId) : null,
            icon: const Icon(Icons.delete_sweep_outlined),
          ),
        ],
        bottom: TabBar(
          controller: _tabs,
          tabs: [
            for (final kind in kMessageKinds)
              Tab(
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(messageKindLabel(context, kind)),
                    if (all.any((m) => m.kind == kind && !m.read)) ...[
                      const SizedBox(width: 6),
                      Badge.count(
                        count: all.where((m) => m.kind == kind && !m.read).length,
                        backgroundColor: Theme.of(context).colorScheme.error,
                      ),
                    ],
                  ],
                ),
              ),
          ],
        ),
      ),
      body: messages.when(
        loading: () => const LoadingView(),
        error: (error, _) => ErrorView(error: error, onRetry: () => ref.read(messagesProvider(homeId).notifier).refresh()),
        data: (list) => TabBarView(
          controller: _tabs,
          children: [
            for (final kind in kMessageKinds)
              _MessageList(
                kind: kind,
                messages: list.where((m) => m.kind == kind).toList(),
                onRefresh: () => ref.read(messagesProvider(homeId).notifier).refresh(),
                onOpen: (m) => _open(homeId, m),
                onDelete: (m) => _delete(homeId, m),
              ),
          ],
        ),
      ),
    );
  }
}

class _MessageList extends StatelessWidget {
  const _MessageList({required this.kind, required this.messages, required this.onRefresh, required this.onOpen, required this.onDelete});

  final String kind;
  final List<HubMessage> messages;
  final Future<void> Function() onRefresh;
  final ValueChanged<HubMessage> onOpen;
  final ValueChanged<HubMessage> onDelete;

  @override
  Widget build(BuildContext context) {
    if (messages.isEmpty) {
      return RefreshIndicator(
        onRefresh: onRefresh,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          children: [
            SizedBox(
              height: MediaQuery.sizeOf(context).height * 0.6,
              child: EmptyState(
                icon: messageKindIcon(kind),
                title: switch (kind) {
                  'alarm' => context.tr(fr: 'Aucune alarme', en: 'No alarms'),
                  'home' => context.tr(fr: 'Aucun message de la maison', en: 'No home messages'),
                  _ => context.tr(fr: 'Aucune notification', en: 'No notifications'),
                },
                subtitle: switch (kind) {
                  'alarm' => context.tr(fr: 'Les alertes des capteurs et de la centrale apparaîtront ici.', en: 'Sensor and panel alerts will appear here.'),
                  'home' => context.tr(fr: 'Ajouts d\'appareils, membres et changements de mode.', en: 'Device additions, members and mode changes.'),
                  _ => context.tr(fr: 'Les informations SafeR apparaîtront ici.', en: 'SafeR notices will appear here.'),
                },
                actionLabel: context.tr(fr: 'Actualiser', en: 'Refresh'),
                onAction: onRefresh,
              ),
            ),
          ],
        ),
      );
    }
    return RefreshIndicator(
      onRefresh: onRefresh,
      child: ListView.separated(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.symmetric(vertical: 8),
        itemCount: messages.length,
        separatorBuilder: (_, __) => const Divider(height: 1, indent: 72),
        itemBuilder: (context, index) {
          final message = messages[index];
          return MessageTile(message: message, onTap: () => onOpen(message), onDelete: () => onDelete(message));
        },
      ),
    );
  }
}
