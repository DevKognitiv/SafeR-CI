import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:safer_ci/core/providers/providers.dart';
import 'package:safer_ci/features/auth/login_screen.dart';
import 'package:safer_ci/features/auth/register_screen.dart';
import 'package:safer_ci/features/auth/widgets/auth_validators.dart';

import 'helpers/fake_hub_client.dart';
import 'helpers/pump_app.dart';

void main() {
  group('LoginScreen', () {
    testWidgets('renders the login form and the hub footer', (tester) async {
      await pumpApp(tester, const LoginScreen(), authenticated: false);
      expect(find.text('SafeR'), findsOneWidget);
      expect(find.text('E-mail'), findsOneWidget);
      expect(find.text('Mot de passe'), findsOneWidget);
      expect(find.text('Se connecter'), findsOneWidget);
      expect(find.text('Créer un compte'), findsOneWidget);
      expect(find.textContaining('http://localhost:8000'), findsOneWidget);
      expect(find.byTooltip("Changer l'URL du hub"), findsOneWidget);
    });

    testWidgets('empty submit shows validation errors without calling the hub', (tester) async {
      final container = await pumpApp(tester, const LoginScreen(), authenticated: false);
      await tester.tap(find.text('Se connecter'));
      await tester.pump();
      expect(find.text('Saisissez votre e-mail'), findsOneWidget);
      expect(find.text('Saisissez votre mot de passe'), findsOneWidget);
      expect(container.read(authProvider).status, AuthStatus.unauthenticated);

      await tester.enterText(find.byKey(const Key('login-email')), 'not-an-email');
      await tester.pump();
      expect(find.text('Adresse e-mail invalide'), findsOneWidget);
    });

    testWidgets('wrong password shows the hub error, which can be dismissed', (tester) async {
      final container = await pumpApp(tester, const LoginScreen(), authenticated: false);
      await tester.enterText(find.byKey(const Key('login-email')), 'alice@safer.ci');
      await tester.enterText(find.byKey(const Key('login-password')), 'wrong-password');
      await tester.tap(find.text('Se connecter'));
      await settle(tester);
      expect(find.text('Invalid credentials'), findsOneWidget);
      expect(container.read(authProvider).status, AuthStatus.unauthenticated);
      expect(container.read(authProvider).error, 'Invalid credentials');

      await tester.tap(find.byTooltip('Fermer'));
      await tester.pump();
      expect(find.text('Invalid credentials'), findsNothing);
      expect(container.read(authProvider).error, isNull);
    });

    testWidgets('successful login sets authProvider to authenticated', (tester) async {
      final container = await pumpApp(tester, const LoginScreen(), authenticated: false);
      expect(container.read(authProvider).isAuthenticated, isFalse);
      await tester.enterText(find.byKey(const Key('login-email')), 'alice@safer.ci');
      await tester.enterText(find.byKey(const Key('login-password')), 'secret123');
      await tester.tap(find.text('Se connecter'));
      await settle(tester);
      final auth = container.read(authProvider);
      expect(auth.isAuthenticated, isTrue);
      expect(auth.user?.name, 'Alice Kouassi');
      expect(auth.error, isNull);
      expect(container.read(tokenProvider), 'test-token');
      expect(find.text('Se connecter'), findsOneWidget); // loading state is over
    });

    testWidgets('password visibility toggle reveals the password', (tester) async {
      await pumpApp(tester, const LoginScreen(), authenticated: false);
      EditableText editable() => tester.widget<EditableText>(find.descendant(of: find.byKey(const Key('login-password')), matching: find.byType(EditableText)));
      expect(editable().obscureText, isTrue);
      await tester.tap(find.byTooltip('Afficher le mot de passe'));
      await tester.pump();
      expect(editable().obscureText, isFalse);
      expect(find.byTooltip('Masquer le mot de passe'), findsOneWidget);
    });

    testWidgets('hub URL sheet tests the connection and updates hubUrlProvider', (tester) async {
      final container = await pumpApp(tester, const LoginScreen(), authenticated: false);
      expect(container.read(hubUrlProvider), 'http://localhost:8000');

      await tester.tap(find.byTooltip("Changer l'URL du hub"));
      await settle(tester);
      expect(find.text('URL du hub'), findsOneWidget);

      await tester.enterText(find.byKey(const Key('hub-url-field')), 'http://192.168.1.50:8000/');
      await tester.tap(find.text('Tester la connexion'));
      await settle(tester);
      expect(find.text('Hub joignable'), findsOneWidget);

      await tester.tap(find.text('Enregistrer'));
      await settle(tester);
      expect(container.read(hubUrlProvider), 'http://192.168.1.50:8000');
      expect(find.text('URL du hub'), findsNothing); // sheet closed
      expect(find.textContaining('192.168.1.50:8000'), findsOneWidget); // footer updated
      expect(find.text('URL du hub enregistrée'), findsOneWidget);
    });

    testWidgets('hub URL sheet rejects invalid URLs and reverts an unsaved test', (tester) async {
      final container = await pumpApp(tester, const LoginScreen(), authenticated: false, client: FakeHubClient(authenticated: false, failNetwork: true));
      await tester.tap(find.byTooltip("Changer l'URL du hub"));
      await settle(tester);

      await tester.enterText(find.byKey(const Key('hub-url-field')), 'not a url');
      await tester.tap(find.text('Tester la connexion'));
      await tester.pump();
      expect(find.textContaining('URL invalide'), findsOneWidget);
      expect(container.read(hubUrlProvider), 'http://localhost:8000');

      await tester.enterText(find.byKey(const Key('hub-url-field')), 'http://10.0.0.5:8000');
      await tester.tap(find.text('Tester la connexion'));
      await settle(tester);
      expect(find.text('Hub injoignable'), findsOneWidget);
      expect(container.read(hubUrlProvider), 'http://10.0.0.5:8000'); // applied for the probe

      await tester.tap(find.text('Annuler'));
      await settle(tester);
      expect(container.read(hubUrlProvider), 'http://localhost:8000'); // reverted
    });
  });

  group('RegisterScreen', () {
    testWidgets('renders the fields and validates the password confirmation', (tester) async {
      final container = await pumpApp(tester, const RegisterScreen(), authenticated: false, size: const Size(400, 1100));
      for (final label in ['Nom complet', 'E-mail', 'Téléphone', 'Mot de passe', 'Confirmer le mot de passe', 'Français', 'English', 'Créer mon compte', 'Se connecter']) {
        expect(find.text(label), findsOneWidget, reason: label);
      }

      await tester.enterText(find.byKey(const Key('register-name')), 'Awa Koné');
      await tester.enterText(find.byKey(const Key('register-email')), 'awa@safer.ci');
      await tester.enterText(find.byKey(const Key('register-password')), 'secret123');
      await tester.enterText(find.byKey(const Key('register-confirm')), 'secret124');
      await tester.ensureVisible(find.text('Créer mon compte'));
      await tester.tap(find.text('Créer mon compte'));
      await settle(tester);
      expect(find.text('Les mots de passe ne correspondent pas'), findsOneWidget);
      expect(container.read(authProvider).isAuthenticated, isFalse);

      await tester.enterText(find.byKey(const Key('register-password')), 'abc');
      await tester.pump();
      expect(find.text('Au moins 6 caractères'), findsWidgets);
    });

    testWidgets('register succeeds and applies the chosen language', (tester) async {
      final container = await pumpApp(tester, const RegisterScreen(), authenticated: false, size: const Size(400, 1100));
      await tester.enterText(find.byKey(const Key('register-name')), 'Awa Koné');
      await tester.enterText(find.byKey(const Key('register-email')), 'awa@safer.ci');
      await tester.enterText(find.byKey(const Key('register-phone')), '07 00 00 00 00');
      await tester.enterText(find.byKey(const Key('register-password')), 'secret123');
      await tester.enterText(find.byKey(const Key('register-confirm')), 'secret123');
      await tester.ensureVisible(find.text('English'));
      await tester.tap(find.text('English'));
      await tester.pump();
      await tester.ensureVisible(find.text('Créer mon compte'));
      await tester.tap(find.text('Créer mon compte'));
      await settle(tester);

      final auth = container.read(authProvider);
      expect(auth.isAuthenticated, isTrue);
      expect(auth.user?.email, 'awa@safer.ci');
      expect(auth.user?.name, 'Awa Koné');
      expect(auth.user?.locale, 'en');
      expect(container.read(localeProvider), const Locale('en'));
      expect(container.read(tokenProvider), 'test-token');
    });

    testWidgets('register shows the hub error for an already used e-mail', (tester) async {
      final container = await pumpApp(tester, const RegisterScreen(), authenticated: false, size: const Size(400, 1100));
      await tester.enterText(find.byKey(const Key('register-name')), 'Awa Koné');
      await tester.enterText(find.byKey(const Key('register-email')), 'taken@safer.ci');
      await tester.enterText(find.byKey(const Key('register-password')), 'secret123');
      await tester.enterText(find.byKey(const Key('register-confirm')), 'secret123');
      await tester.ensureVisible(find.text('Créer mon compte'));
      await tester.tap(find.text('Créer mon compte'));
      await settle(tester);
      expect(find.text('E-mail already registered'), findsOneWidget);
      expect(container.read(authProvider).isAuthenticated, isFalse);
    });
  });

  group('AuthValidators', () {
    test('normalizePhone adds the +225 prefix and strips separators', () {
      expect(AuthValidators.normalizePhone(''), isNull);
      expect(AuthValidators.normalizePhone('  '), isNull);
      expect(AuthValidators.normalizePhone('07 00 00 00 00'), '+2250700000000');
      expect(AuthValidators.normalizePhone('+225 07-00-00-00-00'), '+2250700000000');
      expect(AuthValidators.normalizePhone('0022507.00.00.00.00'), '+2250700000000');
    });

    test('normalizeHubUrl trims and drops trailing slashes', () {
      expect(AuthValidators.normalizeHubUrl(' http://hub.local:8000/// '), 'http://hub.local:8000');
    });
  });
}
