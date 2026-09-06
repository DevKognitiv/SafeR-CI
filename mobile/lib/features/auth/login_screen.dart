import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/i18n.dart';
import '../../core/providers/providers.dart';
import '../../core/routes.dart';
import 'widgets/auth_form_widgets.dart';
import 'widgets/auth_hero.dart';
import 'widgets/auth_validators.dart';
import 'widgets/hub_url_sheet.dart';

/// E-mail + password sign-in. On success the router redirects (authProvider status).
class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _passwordFocus = FocusNode();
  AutovalidateMode _autovalidate = AutovalidateMode.disabled;
  bool _submitting = false;

  @override
  void initState() {
    super.initState();
    // Do not carry over an error from another screen (e.g. a failed registration).
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) ref.read(authProvider.notifier).clearError();
    });
  }

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    _passwordFocus.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_submitting) return;
    FocusScope.of(context).unfocus();
    if (!(_formKey.currentState?.validate() ?? false)) {
      setState(() => _autovalidate = AutovalidateMode.onUserInteraction);
      return;
    }
    setState(() => _submitting = true);
    final notifier = ref.read(authProvider.notifier);
    notifier.clearError();
    await notifier.login(_email.text.trim(), _password.text);
    if (mounted) setState(() => _submitting = false);
  }

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authProvider);
    final hubUrl = ref.watch(hubUrlProvider);
    final theme = Theme.of(context);
    return Scaffold(
      body: SingleChildScrollView(
        keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
        child: Column(
          children: [
            AuthHero(tagline: context.tr(fr: 'Votre maison, sous protection', en: 'Your home, protected')),
            Padding(
              padding: const EdgeInsets.fromLTRB(24, 28, 24, 8),
              child: Form(
                key: _formKey,
                autovalidateMode: _autovalidate,
                child: AutofillGroup(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Text(context.tr(fr: 'Connexion', en: 'Log in'), style: theme.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w700)),
                      const SizedBox(height: 4),
                      Text(
                        context.tr(fr: 'Connectez-vous à votre hub SafeR', en: 'Sign in to your SafeR hub'),
                        style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                      ),
                      const SizedBox(height: 24),
                      if (auth.error != null) ...[
                        AuthErrorBanner(message: auth.error!, onDismiss: () => ref.read(authProvider.notifier).clearError()),
                        const SizedBox(height: 16),
                      ],
                      TextFormField(
                        key: const Key('login-email'),
                        controller: _email,
                        keyboardType: TextInputType.emailAddress,
                        textInputAction: TextInputAction.next,
                        autocorrect: false,
                        autofillHints: const [AutofillHints.email],
                        validator: (v) => AuthValidators.email(context, v),
                        onFieldSubmitted: (_) => _passwordFocus.requestFocus(),
                        decoration: InputDecoration(labelText: context.tr(fr: 'E-mail', en: 'E-mail'), prefixIcon: const Icon(Icons.mail_outline)),
                      ),
                      const SizedBox(height: 14),
                      PasswordField(
                        key: const Key('login-password'),
                        controller: _password,
                        focusNode: _passwordFocus,
                        label: context.tr(fr: 'Mot de passe', en: 'Password'),
                        textInputAction: TextInputAction.done,
                        autofillHints: const [AutofillHints.password],
                        validator: (v) => AuthValidators.password(context, v),
                        onFieldSubmitted: (_) => _submit(),
                      ),
                      const SizedBox(height: 24),
                      FilledButton(
                        key: const Key('login-submit'),
                        onPressed: _submit,
                        child: _submitting
                            ? Semantics(
                                label: context.tr(fr: 'Connexion en cours', en: 'Signing in'),
                                child: const SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2.5, color: Colors.white)),
                              )
                            : Text(context.tr(fr: 'Se connecter', en: 'Log in')),
                      ),
                      const SizedBox(height: 12),
                      AuthSwitchLink(
                        prompt: context.tr(fr: 'Pas encore de compte ?', en: "Don't have an account?"),
                        action: context.tr(fr: 'Créer un compte', en: 'Create an account'),
                        onTap: () => context.push(Routes.register),
                      ),
                    ],
                  ),
                ),
              ),
            ),
            SafeArea(
              top: false,
              child: Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: HubFooter(url: hubUrl, onEdit: () => showHubUrlSheet(context, ref)),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
