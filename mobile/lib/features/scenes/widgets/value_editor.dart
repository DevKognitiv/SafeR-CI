import 'package:flutter/material.dart';

import '../../../core/i18n.dart';
import '../../../core/models/device.dart';
import 'labels.dart';
import 'sheet_scaffold.dart';

/// Sensible initial value for a capability (used before the user edits it).
dynamic defaultValueFor(Capability capability, dynamic current) {
  switch (capability.type) {
    case 'bool':
      return current is bool ? current : true;
    case 'int':
      final min = capability.min ?? 0;
      final max = capability.max ?? 100;
      final n = current is num ? current : min;
      return n.clamp(min, max).round();
    case 'float':
      final min = capability.min ?? 0;
      final max = capability.max ?? 100;
      final n = current is num ? current : min;
      return n.clamp(min, max).toDouble();
    case 'enum':
      if (current is String && capability.values.contains(current)) return current;
      return capability.values.isEmpty ? '' : capability.values.first;
    case 'color':
      if (current is Map) return Map<String, dynamic>.from(current);
      return <String, dynamic>{'h': 0, 's': 100, 'v': 100};
    default:
      return current?.toString() ?? '';
  }
}

/// Editor for one capability value: switch, slider, chips, hue or text.
class ValueEditor extends StatelessWidget {
  const ValueEditor({super.key, required this.capability, required this.value, required this.onChanged, this.command = true});

  final Capability capability;
  final dynamic value;
  final ValueChanged<dynamic> onChanged;

  /// True for actions (verbs: "allumer"), false for triggers (states: "oui").
  final bool command;

  @override
  Widget build(BuildContext context) {
    switch (capability.type) {
      case 'bool':
        return SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: Text(valueLabel(context, code: capability.code, value: value, capability: capability, command: command)),
          value: isTruthy(value),
          onChanged: onChanged,
        );
      case 'int':
      case 'float':
        return _NumberEditor(capability: capability, value: value, onChanged: onChanged);
      case 'enum':
        return Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final v in capability.values)
              ChoiceChip(label: Text(enumLabel(context, capability.code, v)), selected: value == v, onSelected: (_) => onChanged(v)),
          ],
        );
      case 'color':
        return _HueEditor(value: value, onChanged: onChanged);
      default:
        return TextFormField(
          initialValue: value?.toString() ?? '',
          decoration: InputDecoration(labelText: context.tr(fr: 'Valeur', en: 'Value')),
          onChanged: onChanged,
        );
    }
  }
}

class _NumberEditor extends StatelessWidget {
  const _NumberEditor({required this.capability, required this.value, required this.onChanged});

  final Capability capability;
  final dynamic value;
  final ValueChanged<dynamic> onChanged;

  @override
  Widget build(BuildContext context) {
    final isInt = capability.type == 'int';
    final min = (capability.min ?? 0).toDouble();
    final max = (capability.max ?? 100).toDouble();
    final step = capability.step?.toDouble() ?? (isInt ? 1.0 : null);
    final current = (value is num ? (value as num).toDouble() : min).clamp(min, max);
    final divisions = step != null && step > 0 && max > min ? ((max - min) / step).round() : null;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          valueLabel(context, code: capability.code, value: isInt ? current.round() : current, capability: capability),
          style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w700),
        ),
        Slider(
          value: current,
          min: min,
          max: max,
          divisions: divisions,
          label: valueLabel(context, code: capability.code, value: isInt ? current.round() : current, capability: capability),
          onChanged: (v) {
            if (isInt) {
              onChanged(v.round());
            } else if (step != null && step > 0) {
              onChanged(double.parse(((v / step).round() * step).toStringAsFixed(2)));
            } else {
              onChanged(double.parse(v.toStringAsFixed(1)));
            }
          },
        ),
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(valueLabel(context, code: capability.code, value: min, capability: capability), style: Theme.of(context).textTheme.bodySmall),
            Text(valueLabel(context, code: capability.code, value: max, capability: capability), style: Theme.of(context).textTheme.bodySmall),
          ],
        ),
      ],
    );
  }
}

class _HueEditor extends StatelessWidget {
  const _HueEditor({required this.value, required this.onChanged});

  final dynamic value;
  final ValueChanged<dynamic> onChanged;

  @override
  Widget build(BuildContext context) {
    final hue = (value is Map ? (value['h'] as num?)?.toDouble() : null)?.clamp(0.0, 360.0) ?? 0.0;
    final color = HSVColor.fromAHSV(1, hue, 1, 1).toColor();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Container(width: 36, height: 36, decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
            const SizedBox(width: 12),
            Text(context.tr(fr: 'Teinte ${hue.round()}°', en: 'Hue ${hue.round()}°'), style: Theme.of(context).textTheme.titleMedium),
          ],
        ),
        const SizedBox(height: 12),
        Stack(
          alignment: Alignment.center,
          children: [
            Container(
              height: 14,
              margin: const EdgeInsets.symmetric(horizontal: 12),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(7),
                gradient: LinearGradient(colors: [for (var h = 0; h <= 360; h += 30) HSVColor.fromAHSV(1, h.toDouble(), 1, 1).toColor()]),
              ),
            ),
            SliderTheme(
              data: SliderThemeData(
                trackHeight: 14,
                activeTrackColor: Colors.transparent,
                inactiveTrackColor: Colors.transparent,
                thumbColor: color,
                overlayColor: color.withValues(alpha: 0.2),
              ),
              child: Semantics(
                label: context.tr(fr: 'Teinte', en: 'Hue'),
                child: Slider(
                  value: hue,
                  max: 360,
                  onChanged: (h) => onChanged(<String, dynamic>{'h': h.round(), 's': 100, 'v': 100}),
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }
}

/// Bottom sheet wrapping a [ValueEditor] with a "Valider" button. Resolves to the value or null.
Future<dynamic> showValueSheet(BuildContext context, {required Capability capability, required String title, dynamic initial, bool command = true}) =>
    showSafeRSheet<dynamic>(context, builder: (_) => _ValueSheet(capability: capability, title: title, initial: initial, command: command));

class _ValueSheet extends StatefulWidget {
  const _ValueSheet({required this.capability, required this.title, this.initial, required this.command});

  final Capability capability;
  final String title;
  final dynamic initial;
  final bool command;

  @override
  State<_ValueSheet> createState() => _ValueSheetState();
}

class _ValueSheetState extends State<_ValueSheet> {
  dynamic _value;

  @override
  void initState() {
    super.initState();
    _value = widget.initial ?? defaultValueFor(widget.capability, null);
  }

  @override
  Widget build(BuildContext context) => SheetScaffold(
        title: widget.title,
        subtitle: context.tr(fr: 'Choisissez la valeur', en: 'Pick the value'),
        action: FilledButton(onPressed: () => Navigator.of(context).pop(_value), child: Text(context.tr(fr: 'Valider', en: 'Confirm'))),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
          child: ValueEditor(capability: widget.capability, value: _value, command: widget.command, onChanged: (v) => setState(() => _value = v)),
        ),
      );
}
