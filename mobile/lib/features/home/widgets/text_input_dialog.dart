import 'package:flutter/material.dart';

import '../../../core/i18n.dart';

/// Simple one-field dialog (rename / create). Resolves with the trimmed text or null.
Future<String?> showTextInputDialog(
  BuildContext context, {
  required String title,
  required String confirmLabel,
  String? initialValue,
  String? hint,
}) =>
    showDialog<String>(
      context: context,
      builder: (_) => _TextInputDialog(title: title, confirmLabel: confirmLabel, initialValue: initialValue, hint: hint),
    );

class _TextInputDialog extends StatefulWidget {
  const _TextInputDialog({required this.title, required this.confirmLabel, this.initialValue, this.hint});

  final String title;
  final String confirmLabel;
  final String? initialValue;
  final String? hint;

  @override
  State<_TextInputDialog> createState() => _TextInputDialogState();
}

class _TextInputDialogState extends State<_TextInputDialog> {
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
        content: ValueListenableBuilder<TextEditingValue>(
          valueListenable: _controller,
          builder: (_, __, ___) => TextField(
            controller: _controller,
            autofocus: true,
            textInputAction: TextInputAction.done,
            textCapitalization: TextCapitalization.sentences,
            decoration: InputDecoration(hintText: widget.hint),
            onSubmitted: (_) => _submit(),
          ),
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
