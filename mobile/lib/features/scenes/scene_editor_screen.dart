import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/i18n.dart';
import '../../core/models/models.dart';
import '../../core/providers/providers.dart';
import '../../core/router.dart';
import '../../core/widgets/widgets.dart';
import 'widgets/action_list.dart';
import 'widgets/action_picker.dart';
import 'widgets/common_sheets.dart';
import 'widgets/icon_color_pickers.dart';
import 'widgets/no_home_view.dart';
import 'widgets/scene_style.dart';

/// Create or edit a tap-to-run scene: name, icon, colour and ordered actions.
class SceneEditorScreen extends ConsumerStatefulWidget {
  const SceneEditorScreen({super.key, this.sceneId});

  final String? sceneId;

  @override
  ConsumerState<SceneEditorScreen> createState() => _SceneEditorScreenState();
}

class _SceneEditorScreenState extends ConsumerState<SceneEditorScreen> {
  final _name = TextEditingController();
  String _icon = kSceneIconNames.first;
  String _color = kSceneColors.first;
  List<SceneAction> _actions = [];
  bool _hydrated = false;
  bool _busy = false;

  bool get _isNew => widget.sceneId == null;

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  /// Copy the existing scene into the form once it is available.
  void _hydrate(Scene scene) {
    if (_hydrated) return;
    _hydrated = true;
    _name.text = scene.name;
    _icon = scene.icon ?? kSceneIconNames.first;
    _color = scene.color ?? kSceneColors.first;
    _actions = List.of(scene.actions);
  }

  /// Back to the tap-to-run list. `go` (not `pop`) so the list is shown on the
  /// right tab even when the editor was opened from a deep link.
  void _close() => context.go(Routes.scenes);

  Future<void> _addAction(String homeId) async {
    final action = await showActionPicker(context, homeId: homeId, excludeSceneId: widget.sceneId);
    if (action == null || !mounted) return;
    setState(() => _actions = [..._actions, action]);
  }

  void _reorder(int oldIndex, int newIndex) => setState(() => _actions = reorderedList(_actions, oldIndex, newIndex));

  Future<void> _save(String homeId) async {
    final name = _name.text.trim();
    if (name.isEmpty) {
      showErrorSnack(context, context.tr(fr: 'Donnez un nom à la scène', en: 'Give the scene a name'));
      return;
    }
    if (_actions.isEmpty) {
      showErrorSnack(context, context.tr(fr: 'Ajoutez au moins une action', en: 'Add at least one action'));
      return;
    }
    setState(() => _busy = true);
    final body = Scene(id: widget.sceneId ?? '', homeId: homeId, name: name, icon: _icon, color: _color, actions: _actions).toJson();
    try {
      final notifier = ref.read(scenesProvider(homeId).notifier);
      if (_isNew) {
        await notifier.create(body);
      } else {
        await notifier.updateScene(widget.sceneId!, body);
      }
      if (!mounted) return;
      showSnack(context, context.tr(fr: 'Scène enregistrée', en: 'Scene saved'));
      _close();
    } catch (error) {
      if (mounted) showErrorSnack(context, error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _delete(String homeId) async {
    final confirmed = await confirmDelete(
      context,
      title: context.tr(fr: 'Supprimer la scène ?', en: 'Delete this scene?'),
      message: context.tr(fr: 'Cette action est irréversible.', en: 'This cannot be undone.'),
    );
    if (!confirmed || !mounted) return;
    setState(() => _busy = true);
    try {
      await ref.read(scenesProvider(homeId).notifier).delete(widget.sceneId!);
      if (!mounted) return;
      showSnack(context, context.tr(fr: 'Scène supprimée', en: 'Scene deleted'));
      _close();
    } catch (error) {
      if (mounted) showErrorSnack(context, error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final homes = ref.watch(homesProvider);
    final home = ref.watch(currentHomeProvider);
    final title = Text(_isNew ? context.tr(fr: 'Nouvelle scène', en: 'New scene') : context.tr(fr: 'Modifier la scène', en: 'Edit scene'));
    if (home == null) return Scaffold(appBar: AppBar(title: title), body: NoHomeView(homes: homes));
    final homeId = home.id;
    final scenesAsync = ref.watch(scenesProvider(homeId));
    if (!_isNew) {
      final scene = scenesAsync.value?.where((s) => s.id == widget.sceneId);
      if (scene == null || scene.isEmpty) {
        return Scaffold(
          appBar: AppBar(title: title),
          body: scenesAsync.when(
            loading: () => const LoadingView(),
            error: (error, _) => ErrorView(error: error, onRetry: () => ref.read(scenesProvider(homeId).notifier).refresh()),
            data: (_) => EmptyState(
              icon: Icons.search_off,
              title: context.tr(fr: 'Scène introuvable', en: 'Scene not found'),
              actionLabel: context.tr(fr: 'Retour aux scènes', en: 'Back to scenes'),
              onAction: _close,
            ),
          ),
        );
      }
      _hydrate(scene.first);
    }
    final devices = ref.watch(devicesProvider(homeId)).value ?? const <Device>[];
    final scenes = scenesAsync.value ?? const <Scene>[];
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(
        title: title,
        actions: [
          if (!_isNew)
            IconButton(
              icon: const Icon(Icons.delete_outline),
              tooltip: context.tr(fr: 'Supprimer la scène', en: 'Delete scene'),
              onPressed: _busy ? null : () => _delete(homeId),
            ),
        ],
      ),
      body: CustomScrollView(
        slivers: [
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  _ScenePreview(nameListenable: _name, icon: _icon, color: colorFromHex(_color)),
                  const SizedBox(height: 16),
                  TextField(
                    controller: _name,
                    textCapitalization: TextCapitalization.sentences,
                    textInputAction: TextInputAction.done,
                    decoration: InputDecoration(
                      labelText: context.tr(fr: 'Nom de la scène', en: 'Scene name'),
                      hintText: context.tr(fr: 'Ex. : Bonne nuit', en: 'E.g. Good night'),
                    ),
                  ),
                ],
              ),
            ),
          ),
          SliverToBoxAdapter(child: SectionHeader(title: context.tr(fr: 'Icône', en: 'Icon'))),
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: SceneIconPicker(selected: _icon, color: colorFromHex(_color), onSelected: (name) => setState(() => _icon = name)),
            ),
          ),
          SliverToBoxAdapter(child: SectionHeader(title: context.tr(fr: 'Couleur', en: 'Colour'))),
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: SceneColorPicker(selected: _color, onSelected: (hex) => setState(() => _color = hex)),
            ),
          ),
          SliverToBoxAdapter(
            child: SectionHeader(
              title: context.tr(fr: 'Actions', en: 'Actions'),
              trailing: Text('${_actions.length}', style: theme.textTheme.labelLarge?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
            ),
          ),
          if (_actions.isEmpty)
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
                child: Text(
                  context.tr(fr: 'Aucune action pour le moment. Ajoutez ce que la scène doit faire.', en: 'No action yet. Add what the scene should do.'),
                  style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                ),
              ),
            ),
          SliverActionList(
            actions: _actions,
            devices: devices,
            scenes: scenes,
            onReorder: _reorder,
            onRemove: (index) => setState(() => _actions = [..._actions]..removeAt(index)),
          ),
          SliverToBoxAdapter(child: AddItemButton(label: context.tr(fr: 'Ajouter une action', en: 'Add an action'), onPressed: _busy ? null : () => _addAction(homeId))),
          const SliverToBoxAdapter(child: SizedBox(height: 24)),
        ],
      ),
      bottomNavigationBar: SaveBar(label: context.tr(fr: 'Enregistrer', en: 'Save'), busy: _busy, onPressed: () => _save(homeId)),
    );
  }
}

/// Live preview of the scene card while editing.
class _ScenePreview extends StatelessWidget {
  const _ScenePreview({required this.nameListenable, required this.icon, required this.color});

  final TextEditingController nameListenable;
  final String icon;
  final Color color;

  @override
  Widget build(BuildContext context) => AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          gradient: LinearGradient(colors: [color, color.withValues(alpha: 0.75)], begin: Alignment.topLeft, end: Alignment.bottomRight),
          borderRadius: BorderRadius.circular(16),
        ),
        child: Row(
          children: [
            Container(
              width: 48,
              height: 48,
              decoration: BoxDecoration(color: Colors.white.withValues(alpha: 0.22), borderRadius: BorderRadius.circular(14)),
              child: Icon(iconFromName(icon, fallback: Icons.play_circle), color: Colors.white, size: 26),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: ListenableBuilder(
                listenable: nameListenable,
                builder: (context, _) => Text(
                  nameListenable.text.trim().isEmpty ? context.tr(fr: 'Ma scène', en: 'My scene') : nameListenable.text.trim(),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: Theme.of(context).textTheme.titleLarge?.copyWith(color: Colors.white, fontWeight: FontWeight.w700),
                ),
              ),
            ),
          ],
        ),
      );
}
