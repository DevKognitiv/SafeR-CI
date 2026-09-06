import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/i18n.dart';
import '../../../core/models/models.dart';
import '../../../core/providers/providers.dart';
import '../../../core/widgets/widgets.dart';
import 'common_sheets.dart';
import 'device_picker.dart';
import 'labels.dart';
import 'scene_style.dart';
import 'sheet_scaffold.dart';
import 'value_editor.dart';

/// "Ajouter une action" flow shared by the scene and automation editors.
/// Resolves to the configured action or null when the user backs out.
Future<SceneAction?> showActionPicker(BuildContext context, {required String homeId, String? excludeSceneId}) async {
  final type = await showSafeRSheet<String>(
    context,
    builder: (ctx) => SheetScaffold(
      title: ctx.tr(fr: 'Action', en: 'Action'),
      subtitle: ctx.tr(fr: 'Que doit-il se passer ?', en: 'What should happen?'),
      scrollable: false,
      child: SheetOptionList(options: [
        SheetOption(id: 'device_command', icon: Icons.devices, title: ctx.tr(fr: 'Contrôler un appareil', en: 'Control a device'), subtitle: ctx.tr(fr: 'Allumer, régler, ouvrir…', en: 'Turn on, adjust, open…')),
        SheetOption(id: 'delay', icon: Icons.timer_outlined, title: ctx.tr(fr: 'Délai', en: 'Delay'), subtitle: ctx.tr(fr: "Attendre avant l'action suivante", en: 'Wait before the next action')),
        SheetOption(id: 'security_mode', icon: Icons.shield_outlined, title: ctx.tr(fr: 'Mode de sécurité', en: 'Security mode'), subtitle: ctx.tr(fr: 'Armer ou désarmer la maison', en: 'Arm or disarm the home')),
        SheetOption(id: 'notify', icon: Icons.notifications_outlined, title: ctx.tr(fr: 'Envoyer une notification', en: 'Send a notification')),
        SheetOption(id: 'run_scene', icon: Icons.play_circle_outline, title: ctx.tr(fr: 'Exécuter une scène', en: 'Run a scene')),
      ]),
    ),
  );
  if (type == null || !context.mounted) return null;
  switch (type) {
    case 'device_command':
      return _pickDeviceCommand(context, homeId);
    case 'delay':
      final seconds = await showSafeRSheet<num>(context, builder: (_) => const _DelaySheet());
      return seconds == null ? null : SceneAction.delay(seconds);
    case 'security_mode':
      final mode = await showSecurityModePicker(context, title: context.tr(fr: 'Mode de sécurité', en: 'Security mode'));
      return mode == null ? null : SceneAction.securityMode(mode);
    case 'notify':
      final result = await showSafeRSheet<({String title, String body})>(context, builder: (_) => const _NotifySheet());
      return result == null ? null : SceneAction.notify(result.title, result.body);
    case 'run_scene':
      final scene = await showSafeRSheet<Scene>(context, builder: (_) => _ScenePickerSheet(homeId: homeId, excludeSceneId: excludeSceneId));
      return scene == null ? null : SceneAction.runScene(scene.id);
    default:
      return null;
  }
}

Future<SceneAction?> _pickDeviceCommand(BuildContext context, String homeId) async {
  final device = await showDevicePicker(context, homeId: homeId, writableOnly: true);
  if (device == null || !context.mounted) return null;
  final cap = await showCapabilityPicker(context, device: device, writableOnly: true);
  if (cap == null || !context.mounted) return null;
  final value = await showValueSheet(
    context,
    capability: cap,
    title: '${device.name} · ${capabilityLabel(context, cap.code, capability: cap)}',
    initial: defaultValueFor(cap, device.state[cap.code]),
  );
  if (value == null) return null;
  return SceneAction.deviceCommand(device.id, cap.code, value);
}

class _DelaySheet extends StatefulWidget {
  const _DelaySheet();

  @override
  State<_DelaySheet> createState() => _DelaySheetState();
}

class _DelaySheetState extends State<_DelaySheet> {
  static const _presets = [5, 30, 60, 300];
  int _seconds = 30;
  late final TextEditingController _controller = TextEditingController(text: '$_seconds');

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _select(int seconds) => setState(() {
        _seconds = seconds;
        _controller.text = '$seconds';
      });

  @override
  Widget build(BuildContext context) => SheetScaffold(
        title: context.tr(fr: 'Délai', en: 'Delay'),
        subtitle: context.tr(fr: "Temps d'attente avant l'action suivante", en: 'Time to wait before the next action'),
        action: FilledButton(
          onPressed: _seconds > 0 ? () => Navigator.of(context).pop(_seconds) : null,
          child: Text(context.tr(fr: 'Valider', en: 'Confirm')),
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Wrap(
                spacing: 8,
                children: [
                  for (final preset in _presets)
                    ChoiceChip(label: Text(formatSeconds(context, preset)), selected: _seconds == preset, onSelected: (_) => _select(preset)),
                ],
              ),
              const SizedBox(height: 16),
              TextField(
                controller: _controller,
                keyboardType: TextInputType.number,
                decoration: InputDecoration(labelText: context.tr(fr: 'Secondes', en: 'Seconds'), suffixText: 's'),
                onChanged: (v) => setState(() => _seconds = int.tryParse(v) ?? 0),
              ),
            ],
          ),
        ),
      );
}

class _NotifySheet extends StatefulWidget {
  const _NotifySheet();

  @override
  State<_NotifySheet> createState() => _NotifySheetState();
}

class _NotifySheetState extends State<_NotifySheet> {
  final _title = TextEditingController();
  final _body = TextEditingController();

  @override
  void dispose() {
    _title.dispose();
    _body.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => SheetScaffold(
        title: context.tr(fr: 'Notification', en: 'Notification'),
        subtitle: context.tr(fr: 'Message envoyé aux membres de la maison', en: 'Message sent to the home members'),
        action: ListenableBuilder(
          listenable: _title,
          builder: (context, _) => FilledButton(
            onPressed: _title.text.trim().isEmpty ? null : () => Navigator.of(context).pop((title: _title.text.trim(), body: _body.text.trim())),
            child: Text(context.tr(fr: 'Valider', en: 'Confirm')),
          ),
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
          child: Column(
            children: [
              TextField(
                controller: _title,
                textCapitalization: TextCapitalization.sentences,
                decoration: InputDecoration(labelText: context.tr(fr: 'Titre', en: 'Title')),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _body,
                textCapitalization: TextCapitalization.sentences,
                maxLines: 3,
                decoration: InputDecoration(labelText: context.tr(fr: 'Message', en: 'Message')),
              ),
            ],
          ),
        ),
      );
}

class _ScenePickerSheet extends ConsumerWidget {
  const _ScenePickerSheet({required this.homeId, this.excludeSceneId});

  final String homeId;
  final String? excludeSceneId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final scenesAsync = ref.watch(scenesProvider(homeId));
    return SheetScaffold(
      title: context.tr(fr: 'Exécuter une scène', en: 'Run a scene'),
      scrollable: false,
      child: scenesAsync.when(
        loading: () => const SizedBox(height: 180, child: LoadingView()),
        error: (error, _) => SizedBox(height: 260, child: ErrorView(error: error, onRetry: () => ref.read(scenesProvider(homeId).notifier).refresh())),
        data: (all) {
          final scenes = all.where((s) => s.id != excludeSceneId).toList();
          if (scenes.isEmpty) {
            return SizedBox(height: 220, child: EmptyState(icon: Icons.auto_awesome_outlined, title: context.tr(fr: 'Aucune autre scène', en: 'No other scene')));
          }
          return ListView(
            shrinkWrap: true,
            padding: const EdgeInsets.only(bottom: 16),
            children: [
              for (final scene in scenes)
                ListTile(
                  minTileHeight: 56,
                  leading: CircleAvatar(backgroundColor: colorFromHex(scene.color), child: Icon(iconFromName(scene.icon, fallback: Icons.play_circle), color: Colors.white)),
                  title: Text(scene.name),
                  subtitle: Text('${scene.actions.length} ${context.tr(fr: scene.actions.length > 1 ? 'actions' : 'action', en: scene.actions.length > 1 ? 'actions' : 'action')}'),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: () => Navigator.of(context).pop(scene),
                ),
            ],
          );
        },
      ),
    );
  }
}
