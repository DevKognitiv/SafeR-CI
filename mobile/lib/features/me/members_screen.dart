import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/i18n.dart';
import '../../core/models/home.dart';
import '../../core/providers/providers.dart';
import '../../core/widgets/widgets.dart';
import 'widgets/me_common.dart';
import 'widgets/member_dialogs.dart';
import 'widgets/member_tile.dart';

/// Members of a home: list with roles; owner/admin can invite, change roles and remove.
class MembersScreen extends ConsumerWidget {
  const MembersScreen({super.key, required this.homeId});

  final String homeId;

  Home? _home(WidgetRef ref) {
    for (final h in ref.watch(homesProvider).valueOrNull ?? const <Home>[]) {
      if (h.id == homeId) return h;
    }
    return null;
  }

  void _refresh(WidgetRef ref) {
    ref.invalidate(membersProvider(homeId));
    ref.read(homesProvider.notifier).refresh();
  }

  Future<void> _add(BuildContext context, WidgetRef ref) async {
    final value = await showAddMemberDialog(context);
    if (value == null || !context.mounted) return;
    try {
      await ref.read(hubClientProvider).addMember(homeId, value.email, role: value.role);
      _refresh(ref);
      if (!context.mounted) return;
      showSnack(context, context.tr(fr: '${value.email} ajouté à la maison', en: '${value.email} added to the home'));
    } catch (e) {
      if (context.mounted) showErrorSnack(context, memberErrorMessage(context, e));
    }
  }

  Future<void> _changeRole(BuildContext context, WidgetRef ref, Member member) async {
    final role = await showRolePickerSheet(context, current: member.role);
    if (role == null || role == member.role || !context.mounted) return;
    try {
      await ref.read(hubClientProvider).updateMember(homeId, member.userId, role);
      ref.invalidate(membersProvider(homeId));
      if (!context.mounted) return;
      showSnack(context, context.tr(fr: 'Rôle mis à jour', en: 'Role updated'));
    } catch (e) {
      if (context.mounted) showErrorSnack(context, memberErrorMessage(context, e));
    }
  }

  Future<void> _remove(BuildContext context, WidgetRef ref, Member member) async {
    final name = member.name.isEmpty ? member.email : member.name;
    final confirmed = await confirmDialog(
      context,
      title: context.tr(fr: 'Retirer $name ?', en: 'Remove $name?'),
      message: context.tr(fr: 'Cette personne n\'aura plus accès à la maison et à ses appareils.', en: 'This person will no longer have access to the home and its devices.'),
      confirmLabel: context.tr(fr: 'Retirer', en: 'Remove'),
      destructive: true,
    );
    if (!confirmed || !context.mounted) return;
    try {
      await ref.read(hubClientProvider).removeMember(homeId, member.userId);
      _refresh(ref);
      if (!context.mounted) return;
      showSnack(context, context.tr(fr: 'Membre retiré', en: 'Member removed'));
    } catch (e) {
      if (context.mounted) showErrorSnack(context, memberErrorMessage(context, e));
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final home = _home(ref);
    final canManage = home?.canManage ?? false;
    final myId = ref.watch(authProvider).user?.id;
    final members = ref.watch(membersProvider(homeId));
    return Scaffold(
      appBar: AppBar(
        title: Text(home == null ? context.tr(fr: 'Membres', en: 'Members') : context.tr(fr: 'Membres · ${home.name}', en: 'Members · ${home.name}')),
        actions: [
          if (canManage)
            IconButton(
              key: const Key('members-add'),
              tooltip: context.tr(fr: 'Ajouter un membre', en: 'Add a member'),
              onPressed: () => _add(context, ref),
              icon: const Icon(Icons.person_add_alt_1_outlined),
            ),
        ],
      ),
      body: members.when(
        loading: () => const LoadingView(),
        error: (error, _) => ErrorView(error: error, onRetry: () => ref.invalidate(membersProvider(homeId))),
        data: (list) {
          if (list.isEmpty) {
            return EmptyState(
              icon: Icons.people_outline,
              title: context.tr(fr: 'Aucun membre', en: 'No members'),
              subtitle: context.tr(fr: 'Invitez votre famille pour partager le contrôle de la maison.', en: 'Invite your family to share control of the home.'),
              actionLabel: canManage ? context.tr(fr: 'Ajouter un membre', en: 'Add a member') : null,
              onAction: canManage ? () => _add(context, ref) : null,
            );
          }
          final sorted = [...list]..sort((a, b) => _rank(a.role).compareTo(_rank(b.role)));
          return RefreshIndicator(
            onRefresh: () async => ref.invalidate(membersProvider(homeId)),
            child: ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
              children: [
                GroupedCard(
                  dividerIndent: 72,
                  children: [
                    for (final member in sorted)
                      MemberTile(
                        member: member,
                        isMe: member.userId == myId,
                        onChangeRole: canManage && member.role != 'owner' ? () => _changeRole(context, ref, member) : null,
                        onRemove: canManage && member.role != 'owner' ? () => _remove(context, ref, member) : null,
                      ),
                  ],
                ),
                const SizedBox(height: 16),
                Text(
                  canManage
                      ? context.tr(fr: 'Les membres invités doivent déjà avoir un compte SafeR. Le propriétaire ne peut pas être retiré.', en: 'Invited members must already have a SafeR account. The owner cannot be removed.')
                      : context.tr(fr: 'Seuls le propriétaire et les administrateurs peuvent gérer les membres.', en: 'Only the owner and admins can manage members.'),
                  textAlign: TextAlign.center,
                  style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                ),
              ],
            ),
          );
        },
      ),
      bottomNavigationBar: !canManage || (members.valueOrNull?.isEmpty ?? true)
          ? null
          : SafeArea(
              minimum: const EdgeInsets.fromLTRB(16, 8, 16, 16),
              child: FilledButton.icon(
                onPressed: () => _add(context, ref),
                icon: const Icon(Icons.person_add_alt_1_outlined),
                label: Text(context.tr(fr: 'Ajouter un membre', en: 'Add a member')),
              ),
            ),
    );
  }

  static int _rank(String role) => role == 'owner' ? 0 : (role == 'admin' ? 1 : 2);
}
