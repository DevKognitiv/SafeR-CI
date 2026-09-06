import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/i18n.dart';
import '../../../core/models/home.dart';
import '../../../core/theme.dart';
import 'home_location.dart';

/// Values entered in the create/edit home sheet.
typedef HomeFormResult = ({String name, String? address, double? lat, double? lon, List<String> rooms});

/// Default rooms proposed when creating a home (Tuya-like).
const List<String> kDefaultRooms = ['Salon', 'Chambre', 'Cuisine', 'Entrée'];

/// Opens the create (initial == null) or edit home sheet. Resolves with the values or null.
Future<HomeFormResult?> showHomeFormSheet(BuildContext context, {Home? initial}) => showModalBottomSheet<HomeFormResult>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      showDragHandle: true,
      builder: (_) => HomeFormSheet(initial: initial),
    );

class HomeFormSheet extends ConsumerStatefulWidget {
  const HomeFormSheet({super.key, this.initial});

  final Home? initial;

  @override
  ConsumerState<HomeFormSheet> createState() => _HomeFormSheetState();
}

class _HomeFormSheetState extends ConsumerState<HomeFormSheet> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _name = TextEditingController(text: widget.initial?.name ?? '');
  late final TextEditingController _address = TextEditingController(text: widget.initial?.address ?? '');
  late double? _lat = widget.initial?.lat;
  late double? _lon = widget.initial?.lon;
  late final Set<String> _rooms = {...kDefaultRooms};
  bool _locating = false;
  bool _locationFailed = false;

  bool get _creating => widget.initial == null;

  @override
  void dispose() {
    _name.dispose();
    _address.dispose();
    super.dispose();
  }

  Future<void> _locate() async {
    if (_locating) return;
    setState(() {
      _locating = true;
      _locationFailed = false;
    });
    HomeGeoPoint? point;
    try {
      point = await ref.read(homeLocationServiceProvider).currentPosition();
    } catch (_) {
      point = null;
    }
    if (!mounted) return;
    setState(() {
      _locating = false;
      _locationFailed = point == null;
      if (point != null) {
        _lat = point.lat;
        _lon = point.lon;
      }
    });
  }

  void _submit() {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    final address = _address.text.trim();
    Navigator.of(context).pop((
      name: _name.text.trim(),
      address: address.isEmpty ? null : address,
      lat: _lat,
      lon: _lon,
      rooms: _creating ? _rooms.toList() : const <String>[],
    ));
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final muted = theme.colorScheme.onSurfaceVariant;
    final lat = _lat;
    final lon = _lon;
    return Padding(
      padding: EdgeInsets.fromLTRB(20, 0, 20, 20 + MediaQuery.viewInsetsOf(context).bottom),
      child: SingleChildScrollView(
        child: Form(
          key: _formKey,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                _creating ? context.tr(fr: 'Créer une maison', en: 'Create a home') : context.tr(fr: 'Modifier la maison', en: 'Edit home'),
                style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 16),
              TextFormField(
                key: const Key('home-name'),
                controller: _name,
                autofocus: _creating,
                textCapitalization: TextCapitalization.sentences,
                textInputAction: TextInputAction.next,
                decoration: InputDecoration(
                  labelText: context.tr(fr: 'Nom de la maison', en: 'Home name'),
                  hintText: context.tr(fr: 'ex. Maison Cocody', en: 'e.g. Cocody house'),
                  prefixIcon: const Icon(Icons.home_outlined),
                ),
                validator: (v) => (v ?? '').trim().isEmpty ? context.tr(fr: 'Saisissez un nom', en: 'Enter a name') : null,
              ),
              const SizedBox(height: 12),
              TextFormField(
                key: const Key('home-address'),
                controller: _address,
                textCapitalization: TextCapitalization.sentences,
                textInputAction: TextInputAction.done,
                onFieldSubmitted: (_) => _submit(),
                decoration: InputDecoration(
                  labelText: context.tr(fr: 'Adresse (facultatif)', en: 'Address (optional)'),
                  hintText: context.tr(fr: 'Quartier, ville', en: 'Area, city'),
                  prefixIcon: const Icon(Icons.place_outlined),
                ),
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  OutlinedButton.icon(
                    style: OutlinedButton.styleFrom(minimumSize: const Size(0, 44), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12))),
                    onPressed: _locating ? null : _locate,
                    icon: _locating
                        ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                        : const Icon(Icons.my_location, size: 18),
                    label: Text(context.tr(fr: 'Utiliser ma position', en: 'Use my location')),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      _locationFailed
                          ? context.tr(fr: 'Position indisponible', en: 'Location unavailable')
                          : (lat != null && lon != null)
                              ? '${lat.toStringAsFixed(4)}, ${lon.toStringAsFixed(4)}'
                              : context.tr(fr: 'Position utilisée pour la météo', en: 'Used for the weather'),
                      style: theme.textTheme.bodySmall?.copyWith(color: _locationFailed ? SafeRColors.danger : muted),
                    ),
                  ),
                ],
              ),
              if (_creating) ...[
                const SizedBox(height: 20),
                Text(context.tr(fr: 'Pièces par défaut', en: 'Default rooms'), style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700)),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 8,
                  runSpacing: 4,
                  children: [
                    for (final room in kDefaultRooms)
                      FilterChip(
                        label: Text(room),
                        selected: _rooms.contains(room),
                        onSelected: (selected) => setState(() => selected ? _rooms.add(room) : _rooms.remove(room)),
                      ),
                  ],
                ),
              ],
              const SizedBox(height: 24),
              FilledButton(
                onPressed: _submit,
                child: Text(_creating ? context.tr(fr: 'Créer', en: 'Create') : context.tr(fr: 'Enregistrer', en: 'Save')),
              ),
              const SizedBox(height: 4),
              TextButton(
                onPressed: () => Navigator.of(context).pop(),
                child: Text(context.tr(fr: 'Annuler', en: 'Cancel')),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
