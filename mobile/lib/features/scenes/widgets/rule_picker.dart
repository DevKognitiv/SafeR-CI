import 'package:flutter/material.dart';

import '../../../core/i18n.dart';
import '../../../core/models/models.dart';
import 'common_sheets.dart';
import 'device_picker.dart';
import 'labels.dart';
import 'sheet_scaffold.dart';
import 'value_editor.dart';

/// "Si" step of the automation editor. Resolves to a trigger or null.
Future<Rule?> showTriggerPicker(BuildContext context, {required String homeId}) async {
  final type = await showSafeRSheet<String>(
    context,
    builder: (ctx) => SheetScaffold(
      title: ctx.tr(fr: 'Déclencheur', en: 'Trigger'),
      subtitle: ctx.tr(fr: 'Quand lancer cette automatisation ?', en: 'When should this automation run?'),
      scrollable: false,
      child: SheetOptionList(options: [
        SheetOption(id: 'device_state', icon: Icons.sensors, title: ctx.tr(fr: "État d'un appareil", en: 'Device state'), subtitle: ctx.tr(fr: 'Mouvement, ouverture, température…', en: 'Motion, contact, temperature…')),
        SheetOption(id: 'schedule', icon: Icons.schedule, title: ctx.tr(fr: 'Programmation', en: 'Schedule'), subtitle: ctx.tr(fr: 'À une heure précise', en: 'At a given time')),
        SheetOption(id: 'security_mode', icon: Icons.shield_outlined, title: ctx.tr(fr: 'Mode de sécurité', en: 'Security mode'), subtitle: ctx.tr(fr: 'Quand la maison est armée / désarmée', en: 'When the home is armed / disarmed')),
      ]),
    ),
  );
  if (type == null || !context.mounted) return null;
  switch (type) {
    case 'device_state':
      return _pickDeviceState(context, homeId, allowChanged: true);
    case 'schedule':
      return showSafeRSheet<Rule>(context, builder: (_) => const _ScheduleSheet());
    case 'security_mode':
      final mode = await showSecurityModePicker(context, title: context.tr(fr: 'Quand le mode devient', en: 'When the mode becomes'));
      return mode == null ? null : Rule.securityMode(mode);
    default:
      return null;
  }
}

/// "Et si" step of the automation editor. Resolves to a condition or null.
Future<Rule?> showConditionPicker(BuildContext context, {required String homeId}) async {
  final type = await showSafeRSheet<String>(
    context,
    builder: (ctx) => SheetScaffold(
      title: ctx.tr(fr: 'Condition', en: 'Condition'),
      subtitle: ctx.tr(fr: 'Vérifiée au moment du déclenchement', en: 'Checked when the trigger fires'),
      scrollable: false,
      child: SheetOptionList(options: [
        SheetOption(id: 'device_state', icon: Icons.sensors, title: ctx.tr(fr: "État d'un appareil", en: 'Device state')),
        SheetOption(id: 'time_range', icon: Icons.timelapse, title: ctx.tr(fr: 'Plage horaire', en: 'Time range'), subtitle: ctx.tr(fr: 'Uniquement entre deux heures', en: 'Only between two times')),
        SheetOption(id: 'security_mode', icon: Icons.shield_outlined, title: ctx.tr(fr: 'Mode de sécurité', en: 'Security mode')),
      ]),
    ),
  );
  if (type == null || !context.mounted) return null;
  switch (type) {
    case 'device_state':
      return _pickDeviceState(context, homeId, allowChanged: false);
    case 'time_range':
      return showSafeRSheet<Rule>(context, builder: (_) => const _TimeRangeSheet());
    case 'security_mode':
      final mode = await showSecurityModePicker(context, title: context.tr(fr: 'Si le mode est', en: 'If the mode is'));
      return mode == null ? null : Rule.securityMode(mode);
    default:
      return null;
  }
}

Future<Rule?> _pickDeviceState(BuildContext context, String homeId, {required bool allowChanged}) async {
  final device = await showDevicePicker(context, homeId: homeId);
  if (device == null || !context.mounted) return null;
  final cap = await showCapabilityPicker(context, device: device);
  if (cap == null || !context.mounted) return null;
  return showSafeRSheet<Rule>(context, builder: (_) => _DeviceStateSheet(device: device, capability: cap, allowChanged: allowChanged));
}

String formatTimeOfDay(TimeOfDay time) => '${time.hour.toString().padLeft(2, '0')}:${time.minute.toString().padLeft(2, '0')}';

class _DeviceStateSheet extends StatefulWidget {
  const _DeviceStateSheet({required this.device, required this.capability, required this.allowChanged});

  final Device device;
  final Capability capability;
  final bool allowChanged;

  @override
  State<_DeviceStateSheet> createState() => _DeviceStateSheetState();
}

class _DeviceStateSheetState extends State<_DeviceStateSheet> {
  String _op = 'eq';
  dynamic _value;

  List<String> get _ops {
    final numeric = widget.capability.type == 'int' || widget.capability.type == 'float';
    return ['eq', 'ne', if (numeric) ...['gt', 'lt', 'gte', 'lte'], if (widget.allowChanged) 'changed'];
  }

  @override
  void initState() {
    super.initState();
    _value = defaultValueFor(widget.capability, widget.device.state[widget.capability.code]);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return SheetScaffold(
      title: widget.device.name,
      subtitle: capabilityLabel(context, widget.capability.code, capability: widget.capability),
      action: FilledButton(
        onPressed: () => Navigator.of(context).pop(Rule.deviceState(widget.device.id, widget.capability.code, _op, _op == 'changed' ? null : _value)),
        child: Text(context.tr(fr: 'Valider', en: 'Confirm')),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(context.tr(fr: 'Condition', en: 'Condition'), style: theme.textTheme.labelLarge),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final op in _ops) ChoiceChip(label: Text(opLabel(context, op)), selected: _op == op, onSelected: (_) => setState(() => _op = op)),
              ],
            ),
            if (_op != 'changed') ...[
              const SizedBox(height: 16),
              Text(context.tr(fr: 'Valeur', en: 'Value'), style: theme.textTheme.labelLarge),
              const SizedBox(height: 4),
              ValueEditor(capability: widget.capability, value: _value, command: false, onChanged: (v) => setState(() => _value = v)),
            ],
          ],
        ),
      ),
    );
  }
}

class _ScheduleSheet extends StatefulWidget {
  const _ScheduleSheet();

  @override
  State<_ScheduleSheet> createState() => _ScheduleSheetState();
}

class _ScheduleSheetState extends State<_ScheduleSheet> {
  TimeOfDay _time = const TimeOfDay(hour: 7, minute: 0);
  Set<int> _days = {0, 1, 2, 3, 4, 5, 6};

  Future<void> _pickTime() async {
    final picked = await showTimePicker(context: context, initialTime: _time);
    if (picked != null && mounted) setState(() => _time = picked);
  }

  @override
  Widget build(BuildContext context) => SheetScaffold(
        title: context.tr(fr: 'Programmation', en: 'Schedule'),
        subtitle: context.tr(fr: 'Heure et jours de déclenchement', en: 'Time and days to fire'),
        action: FilledButton(
          onPressed: _days.isEmpty ? null : () => Navigator.of(context).pop(Rule.schedule(formatTimeOfDay(_time), _days.toList()..sort())),
          child: Text(context.tr(fr: 'Valider', en: 'Confirm')),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            ListTile(
              leading: const Icon(Icons.schedule),
              title: Text(context.tr(fr: 'Heure', en: 'Time')),
              subtitle: Text(formatTimeOfDay(_time), style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w700)),
              trailing: const Icon(Icons.edit_outlined),
              onTap: _pickTime,
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 4, 20, 8),
              child: Wrap(
                spacing: 6,
                runSpacing: 6,
                children: [
                  for (var day = 0; day < 7; day++)
                    FilterChip(
                      label: Text(dayLabel(context, day)),
                      selected: _days.contains(day),
                      onSelected: (selected) => setState(() => _days = selected ? {..._days, day} : ({..._days}..remove(day))),
                    ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12),
              child: Wrap(
                children: [
                  TextButton(onPressed: () => setState(() => _days = {0, 1, 2, 3, 4, 5, 6}), child: Text(context.tr(fr: 'Tous les jours', en: 'Every day'))),
                  TextButton(onPressed: () => setState(() => _days = {0, 1, 2, 3, 4}), child: Text(context.tr(fr: 'En semaine', en: 'Weekdays'))),
                  TextButton(onPressed: () => setState(() => _days = {5, 6}), child: Text(context.tr(fr: 'Week-end', en: 'Weekend'))),
                ],
              ),
            ),
          ],
        ),
      );
}

class _TimeRangeSheet extends StatefulWidget {
  const _TimeRangeSheet();

  @override
  State<_TimeRangeSheet> createState() => _TimeRangeSheetState();
}

class _TimeRangeSheetState extends State<_TimeRangeSheet> {
  TimeOfDay _start = const TimeOfDay(hour: 19, minute: 0);
  TimeOfDay _end = const TimeOfDay(hour: 6, minute: 0);

  Future<void> _pick(bool start) async {
    final picked = await showTimePicker(context: context, initialTime: start ? _start : _end);
    if (picked == null || !mounted) return;
    setState(() {
      if (start) {
        _start = picked;
      } else {
        _end = picked;
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final style = Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700);
    return SheetScaffold(
      title: context.tr(fr: 'Plage horaire', en: 'Time range'),
      subtitle: context.tr(fr: 'Une plage qui passe minuit est acceptée (19:00 → 06:00)', en: 'Ranges crossing midnight are fine (19:00 → 06:00)'),
      action: FilledButton(
        onPressed: () => Navigator.of(context).pop(Rule.timeRange(formatTimeOfDay(_start), formatTimeOfDay(_end))),
        child: Text(context.tr(fr: 'Valider', en: 'Confirm')),
      ),
      child: Column(
        children: [
          ListTile(
            leading: const Icon(Icons.play_arrow_outlined),
            title: Text(context.tr(fr: 'Début', en: 'Start')),
            subtitle: Text(formatTimeOfDay(_start), style: style),
            trailing: const Icon(Icons.edit_outlined),
            onTap: () => _pick(true),
          ),
          ListTile(
            leading: const Icon(Icons.stop_outlined),
            title: Text(context.tr(fr: 'Fin', en: 'End')),
            subtitle: Text(formatTimeOfDay(_end), style: style),
            trailing: const Icon(Icons.edit_outlined),
            onTap: () => _pick(false),
          ),
        ],
      ),
    );
  }
}
