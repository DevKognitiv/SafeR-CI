import 'dart:async';

import 'package:flutter/material.dart';

import '../services/ha_client.dart';
import 'ha_entity_visuals.dart';

/// Bottom sheet with full controls for a single entity. Renders the right
/// control surface for each HA domain (brightness, target temperature,
/// cover position, media transport, alarm keypad, …) and falls back to a
/// read-only attribute view for domains without dedicated controls — so
/// every device any integration exposes is at least inspectable.
class EntityDetailSheet extends StatefulWidget {
  final HaClient client;
  final String entityId;

  const EntityDetailSheet({
    super.key,
    required this.client,
    required this.entityId,
  });

  static Future<void> show(
    BuildContext context,
    HaClient client,
    String entityId,
  ) {
    return showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (_) => EntityDetailSheet(client: client, entityId: entityId),
    );
  }

  @override
  State<EntityDetailSheet> createState() => _EntityDetailSheetState();
}

class _EntityDetailSheetState extends State<EntityDetailSheet> {
  StreamSubscription<Map<String, HaState>>? _sub;
  HaState? _state;
  final TextEditingController _codeCtrl = TextEditingController();

  @override
  void initState() {
    super.initState();
    _state = widget.client.currentStates[widget.entityId];
    _sub = widget.client.states.listen((states) {
      if (!mounted) return;
      setState(() => _state = states[widget.entityId]);
    });
  }

  @override
  void dispose() {
    _sub?.cancel();
    _codeCtrl.dispose();
    super.dispose();
  }

  Future<void> _run(Future<void> Function() action) async {
    try {
      await action();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Command failed: $e')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = _state;
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.only(
          left: 20,
          right: 20,
          top: 20,
          bottom: 20 + MediaQuery.of(context).viewInsets.bottom,
        ),
        child: state == null
            ? const Padding(
                padding: EdgeInsets.all(24),
                child: Text('Entity no longer available.'),
              )
            : SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    _Header(state: state),
                    const SizedBox(height: 16),
                    ..._controlsFor(state),
                  ],
                ),
              ),
      ),
    );
  }

  List<Widget> _controlsFor(HaState state) {
    final client = widget.client;
    final id = state.entityId;
    switch (state.domain) {
      case 'light':
        return [
          _ToggleRow(
            isOn: state.isOn,
            onChanged: (_) => _run(() => client.primaryAction(id)),
          ),
          if (state.isOn && state.brightness != null)
            _ServiceSlider(
              label: 'Brightness',
              value: state.brightness!.toDouble(),
              min: 0,
              max: 255,
              display: (v) => '${(v / 255 * 100).round()}%',
              onCommit: (v) =>
                  _run(() => client.setLightBrightness(id, v.round())),
            ),
        ];

      case 'switch':
      case 'input_boolean':
      case 'siren':
      case 'remote':
      case 'humidifier':
        return [
          _ToggleRow(
            isOn: state.isOn,
            onChanged: (_) => _run(() => client.primaryAction(id)),
          ),
        ];

      case 'fan':
        final pct = state.attributes['percentage'];
        return [
          _ToggleRow(
            isOn: state.isOn,
            onChanged: (_) => _run(() => client.primaryAction(id)),
          ),
          if (pct is num)
            _ServiceSlider(
              label: 'Speed',
              value: pct.toDouble(),
              min: 0,
              max: 100,
              display: (v) => '${v.round()}%',
              onCommit: (v) =>
                  _run(() => client.setFanPercentage(id, v.round())),
            ),
        ];

      case 'cover':
      case 'valve':
        return [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
            children: [
              _ActionIcon(
                icon: Icons.keyboard_arrow_up,
                label: 'Open',
                onTap: () => _run(() => client.coverCommand(
                    id, state.domain == 'valve' ? 'open_valve' : 'open_cover')),
              ),
              _ActionIcon(
                icon: Icons.stop,
                label: 'Stop',
                onTap: () => _run(() => client.coverCommand(
                    id, state.domain == 'valve' ? 'stop_valve' : 'stop_cover')),
              ),
              _ActionIcon(
                icon: Icons.keyboard_arrow_down,
                label: 'Close',
                onTap: () => _run(() => client.coverCommand(id,
                    state.domain == 'valve' ? 'close_valve' : 'close_cover')),
              ),
            ],
          ),
          if (state.domain == 'cover' && state.coverPosition != null)
            _ServiceSlider(
              label: 'Position',
              value: state.coverPosition!.toDouble(),
              min: 0,
              max: 100,
              display: (v) => '${v.round()}%',
              onCommit: (v) =>
                  _run(() => client.setCoverPosition(id, v.round())),
            ),
        ];

      case 'climate':
        final modes = (state.attributes['hvac_modes'] as List?)
                ?.map((m) => m.toString())
                .toList() ??
            const <String>[];
        final current = state.attributes['current_temperature'];
        return [
          if (current is num)
            Center(
              child: Text(
                'Current: ${current.toStringAsFixed(1)}°',
                style: const TextStyle(color: Colors.black54),
              ),
            ),
          if (state.targetTemperature != null)
            _TemperatureStepper(
              value: state.targetTemperature!,
              min: (state.attributes['min_temp'] as num?)?.toDouble() ?? 7,
              max: (state.attributes['max_temp'] as num?)?.toDouble() ?? 35,
              step: (state.attributes['target_temp_step'] as num?)
                      ?.toDouble() ??
                  0.5,
              onChanged: (v) =>
                  _run(() => client.setClimateTemperature(id, v)),
            ),
          if (modes.isNotEmpty)
            Wrap(
              spacing: 8,
              children: [
                for (final mode in modes)
                  ChoiceChip(
                    label: Text(mode),
                    selected: state.state == mode,
                    onSelected: (_) =>
                        _run(() => client.setClimateHvacMode(id, mode)),
                  ),
              ],
            ),
        ];

      case 'media_player':
        final title = state.attributes['media_title']?.toString();
        return [
          if (title != null && title.isNotEmpty)
            Center(
              child: Text(title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontWeight: FontWeight.w600)),
            ),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
            children: [
              _ActionIcon(
                icon: Icons.skip_previous,
                label: 'Prev',
                onTap: () =>
                    _run(() => client.mediaCommand(id, 'media_previous_track')),
              ),
              _ActionIcon(
                icon: state.state == 'playing'
                    ? Icons.pause_circle
                    : Icons.play_circle,
                label: state.state == 'playing' ? 'Pause' : 'Play',
                onTap: () =>
                    _run(() => client.mediaCommand(id, 'media_play_pause')),
              ),
              _ActionIcon(
                icon: Icons.skip_next,
                label: 'Next',
                onTap: () =>
                    _run(() => client.mediaCommand(id, 'media_next_track')),
              ),
            ],
          ),
          if (state.volumeLevel != null)
            _ServiceSlider(
              label: 'Volume',
              value: state.volumeLevel!,
              min: 0,
              max: 1,
              display: (v) => '${(v * 100).round()}%',
              onCommit: (v) => _run(() => client.setMediaVolume(id, v)),
            ),
        ];

      case 'vacuum':
        return [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
            children: [
              _ActionIcon(
                icon: Icons.play_arrow,
                label: 'Start',
                onTap: () => _run(() => client.vacuumCommand(id, 'start')),
              ),
              _ActionIcon(
                icon: Icons.pause,
                label: 'Pause',
                onTap: () => _run(() => client.vacuumCommand(id, 'pause')),
              ),
              _ActionIcon(
                icon: Icons.home,
                label: 'Dock',
                onTap: () =>
                    _run(() => client.vacuumCommand(id, 'return_to_base')),
              ),
            ],
          ),
        ];

      case 'lock':
        final needsCode = state.attributes['code_format'] != null;
        return [
          if (needsCode) _codeField(),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
            children: [
              _ActionIcon(
                icon: Icons.lock_open,
                label: 'Unlock',
                onTap: () => _run(() => client.lockCommand(id, 'unlock',
                    code: needsCode ? _codeOrNull() : null)),
              ),
              _ActionIcon(
                icon: Icons.lock,
                label: 'Lock',
                onTap: () => _run(() => client.lockCommand(id, 'lock',
                    code: needsCode ? _codeOrNull() : null)),
              ),
            ],
          ),
        ];

      case 'alarm_control_panel':
        return [
          _codeField(),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            alignment: WrapAlignment.center,
            children: [
              FilledButton.tonal(
                onPressed: () => _run(() =>
                    client.alarmCommand(id, 'disarm', code: _codeOrNull())),
                child: const Text('Disarm'),
              ),
              FilledButton.tonal(
                onPressed: () => _run(() =>
                    client.alarmCommand(id, 'arm_home', code: _codeOrNull())),
                child: const Text('Arm home'),
              ),
              FilledButton.tonal(
                onPressed: () => _run(() =>
                    client.alarmCommand(id, 'arm_away', code: _codeOrNull())),
                child: const Text('Arm away'),
              ),
              FilledButton.tonal(
                onPressed: () => _run(() =>
                    client.alarmCommand(id, 'arm_night', code: _codeOrNull())),
                child: const Text('Arm night'),
              ),
            ],
          ),
        ];

      case 'scene':
        return [
          FilledButton(
            onPressed: () => _run(() => client.primaryAction(id)),
            child: const Text('Activate scene'),
          ),
        ];

      case 'script':
        return [
          FilledButton(
            onPressed: () =>
                _run(() => client.callService('script', 'turn_on',
                    entityId: id)),
            child: const Text('Run script'),
          ),
        ];

      case 'automation':
        return [
          _ToggleRow(
            isOn: state.isOn,
            label: 'Enabled',
            onChanged: (_) => _run(() => client.primaryAction(id)),
          ),
          OutlinedButton(
            onPressed: () => _run(() =>
                client.callService('automation', 'trigger', entityId: id)),
            child: const Text('Run now'),
          ),
        ];

      case 'button':
      case 'input_button':
        return [
          FilledButton(
            onPressed: () => _run(() => client.primaryAction(id)),
            child: const Text('Press'),
          ),
        ];

      case 'select':
      case 'input_select':
        final options = (state.attributes['options'] as List?)
                ?.map((o) => o.toString())
                .toList() ??
            const <String>[];
        return [
          if (options.isEmpty)
            const Text('No options available.',
                style: TextStyle(color: Colors.black54))
          else
            DropdownButtonFormField<String>(
              value: options.contains(state.state) ? state.state : null,
              items: [
                for (final o in options)
                  DropdownMenuItem(value: o, child: Text(o)),
              ],
              onChanged: (v) {
                if (v != null) _run(() => client.selectOption(id, v));
              },
              decoration: const InputDecoration(border: OutlineInputBorder()),
            ),
        ];

      case 'number':
      case 'input_number':
        final minV = (state.attributes['min'] as num?)?.toDouble() ?? 0;
        final maxV = (state.attributes['max'] as num?)?.toDouble() ?? 100;
        final current = double.tryParse(state.state) ?? minV;
        return [
          _ServiceSlider(
            label: state.unit ?? 'Value',
            value: current.clamp(minV, maxV).toDouble(),
            min: minV,
            max: maxV,
            display: (v) => v.toStringAsFixed(1),
            onCommit: (v) => _run(() => client.setNumberValue(id, v)),
          ),
        ];

      case 'camera':
        return [
          const Text(
            'Live streaming is not supported in-app yet. '
            'State and attributes are shown below.',
            style: TextStyle(color: Colors.black54),
          ),
          const SizedBox(height: 8),
          _AttributesView(state: state),
        ];

      default:
        // Universal fallback: any domain from any integration is inspectable.
        return [_AttributesView(state: state)];
    }
  }

  Widget _codeField() {
    return TextField(
      controller: _codeCtrl,
      obscureText: true,
      keyboardType: TextInputType.number,
      decoration: const InputDecoration(
        labelText: 'Code (if required)',
        border: OutlineInputBorder(),
      ),
    );
  }

  String? _codeOrNull() {
    final code = _codeCtrl.text.trim();
    return code.isEmpty ? null : code;
  }
}

class _Header extends StatelessWidget {
  final HaState state;
  const _Header({required this.state});

  @override
  Widget build(BuildContext context) {
    final accent = haDomainColor(state.domain);
    return Row(
      children: [
        Container(
          width: 44,
          height: 44,
          decoration: BoxDecoration(
            color: state.isOn ? accent.withOpacity(0.18) : Colors.black12,
            shape: BoxShape.circle,
          ),
          child: Icon(haDomainIcon(state.domain),
              color: state.isOn ? accent : Colors.black45),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(state.friendlyName,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                      fontSize: 17, fontWeight: FontWeight.w600)),
              Text('${haStateLabel(state)} · ${state.entityId}',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style:
                      const TextStyle(color: Colors.black54, fontSize: 12)),
            ],
          ),
        ),
      ],
    );
  }
}

class _ToggleRow extends StatelessWidget {
  final bool isOn;
  final String label;
  final ValueChanged<bool> onChanged;
  const _ToggleRow({
    required this.isOn,
    required this.onChanged,
    this.label = 'Power',
  });

  @override
  Widget build(BuildContext context) {
    return SwitchListTile(
      title: Text(label),
      value: isOn,
      onChanged: onChanged,
      contentPadding: EdgeInsets.zero,
    );
  }
}

/// Slider that only issues the service call on release, so dragging does
/// not flood HA with intermediate values.
class _ServiceSlider extends StatefulWidget {
  final String label;
  final double value;
  final double min;
  final double max;
  final String Function(double) display;
  final ValueChanged<double> onCommit;

  const _ServiceSlider({
    required this.label,
    required this.value,
    required this.min,
    required this.max,
    required this.display,
    required this.onCommit,
  });

  @override
  State<_ServiceSlider> createState() => _ServiceSliderState();
}

class _ServiceSliderState extends State<_ServiceSlider> {
  double? _drag;

  @override
  Widget build(BuildContext context) {
    final shown = _drag ?? widget.value.clamp(widget.min, widget.max);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Text('${widget.label}: ${widget.display(shown.toDouble())}',
              style: const TextStyle(color: Colors.black54, fontSize: 13)),
        ),
        Slider(
          value: shown.toDouble(),
          min: widget.min,
          max: widget.max,
          onChanged: (v) => setState(() => _drag = v),
          onChangeEnd: (v) {
            setState(() => _drag = null);
            widget.onCommit(v);
          },
        ),
      ],
    );
  }
}

class _TemperatureStepper extends StatelessWidget {
  final double value;
  final double min;
  final double max;
  final double step;
  final ValueChanged<double> onChanged;

  const _TemperatureStepper({
    required this.value,
    required this.min,
    required this.max,
    required this.step,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        IconButton.filledTonal(
          onPressed:
              value - step >= min ? () => onChanged(value - step) : null,
          icon: const Icon(Icons.remove),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20),
          child: Text('${value.toStringAsFixed(1)}°',
              style:
                  const TextStyle(fontSize: 28, fontWeight: FontWeight.w600)),
        ),
        IconButton.filledTonal(
          onPressed:
              value + step <= max ? () => onChanged(value + step) : null,
          icon: const Icon(Icons.add),
        ),
      ],
    );
  }
}

class _ActionIcon extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onTap;
  const _ActionIcon({
    required this.icon,
    required this.label,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        IconButton.filledTonal(onPressed: onTap, icon: Icon(icon, size: 28)),
        const SizedBox(height: 4),
        Text(label,
            style: const TextStyle(fontSize: 12, color: Colors.black54)),
      ],
    );
  }
}

class _AttributesView extends StatelessWidget {
  final HaState state;
  const _AttributesView({required this.state});

  @override
  Widget build(BuildContext context) {
    final entries = state.attributes.entries
        .where((e) => e.key != 'friendly_name')
        .take(14)
        .toList();
    if (entries.isEmpty) {
      return const Text('No attributes.',
          style: TextStyle(color: Colors.black54));
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (final e in entries)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 3),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                SizedBox(
                  width: 140,
                  child: Text(e.key,
                      style: const TextStyle(
                          color: Colors.black54, fontSize: 12)),
                ),
                Expanded(
                  child: Text('${e.value}',
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontSize: 12)),
                ),
              ],
            ),
          ),
      ],
    );
  }
}
