import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:safer_ci/core/models/models.dart';
import 'package:safer_ci/core/providers/providers.dart';
import 'package:safer_ci/core/router.dart';
import 'package:safer_ci/core/widgets/widgets.dart';
import 'package:safer_ci/features/me/about_screen.dart';
import 'package:safer_ci/features/me/home_management_screen.dart';
import 'package:safer_ci/features/me/me_screen.dart';
import 'package:safer_ci/features/me/members_screen.dart';
import 'package:safer_ci/features/me/message_center_screen.dart';
import 'package:safer_ci/features/me/profile_screen.dart';
import 'package:safer_ci/features/me/widgets/home_tile.dart';
import 'package:safer_ci/features/me/widgets/integration_tile.dart';
import 'package:safer_ci/features/me/widgets/me_common.dart';
import 'package:safer_ci/features/me/widgets/member_tile.dart';
import 'package:safer_ci/features/me/widgets/message_tile.dart';
import 'package:safer_ci/features/me/widgets/notification_prefs.dart';

import 'helpers/fake_hub_client.dart';
import 'helpers/me_fake_client.dart';
import 'helpers/me_router.dart';
import 'helpers/pump_app.dart';

const homeId = FakeHubClient.homeId;

/// Scroll the first Scrollable until [finder] is built, then bring it into the viewport.
Future<void> scrollTo(WidgetTester tester, Finder finder) async {
  await tester.scrollUntilVisible(finder, 200, scrollable: find.byType(Scrollable).first);
  await tester.ensureVisible(finder);
  await settle(tester);
}

/// SnackBars are shown one after the other: clear the queue between two assertions.
Future<void> clearSnacks(WidgetTester tester) async {
  tester.state<ScaffoldMessengerState>(find.byType(ScaffoldMessenger)).clearSnackBars();
  await settle(tester);
}

void main() {
  group('MeScreen', () {
    testWidgets('shows the user, the unread badge and the current home', (tester) async {
      await pumpMe(tester);
      expect(find.byType(MeScreen), findsOneWidget);
      expect(find.text('Alice Kouassi'), findsOneWidget);
      expect(find.text('alice@safer.ci'), findsOneWidget);
      // Two unread demo messages (alarm + notice) -> badge on "Centre de messages".
      expect(find.text('Centre de messages'), findsOneWidget);
      expect(find.text('2'), findsOneWidget);
      expect(find.text('Gestion des maisons'), findsOneWidget);
      expect(find.text('Intégrations'), findsOneWidget);
      expect(find.text('Paramètres'), findsOneWidget);
      expect(find.text('Maison actuelle'), findsOneWidget);
      expect(find.text('Maison Cocody'), findsOneWidget);
      expect(find.text('Propriétaire'), findsOneWidget);
      expect(find.text('2 membres'), findsOneWidget);
      expect(find.text('12 appareils'), findsOneWidget);
    });

    testWidgets('quick grid opens home management and the header opens the profile', (tester) async {
      await pumpMe(tester);
      await tester.tap(find.text('Gestion des maisons'));
      await settle(tester);
      expect(find.byType(HomeManagementScreen), findsOneWidget);
      await tester.tap(find.byType(BackButton));
      await settle(tester, frames: 30);
      expect(find.byType(HomeManagementScreen), findsNothing);
      await tester.tap(find.text('Alice Kouassi'));
      await settle(tester);
      expect(find.byType(ProfileScreen), findsOneWidget);
    });

    testWidgets('Aide & FAQ opens the project page and À propos navigates', (tester) async {
      final app = await pumpMe(tester);
      await tester.scrollUntilVisible(find.text('Aide & FAQ'), 200, scrollable: find.byType(Scrollable).first);
      await tester.tap(find.text('Aide & FAQ'));
      await settle(tester);
      expect(app.links.map((u) => u.toString()), [kSafeRRepoUrl]);
      await tester.tap(find.text('À propos'));
      await settle(tester);
      expect(find.byType(AboutScreen), findsOneWidget);
    });

    testWidgets('logout asks for confirmation then signs out', (tester) async {
      final app = await pumpMe(tester);
      await tester.scrollUntilVisible(find.byKey(const Key('me-logout')), 200, scrollable: find.byType(Scrollable).first);
      await tester.tap(find.byKey(const Key('me-logout')));
      await settle(tester);
      expect(find.text('Se déconnecter ?'), findsOneWidget);
      await tester.tap(find.text('Annuler'));
      await settle(tester);
      expect(app.container.read(authProvider).isAuthenticated, isTrue);

      await tester.tap(find.byKey(const Key('me-logout')));
      await settle(tester);
      await tester.tap(find.widgetWithText(FilledButton, 'Se déconnecter'));
      await settle(tester);
      expect(app.container.read(authProvider).status, AuthStatus.unauthenticated);
      expect(app.container.read(tokenProvider), isNull);
    });

    testWidgets('invites to create a home when the user has none', (tester) async {
      await pumpMe(tester, client: MeFakeHubClient(noHomes: true));
      expect(find.text('Aucune maison'), findsOneWidget);
      await tester.tap(find.text('Créer une maison'));
      await settle(tester);
      expect(find.byType(HomeManagementScreen), findsOneWidget);
      expect(find.byType(EmptyState), findsOneWidget);
    });
  });

  group('ProfileScreen', () {
    testWidgets('shows the read-only e-mail and updates the name', (tester) async {
      final app = await pumpMe(tester, initialLocation: Routes.profile);
      expect(find.text('Mon profil'), findsOneWidget);
      expect(find.text('alice@safer.ci'), findsOneWidget);
      expect(find.widgetWithText(TextFormField, 'Alice Kouassi'), findsOneWidget);
      await tester.enterText(find.byKey(const Key('profile-name')), 'Alice K.');
      await tester.enterText(find.byKey(const Key('profile-phone')), '+225 0700000000');
      await tester.tap(find.text('English'));
      await tester.pump();
      await tester.tap(find.byKey(const Key('profile-save')));
      await settle(tester);
      final user = app.container.read(authProvider).user!;
      expect(user.name, 'Alice K.');
      expect(user.phone, '+225 0700000000');
      expect(user.locale, 'en');
      expect(find.text('Profil mis à jour'), findsOneWidget);
      // Saved -> back on the Me tab with the new name.
      expect(find.byType(MeScreen), findsOneWidget);
      expect(find.text('Alice K.'), findsOneWidget);
    });

    testWidgets('refuses an empty name', (tester) async {
      await pumpMe(tester, initialLocation: Routes.profile);
      await tester.enterText(find.byKey(const Key('profile-name')), '   ');
      await tester.tap(find.byKey(const Key('profile-save')));
      await settle(tester);
      expect(find.text('Saisissez votre nom'), findsOneWidget);
      expect(find.byType(ProfileScreen), findsOneWidget);
    });
  });

  group('HomeManagementScreen', () {
    testWidgets('lists the homes with a check on the current one and creates a new home', (tester) async {
      final app = await pumpMe(tester, initialLocation: Routes.homes);
      expect(find.byType(HomeTile), findsOneWidget);
      expect(find.text('Maison Cocody'), findsOneWidget);
      expect(find.textContaining('Cocody, Abidjan'), findsOneWidget);
      expect(find.text('Propriétaire'), findsOneWidget);
      expect(find.byKey(const ValueKey('home-check-$homeId')), findsOneWidget);

      await tester.tap(find.byKey(const Key('homes-create')));
      await settle(tester);
      expect(find.text('Créer une maison'), findsWidgets);
      await tester.enterText(find.byKey(const Key('home-name')), 'Villa Bassam');
      await tester.enterText(find.byKey(const Key('home-address')), 'Grand-Bassam');
      await tester.tap(find.text('Utiliser ma position'));
      await settle(tester);
      expect(find.text('5.3599, -4.0083'), findsOneWidget);
      // Default rooms: unselect the kitchen.
      await tester.tap(find.widgetWithText(FilterChip, 'Cuisine'));
      await tester.pump();
      await tester.tap(find.widgetWithText(FilledButton, 'Créer'));
      await settle(tester);

      expect(find.text('Villa Bassam'), findsOneWidget);
      expect(find.byType(HomeTile), findsNWidgets(2));
      expect(find.text('Maison « Villa Bassam » créée'), findsOneWidget);
      final created = app.client.homes_.last;
      expect(created.address, 'Grand-Bassam');
      expect(created.lat, closeTo(5.3599, 1e-6));
      expect(created.rooms.map((r) => r.name), ['Salon', 'Chambre', 'Entrée']);
      // The new home becomes the current one.
      expect(app.container.read(currentHomeIdProvider), created.id);
      expect(find.byKey(ValueKey('home-check-${created.id}')), findsOneWidget);
      expect(find.byKey(const ValueKey('home-check-$homeId')), findsNothing);
    });

    testWidgets('tapping a home selects it; edit and delete go through the hub', (tester) async {
      final app = await pumpMe(tester, initialLocation: Routes.homes);
      // Create a second home then switch back to the first by tapping it.
      await app.client.createHome(name: 'Bureau', rooms: const []);
      await app.container.read(homesProvider.notifier).refresh();
      await settle(tester);
      await tester.tap(find.text('Bureau'));
      await settle(tester);
      expect(app.container.read(currentHomeIdProvider), 'home-new');
      await tester.tap(find.text('Maison Cocody'));
      await settle(tester);
      expect(app.container.read(currentHomeIdProvider), homeId);
      expect(find.text('« Maison Cocody » est maintenant la maison actuelle'), findsOneWidget);

      // Edit the name.
      await tester.tap(find.byTooltip('Options de la maison').first);
      await settle(tester);
      await tester.tap(find.text('Modifier'));
      await settle(tester);
      expect(find.text('Modifier la maison'), findsOneWidget);
      expect(find.widgetWithText(TextFormField, 'Maison Cocody'), findsOneWidget);
      await tester.enterText(find.byKey(const Key('home-name')), 'Maison Riviera');
      await tester.tap(find.widgetWithText(FilledButton, 'Enregistrer'));
      await settle(tester);
      expect(app.client.homeUpdates.single.name, 'Maison Riviera');
      expect(find.text('Maison Riviera'), findsOneWidget);
      expect(find.text('Maison mise à jour'), findsOneWidget);

      // Delete it (owner only) after confirmation.
      await tester.tap(find.byTooltip('Options de la maison').first);
      await settle(tester);
      await tester.tap(find.text('Supprimer'));
      await settle(tester);
      expect(find.text('Supprimer « Maison Riviera » ?'), findsOneWidget);
      await tester.tap(find.widgetWithText(FilledButton, 'Supprimer'));
      await settle(tester);
      expect(app.client.deletedHomes, [homeId]);
      expect(find.text('Maison Riviera'), findsNothing);
      expect(find.text('Maison supprimée'), findsOneWidget);
    });

    testWidgets('shows the empty state with a call to action', (tester) async {
      await pumpMe(tester, initialLocation: Routes.homes, client: MeFakeHubClient(noHomes: true));
      expect(find.byType(EmptyState), findsOneWidget);
      expect(find.text('Aucune maison'), findsOneWidget);
      await tester.tap(find.widgetWithText(FilledButton, 'Créer une maison'));
      await settle(tester);
      expect(find.byKey(const Key('home-name')), findsOneWidget);
    });
  });

  group('MembersScreen', () {
    testWidgets('lists members, adds one and explains the 404', (tester) async {
      await pumpMe(tester, initialLocation: Routes.members(homeId));
      expect(find.byType(MemberTile), findsNWidgets(2));
      expect(find.text('Alice'), findsOneWidget);
      expect(find.text('(moi)'), findsOneWidget);
      expect(find.text('Bob'), findsOneWidget);
      expect(find.text('bob@safer.ci'), findsOneWidget);
      expect(find.text('Propriétaire'), findsOneWidget);
      expect(find.text('Membre'), findsOneWidget);

      // Unknown e-mail -> friendly 404 message.
      await tester.tap(find.byKey(const Key('members-add')));
      await settle(tester);
      expect(find.text('Ajouter un membre'), findsWidgets);
      await tester.enterText(find.byKey(const Key('member-email')), 'nobody@safer.ci');
      await tester.tap(find.widgetWithText(FilledButton, 'Ajouter'));
      await settle(tester);
      expect(find.text("Cet utilisateur doit d'abord créer un compte SafeR"), findsOneWidget);
      expect(find.byType(MemberTile), findsNWidgets(2));

      // Existing account -> added as admin.
      await tester.tap(find.byKey(const Key('members-add')));
      await settle(tester);
      await tester.enterText(find.byKey(const Key('member-email')), 'carla@safer.ci');
      await tester.tap(find.text('Administrateur'));
      await tester.pump();
      await tester.tap(find.widgetWithText(FilledButton, 'Ajouter'));
      await settle(tester);
      expect(find.text('carla@safer.ci ajouté à la maison'), findsOneWidget);
      expect(find.byType(MemberTile), findsNWidgets(3));
      expect(find.text('carla@safer.ci'), findsOneWidget);
      expect(find.text('Administrateur'), findsOneWidget);
    });

    testWidgets('validates the e-mail before calling the hub', (tester) async {
      await pumpMe(tester, initialLocation: Routes.members(homeId));
      await tester.tap(find.byKey(const Key('members-add')));
      await settle(tester);
      await tester.enterText(find.byKey(const Key('member-email')), 'not-an-email');
      await tester.tap(find.widgetWithText(FilledButton, 'Ajouter'));
      await settle(tester);
      expect(find.text('Adresse e-mail invalide'), findsOneWidget);
    });

    testWidgets('changes a role and removes a member after confirmation', (tester) async {
      final app = await pumpMe(tester, initialLocation: Routes.members(homeId));
      // Only Bob has a menu: the owner cannot be edited or removed.
      expect(find.byTooltip('Options du membre'), findsOneWidget);
      await tester.tap(find.byTooltip('Options du membre'));
      await settle(tester);
      await tester.tap(find.text('Changer le rôle'));
      await settle(tester);
      expect(find.text('Rôle du membre'), findsOneWidget);
      await tester.tap(find.text('Administrateur'));
      await settle(tester);
      expect(app.client.roleUpdates, [(userId: 'user-2', role: 'admin')]);
      expect(find.text('Rôle mis à jour'), findsOneWidget);

      await tester.tap(find.byTooltip('Options du membre'));
      await settle(tester);
      await tester.tap(find.text('Retirer'));
      await settle(tester);
      expect(find.text('Retirer Bob ?'), findsOneWidget);
      await tester.tap(find.widgetWithText(FilledButton, 'Retirer'));
      await settle(tester);
      expect(find.text('Bob'), findsNothing);
      expect(find.text('Membre retiré'), findsOneWidget);
      expect(find.byType(MemberTile), findsOneWidget);
    });

    testWidgets('plain members cannot manage the list', (tester) async {
      await pumpMe(tester, initialLocation: Routes.members(homeId), client: MeFakeHubClient(role: 'member'));
      expect(find.byType(MembersScreen), findsOneWidget);
      expect(find.byKey(const Key('members-add')), findsNothing);
      expect(find.byTooltip('Options du membre'), findsNothing);
      expect(find.text('Seuls le propriétaire et les administrateurs peuvent gérer les membres.'), findsOneWidget);
    });
  });

  group('MessageCenterScreen', () {
    testWidgets('tabs filter by kind and tapping a message marks it read', (tester) async {
      final app = await pumpMe(tester, initialLocation: Routes.messages);
      expect(find.text('Alarmes'), findsOneWidget);
      expect(find.text('Notifications'), findsOneWidget);
      expect(find.text('Mouvement détecté — Détecteur couloir'), findsOneWidget);
      expect(find.text('Nouvel appareil: Lampe salon'), findsNothing);
      expect(find.byKey(const ValueKey('unread-msg-1')), findsOneWidget);
      expect(find.text('Il y a 5 min'), findsOneWidget);

      await tester.tap(find.text('Mouvement détecté — Détecteur couloir'));
      await settle(tester);
      expect(find.byKey(const ValueKey('unread-msg-1')), findsNothing);
      expect((await app.client.unreadCount(homeId)).total, 1);
      expect(app.container.read(messagesProvider(homeId)).value!.firstWhere((m) => m.id == 'msg-1').read, isTrue);

      await tester.tap(find.text('Maison'));
      await settle(tester);
      expect(find.text('Nouvel appareil: Lampe salon'), findsOneWidget);
      expect(find.text('Mouvement détecté — Détecteur couloir'), findsNothing);

      await tester.tap(find.text('Notifications'));
      await settle(tester);
      expect(find.text('Bienvenue sur SafeR'), findsOneWidget);
      expect(find.byKey(const ValueKey('unread-msg-3')), findsOneWidget);
    });

    testWidgets('initialKind selects the tab and a device message opens the device', (tester) async {
      final client = MeFakeHubClient()
        ..extraMessages = [
          HubMessage(id: 'msg-dev', homeId: homeId, kind: 'notice', title: 'Batterie faible — Serrure entrée', deviceId: 'dev-lock', severity: 'critical', createdAt: DateTime.now()),
        ];
      await pumpMe(tester, initialLocation: '${Routes.messages}?kind=notice', client: client);
      expect(find.text('Bienvenue sur SafeR'), findsOneWidget);
      expect(find.text('Batterie faible — Serrure entrée'), findsOneWidget);
      await tester.tap(find.text('Batterie faible — Serrure entrée'));
      await settle(tester);
      expect(find.text('$kMeDeviceStubText dev-lock'), findsOneWidget);
      expect(client.extraMessages.single.read, isTrue);
    });

    testWidgets('mark all read, swipe to delete and clear the tab', (tester) async {
      final app = await pumpMe(tester, initialLocation: Routes.messages);
      await tester.tap(find.byKey(const Key('messages-read-all')));
      await settle(tester);
      expect(find.byKey(const ValueKey('unread-msg-1')), findsNothing);
      expect(find.text('Messages marqués comme lus'), findsOneWidget);
      // Only the current tab was affected.
      expect((await app.client.unreadCount(homeId)).notice, 1);

      await tester.drag(find.byType(MessageTile), const Offset(-600, 0));
      await settle(tester);
      expect(find.text('Mouvement détecté — Détecteur couloir'), findsNothing);
      expect(find.text('Message supprimé'), findsOneWidget);
      expect(find.text('Aucune alarme'), findsOneWidget);

      await tester.tap(find.text('Notifications'));
      await settle(tester);
      await tester.tap(find.byKey(const Key('messages-clear')));
      await settle(tester);
      expect(find.text('Effacer les messages ?'), findsOneWidget);
      await tester.tap(find.widgetWithText(FilledButton, 'Effacer'));
      await settle(tester);
      expect(find.text('Bienvenue sur SafeR'), findsNothing);
      expect(find.text('Aucune notification'), findsOneWidget);
      expect((await app.client.messages(homeId)).map((m) => m.id), ['msg-2']);
    });

    testWidgets('invites to create a home when the user has none', (tester) async {
      await pumpMe(tester, initialLocation: Routes.messages, client: MeFakeHubClient(noHomes: true));
      expect(find.byType(MessageCenterScreen), findsOneWidget);
      expect(find.text('Aucune maison'), findsOneWidget);
      expect(find.text('Créer une maison'), findsOneWidget);
    });
  });

  group('SettingsScreen', () {
    testWidgets('changes the locale, the theme and the realtime alerts toggle', (tester) async {
      final app = await pumpMe(tester, initialLocation: Routes.settings);
      expect(find.text('Paramètres'), findsOneWidget);
      expect(find.text('Système'), findsNWidgets(2));
      expect(find.text('SafeR 0.2.0'), findsOneWidget);

      await tester.tap(find.byKey(const Key('settings-language')));
      await settle(tester);
      expect(find.text('Langue'), findsNWidgets(2));
      await tester.tap(find.text('English'));
      await settle(tester);
      expect(app.container.read(localeProvider), const Locale('en'));
      expect(find.text('English'), findsOneWidget);

      await tester.tap(find.byKey(const Key('settings-theme')));
      await settle(tester);
      await tester.tap(find.text('Sombre'));
      await settle(tester);
      expect(app.container.read(themeModeProvider), ThemeMode.dark);
      expect(find.text('Sombre'), findsOneWidget);

      expect(await app.container.read(realtimeAlertsProvider.future), isTrue);
      await tester.tap(find.byKey(const Key('settings-realtime')));
      await settle(tester);
      expect(app.container.read(realtimeAlertsProvider).value, isFalse);
    });

    testWidgets('edits the hub URL with a connection test', (tester) async {
      final app = await pumpMe(tester, initialLocation: Routes.settings);
      expect(find.text('http://localhost:8000'), findsOneWidget);
      await tester.tap(find.byKey(const Key('settings-hub')));
      await settle(tester);
      expect(find.text('Hub SafeR'), findsNWidgets(2));
      await tester.enterText(find.byKey(const Key('settings-hub-url')), 'not a url');
      await tester.tap(find.text('Tester la connexion'));
      await settle(tester);
      expect(find.textContaining('URL invalide'), findsOneWidget);

      await tester.enterText(find.byKey(const Key('settings-hub-url')), 'http://192.168.1.20:8000/');
      await tester.tap(find.text('Tester la connexion'));
      await settle(tester);
      expect(find.text('Hub joignable'), findsOneWidget);
      await tester.tap(find.widgetWithText(FilledButton, 'Enregistrer'));
      await settle(tester);
      expect(app.container.read(hubUrlProvider), 'http://192.168.1.20:8000');
      expect(find.text('URL du hub enregistrée'), findsOneWidget);
      expect(find.text('http://192.168.1.20:8000'), findsOneWidget);
    });
  });

  group('AboutScreen', () {
    testWidgets('shows the version, the supported brands and the links', (tester) async {
      final app = await pumpMe(tester, initialLocation: Routes.about);
      expect(find.text('SafeR'), findsOneWidget);
      expect(find.text('Version 0.2.0'), findsOneWidget);
      expect(find.text('Marques compatibles'), findsOneWidget);
      expect(find.text('Tuya / Smart Life'), findsOneWidget);
      expect(find.text('Hikvision'), findsOneWidget);
      expect(find.text('Matter'), findsOneWidget);
      await tester.scrollUntilVisible(find.text('Code source'), 200, scrollable: find.byType(Scrollable).first);
      await tester.tap(find.text('Code source'));
      await settle(tester);
      expect(app.links.map((u) => u.toString()), [kSafeRRepoUrl]);
      await tester.scrollUntilVisible(find.text('Licences open source'), 200, scrollable: find.byType(Scrollable).first);
      expect(find.text('Licences open source'), findsOneWidget);
      expect(find.textContaining('SafeR CI'), findsWidgets);
    });
  });

  group('IntegrationsScreen', () {
    testWidgets('lists the integrations with their brand and deletes one', (tester) async {
      final app = await pumpMe(tester, initialLocation: Routes.integrations);
      expect(find.byType(IntegrationTile), findsNWidgets(2));
      expect(find.text('Tuya Cloud (eu)'), findsOneWidget);
      expect(find.text('tuya_cloud:abc'), findsOneWidget);
      expect(find.text('Tuya / Smart Life'), findsOneWidget);
      expect(find.text('Serveur Matter'), findsOneWidget);
      expect(find.text('Ajoutée il y a 3 j'), findsOneWidget);

      await tester.tap(find.byTooltip('Supprimer').first);
      await settle(tester);
      expect(find.text('Supprimer « Tuya Cloud (eu) » ?'), findsOneWidget);
      await tester.tap(find.widgetWithText(FilledButton, 'Supprimer'));
      await settle(tester);
      expect(app.client.deletedIntegrations, ['int-1']);
      expect(find.text('Tuya Cloud (eu)'), findsNothing);
      expect(find.byType(IntegrationTile), findsOneWidget);
      expect(find.text('Intégration supprimée'), findsOneWidget);

      await tester.tap(find.byKey(const Key('integrations-add')));
      await settle(tester);
      expect(find.text(kMeAddDeviceStubText), findsOneWidget);
    });

    testWidgets('shows an empty state leading to the add-device flow', (tester) async {
      final client = MeFakeHubClient()..integrations_.clear();
      await pumpMe(tester, initialLocation: Routes.integrations, client: client);
      expect(find.text('Aucune intégration'), findsOneWidget);
      await tester.tap(find.text('Ajouter un appareil'));
      await settle(tester);
      expect(find.text(kMeAddDeviceStubText), findsOneWidget);
    });
  });
}
