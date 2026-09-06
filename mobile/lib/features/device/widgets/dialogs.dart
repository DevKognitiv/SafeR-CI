import 'package:flutter/material.dart';

import '../../../core/i18n.dart';
import '../../../core/theme.dart';

/// Yes/no confirmation. Resolves true when confirmed.
Future<bool> showConfirmDialog(
  BuildContext context, {
  required String title,
  required String message,
  required String confirmLabel,
  bool destructive = false,
  IconData? icon,
}) async {
  final result = await showDialog<bool>(
    context: context,
    builder: (context) => AlertDialog(
      icon: icon == null ? null : Icon(icon, color: destructive ? SafeRColors.danger : null, size: 32),
      title: Text(title),
      content: Text(message),
      actions: [
        TextButton(onPressed: () => Navigator.of(context).pop(false), child: Text(context.tr(fr: 'Annuler', en: 'Cancel'))),
        FilledButton(
          style: FilledButton.styleFrom(minimumSize: const Size(88, 44), backgroundColor: destructive ? SafeRColors.danger : null),
          onPressed: () => Navigator.of(context).pop(true),
          child: Text(confirmLabel),
        ),
      ],
    ),
  );
  return result ?? false;
}

/// One-field text prompt (rename). Resolves with the trimmed text or null.
Future<String?> showTextPromptDialog(BuildContext context, {required String title, required String confirmLabel, String? initialValue, String? hint}) =>
    showDialog<String>(context: context, builder: (_) => _TextPromptDialog(title: title, confirmLabel: confirmLabel, initialValue: initialValue, hint: hint));

class _TextPromptDialog extends StatefulWidget {
  const _TextPromptDialog({required this.title, required this.confirmLabel, this.initialValue, this.hint});

  final String title;
  final String confirmLabel;
  final String? initialValue;
  final String? hint;

  @override
  State<_TextPromptDialog> createState() => _TextPromptDialogState();
}

class _TextPromptDialogState extends State<_TextPromptDialog> {
  late final TextEditingController _controller = TextEditingController(text: widget.initialValue);

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _submit() {
    final value = _controller.text.trim();
    if (value.isEmpty) return;
    Navigator.of(context).pop(value);
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text(widget.title),
        content: TextField(
          controller: _controller,
          autofocus: true,
          textInputAction: TextInputAction.done,
          textCapitalization: TextCapitalization.sentences,
          decoration: InputDecoration(hintText: widget.hint),
          onSubmitted: (_) => _submit(),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.of(context).pop(), child: Text(context.tr(fr: 'Annuler', en: 'Cancel'))),
          ValueListenableBuilder<TextEditingValue>(
            valueListenable: _controller,
            builder: (_, value, __) => FilledButton(
              style: FilledButton.styleFrom(minimumSize: const Size(88, 44)),
              onPressed: value.text.trim().isEmpty ? null : _submit,
              child: Text(widget.confirmLabel),
            ),
          ),
        ],
      );
}
