import 'package:flutter/material.dart';

import '../../../core/i18n.dart';
import '../../../core/models/brand.dart';

/// Asks the host to open the scanner; resolves with the scanned code or null.
typedef ScanRequest = Future<String?> Function(FormFieldSpec field);

/// Extra validation hook (returns an error message or null).
typedef FieldValidator = String? Function(FormFieldSpec field, String value);

/// Builds a widget under the fields from the current values (e.g. a Matter summary).
typedef FormFooterBuilder = Widget? Function(BuildContext context, Map<String, dynamic> values);

/// Key of the input rendered for a pairing field (handy for tests).
Key pairingFieldKey(String name) => ValueKey('pairing-field-$name');

/// Dynamic form rendered from `PairingMethod.fields`.
///
/// Supports text, password (with eye), number, select, toggle, textarea and qr
/// (read-only + "Scanner" button). Required fields are validated on submit.
class PairingForm extends StatefulWidget {
  const PairingForm({
    super.key,
    required this.fields,
    required this.submitLabel,
    required this.onSubmit,
    this.initialValues = const {},
    this.onScan,
    this.extraValidator,
    this.footerBuilder,
    this.header,
  });

  final List<FormFieldSpec> fields;
  final Map<String, dynamic> initialValues;
  final String submitLabel;
  final ValueChanged<Map<String, dynamic>> onSubmit;
  final ScanRequest? onScan;
  final FieldValidator? extraValidator;
  final FormFooterBuilder? footerBuilder;
  final Widget? header;

  @override
  State<PairingForm> createState() => PairingFormState();
}

class PairingFormState extends State<PairingForm> {
  final _formKey = GlobalKey<FormState>();
  final Map<String, TextEditingController> _controllers = {};
  final Map<String, bool> _toggles = {};
  final Map<String, String?> _selects = {};
  final Set<String> _revealed = {};
  bool _autovalidate = false;

  @override
  void initState() {
    super.initState();
    for (final field in widget.fields) {
      final initial = widget.initialValues.containsKey(field.name) ? widget.initialValues[field.name] : field.defaultValue;
      switch (field.type) {
        case 'toggle':
          _toggles[field.name] = initial == true || initial.toString() == 'true';
        case 'select':
          final value = initial?.toString();
          _selects[field.name] = value != null && field.options.any((o) => o.value == value) ? value : null;
        default:
          _controllers[field.name] = TextEditingController(text: initial?.toString() ?? '');
      }
    }
  }

  @override
  void dispose() {
    for (final c in _controllers.values) {
      c.dispose();
    }
    super.dispose();
  }

  /// Current typed values (numbers parsed, toggles as bool, text trimmed).
  Map<String, dynamic> get values => {
        for (final field in widget.fields)
          if (field.type == 'toggle')
            field.name: _toggles[field.name] ?? false
          else if (field.type == 'select')
            field.name: _selects[field.name]
          else if (field.type == 'number')
            field.name: _parseNumber(_controllers[field.name]!.text)
          else
            field.name: _controllers[field.name]!.text.trim(),
      };

  static dynamic _parseNumber(String text) {
    final t = text.trim();
    if (t.isEmpty) return null;
    return int.tryParse(t) ?? num.tryParse(t);
  }

  /// Validate and call [PairingForm.onSubmit]; returns false when invalid.
  bool submit() {
    final valid = _formKey.currentState?.validate() ?? false;
    if (!valid) {
      setState(() => _autovalidate = true);
      return false;
    }
    widget.onSubmit(values);
    return true;
  }

  String? _validate(FormFieldSpec field, String? raw) {
    final value = (raw ?? '').trim();
    if (field.required && value.isEmpty) return context.tr(fr: 'Ce champ est obligatoire', en: 'This field is required');
    if (field.type == 'number' && value.isNotEmpty && num.tryParse(value) == null) return context.tr(fr: 'Nombre invalide', en: 'Invalid number');
    if (value.isNotEmpty) return widget.extraValidator?.call(field, value);
    return null;
  }

  Future<void> _scan(FormFieldSpec field) async {
    final code = await widget.onScan?.call(field);
    if (!mounted || code == null || code.isEmpty) return;
    setState(() => _controllers[field.name]!.text = code);
  }

  String _label(FormFieldSpec field) => field.required ? field.label : '${field.label} (${context.tr(fr: 'optionnel', en: 'optional')})';

  @override
  Widget build(BuildContext context) {
    final footer = widget.footerBuilder?.call(context, values);
    return Form(
      key: _formKey,
      autovalidateMode: _autovalidate ? AutovalidateMode.always : AutovalidateMode.disabled,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
        children: [
          if (widget.header != null) ...[widget.header!, const SizedBox(height: 16)],
          for (final field in widget.fields) ...[_buildField(context, field), const SizedBox(height: 14)],
          if (footer != null) ...[footer, const SizedBox(height: 14)],
          const SizedBox(height: 8),
          FilledButton(onPressed: submit, child: Text(widget.submitLabel)),
        ],
      ),
    );
  }

  Widget _buildField(BuildContext context, FormFieldSpec field) {
    switch (field.type) {
      case 'toggle':
        return _ToggleField(
          key: pairingFieldKey(field.name),
          label: field.label,
          help: field.help,
          value: _toggles[field.name] ?? false,
          onChanged: (v) => setState(() => _toggles[field.name] = v),
        );
      case 'select':
        return DropdownButtonFormField<String>(
          key: pairingFieldKey(field.name),
          initialValue: _selects[field.name],
          decoration: InputDecoration(labelText: _label(field), helperText: field.help, helperMaxLines: 3),
          hint: Text(field.placeholder ?? context.tr(fr: 'Sélectionner', en: 'Select')),
          items: [for (final o in field.options) DropdownMenuItem(value: o.value, child: Text(o.label))],
          validator: (v) => field.required && (v == null || v.isEmpty) ? context.tr(fr: 'Ce champ est obligatoire', en: 'This field is required') : null,
          onChanged: (v) => setState(() => _selects[field.name] = v),
        );
      case 'password':
        final hidden = !_revealed.contains(field.name);
        return TextFormField(
          key: pairingFieldKey(field.name),
          controller: _controllers[field.name],
          obscureText: hidden,
          autocorrect: false,
          enableSuggestions: false,
          onChanged: (_) => setState(() {}),
          validator: (v) => _validate(field, v),
          decoration: InputDecoration(
            labelText: _label(field),
            hintText: field.placeholder,
            helperText: field.help,
            helperMaxLines: 3,
            suffixIcon: IconButton(
              tooltip: hidden ? context.tr(fr: 'Afficher le mot de passe', en: 'Show password') : context.tr(fr: 'Masquer le mot de passe', en: 'Hide password'),
              icon: Icon(hidden ? Icons.visibility_outlined : Icons.visibility_off_outlined),
              onPressed: () => setState(() => hidden ? _revealed.add(field.name) : _revealed.remove(field.name)),
            ),
          ),
        );
      case 'qr':
        return TextFormField(
          key: pairingFieldKey(field.name),
          controller: _controllers[field.name],
          readOnly: true,
          onTap: widget.onScan == null ? null : () => _scan(field),
          onChanged: (_) => setState(() {}),
          validator: (v) => _validate(field, v),
          decoration: InputDecoration(
            labelText: _label(field),
            hintText: field.placeholder ?? context.tr(fr: 'Appuyez sur Scanner', en: 'Tap Scan'),
            helperText: field.help,
            helperMaxLines: 3,
            suffixIconConstraints: const BoxConstraints(minHeight: 44, minWidth: 44),
            suffixIcon: Padding(
              padding: const EdgeInsets.only(right: 6),
              child: TextButton.icon(
                onPressed: widget.onScan == null ? null : () => _scan(field),
                icon: const Icon(Icons.qr_code_scanner, size: 18),
                label: Text(context.tr(fr: 'Scanner', en: 'Scan')),
              ),
            ),
          ),
        );
      case 'number':
        return TextFormField(
          key: pairingFieldKey(field.name),
          controller: _controllers[field.name],
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          onChanged: (_) => setState(() {}),
          validator: (v) => _validate(field, v),
          decoration: InputDecoration(labelText: _label(field), hintText: field.placeholder, helperText: field.help, helperMaxLines: 3),
        );
      case 'textarea':
        return TextFormField(
          key: pairingFieldKey(field.name),
          controller: _controllers[field.name],
          minLines: 3,
          maxLines: 6,
          keyboardType: TextInputType.multiline,
          onChanged: (_) => setState(() {}),
          validator: (v) => _validate(field, v),
          decoration: InputDecoration(labelText: _label(field), hintText: field.placeholder, helperText: field.help, helperMaxLines: 3, alignLabelWithHint: true),
        );
      default:
        return TextFormField(
          key: pairingFieldKey(field.name),
          controller: _controllers[field.name],
          autocorrect: false,
          keyboardType: field.name.contains('host') || field.name.contains('ip') ? TextInputType.url : TextInputType.text,
          onChanged: (_) => setState(() {}),
          validator: (v) => _validate(field, v),
          decoration: InputDecoration(labelText: _label(field), hintText: field.placeholder, helperText: field.help, helperMaxLines: 3),
        );
    }
  }
}

class _ToggleField extends StatelessWidget {
  const _ToggleField({super.key, required this.label, required this.value, required this.onChanged, this.help});

  final String label;
  final String? help;
  final bool value;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) => Card(
        child: SwitchListTile.adaptive(
          value: value,
          onChanged: onChanged,
          title: Text(label),
          subtitle: help == null ? null : Text(help!),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 2),
        ),
      );
}
