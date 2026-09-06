import 'package:flutter/material.dart';

import '../../../core/i18n.dart';

/// Password input with a show/hide toggle.
class PasswordField extends StatefulWidget {
  const PasswordField({
    super.key,
    required this.controller,
    required this.label,
    this.validator,
    this.focusNode,
    this.textInputAction,
    this.onFieldSubmitted,
    this.autofillHints,
    this.helperText,
  });

  final TextEditingController controller;
  final String label;
  final FormFieldValidator<String>? validator;
  final FocusNode? focusNode;
  final TextInputAction? textInputAction;
  final ValueChanged<String>? onFieldSubmitted;
  final Iterable<String>? autofillHints;
  final String? helperText;

  @override
  State<PasswordField> createState() => _PasswordFieldState();
}

class _PasswordFieldState extends State<PasswordField> {
  bool _obscure = true;

  @override
  Widget build(BuildContext context) => TextFormField(
        controller: widget.controller,
        focusNode: widget.focusNode,
        obscureText: _obscure,
        validator: widget.validator,
        textInputAction: widget.textInputAction,
        onFieldSubmitted: widget.onFieldSubmitted,
        autofillHints: widget.autofillHints,
        autocorrect: false,
        enableSuggestions: false,
        decoration: InputDecoration(
          labelText: widget.label,
          helperText: widget.helperText,
          prefixIcon: const Icon(Icons.lock_outline),
          suffixIcon: IconButton(
            tooltip: _obscure ? context.tr(fr: 'Afficher le mot de passe', en: 'Show password') : context.tr(fr: 'Masquer le mot de passe', en: 'Hide password'),
            icon: Icon(_obscure ? Icons.visibility_outlined : Icons.visibility_off_outlined),
            onPressed: () => setState(() => _obscure = !_obscure),
          ),
        ),
      );
}

/// Inline error banner (hub error from `authProvider.error`).
class AuthErrorBanner extends StatelessWidget {
  const AuthErrorBanner({super.key, required this.message, this.onDismiss});

  final String message;
  final VoidCallback? onDismiss;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Semantics(
      liveRegion: true,
      child: Container(
        padding: const EdgeInsets.fromLTRB(14, 6, 4, 6),
        decoration: BoxDecoration(
          color: scheme.error.withValues(alpha: 0.1),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: scheme.error.withValues(alpha: 0.35)),
        ),
        child: Row(
          children: [
            Icon(Icons.error_outline, color: scheme.error, size: 20),
            const SizedBox(width: 10),
            Expanded(child: Text(message, style: TextStyle(color: scheme.error, fontWeight: FontWeight.w600, fontSize: 13))),
            if (onDismiss != null)
              IconButton(
                onPressed: onDismiss,
                tooltip: context.tr(fr: 'Fermer', en: 'Dismiss'),
                icon: Icon(Icons.close, size: 18, color: scheme.error),
              ),
          ],
        ),
      ),
    );
  }
}

/// "Pas encore de compte ? Créer un compte" style row.
class AuthSwitchLink extends StatelessWidget {
  const AuthSwitchLink({super.key, required this.prompt, required this.action, required this.onTap});

  final String prompt;
  final String action;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Flexible(child: Text(prompt, style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant))),
        TextButton(onPressed: onTap, child: Text(action, style: const TextStyle(fontWeight: FontWeight.w700))),
      ],
    );
  }
}

/// FR / EN language picker (chips). Labels are endonyms and intentionally not translated.
class LanguageChips extends StatelessWidget {
  const LanguageChips({super.key, required this.value, required this.onChanged});

  final String value;
  final ValueChanged<String> onChanged;

  static const _languages = [(code: 'fr', label: 'Français'), (code: 'en', label: 'English')];

  @override
  Widget build(BuildContext context) => Wrap(
        spacing: 8,
        children: [
          for (final language in _languages)
            ChoiceChip(
              label: Text(language.label),
              avatar: value == language.code ? null : const Icon(Icons.language, size: 18),
              selected: value == language.code,
              onSelected: (_) => onChanged(language.code),
            ),
        ],
      );
}
