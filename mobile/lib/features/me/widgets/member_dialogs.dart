import 'package:flutter/material.dart';

import '../../../core/api/api_exception.dart';
import '../../../core/i18n.dart';
import 'me_common.dart';

/// Roles that can be granted to another member.
const List<String> kAssignableRoles = ['member', 'admin'];

/// Values of the "add member" dialog.
typedef NewMember = ({String email, String role});

final RegExp _emailRegExp = RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]{2,}$');

/// Human message for member errors (the hub answers 404 when the e-mail has no account).
String memberErrorMessage(BuildContext context, Object error) {
  if (error is ApiException && error.status == 404) {
    return context.tr(fr: "Cet utilisateur doit d'abord créer un compte SafeR", en: 'This user must create a SafeR account first');
  }
  return errorMessage(error);
}

/// Dialog asking for an e-mail and a role. Resolves with the values or null.
Future<NewMember?> showAddMemberDialog(BuildContext context) => showDialog<NewMember>(context: context, builder: (_) => const _AddMemberDialog());

class _AddMemberDialog extends StatefulWidget {
  const _AddMemberDialog();

  @override
  State<_AddMemberDialog> createState() => _AddMemberDialogState();
}

class _AddMemberDialogState extends State<_AddMemberDialog> {
  final _formKey = GlobalKey<FormState>();
  final _email = TextEditingController();
  String _role = 'member';

  @override
  void dispose() {
    _email.dispose();
    super.dispose();
  }

  void _submit() {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    Navigator.of(context).pop((email: _email.text.trim().toLowerCase(), role: _role));
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return AlertDialog(
      title: Text(context.tr(fr: 'Ajouter un membre', en: 'Add a member')),
      content: Form(
        key: _formKey,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            TextFormField(
              key: const Key('member-email'),
              controller: _email,
              autofocus: true,
              keyboardType: TextInputType.emailAddress,
              textInputAction: TextInputAction.done,
              autocorrect: false,
              onFieldSubmitted: (_) => _submit(),
              decoration: InputDecoration(labelText: context.tr(fr: 'E-mail', en: 'E-mail'), prefixIcon: const Icon(Icons.mail_outline)),
              validator: (v) {
                final value = (v ?? '').trim();
                if (value.isEmpty) return context.tr(fr: "Saisissez l'e-mail", en: 'Enter the e-mail');
                if (!_emailRegExp.hasMatch(value)) return context.tr(fr: 'Adresse e-mail invalide', en: 'Invalid e-mail address');
                return null;
              },
            ),
            const SizedBox(height: 16),
            SegmentedButton<String>(
              style: SegmentedButton.styleFrom(minimumSize: const Size(0, 44)),
              segments: [
                for (final role in kAssignableRoles) ButtonSegment(value: role, label: Text(roleLabel(context, role)), icon: Icon(roleIcon(role))),
              ],
              selected: {_role},
              onSelectionChanged: (selection) => setState(() => _role = selection.first),
            ),
            const SizedBox(height: 12),
            Text(
              context.tr(fr: 'La personne doit déjà avoir un compte SafeR avec cet e-mail.', en: 'The person must already have a SafeR account with this e-mail.'),
              style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.of(context).pop(), child: Text(context.tr(fr: 'Annuler', en: 'Cancel'))),
        FilledButton(
          style: FilledButton.styleFrom(minimumSize: const Size(88, 44)),
          onPressed: _submit,
          child: Text(context.tr(fr: 'Ajouter', en: 'Add')),
        ),
      ],
    );
  }
}

/// Bottom sheet picking a role for an existing member. Resolves with the role or null.
Future<String?> showRolePickerSheet(BuildContext context, {required String current}) => showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      builder: (sheetContext) {
        final theme = Theme.of(sheetContext);
        return SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 0, 20, 8),
                child: Text(sheetContext.tr(fr: 'Rôle du membre', en: 'Member role'), style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
              ),
              for (final role in kAssignableRoles)
                ListTile(
                  leading: Icon(roleIcon(role), color: roleColor(role)),
                  title: Text(roleLabel(sheetContext, role)),
                  subtitle: Text(
                    role == 'admin'
                        ? sheetContext.tr(fr: 'Peut gérer les appareils, les pièces et les membres', en: 'Can manage devices, rooms and members')
                        : sheetContext.tr(fr: 'Peut voir et contrôler les appareils', en: 'Can view and control devices'),
                  ),
                  trailing: Icon(role == current ? Icons.check_circle : Icons.circle_outlined, color: role == current ? theme.colorScheme.primary : theme.colorScheme.outline),
                  selected: role == current,
                  onTap: () => Navigator.of(sheetContext).pop(role),
                ),
              const SizedBox(height: 8),
            ],
          ),
        );
      },
    );
