import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/i18n.dart';
import '../../core/models/models.dart';
import '../../core/providers/providers.dart';
import '../../core/router.dart';
import '../../core/widgets/widgets.dart';
import 'matter_payload.dart';
import 'qr_scan_screen.dart';
import 'widgets/brand_color.dart';
import 'widgets/discovery_list.dart';
import 'widgets/matter_summary_card.dart';
import 'widgets/method_chooser.dart';
import 'widgets/pairing_error_card.dart';
import 'widgets/pairing_form.dart';
import 'widgets/pairing_progress.dart';
import 'widgets/pairing_success.dart';
import 'widgets/room_picker.dart';

/// Brand for the wizard: from the cached catalogue, else fetched directly.
final pairingBrandProvider = FutureProvider.autoDispose.family<BrandInfo, String>((ref, brandId) async {
  try {
    final brands = await ref.watch(brandsProvider.future);
    for (final b in brands) {
      if (b.id == brandId) return b;
    }
  } catch (_) {
    // Catalogue unavailable: fall through to a direct fetch.
  }
  return ref.read(hubClientProvider).brand(brandId);
});

enum PairingStep { method, form, discovery, room, pairing, failed, success }

/// Tuya-style pairing wizard: method → form → (discovery) → (room) → pairing → success.
class PairingWizardScreen extends ConsumerStatefulWidget {
  const PairingWizardScreen({super.key, required this.brandId, this.method, this.prefill});

  final String brandId;
  final String? method;

  /// Values applied to the form fields (e.g. the scanned `code`).
  final Map<String, dynamic>? prefill;

  @override
  ConsumerState<PairingWizardScreen> createState() => _PairingWizardScreenState();
}

class _PairingWizardScreenState extends ConsumerState<PairingWizardScreen> {
  PairingStep _step = PairingStep.form;
  bool _initialised = false;
  BrandInfo? _brand;
  PairingMethod? _method;
  Map<String, dynamic> _values = {};
  int _formGeneration = 0;
  List<DiscoveredDevice>? _discovered;
  Set<String> _selected = {};
  bool _discovering = false;
  Object? _discoveryError;
  String? _roomId;
  List<Device> _paired = const [];
  String _pairMessage = '';
  Object? _pairError;

  bool get _hasMethodChooser => (_brand?.methods.length ?? 0) > 1 && widget.method == null;

  // ------------------------------------------------------------------ setup
  void _initialise(BrandInfo brand) {
    if (_initialised) return;
    _initialised = true;
    _brand = brand;
    final requested = widget.method == null ? null : brand.method(widget.method!);
    if (requested != null) {
      _applyMethod(requested);
    } else if (brand.methods.length == 1) {
      _applyMethod(brand.methods.first);
    } else if (brand.methods.isEmpty) {
      _method = null;
      _step = PairingStep.form;
    } else {
      _step = PairingStep.method;
    }
  }

  void _applyMethod(PairingMethod method) {
    _method = method;
    _values = _initialValues(method);
    _discovered = null;
    _selected = {};
    _formGeneration++;
    _step = PairingStep.form;
  }

  Map<String, dynamic> _initialValues(PairingMethod method) {
    final prefill = widget.prefill ?? const <String, dynamic>{};
    return {
      for (final f in method.fields)
        if (prefill.containsKey(f.name)) f.name: prefill[f.name] else if (f.defaultValue != null) f.name: f.defaultValue,
    };
  }

  // ------------------------------------------------------------------ steps
  void _onFormSubmitted(Map<String, dynamic> values) {
    _values = values;
    if (_method?.supportsDiscovery ?? false) {
      _startDiscovery();
    } else {
      _goToRoomOrPair();
    }
  }

  void _goToRoomOrPair() {
    final home = ref.read(currentHomeProvider);
    if (home == null) return;
    if (ref.read(roomsProvider(home.id)).isEmpty) {
      _pair();
    } else {
      setState(() => _step = PairingStep.room);
    }
  }

  Future<void> _startDiscovery() async {
    final home = ref.read(currentHomeProvider);
    final method = _method;
    if (home == null || method == null) return;
    setState(() {
      _step = PairingStep.discovery;
      _discovering = true;
      _discoveryError = null;
    });
    try {
      final found = await ref.read(hubClientProvider).discover(widget.brandId, homeId: home.id, method: method.id, payload: _values);
      if (!mounted) return;
      setState(() {
        _discovered = found;
        _selected = found.map((d) => d.externalId).toSet();
        _discovering = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _discoveryError = e;
        _discovering = false;
      });
    }
  }

  Future<void> _pair() async {
    final home = ref.read(currentHomeProvider);
    final method = _method;
    if (home == null || method == null) return;
    setState(() {
      _step = PairingStep.pairing;
      _pairError = null;
    });
    try {
      final result = await ref.read(hubClientProvider).pair(
            widget.brandId,
            homeId: home.id,
            method: method.id,
            payload: _values,
            roomId: _roomId,
            selectedExternalIds: _discovered == null ? null : _selected.toList(),
          );
      if (!mounted) return;
      setState(() {
        _paired = result.devices;
        _pairMessage = result.message;
        _step = PairingStep.success;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _pairError = e;
        _step = PairingStep.failed;
      });
    }
  }

  void _finish(Home home) {
    ref.read(devicesProvider(home.id).notifier).addAll(_paired);
    context.go(Routes.home);
  }

  void _addAnother() {
    setState(() {
      _paired = const [];
      _pairMessage = '';
      _pairError = null;
      _discovered = null;
      _selected = {};
      _roomId = null;
      if (_hasMethodChooser) {
        _method = null;
        _step = PairingStep.method;
      } else {
        _formGeneration++;
        _step = PairingStep.form;
      }
    });
  }

  /// In-wizard back navigation; false when the route itself should pop.
  bool _back() {
    switch (_step) {
      case PairingStep.form:
        if (!_hasMethodChooser) return false;
        setState(() => _step = PairingStep.method);
      case PairingStep.discovery:
      case PairingStep.failed:
        setState(() => _step = PairingStep.form);
      case PairingStep.room:
        setState(() => _step = _discovered != null ? PairingStep.discovery : PairingStep.form);
      case PairingStep.pairing:
        break; // wait for the hub
      case PairingStep.method:
      case PairingStep.success:
        return false;
    }
    return true;
  }

  bool get _canPop => _step == PairingStep.method || _step == PairingStep.success || (_step == PairingStep.form && !_hasMethodChooser);

  double _progress(bool hasRooms) {
    final steps = [
      if (_hasMethodChooser) PairingStep.method,
      PairingStep.form,
      if (_method?.supportsDiscovery ?? false) PairingStep.discovery,
      if (hasRooms) PairingStep.room,
      PairingStep.pairing,
    ];
    final current = switch (_step) {
      PairingStep.failed || PairingStep.success => PairingStep.pairing,
      _ => _step,
    };
    final index = steps.indexOf(current);
    return ((index < 0 ? steps.length : index) + 1) / steps.length;
  }

  // ------------------------------------------------------------------ helpers for the form
  Future<String?> _scan(FormFieldSpec field) => context.push<String>(scanForResultLocation());

  bool _isMatterCodeField(FormFieldSpec field) => widget.brandId == 'matter' && (field.type == 'qr' || field.name == 'code');

  String? _validateField(FormFieldSpec field, String value) {
    if (_isMatterCodeField(field) || isMatterQr(value)) {
      if (tryParseMatterCode(value) == null) return context.tr(fr: 'Code Matter invalide', en: 'Invalid Matter code');
    }
    return null;
  }

  Widget? _formFooter(BuildContext context, Map<String, dynamic> values) {
    for (final field in _method?.fields ?? const <FormFieldSpec>[]) {
      final value = values[field.name]?.toString() ?? '';
      if (value.isEmpty) continue;
      if (_isMatterCodeField(field) || isMatterQr(value)) return MatterSummaryCard(code: value);
    }
    return null;
  }

  String _submitLabel(BuildContext context, bool hasRooms) {
    if (_method?.supportsDiscovery ?? false) return context.tr(fr: 'Rechercher les appareils', en: 'Search for devices');
    return hasRooms ? context.tr(fr: 'Continuer', en: 'Continue') : context.tr(fr: 'Ajouter', en: 'Add');
  }

  // ------------------------------------------------------------------ build
  @override
  Widget build(BuildContext context) {
    final brandAsync = ref.watch(pairingBrandProvider(widget.brandId));
    final homes = ref.watch(homesProvider);
    final home = ref.watch(currentHomeProvider);
    final title = brandAsync.value?.name ?? context.tr(fr: 'Ajouter un appareil', en: 'Add device');

    if (home == null) {
      final loading = homes.isLoading && !homes.hasValue;
      return Scaffold(
        appBar: AppBar(title: Text(title)),
        body: loading
            ? const LoadingView()
            : EmptyState(
                icon: Icons.home_outlined,
                title: context.tr(fr: "Créez d'abord une maison", en: 'Create a home first'),
                subtitle: context.tr(fr: 'Les appareils sont rattachés à une maison.', en: 'Devices belong to a home.'),
                actionLabel: context.tr(fr: 'Gérer mes maisons', en: 'Manage my homes'),
                onAction: () => context.go(Routes.homes),
              ),
      );
    }

    return brandAsync.when(
      loading: () => Scaffold(appBar: AppBar(title: Text(title)), body: const LoadingView()),
      error: (error, _) => Scaffold(
        appBar: AppBar(title: Text(title)),
        body: ErrorView(error: error, onRetry: () => ref.invalidate(pairingBrandProvider(widget.brandId))),
      ),
      data: (brand) {
        _initialise(brand);
        return _buildWizard(context, brand, home);
      },
    );
  }

  Widget _buildWizard(BuildContext context, BrandInfo brand, Home home) {
    final rooms = ref.watch(roomsProvider(home.id));
    final hasRooms = rooms.isNotEmpty;
    final canPop = _canPop;
    return PopScope(
      canPop: canPop,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _back();
      },
      child: Scaffold(
        appBar: AppBar(
          title: Text(brand.name),
          bottom: PreferredSize(
            preferredSize: const Size.fromHeight(3),
            child: Semantics(
              label: context.tr(fr: 'Progression', en: 'Progress'),
              child: LinearProgressIndicator(value: _progress(hasRooms), minHeight: 3, color: colorFromHex(brand.color)),
            ),
          ),
        ),
        body: _buildStep(context, brand, home, rooms),
      ),
    );
  }

  Widget _buildStep(BuildContext context, BrandInfo brand, Home home, List<Room> rooms) {
    final method = _method;
    switch (_step) {
      case PairingStep.method:
        return MethodChooser(methods: brand.methods, color: colorFromHex(brand.color), onSelected: (m) => setState(() => _applyMethod(m)));
      case PairingStep.form:
        if (method == null) {
          return EmptyState(
            icon: Icons.block,
            title: context.tr(fr: "Aucune méthode d'ajout disponible", en: 'No pairing method available'),
            subtitle: context.tr(fr: 'Cette marque ne peut pas encore être ajoutée depuis l\'application.', en: 'This brand cannot be added from the app yet.'),
            actionLabel: context.tr(fr: 'Retour au catalogue', en: 'Back to catalogue'),
            onAction: () => context.pop(),
          );
        }
        return PairingForm(
          key: ValueKey('pairing-form-${method.id}-$_formGeneration'),
          fields: method.fields,
          initialValues: _values,
          submitLabel: _submitLabel(context, rooms.isNotEmpty),
          onSubmit: _onFormSubmitted,
          onScan: _scan,
          extraValidator: _validateField,
          footerBuilder: _formFooter,
          header: _MethodHeader(brand: brand, method: method),
        );
      case PairingStep.discovery:
        if (_discovering) return LoadingView(message: context.tr(fr: 'Recherche des appareils...', en: 'Searching for devices...'));
        if (_discoveryError != null) {
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [PairingErrorCard(error: _discoveryError!, onRetry: _startDiscovery, onEdit: () => setState(() => _step = PairingStep.form))],
          );
        }
        final found = _discovered ?? const <DiscoveredDevice>[];
        if (found.isEmpty) {
          return EmptyState(
            icon: Icons.search_off,
            title: context.tr(fr: 'Aucun appareil trouvé', en: 'No device found'),
            subtitle: context.tr(fr: 'Vérifiez que les appareils sont allumés et sur le même réseau, puis réessayez.', en: 'Check that the devices are powered on and on the same network, then try again.'),
            actionLabel: context.tr(fr: 'Réessayer', en: 'Retry'),
            onAction: _startDiscovery,
          );
        }
        return DiscoveryList(
          devices: found,
          selected: _selected,
          onToggle: (id, selected) => setState(() => selected ? _selected.add(id) : _selected.remove(id)),
          onSelectAll: (all) => setState(() => _selected = all ? found.map((d) => d.externalId).toSet() : {}),
          onContinue: _goToRoomOrPair,
          onBack: () => setState(() => _step = PairingStep.form),
        );
      case PairingStep.room:
        return RoomPicker(
          rooms: rooms,
          selectedId: _roomId,
          onSelected: (id) => setState(() => _roomId = id),
          onConfirm: _pair,
          confirmLabel: context.tr(fr: 'Ajouter', en: 'Add'),
        );
      case PairingStep.pairing:
        return PairingProgressView(brand: brand);
      case PairingStep.failed:
        return ListView(
          padding: const EdgeInsets.all(16),
          children: [PairingErrorCard(error: _pairError ?? 'Unknown error', onRetry: _pair, onEdit: () => setState(() => _step = PairingStep.form))],
        );
      case PairingStep.success:
        String? roomName;
        for (final r in rooms) {
          if (r.id == _roomId) roomName = r.name;
        }
        return PairingSuccessView(devices: _paired, message: _pairMessage, roomName: roomName, onDone: () => _finish(home), onAddAnother: _addAnother);
    }
  }
}

/// Method title + description at the top of the form.
class _MethodHeader extends StatelessWidget {
  const _MethodHeader({required this.brand, required this.method});

  final BrandInfo brand;
  final PairingMethod method;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final color = colorFromHex(brand.color);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 44,
          height: 44,
          decoration: BoxDecoration(color: color.withValues(alpha: 0.14), borderRadius: BorderRadius.circular(12)),
          child: Icon(iconForMethod(method), color: color),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(method.title, style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
              if (method.description.isNotEmpty) ...[
                const SizedBox(height: 2),
                Text(method.description, style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
              ],
            ],
          ),
        ),
      ],
    );
  }
}
