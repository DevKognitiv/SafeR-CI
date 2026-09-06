import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:safer_ci/core/router.dart';
import 'package:safer_ci/core/widgets/widgets.dart';
import 'package:safer_ci/features/scenes/automation_editor_screen.dart';
import 'package:safer_ci/features/scenes/scene_editor_screen.dart';
import 'package:safer_ci/features/scenes/widgets/automation_card.dart';
import 'package:safer_ci/features/scenes/widgets/scene_card.dart';

import 'helpers/fake_hub_client.dart';
import 'helpers/pump_app.dart';
import 'helpers/scenes_fake_client.dart';
import 'helpers/scenes_router.dart';

const homeId = FakeHubClient.homeId;

void main() {
  group('ScenesScreen · Exécuter', () {
    testWidgets('renders the scene grid and runs a scene on tap', (tester) async {
      final app = await pumpScenes(tester);
      expect(find.byType(SceneCard), findsNWidgets(2));
      expect(find.text('Bonne nuit'), findsOneWidget);
      expect(find.text('Je pars'), findsOneWidget);
      expect(find.textContaining('2 actions'), findsOneWidget);
      expect(find.textContaining('1 action'), findsOneWidget);
      expect(find.textContaining('Jamais exécutée'), findsNWidgets(2));

      await tester.tap(find.text('Bonne nuit'));
      await settle(tester);
      expect(app.client.runCalls, ['scene-1']);
      expect(find.text('Scène exécutée'), findsOneWidget);
    });

    testWidgets('shows the empty state with a call to action', (tester) async {
      await pumpScenes(tester, client: ScenesFakeHubClient(noScenes: true));
      expect(find.byType(EmptyState), findsOneWidget);
      expect(find.text('Aucune scène'), findsOneWidget);
      expect(find.text('Créer une scène'), findsOneWidget);
      await tester.tap(find.text('Créer une scène'));
      await settle(tester);
      expect(find.byType(SceneEditorScreen), findsOneWidget);
      expect(find.text('Nouvelle scène'), findsOneWidget);
    });

    testWidgets('invites to create a home when the user has none', (tester) async {
      await pumpScenes(tester, client: ScenesFakeHubClient(noHomes: true));
      expect(find.text('Créez votre première maison'), findsOneWidget);
      await tester.tap(find.text('Créer une maison'));
      await settle(tester);
      expect(find.text(kScenesHomesStubText), findsOneWidget);
    });

    testWidgets('long press offers to delete a scene', (tester) async {
      final app = await pumpScenes(tester);
      await tester.longPress(find.text('Je pars'));
      await settle(tester);
      expect(find.text('Modifier'), findsOneWidget);
      await tester.tap(find.text('Supprimer'));
      await settle(tester);
      expect(find.text('Supprimer la scène ?'), findsOneWidget);
      await tester.tap(find.widgetWithText(FilledButton, 'Supprimer'));
      await settle(tester);
      expect(find.text('Je pars'), findsNothing);
      expect(find.text('Scène supprimée'), findsOneWidget);
      expect((await app.client.scenes(homeId)).map((s) => s.id), ['scene-1']);
    });

    testWidgets('long press > Modifier opens the editor prefilled', (tester) async {
      await pumpScenes(tester);
      await tester.longPress(find.text('Bonne nuit'));
      await settle(tester);
      await tester.tap(find.text('Modifier'));
      await settle(tester);
      expect(find.byType(SceneEditorScreen), findsOneWidget);
      expect(find.text('Modifier la scène'), findsOneWidget);
      expect(find.widgetWithText(TextField, 'Bonne nuit'), findsOneWidget);
      expect(find.textContaining('Lampe salon éteindre'), findsOneWidget);
      expect(find.textContaining('Mode sécurité : Nuit'), findsOneWidget);
    });
  });

  group('ScenesScreen · Automatiser', () {
    testWidgets('lists automations with a human summary and toggles them', (tester) async {
      final app = await pumpScenes(tester, initialLocation: '${Routes.scenes}?tab=automations');
      expect(find.byType(AutomationCard), findsOneWidget);
      expect(find.text('Lumière si mouvement'), findsOneWidget);
      expect(find.text('Détecteur couloir mouvement = oui'), findsOneWidget);
      expect(find.text('Entre 19:00 et 06:00'), findsOneWidget);
      expect(find.text('Lampe salon allumer'), findsOneWidget);

      await tester.tap(find.byType(Switch));
      await settle(tester);
      expect(app.client.enabledCalls, [(id: 'auto-1', enabled: false)]);
      expect(tester.widget<Switch>(find.byType(Switch)).value, isFalse);
    });

    testWidgets('"Tester" triggers the automation', (tester) async {
      final app = await pumpScenes(tester, initialLocation: '${Routes.scenes}?tab=automations');
      await tester.tap(find.text('Tester'));
      await settle(tester);
      expect(app.client.triggerCalls, ['auto-1']);
      expect(find.text('Automatisation testée'), findsOneWidget);
    });

    testWidgets('swipe to delete asks for confirmation then removes the automation', (tester) async {
      final app = await pumpScenes(tester, initialLocation: '${Routes.scenes}?tab=automations');
      await tester.drag(find.byType(Dismissible), const Offset(-400, 0));
      await settle(tester);
      expect(find.text("Supprimer l'automatisation ?"), findsOneWidget);
      await tester.tap(find.widgetWithText(FilledButton, 'Supprimer'));
      await settle(tester);
      expect(find.text('Lumière si mouvement'), findsNothing);
      expect(find.text('Aucune automatisation'), findsOneWidget);
      expect(await app.client.automations(homeId), isEmpty);
    });

    testWidgets('shows the empty state with a call to action', (tester) async {
      await pumpScenes(tester, initialLocation: '${Routes.scenes}?tab=automations', client: ScenesFakeHubClient(noAutomations: true));
      expect(find.text('Aucune automatisation'), findsOneWidget);
      await tester.tap(find.text('Créer une automatisation'));
      await settle(tester);
      expect(find.byType(AutomationEditorScreen), findsOneWidget);
    });
  });

  group('SceneEditorScreen', () {
    testWidgets('creates a scene with a device_command action', (tester) async {
      final app = await pumpScenes(tester, initialLocation: Routes.sceneNew);
      await tester.enterText(find.byType(TextField), 'Soirée ciné');
      await tester.pump();

      await tester.tap(find.text('Ajouter une action'));
      await settle(tester);
      await tester.tap(find.text('Contrôler un appareil'));
      await settle(tester);
      expect(find.text('Salon'), findsOneWidget); // grouped by room
      await tester.tap(find.text('Lampe salon'));
      await settle(tester);
      await tester.tap(find.text('Interrupteur'));
      await settle(tester);
      expect(find.text('Lampe salon · Interrupteur'), findsOneWidget);
      expect(find.byType(SwitchListTile), findsOneWidget);
      await tester.tap(find.text('Valider'));
      await settle(tester);
      expect(find.text('Lampe salon allumer'), findsOneWidget);

      await tester.tap(find.text('Enregistrer'));
      await settle(tester, frames: 20);
      final scenes = await app.client.scenes(homeId);
      expect(scenes, hasLength(3));
      final created = scenes.last;
      expect(created.name, 'Soirée ciné');
      expect(created.icon, 'play_circle');
      expect(created.color, '#2563EB');
      expect(created.actions.single.data, {'type': 'device_command', 'device_id': 'dev-light', 'code': 'switch', 'value': true});
      // Back on the list, the new scene is visible.
      expect(find.byType(SceneEditorScreen), findsNothing);
      expect(find.text('Soirée ciné'), findsOneWidget);
    });

    testWidgets('refuses to save without a name or without actions', (tester) async {
      final app = await pumpScenes(tester, initialLocation: Routes.sceneNew);
      await tester.tap(find.text('Enregistrer'));
      await settle(tester);
      expect(find.text('Donnez un nom à la scène'), findsOneWidget);
      await tester.pump(const Duration(seconds: 5)); // let the first snackbar expire (they queue)
      await settle(tester);
      await tester.enterText(find.byType(TextField), 'Vide');
      await tester.tap(find.text('Enregistrer'));
      await settle(tester);
      expect(find.text('Ajoutez au moins une action'), findsOneWidget);
      expect(await app.client.scenes(homeId), hasLength(2));
    });

    testWidgets('edits icon/colour and removes an action of an existing scene', (tester) async {
      final app = await pumpScenes(tester, initialLocation: Routes.scene('scene-1'));
      expect(find.textContaining('Lampe salon éteindre'), findsOneWidget);
      await tester.tap(find.bySemanticsLabel('Icône movie'));
      await tester.tap(find.bySemanticsLabel('Couleur #16A34A'));
      await tester.pump();
      await tester.tap(find.byTooltip('Supprimer').first);
      await tester.pump();
      expect(find.textContaining('Lampe salon éteindre'), findsNothing);
      await tester.tap(find.text('Enregistrer'));
      await settle(tester);
      final scene = (await app.client.scenes(homeId)).firstWhere((s) => s.id == 'scene-1');
      expect(scene.icon, 'movie');
      expect(scene.color, '#16A34A');
      expect(scene.actions.single.type, 'security_mode');
    });
  });

  group('AutomationEditorScreen', () {
    testWidgets('creates an automation with a schedule trigger and a security_mode action', (tester) async {
      final app = await pumpScenes(tester, initialLocation: Routes.automationNew);
      await tester.enterText(find.byType(TextField), 'Armer le soir');
      await tester.pump();

      await tester.tap(find.text('Ajouter un déclencheur'));
      await settle(tester);
      await tester.tap(find.text('Programmation'));
      await settle(tester);
      expect(find.text('07:00'), findsOneWidget);
      expect(find.text('Lun'), findsOneWidget);
      await tester.tap(find.text('Valider'));
      await settle(tester);
      expect(find.text('À 07:00 · Tous les jours'), findsOneWidget);

      await tester.ensureVisible(find.text('Ajouter une action'));
      await settle(tester);
      await tester.tap(find.text('Ajouter une action'));
      await settle(tester);
      await tester.tap(find.text('Mode de sécurité'));
      await settle(tester);
      await tester.tap(find.text('Absent'));
      await tester.pump();
      await tester.tap(find.text('Valider'));
      await settle(tester);
      expect(find.text('Mode sécurité : Absent'), findsOneWidget);

      await tester.tap(find.text('Enregistrer'));
      await settle(tester, frames: 20);
      final automations = await app.client.automations(homeId);
      expect(automations, hasLength(2));
      final created = automations.last;
      expect(created.name, 'Armer le soir');
      expect(created.enabled, isTrue);
      expect(created.match, 'all');
      expect(created.triggers.single.data, {'type': 'schedule', 'time': '07:00', 'days': [0, 1, 2, 3, 4, 5, 6]});
      expect(created.actions.single.data, {'type': 'security_mode', 'mode': 'armed_away'});
      expect(find.byType(AutomationEditorScreen), findsNothing);
    });

    testWidgets('edits an existing automation (prefilled) and deletes it', (tester) async {
      final app = await pumpScenes(tester, initialLocation: Routes.automation('auto-1'));
      expect(find.widgetWithText(TextField, 'Lumière si mouvement'), findsOneWidget);
      expect(find.text('Détecteur couloir mouvement = oui'), findsOneWidget);
      expect(find.text('Entre 19:00 et 06:00'), findsOneWidget);
      // The "Alors" list is below the fold on a 400x800 viewport.
      await tester.scrollUntilVisible(
        find.text('Lampe salon allumer'),
        150,
        scrollable: find.descendant(of: find.byType(CustomScrollView), matching: find.byType(Scrollable)).first,
      );
      await settle(tester);
      expect(find.text('Lampe salon allumer'), findsOneWidget);
      expect(find.text('Ajouter une action'), findsOneWidget);

      await tester.tap(find.byTooltip("Supprimer l'automatisation"));
      await settle(tester);
      await tester.tap(find.widgetWithText(FilledButton, 'Supprimer'));
      await settle(tester, frames: 20);
      expect(await app.client.automations(homeId), isEmpty);
      expect(find.byType(AutomationEditorScreen), findsNothing);
      expect(find.text('Aucune automatisation'), findsOneWidget);
    });
  });
}
