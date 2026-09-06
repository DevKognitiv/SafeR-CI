import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/i18n.dart';
import '../../core/models/home.dart';
import '../../core/providers/providers.dart';
import '../../core/widgets/widgets.dart';
import 'widgets/me_common.dart';
import 'widgets/member_dialogs.dart';
import 'widgets/member_tile.dart';

/// Members of a home: list with roles. Mirrors the hub's rules: owner/admin invite,
/// admins remove plain members, only the owner changes roles / removes admins /
/// transfers ownership, and anyone but the owner can leave.
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

  Future<void> _changeRole(BuildContext context, WidgetRef ref, Member member, {required bool isOwner}) async {
    final role = await showRolePickerSheet(context, current: member.role, allowOwner: isOwner);
    if (role == null || role == member.role || !context.mounted) return;
    if (role == 'owner') {
      final name = member.name.isEmpty ? member.email : member.name;
      final confirmed = await confirmDialog(
        context,
        title: context.tr(fr: 'Transférer la propriété à $name ?', en: 'Transfer ownership to $name?'),
        message: context.tr(
          fr: 'Vous deviendrez administrateur de cette maison. Seul le nouveau propriétaire pourra la supprimer ou changer les rôles.',
          en: 'You will become an admin of this home. Only the new owner will be able to delete it or change roles.',
        ),
        confirmLabel: context.tr(fr: 'Transférer', en: 'Transfer'),
        destructive: true,
      );
      if (!confirmed || !context.mounted) return;
    }
    try {
      await ref.read(hubClientProvider).updateMember(homeId, member.userId, role);
      // Ownership transfer also changes the caller's role: refresh the homes too.
      _refresh(ref);
      if (!context.mounted) return;
      showSnack(context, role == 'owner' ? context.tr(fr: 'Propriété transférée', en: 'Ownership transferred') : context.tr(fr: 'Rôle mis à jour', en: 'Role updated'));
    } catch (e) {
      if (context.mounted) showErrorSnack(context, memberErrorMessage(context, e));
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
      if (context.canPop()) context.pop();
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
    final isOwner = home?.isOwner ?? false;
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
                        // Role changes are owner-only (PATCH /members requires owner).
                        onChangeRole: isOwner && member.role != 'owner' ? () => _changeRole(context, ref, member, isOwner: true) : null,
                        // Admins remove plain members; only the owner removes another admin.
                        onRemove: member.userId != myId && member.role != 'owner' && (isOwner || (canManage && member.role == 'member'))
                            ? () => _remove(context, ref, member)
                            : null,
                        // Own row: leave (the owner must transfer ownership first).
                        onLeave: member.userId == myId && member.role != 'owner' && home != null ? () => _leave(context, ref, home) : null,
                      ),
                  ],
                ),
                const SizedBox(height: 16),
                Text(
                  isOwner
                      ? context.tr(
                          fr: 'Les membres invités doivent déjà avoir un compte SafeR. Pour quitter la maison, transférez d\'abord la propriété.',
                          en: 'Invited members must already have a SafeR account. To leave the home, transfer ownership first.')
                      : canManage
                          ? context.tr(
                              fr: 'Les membres invités doivent déjà avoir un compte SafeR. Seul le propriétaire change les rôles ou retire un administrateur.',
                              en: 'Invited members must already have a SafeR account. Only the owner changes roles or removes an admin.')
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
