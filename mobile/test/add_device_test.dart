import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:safer_ci/core/api/api_exception.dart';
import 'package:safer_ci/core/models/models.dart';
import 'package:safer_ci/core/providers/providers.dart';
import 'package:safer_ci/core/router.dart';
import 'package:safer_ci/core/widgets/widgets.dart';
import 'package:safer_ci/features/add_device/brand_catalog_screen.dart';
import 'package:safer_ci/features/add_device/pairing_wizard_screen.dart';
import 'package:safer_ci/features/add_device/qr_scan_screen.dart';
import 'package:safer_ci/features/add_device/widgets/brand_card.dart';
import 'package:safer_ci/features/add_device/widgets/brand_color.dart';
import 'package:safer_ci/features/add_device/widgets/category_grid.dart';
import 'package:safer_ci/features/add_device/widgets/discovery_list.dart';
import 'package:safer_ci/features/add_device/widgets/matter_summary_card.dart';
import 'package:safer_ci/features/add_device/widgets/method_chooser.dart';
import 'package:safer_ci/features/add_device/widgets/pairing_error_card.dart';
import 'package:safer_ci/features/add_device/widgets/pairing_form.dart';
import 'package:safer_ci/features/add_device/widgets/pairing_progress.dart';
import 'package:safer_ci/features/add_device/widgets/pairing_success.dart';
import 'package:safer_ci/features/add_device/widgets/room_picker.dart';

import 'helpers/add_device_router.dart';
import 'helpers/fake_hub_client.dart';
import 'helpers/pump_app.dart';

const _matterQr = 'MT:Y.K9042C00KA0648G00';

/// Card of a brand in the catalogue.
Finder brandCard(String id) => find.byWidgetPredicate((w) => w is BrandCard && w.brand.id == id);

/// Fill the Hikvision "IP + credentials" form.
Future<void> _fillHikvision(WidgetTester tester, {String host = '192.168.1.64'}) async {
  await tester.enterText(find.byKey(pairingFieldKey('host')), host);
  await tester.enterText(find.byKey(pairingFieldKey('username')), 'admin');
  await tester.enterText(find.byKey(pairingFieldKey('password')), 'Secret123');
  await tester.pump();
}

Future<void> _tapButton(WidgetTester tester, String label) async {
  final finder = find.ancestor(of: find.text(label), matching: find.byWidgetPredicate((w) => w is ButtonStyleButton));
  await tester.ensureVisible(finder);
  await tester.pump();
  await tester.tap(finder);
  await settle(tester);
}

/// Client whose catalogue calls fail (used for the error/fallback paths).
class _NoCatalogueClient extends FakeHubClient {
  @override
  Future<List<BrandInfo>> brands() async => throw ApiException('Catalogue indisponible', status: 503);

  @override
  Future<List<CategoryGroup>> categories() async => throw ApiException('Catalogue indisponible', status: 503);
}

class _NoHomeClient extends FakeHubClient {
  @override
  Future<List<Home>> homes() async => [];
}

void main() {
  group('BrandCatalogScreen', () {
    testWidgets('lists the brands of the catalogue and the QR scan card', (tester) async {
      await pumpAddDevice(tester, size: const Size(400, 1500));
      expect(find.text('Ajouter un appareil'), findsOneWidget);
      expect(find.text('Scanner un code QR (Matter, Tuya)'), findsOneWidget);
      expect(find.text('Marques'), findsOneWidget);
      expect(find.byType(BrandCard), findsNWidgets(FakeHubClient.demoBrands.length));
      for (final brand in FakeHubClient.demoBrands) {
        expect(find.descendant(of: brandCard(brand.id), matching: find.text(brand.name)), findsOneWidget);
        expect(find.descendant(of: brandCard(brand.id), matching: find.text(brand.vendor)), findsOneWidget);
      }
      // Protocol chips.
      expect(find.text('tuya_cloud'), findsOneWidget);
      expect(find.text('isapi'), findsOneWidget);
    });

    testWidgets('search filters brands and categories', (tester) async {
      await pumpAddDevice(tester, size: const Size(400, 1500));
      await tester.enterText(find.byType(TextField), 'hik');
      await settle(tester);
      expect(find.byType(BrandCard), findsOneWidget);
      expect(brandCard('hikvision'), findsOneWidget);
      expect(find.text('Tuya / Smart Life'), findsNothing);
      // Group chips are hidden while searching; matching categories from every group are shown.
      expect(find.byType(CategoryGroupChips), findsNothing);
      expect(find.text('Sécurité'), findsNothing);

      await tester.enterText(find.byType(TextField), 'caméra');
      await settle(tester);
      expect(find.byType(CategoryTile), findsOneWidget);
      expect(find.byType(BrandCard), findsNothing);
      expect(find.text('Aucune marque trouvée'), findsOneWidget);

      await tester.tap(find.text('Effacer les filtres'));
      await settle(tester);
      expect(find.byType(BrandCard), findsNWidgets(FakeHubClient.demoBrands.length));
    });

    testWidgets('category grid renders the groups and filters brands by category', (tester) async {
      await pumpAddDevice(tester, size: const Size(400, 1500));
      expect(find.text('Ajouter manuellement'), findsOneWidget);
      expect(find.byType(CategoryGroupChips), findsOneWidget);
      // Chips for every group; first group (Éclairage) selected by default.
      expect(find.widgetWithText(ChoiceChip, 'Éclairage'), findsOneWidget);
      expect(find.widgetWithText(ChoiceChip, 'Caméras & vidéo'), findsOneWidget);
      expect(find.widgetWithText(ChoiceChip, 'Sécurité'), findsOneWidget);
      expect(find.byType(CategoryTile), findsOneWidget);
      expect(find.text('Tuya / Smart Life · Matter · Appareils de démonstration'), findsOneWidget);

      await tester.tap(find.widgetWithText(ChoiceChip, 'Caméras & vidéo'));
      await settle(tester);
      expect(find.widgetWithText(CategoryTile, 'Caméra'), findsOneWidget);

      await tester.tap(find.widgetWithText(CategoryTile, 'Caméra'));
      await settle(tester);
      // Brands filtered to the ones supporting cameras + filter chip in the header.
      expect(find.byType(InputChip), findsOneWidget);
      expect(find.byType(BrandCard), findsNWidgets(3));
      expect(brandCard('hikvision'), findsOneWidget);
      expect(brandCard('matter'), findsNothing);

      await tester.tap(find.byTooltip('Retirer le filtre'));
      await settle(tester);
      expect(find.byType(BrandCard), findsNWidgets(FakeHubClient.demoBrands.length));
    });

    testWidgets('tapping a brand opens the pairing wizard, the scan card opens the scanner', (tester) async {
      final app = await pumpAddDevice(tester, size: const Size(400, 1500), scannerBuilder: fakeScanner(_matterQr));
      await tester.tap(brandCard('hikvision'));
      await settle(tester);
      expect(app.router.state.uri.path, Routes.pair('hikvision'));
      expect(find.text('Adresse IP + identifiants'), findsOneWidget);

      app.router.go(Routes.addDevice);
      await settle(tester);
      await tester.tap(find.text('Scanner un code QR (Matter, Tuya)'));
      await settle(tester);
      expect(app.router.state.uri.path, Routes.scan);
      expect(find.byType(QrScanScreen), findsOneWidget);
    });

    testWidgets('shows error views with retry when the catalogue is unavailable', (tester) async {
      await pumpAddDevice(tester, client: _NoCatalogueClient(), size: const Size(400, 1500));
      expect(find.byType(ErrorView), findsNWidgets(2));
      expect(find.text('Réessayer'), findsNWidgets(2));
    });

    test('filter helpers', () {
      final brands = FakeHubClient.demoBrands;
      expect(filterBrands(brands, query: 'HIK').map((b) => b.id), ['hikvision']);
      expect(filterBrands(brands, query: 'isapi').map((b) => b.id), ['hikvision']);
      expect(filterBrands(brands, categoryId: 'lock').map((b) => b.id), ['matter']);
      const groups = [
        CategoryGroup(id: 'g', name: 'G', nameEn: 'G', icon: 'hub', categories: [DeviceCategoryInfo(id: 'x', name: 'X', nameEn: 'X', icon: 'hub', group: 'g', brands: ['demo'])]),
      ];
      expect(filterBrands(brands, categoryId: 'x', groups: groups).map((b) => b.id), ['demo']);
      expect(filterCategories(groups, query: 'zzz'), isEmpty);
      expect(filterCategories(groups, groupId: 'g').single.id, 'x');
      expect(colorFromHex('#FF4800'), const Color(0xFFFF4800));
      expect(colorFromHex('nope', fallback: Colors.red), Colors.red);
    });
  });

  group('PairingWizardScreen', () {
    testWidgets('shows the method chooser for Tuya and moves to the chosen form', (tester) async {
      await pumpAddDevice(tester, initialLocation: Routes.pair('tuya'));
      expect(find.text('Tuya / Smart Life'), findsOneWidget);
      expect(find.byType(MethodChooser), findsOneWidget);
      expect(find.widgetWithText(MethodCard, 'Projet Tuya Cloud'), findsOneWidget);
      expect(find.widgetWithText(MethodCard, 'Clé locale'), findsOneWidget);
      expect(find.text('Détection automatique'), findsOneWidget);
      expect(find.text('Compte requis'), findsOneWidget);

      await tester.tap(find.widgetWithText(MethodCard, 'Projet Tuya Cloud'));
      await settle(tester);
      expect(find.byType(PairingForm), findsOneWidget);
      // Select field with its default, text + password fields.
      expect(find.byType(DropdownButtonFormField<String>), findsOneWidget);
      expect(find.text('Europe'), findsOneWidget);
      expect(find.byKey(pairingFieldKey('access_id')), findsOneWidget);
      expect(find.byKey(pairingFieldKey('access_secret')), findsOneWidget);
      expect(find.text('Rechercher les appareils'), findsOneWidget);

      // Back returns to the method chooser instead of leaving the wizard.
      await tester.tap(find.byType(BackButton));
      await settle(tester);
      expect(find.byType(MethodChooser), findsOneWidget);
    });

    testWidgets('renders the Hikvision ip_credentials fields', (tester) async {
      await pumpAddDevice(tester, initialLocation: Routes.pair('hikvision'));
      expect(find.text('Hikvision'), findsOneWidget);
      expect(find.text('Adresse IP + identifiants'), findsOneWidget);
      expect(find.byType(MethodChooser), findsNothing);
      expect(find.byKey(pairingFieldKey('host')), findsOneWidget);
      expect(find.byKey(pairingFieldKey('port')), findsOneWidget);
      expect(find.byKey(pairingFieldKey('https')), findsOneWidget);
      expect(find.byKey(pairingFieldKey('username')), findsOneWidget);
      expect(find.byKey(pairingFieldKey('password')), findsOneWidget);
      expect(find.text('Adresse IP'), findsOneWidget);
      expect(find.text('Utilisateur'), findsOneWidget);
      expect(find.text('Mot de passe'), findsOneWidget);
      // Defaults applied: port 80, HTTPS off (optional toggle).
      expect(find.text('80'), findsOneWidget);
      expect(find.byType(SwitchListTile), findsOneWidget);
      expect(tester.widget<SwitchListTile>(find.byType(SwitchListTile)).value, isFalse);
      expect(find.text('HTTPS'), findsOneWidget);
      // Password is obscured until the eye is tapped.
      TextField password() => tester.widget<TextField>(find.descendant(of: find.byKey(pairingFieldKey('password')), matching: find.byType(TextField)));
      expect(password().obscureText, isTrue);
      await tester.tap(find.byTooltip('Afficher le mot de passe'));
      await tester.pump();
      expect(password().obscureText, isFalse);
      expect(find.byTooltip('Masquer le mot de passe'), findsOneWidget);
      expect(find.text('Continuer'), findsOneWidget);
    });

    testWidgets('required validation blocks submit', (tester) async {
      await pumpAddDevice(tester, initialLocation: Routes.pair('hikvision'));
      await _tapButton(tester, 'Continuer');
      expect(find.text('Ce champ est obligatoire'), findsNWidgets(3));
      expect(find.byType(PairingForm), findsOneWidget);
      expect(find.byType(RoomPicker), findsNothing);
      expect(find.byType(PairingProgressView), findsNothing);
      // Invalid number.
      await tester.enterText(find.byKey(pairingFieldKey('port')), 'abc');
      await tester.pump();
      expect(find.text('Nombre invalide'), findsOneWidget);
    });

    testWidgets('unreachable device shows the hub message and the IP hint', (tester) async {
      await pumpAddDevice(tester, initialLocation: Routes.pair('hikvision'));
      await _fillHikvision(tester, host: '10.0.0.99');
      await _tapButton(tester, 'Continuer');
      expect(find.byType(RoomPicker), findsOneWidget);
      await _tapButton(tester, 'Ajouter');
      expect(find.byType(PairingErrorCard), findsOneWidget);
      expect(find.text("Échec de l'ajout"), findsOneWidget);
      expect(find.text('Connexion impossible'), findsOneWidget);
      expect(find.textContaining("Vérifiez l'adresse IP"), findsOneWidget);
      expect(find.text('Réessayer'), findsOneWidget);

      await tester.tap(find.text('Modifier les informations'));
      await settle(tester);
      expect(find.byType(PairingForm), findsOneWidget);
      // Values are kept when coming back to the form.
      expect(find.text('10.0.0.99'), findsOneWidget);
    });

    testWidgets('successful pairing lists the devices and Terminer adds them to the home', (tester) async {
      final client = FakeHubClient();
      final app = await pumpAddDevice(tester, initialLocation: Routes.pair('hikvision'), client: client);
      await _fillHikvision(tester);
      await _tapButton(tester, 'Continuer');
      expect(find.byType(RoomPicker), findsOneWidget);
      expect(find.text('Aucune pièce'), findsOneWidget);
      expect(find.text('Salon'), findsOneWidget);
      await tester.tap(find.text('Salon'));
      await tester.pump();
      await tester.tap(find.widgetWithText(FilledButton, 'Ajouter'));
      await tester.pump();
      expect(find.byType(PairingProgressView), findsOneWidget);
      expect(find.text("Connexion à l'appareil..."), findsOneWidget);
      await settle(tester);
      expect(find.byType(PairingSuccessView), findsOneWidget);
      expect(find.text('Appareil ajouté'), findsOneWidget);
      expect(find.text('1 appareil ajouté'), findsOneWidget);
      expect(find.text('Nouvel appareil hikvision'), findsOneWidget);
      expect(find.text('Éclairage · Salon'), findsOneWidget);
      expect(find.text('Terminer'), findsOneWidget);
      expect(find.text('Ajouter un autre'), findsOneWidget);

      await tester.tap(find.text('Terminer'));
      await settle(tester);
      expect(find.text(kHomeStubText), findsOneWidget);
      final devices = app.container.read(devicesProvider(FakeHubClient.homeId)).value ?? const <Device>[];
      expect(devices.any((d) => d.name == 'Nouvel appareil hikvision' && d.roomId == 'room-1'), isTrue);
    });

    testWidgets('discovery step lists the found devices with checkboxes', (tester) async {
      await pumpAddDevice(tester, initialLocation: Routes.pair('demo'));
      expect(find.text('Ajouter la maison de démonstration'), findsOneWidget);
      expect(find.text('Préfixe (optionnel)'), findsOneWidget);
      await _tapButton(tester, 'Rechercher les appareils');
      expect(find.byType(DiscoveryList), findsOneWidget);
      expect(find.text('2 appareils trouvés'), findsOneWidget);
      expect(find.text('Lampe découverte'), findsOneWidget);
      expect(find.text('Prise découverte'), findsOneWidget);
      expect(find.text('Éclairage · X1 · 192.168.1.10'), findsOneWidget);
      final boxes = find.byType(CheckboxListTile);
      expect(boxes, findsNWidgets(2));
      expect(tester.widgetList<CheckboxListTile>(boxes).every((c) => c.value == true), isTrue);

      // Unselect everything → the button is disabled; reselect one.
      await tester.tap(find.text('Tout désélectionner'));
      await tester.pump();
      expect(tester.widget<FilledButton>(find.widgetWithText(FilledButton, 'Ajouter les appareils sélectionnés')).enabled, isFalse);
      await tester.tap(find.text('Lampe découverte'));
      await tester.pump();
      expect(tester.widget<FilledButton>(find.widgetWithText(FilledButton, 'Ajouter les appareils sélectionnés')).enabled, isTrue);

      await _tapButton(tester, 'Ajouter les appareils sélectionnés');
      expect(find.byType(RoomPicker), findsOneWidget);
      await _tapButton(tester, 'Ajouter');
      expect(find.byType(PairingSuccessView), findsOneWidget);
      expect(find.text('Nouvel appareil demo'), findsOneWidget);

      // "Add another" restarts the flow on the form.
      await _tapButton(tester, 'Ajouter un autre');
      expect(find.byType(PairingForm), findsOneWidget);
    });

    testWidgets('Matter wizard shows the decoded summary for a prefilled code', (tester) async {
      await pumpAddDevice(tester, initialLocation: Routes.pair('matter', method: 'manual_code'));
      expect(find.byType(MethodChooser), findsNothing);
      expect(find.text('Code à 11 chiffres'), findsOneWidget);
      await tester.enterText(find.byKey(pairingFieldKey('code')), '34970112331');
      await tester.pump();
      expect(find.text('Code Matter invalide'), findsOneWidget);
      await _tapButton(tester, 'Continuer');
      expect(find.byType(RoomPicker), findsNothing);

      await tester.enterText(find.byKey(pairingFieldKey('code')), '34970112332');
      await tester.pump();
      expect(find.byType(MatterSummaryCard), findsOneWidget);
      expect(find.text('Appareil Matter détecté'), findsOneWidget);
      expect(find.textContaining('Discriminant court 15'), findsOneWidget);
    });

    testWidgets('shows the create-home empty state when the user has no home', (tester) async {
      await pumpAddDevice(tester, initialLocation: Routes.pair('hikvision'), client: _NoHomeClient());
      expect(find.text("Créez d'abord une maison"), findsOneWidget);
      await tester.tap(find.text('Gérer mes maisons'));
      await settle(tester);
      expect(find.text(kHomesStubText), findsOneWidget);
    });

    testWidgets('falls back to a direct brand fetch when the catalogue fails', (tester) async {
      await pumpAddDevice(tester, initialLocation: Routes.pair('hikvision'), client: _NoCatalogueClient());
      expect(find.text('Hikvision'), findsOneWidget);
      expect(find.byType(PairingForm), findsOneWidget);
    });
  });

  group('QrScanScreen', () {
    testWidgets('a detected MT: code opens the Matter wizard with the code prefilled', (tester) async {
      final app = await pumpAddDevice(tester, initialLocation: Routes.scan, scannerBuilder: fakeScanner(_matterQr));
      expect(find.text('Scanner un code'), findsOneWidget);
      expect(find.text('Placez le code QR dans le cadre'), findsOneWidget);
      expect(find.text('Saisir manuellement'), findsOneWidget);
      expect(find.byTooltip('Allumer la lampe torche'), findsOneWidget);

      await tester.tap(find.text('simulate scan'));
      await settle(tester);
      expect(app.router.state.uri.path, Routes.pair('matter'));
      expect(app.router.state.uri.queryParameters['method'], 'qr_code');
      expect(find.byType(QrScanScreen), findsNothing);
      expect(find.byType(PairingWizardScreen), findsOneWidget);
      expect(find.text('Scanner le code QR Matter'), findsOneWidget);
      expect(find.text(_matterQr), findsOneWidget);
      expect(find.text('Appareil Matter détecté'), findsOneWidget);
      expect(find.text('Fabricant 0xFFF1 · Produit 0x8000 · Discriminant 3840'), findsOneWidget);
      // The scanner replaced itself: back leaves the wizard for the catalogue.
      expect(app.router.canPop(), isTrue);
    });

    testWidgets('an unknown code shows the "Code non reconnu" snack and stays on the scanner', (tester) async {
      final app = await pumpAddDevice(tester, initialLocation: Routes.scan, scannerBuilder: fakeScanner('https://example.com/whatever'));
      await tester.tap(find.text('simulate scan'));
      await settle(tester);
      expect(find.text('Code non reconnu'), findsOneWidget);
      expect(app.router.state.uri.path, Routes.scan);
      await tester.pump(const Duration(seconds: 3));
    });

    testWidgets('manual entry dialog accepts a typed code', (tester) async {
      final app = await pumpAddDevice(tester, initialLocation: Routes.scan, scannerBuilder: fakeScanner('unused'));
      await tester.tap(find.text('Saisir manuellement'));
      await settle(tester);
      expect(find.text('Saisir le code'), findsOneWidget);
      await tester.enterText(find.byType(TextField), _matterQr);
      await tester.tap(find.text('Valider'));
      await settle(tester);
      expect(app.router.state.uri.path, Routes.pair('matter'));
      expect(find.text(_matterQr), findsOneWidget);
    });

    testWidgets('the wizard "Scanner" button opens the scanner and takes the result back', (tester) async {
      final app = await pumpAddDevice(tester, initialLocation: Routes.pair('matter', method: 'qr_code'), scannerBuilder: fakeScanner(_matterQr));
      expect(find.text('Scanner'), findsOneWidget);
      await tester.tap(find.text('Scanner'));
      await settle(tester);
      expect(app.router.state.uri.path, Routes.scan);
      expect(app.router.state.uri.queryParameters[kScanResultQuery], '1');
      expect(find.text('Le code sera reporté dans le formulaire.'), findsOneWidget);
      await tester.tap(find.text('simulate scan'));
      await settle(tester);
      expect(app.router.state.uri.path, Routes.pair('matter'));
      expect(find.text(_matterQr), findsOneWidget);
      expect(find.text('Appareil Matter détecté'), findsOneWidget);
    });

    testWidgets('torch button toggles its icon and the overlay is present', (tester) async {
      await pumpAddDevice(tester, initialLocation: Routes.scan, scannerBuilder: fakeScanner('unused'));
      await tester.tap(find.byTooltip('Allumer la lampe torche'));
      await tester.pump();
      expect(find.byTooltip('Éteindre la lampe torche'), findsOneWidget);
      expect(find.byIcon(Icons.flash_on), findsOneWidget);
    });
  });

  group('widgets', () {
    testWidgets('PairingErrorCard maps hub codes to hints', (tester) async {
      await pumpApp(tester, Scaffold(body: PairingErrorCard(error: ApiException('Bad credentials', status: 401, code: 'auth_failed'), onRetry: () {})));
      expect(find.text('Bad credentials'), findsOneWidget);
      expect(find.textContaining("Vérifiez le nom d'utilisateur"), findsOneWidget);
      expect(pairingErrorCode(ApiException('x', status: 502)), 'unreachable');
      expect(pairingErrorCode(ApiException('x', status: null)), 'unreachable');
      expect(pairingErrorCode(ApiException('x', status: 401)), 'auth_failed');
      expect(pairingErrorCode(ApiException('x', status: 400)), 'invalid_input');
      expect(pairingErrorCode(StateError('x')), isNull);
    });

    testWidgets('MatterSummaryCard renders the vendor/product/discriminator line', (tester) async {
      await pumpApp(tester, const Scaffold(body: MatterSummaryCard(code: 'MT:-24J0AFN00KA0648G00')));
      expect(find.text('Appareil Matter détecté'), findsOneWidget);
      expect(find.text('Fabricant 0xFFF1 · Produit 0x8001 · Discriminant 3840'), findsOneWidget);
      expect(find.text('Réseau IP'), findsOneWidget);
    });
  });
}
