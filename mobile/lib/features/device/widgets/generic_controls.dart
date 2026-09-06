import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/i18n.dart';
import '../../../core/models/device.dart';
import '../../../core/widgets/widgets.dart';
import 'capability_format.dart';
import 'capability_slider.dart';
import 'device_command.dart';
import 'hue_picker.dart';
import 'info_rows.dart';

/// Auto-generated controls for every capability not handled by a dedicated panel:
/// bool -> switch, int/float -> slider, enum -> chips, string -> text, color -> hue/saturation,
/// read-only -> value rows.
class GenericControls extends ConsumerWidget {
  const GenericControls({super.key, required this.device, this.exclude = const {}, this.controlsTitle, this.stateTitle, this.showEmpty = false});

  final Device device;
  final Set<String> exclude;
  final String? controlsTitle;
  final String? stateTitle;
  final bool showEmpty;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final caps = device.capabilities.where((c) => !exclude.contains(c.code) && !c.code.startsWith('stream_')).toList();
    final writable = caps.where((c) => c.writable).toList();
    final readOnly = caps.where((c) => !c.writable).toList();
    if (writable.isEmpty && readOnly.isEmpty) {
      if (!showEmpty) return const SizedBox.shrink();
      return EmptyState(
        icon: Icons.tune,
        title: context.tr(fr: 'Aucune commande disponible', en: 'No controls available'),
        subtitle: context.tr(fr: "Cet appareil n'expose aucune capacité", en: 'This device exposes no capability'),
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (writable.isNotEmpty) ...[
          SectionHeader(title: controlsTitle ?? context.tr(fr: 'Commandes', en: 'Controls'), padding: const EdgeInsets.fromLTRB(4, 16, 4, 8)),
          Card(
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 4),
              child: Column(
                children: [
                  for (var i = 0; i < writable.length; i++) ...[
                    if (i > 0) const Divider(indent: 16, endIndent: 16),
                    _WritableControl(device: device, cap: writable[i]),
                  ],
                ],
              ),
            ),
          ),
        ],
        if (readOnly.isNotEmpty) ...[
          SectionHeader(title: stateTitle ?? context.tr(fr: 'État', en: 'State'), padding: const EdgeInsets.fromLTRB(4, 16, 4, 8)),
          Card(
            child: Column(
              children: [
                for (var i = 0; i < readOnly.length; i++) ...[
                  if (i > 0) const Divider(indent: 16, endIndent: 16),
                  ValueRow(label: capabilityLabel(context, readOnly[i]), value: formatCapabilityValue(context, readOnly[i], device.state[readOnly[i].code])),
                ],
              ],
            ),
          ),
        ],
      ],
    );
  }
}

class _WritableControl extends ConsumerWidget {
  const _WritableControl({required this.device, required this.cap});

  final Device device;
  final Capability cap;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final label = capabilityLabel(context, cap);
    switch (cap.type) {
      case 'bool':
        return SwitchListTile.adaptive(
          title: Text(label),
          value: device.boolValue(cap.code) ?? false,
          onChanged: (v) => sendDeviceCommand(context, ref, device, cap.code, v),
        );
      case 'int':
      case 'float':
        final min = (cap.min ?? 0).toDouble();
        final max = (cap.max ?? (min < 100 ? 100 : min + 100)).toDouble();
        final step = (cap.step ?? (cap.type == 'int' ? 1 : 0)).toDouble();
        final divisions = step > 0 ? ((max - min) / step).round().clamp(1, 1000) : null;
        return Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
          child: CapabilitySlider(
            key: Key('slider-${cap.code}'),
            label: label,
            unit: cap.unit,
            value: (device.numValue(cap.code) ?? min).toDouble(),
            min: min,
            max: max,
            divisions: divisions,
            onCommit: (v) => sendDeviceCommand(context, ref, device, cap.code, cap.type == 'int' ? v.round() : double.parse(v.toStringAsFixed(2))),
          ),
        );
      case 'enum':
        final current = device.stringValue(cap.code);
        return Padding(
          padding: const EdgeInsets.fromLTRB(16, 10, 16, 10),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(label, style: Theme.of(context).textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w600)),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final value in cap.values)
                    ChoiceChip(
                      label: Text(enumValueLabel(context, value)),
                      selected: current == value,
                      onSelected: (_) => sendDeviceCommand(context, ref, device, cap.code, value),
                    ),
                ],
              ),
            ],
          ),
        );
      case 'color':
        final raw = device.state[cap.code];
        final hsv = raw is Map ? Map<String, dynamic>.from(raw) : const <String, dynamic>{};
        return Padding(
          padding: const EdgeInsets.fromLTRB(16, 10, 16, 4),
          child: HueSaturationPicker(
            hue: (hsv['h'] as num?)?.round() ?? 0,
            saturation: (hsv['s'] as num?)?.round() ?? 100,
            value: (hsv['v'] as num?)?.round() ?? 100,
            onChanged: (h, s) => sendDeviceCommand(context, ref, device, cap.code, {'h': h, 's': s, 'v': (hsv['v'] as num?)?.round() ?? 100}),
          ),
        );
      default:
        return _TextCommandRow(device: device, cap: cap, label: label);
    }
  }
}

class _TextCommandRow extends ConsumerStatefulWidget {
  const _TextCommandRow({required this.device, required this.cap, required this.label});

  final Device device;
  final Capability cap;
  final String label;

  @override
  ConsumerState<_TextCommandRow> createState() => _TextCommandRowState();
}

class _TextCommandRowState extends ConsumerState<_TextCommandRow> {
  late final TextEditingController _controller = TextEditingController(text: widget.device.stringValue(widget.cap.code) ?? '');

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    final value = _controller.text.trim();
    if (value.isEmpty) return;
    dynamic payload = value;
    if (widget.cap.type == 'json') {
      try {
        payload = jsonDecode(value);
      } on FormatException {
        showErrorSnack(context, context.tr(fr: 'JSON invalide', en: 'Invalid JSON'));
        return;
      }
    }
    final ok = await sendDeviceCommand(context, ref, widget.device, widget.cap.code, payload);
    if (ok && mounted) showSnack(context, context.tr(fr: 'Commande envoyée', en: 'Command sent'));
  }

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.fromLTRB(16, 8, 8, 8),
        child: Row(
          children: [
            Expanded(
              child: TextField(
                controller: _controller,
                decoration: InputDecoration(labelText: widget.label, isDense: true),
                onSubmitted: (_) => _send(),
              ),
            ),
            IconButton(
              tooltip: context.tr(fr: 'Envoyer', en: 'Send'),
              onPressed: _send,
              icon: const Icon(Icons.send),
              constraints: const BoxConstraints(minWidth: 44, minHeight: 44),
            ),
          ],
        ),
      );
}
