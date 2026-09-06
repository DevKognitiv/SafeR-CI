import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/i18n.dart';
import '../../core/providers/providers.dart';
import '../../core/router.dart';
import 'widgets/auth_form_widgets.dart';
import 'widgets/auth_hero.dart';
import 'widgets/auth_validators.dart';

/// Account creation on the hub. On success the router redirects (authProvider status).
class RegisterScreen extends ConsumerStatefulWidget {
  const RegisterScreen({super.key});

  @override
  ConsumerState<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends ConsumerState<RegisterScreen> {
  final _formKey = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _email = TextEditingController();
  final _phone = TextEditingController();
  final _password = TextEditingController();
  final _confirm = TextEditingController();
  AutovalidateMode _autovalidate = AutovalidateMode.disabled;
  bool _submitting = false;
  String? _locale;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) ref.read(authProvider.notifier).clearError();
    });
  }

  @override
  void dispose() {
    _name.dispose();
    _email.dispose();
    _phone.dispose();
    _password.dispose();
    _confirm.dispose();
    super.dispose();
  }

  void _backToLogin() {
    if (context.canPop()) {
      context.pop();
    } else {
      context.go(Routes.login);
    }
  }

  Future<void> _submit() async {
    if (_submitting) return;
    FocusScope.of(context).unfocus();
    if (!(_formKey.currentState?.validate() ?? false)) {
      setState(() => _autovalidate = AutovalidateMode.onUserInteraction);
      return;
    }
    final locale = _locale ?? (context.isEnglish ? 'en' : 'fr');
    setState(() => _submitting = true);
    final notifier = ref.read(authProvider.notifier);
    notifier.clearError();
    final ok = await notifier.register(
      email: _email.text.trim(),
      password: _password.text,
      name: _name.text.trim(),
      phone: AuthValidators.normalizePhone(_phone.text),
      locale: locale,
    );
    if (!mounted) return;
    if (ok) {
      // The chosen language becomes the app language too.
      await ref.read(localeProvider.notifier).set(Locale(locale));
    }
    if (mounted) setState(() => _submitting = false);
  }

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authProvider);
    final theme = Theme.of(context);
    final locale = _locale ?? (context.isEnglish ? 'en' : 'fr');
    return Scaffold(
      body: SingleChildScrollView(
        keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
        child: Column(
          children: [
            AuthHero(compact: true, tagline: context.tr(fr: 'Créer un compte', en: 'Create an account'), onBack: _backToLogin),
            SafeArea(
              top: false,
              child: Padding(
                padding: const EdgeInsets.fromLTRB(24, 24, 24, 16),
                child: Form(
                  key: _formKey,
                  autovalidateMode: _autovalidate,
                  child: AutofillGroup(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Text(context.tr(fr: 'Bienvenue sur SafeR', en: 'Welcome to SafeR'), style: theme.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w700)),
                        const SizedBox(height: 4),
                        Text(
                          context.tr(fr: 'Quelques informations pour créer votre compte', en: 'A few details to create your account'),
                          style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                        ),
                        const SizedBox(height: 20),
                        if (auth.error != null) ...[
                          AuthErrorBanner(message: auth.error!, onDismiss: () => ref.read(authProvider.notifier).clearError()),
                          const SizedBox(height: 16),
                        ],
                        TextFormField(
                          key: const Key('register-name'),
                          controller: _name,
                          textCapitalization: TextCapitalization.words,
                          textInputAction: TextInputAction.next,
                          autofillHints: const [AutofillHints.name],
                          validator: (v) => AuthValidators.name(context, v),
                          decoration: InputDecoration(labelText: context.tr(fr: 'Nom complet', en: 'Full name'), prefixIcon: const Icon(Icons.person_outline)),
                        ),
                        const SizedBox(height: 14),
                        TextFormField(
                          key: const Key('register-email'),
                          controller: _email,
                          keyboardType: TextInputType.emailAddress,
                          textInputAction: TextInputAction.next,
                          autocorrect: false,
                          autofillHints: const [AutofillHints.email],
                          validator: (v) => AuthValidators.email(context, v),
                          decoration: InputDecoration(labelText: context.tr(fr: 'E-mail', en: 'E-mail'), prefixIcon: const Icon(Icons.mail_outline)),
                        ),
                        const SizedBox(height: 14),
                        TextFormField(
                          key: const Key('register-phone'),
                          controller: _phone,
                          keyboardType: TextInputType.phone,
                          textInputAction: TextInputAction.next,
                          autofillHints: const [AutofillHints.telephoneNumber],
                          validator: (v) => AuthValidators.phone(context, v),
                          decoration: InputDecoration(
                            labelText: context.tr(fr: 'Téléphone', en: 'Phone'),
                            hintText: '07 00 00 00 00',
                            prefixText: '+225 ',
                            helperText: context.tr(fr: 'Facultatif — utilisé pour les alertes SOS', en: 'Optional — used for SOS alerts'),
                            prefixIcon: const Icon(Icons.phone_outlined),
                          ),
                        ),
                        const SizedBox(height: 14),
                        PasswordField(
                          key: const Key('register-password'),
                          controller: _password,
                          label: context.tr(fr: 'Mot de passe', en: 'Password'),
                          textInputAction: TextInputAction.next,
                          autofillHints: const [AutofillHints.newPassword],
                          helperText: context.tr(fr: 'Au moins $kMinPasswordLength caractères', en: 'At least $kMinPasswordLength characters'),
                          validator: (v) => AuthValidators.password(context, v, strict: true),
                        ),
                        const SizedBox(height: 14),
                        PasswordField(
                          key: const Key('register-confirm'),
                          controller: _confirm,
                          label: context.tr(fr: 'Confirmer le mot de passe', en: 'Confirm password'),
                          textInputAction: TextInputAction.done,
                          autofillHints: const [AutofillHints.newPassword],
                          validator: (v) => AuthValidators.confirmPassword(context, v, _password.text),
                          onFieldSubmitted: (_) => _submit(),
                        ),
                        const SizedBox(height: 20),
                        Text(context.tr(fr: "Langue de l'application", en: 'App language'), style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700)),
                        const SizedBox(height: 8),
                        LanguageChips(value: locale, onChanged: (code) => setState(() => _locale = code)),
                        const SizedBox(height: 24),
                        FilledButton(
                          key: const Key('register-submit'),
                          onPressed: _submit,
                          child: _submitting
                              ? Semantics(
                                  label: context.tr(fr: 'Création du compte en cours', en: 'Creating account'),
                                  child: const SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2.5, color: Colors.white)),
                                )
                              : Text(context.tr(fr: 'Créer mon compte', en: 'Create my account')),
                        ),
                        const SizedBox(height: 12),
                        AuthSwitchLink(
                          prompt: context.tr(fr: 'Déjà un compte ?', en: 'Already have an account?'),
                          action: context.tr(fr: 'Se connecter', en: 'Log in'),
                          onTap: _backToLogin,
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
