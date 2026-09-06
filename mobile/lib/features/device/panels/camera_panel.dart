import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/i18n.dart';
import '../../../core/models/device.dart';
import '../../../core/providers/providers.dart';
import '../../../core/theme.dart';
import '../../../core/widgets/widgets.dart';
import '../widgets/capability_format.dart';
import '../widgets/device_command.dart';
import '../widgets/device_children_list.dart';
import '../widgets/generic_controls.dart';
import '../widgets/mode_selector.dart';
import '../widgets/panel_card.dart';
import '../widgets/ptz_pad.dart';
import '../widgets/status_chips.dart';
import '../widgets/stream_player.dart';

/// Camera / doorbell / NVR: live player, quality toggle, PTZ, toggles and snapshot.
class CameraPanel extends ConsumerStatefulWidget {
  const CameraPanel({super.key, required this.device});

  final Device device;

  @override
  ConsumerState<CameraPanel> createState() => _CameraPanelState();
}

class _CameraPanelState extends ConsumerState<CameraPanel> {
  String _quality = 'main';
  bool _snapshotBusy = false;

  Device get device => widget.device;

  Future<void> _snapshot() async {
    setState(() => _snapshotBusy = true);
    try {
      final bytes = await ref.read(hubClientProvider).snapshot(device.id);
      if (!mounted) return;
      await _showSnapshot(bytes);
    } catch (e) {
      if (mounted) showErrorSnack(context, e);
    } finally {
      if (mounted) setState(() => _snapshotBusy = false);
    }
  }

  Future<void> _showSnapshot(Uint8List bytes) => showDialog<void>(
        context: context,
        builder: (context) => Dialog(
          clipBehavior: Clip.antiAlias,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              AspectRatio(
                aspectRatio: 16 / 9,
                child: ColoredBox(
                  color: Colors.black,
                  child: Image.memory(
                    bytes,
                    fit: BoxFit.contain,
                    errorBuilder: (_, __, ___) => Center(child: Text(context.tr(fr: 'Image illisible', en: 'Unreadable image'), style: const TextStyle(color: Colors.white70))),
                  ),
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
                child: Row(
                  children: [
                    Expanded(child: Text(device.name, style: const TextStyle(fontWeight: FontWeight.w700), maxLines: 1, overflow: TextOverflow.ellipsis)),
                    TextButton(onPressed: () => Navigator.of(context).pop(), child: Text(context.tr(fr: 'Fermer', en: 'Close'))),
                  ],
                ),
              ),
            ],
          ),
        ),
      );

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final hasSub = device.hasCapability('stream_sub');
    final hasStream = device.hasCapability('stream_main') || device.hasCapability('stream_sub');
    final ptz = writableCapability(device, 'ptz', type: 'enum');
    final motion = device.hasCapability('motion') ? (device.boolValue('motion') ?? false) : null;
    final recording = device.hasCapability('recording') ? (device.boolValue('recording') ?? false) : null;
    final doorbell = device.hasCapability('doorbell_pressed') ? (device.boolValue('doorbell_pressed') ?? false) : null;
    final nightVision = writableCapability(device, 'night_vision', type: 'enum');
    final toggles = [
      for (final code in const ['siren', 'light', 'privacy_mode'])
        if (writableCapability(device, code, type: 'bool') != null) device.capability(code)!,
    ];
    final enabled = device.online;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (hasStream) StreamPlayer(device: device, quality: hasSub ? _quality : 'main'),
        const SizedBox(height: 12),
        PanelCard(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          child: Row(
            children: [
              Expanded(
                child: Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    OnlineChip(online: device.online),
                    if (motion != null)
                      BoolChip(active: motion, activeLabel: context.tr(fr: 'MOUVEMENT', en: 'MOTION'), inactiveLabel: context.tr(fr: 'CALME', en: 'CLEAR'), icon: Icons.directions_run),
                    if (recording != null)
                      BoolChip(active: recording, activeLabel: 'REC', inactiveLabel: context.tr(fr: 'Pas d\'enregistrement', en: 'Not recording'), activeColor: SafeRColors.danger, icon: Icons.fiber_manual_record),
                    if (doorbell == true) StateChip(label: context.tr(fr: 'Sonnette pressée', en: 'Doorbell pressed'), icon: Icons.doorbell, color: SafeRColors.warning),
                  ],
                ),
              ),
              if (hasSub) ...[
                const SizedBox(width: 8),
                SegmentedButton<String>(
                  showSelectedIcon: false,
                  style: const ButtonStyle(visualDensity: VisualDensity.compact),
                  segments: [
                    ButtonSegment(value: 'main', label: Text(context.tr(fr: 'HD', en: 'HD'))),
                    ButtonSegment(value: 'sub', label: Text(context.tr(fr: 'SD', en: 'SD'))),
                  ],
                  selected: {_quality},
                  onSelectionChanged: (s) => setState(() => _quality = s.first),
                ),
              ],
            ],
          ),
        ),
        const SizedBox(height: 12),
        PanelCard(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          child: Row(
            children: [
              Expanded(
                child: FilledButton.tonalIcon(
                  onPressed: enabled && !_snapshotBusy ? _snapshot : null,
                  icon: _snapshotBusy ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)) : const Icon(Icons.photo_camera_outlined),
                  label: Text(context.tr(fr: 'Instantané', en: 'Snapshot')),
                ),
              ),
            ],
          ),
        ),
        if (toggles.isNotEmpty || nightVision != null) ...[
          const SizedBox(height: 12),
          PanelCard(
            title: context.tr(fr: 'Fonctions', en: 'Features'),
            padding: const EdgeInsets.fromLTRB(16, 16, 8, 8),
            child: Column(
              children: [
                for (final cap in toggles)
                  SwitchListTile.adaptive(
                    contentPadding: EdgeInsets.zero,
                    secondary: Icon(cap.code == 'siren'
                        ? Icons.campaign_outlined
                        : cap.code == 'light'
                            ? Icons.flashlight_on_outlined
                            : Icons.visibility_off_outlined),
                    title: Text(capabilityLabel(context, cap)),
                    value: device.boolValue(cap.code) ?? false,
                    onChanged: enabled ? (v) => sendDeviceCommand(context, ref, device, cap.code, v) : null,
                  ),
                if (nightVision != null)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(0, 8, 8, 4),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(capabilityLabel(context, nightVision), style: theme.textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w600)),
                        const SizedBox(height: 8),
                        ModeSelector<String>(
                          options: [for (final v in nightVision.values) ModeOption(value: v, label: enumValueLabel(context, v))],
                          selected: device.stringValue('night_vision'),
                          enabled: enabled,
                          onSelected: (v) => sendDeviceCommand(context, ref, device, 'night_vision', v),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
          ),
        ],
        if (ptz != null) ...[
          const SizedBox(height: 12),
          PanelCard(
            title: context.tr(fr: 'Orientation (PTZ)', en: 'Pan / tilt / zoom'),
            child: Center(
              child: PtzPad(
                supported: ptz.values.toSet(),
                enabled: enabled,
                onStart: (direction) => sendDeviceCommand(context, ref, device, 'ptz', direction),
                onStop: () => sendDeviceCommand(context, ref, device, 'ptz', 'stop'),
              ),
            ),
          ),
        ],
        GenericControls(
          device: device,
          exclude: const {'stream_main', 'stream_sub', 'snapshot', 'ptz', 'motion', 'recording', 'siren', 'light', 'privacy_mode', 'night_vision', 'doorbell_pressed'},
        ),
        if (device.category == 'nvr') ...[
          SectionHeader(title: context.tr(fr: 'Canaux', en: 'Channels'), padding: const EdgeInsets.fromLTRB(4, 20, 4, 8)),
          DeviceChildrenList(parent: device, emptyTitle: context.tr(fr: 'Aucun canal', en: 'No channels')),
        ],
      ],
    );
  }
}
