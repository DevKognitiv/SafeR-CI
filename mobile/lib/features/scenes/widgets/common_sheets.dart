import 'package:flutter/material.dart';

import '../../../core/i18n.dart';
import '../../../core/theme.dart';
import 'labels.dart';
import 'sheet_scaffold.dart';

/// Chips to pick one of the four home security modes.
class SecurityModeChips extends StatelessWidget {
  const SecurityModeChips({super.key, required this.selected, required this.onSelected});

  final String? selected;
  final ValueChanged<String> onSelected;

  @override
  Widget build(BuildContext context) => Wrap(
        spacing: 8,
        runSpacing: 8,
        children: [
          for (final mode in kSecurityModes)
            ChoiceChip(
              avatar: Icon(securityModeIcon(mode), size: 18, color: SafeRColors.forSecurityMode(mode)),
              label: Text(securityModeLabel(context, mode)),
              selected: selected == mode,
              onSelected: (_) => onSelected(mode),
            ),
        ],
      );
}

/// Bottom sheet returning the chosen security mode (null when dismissed).
Future<String?> showSecurityModePicker(BuildContext context, {required String title, String? initial}) =>
    showSafeRSheet<String>(context, builder: (_) => _SecurityModeSheet(title: title, initial: initial));

class _SecurityModeSheet extends StatefulWidget {
  const _SecurityModeSheet({required this.title, this.initial});

  final String title;
  final String? initial;

  @override
  State<_SecurityModeSheet> createState() => _SecurityModeSheetState();
}

class _SecurityModeSheetState extends State<_SecurityModeSheet> {
  String? _mode;

  @override
  void initState() {
    super.initState();
    _mode = widget.initial;
  }

  @override
  Widget build(BuildContext context) => SheetScaffold(
        title: widget.title,
        subtitle: context.tr(fr: 'Choisissez le mode de sécurité', en: 'Pick the security mode'),
        action: FilledButton(
          onPressed: _mode == null ? null : () => Navigator.of(context).pop(_mode),
          child: Text(context.tr(fr: 'Valider', en: 'Confirm')),
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
          child: SecurityModeChips(selected: _mode, onSelected: (m) => setState(() => _mode = m)),
        ),
      );
}

/// "Modifier / Supprimer" context menu shown on long press. Returns 'edit' or 'delete'.
Future<String?> showEditDeleteSheet(BuildContext context, {required String title}) => showSafeRSheet<String>(
      context,
      builder: (ctx) => SheetScaffold(
        title: title,
        scrollable: false,
        child: SheetOptionList(options: [
          SheetOption(id: 'edit', icon: Icons.edit_outlined, title: ctx.tr(fr: 'Modifier', en: 'Edit')),
          SheetOption(id: 'delete', icon: Icons.delete_outline, title: ctx.tr(fr: 'Supprimer', en: 'Delete')),
        ]),
      ),
    );

/// Destructive confirmation dialog. Resolves to true when the user confirms.
Future<bool> confirmDelete(BuildContext context, {required String title, required String message}) async {
  final result = await showDialog<bool>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: Text(title),
      content: Text(message),
      actions: [
        TextButton(onPressed: () => Navigator.of(ctx).pop(false), child: Text(ctx.tr(fr: 'Annuler', en: 'Cancel'))),
        FilledButton(
          style: FilledButton.styleFrom(backgroundColor: SafeRColors.danger, minimumSize: const Size(96, 44)),
          onPressed: () => Navigator.of(ctx).pop(true),
          child: Text(ctx.tr(fr: 'Supprimer', en: 'Delete')),
        ),
      ],
    ),
  );
  return result ?? false;
}
