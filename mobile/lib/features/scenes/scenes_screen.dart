import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/i18n.dart';
import '../../core/models/models.dart';
import '../../core/providers/providers.dart';
import '../../core/router.dart';
import '../../core/theme.dart';
import '../../core/widgets/widgets.dart';
import 'widgets/automation_card.dart';
import 'widgets/common_sheets.dart';
import 'widgets/no_home_view.dart';
import 'widgets/scene_card.dart';

/// Tuya-style "Scenes" tab: tap-to-run scenes and automations.
class ScenesScreen extends ConsumerStatefulWidget {
  const ScenesScreen({super.key, this.initialTab = 0});

  /// 0 = tap-to-run, 1 = automations.
  final int initialTab;

  @override
  ConsumerState<ScenesScreen> createState() => _ScenesScreenState();
}

class _ScenesScreenState extends ConsumerState<ScenesScreen> with SingleTickerProviderStateMixin {
  late final TabController _tabs = TabController(length: 2, vsync: this, initialIndex: widget.initialTab.clamp(0, 1));

  @override
  void dispose() {
    _tabs.dispose();
    super.dispose();
  }

  void _create() => context.push(_tabs.index == 0 ? Routes.sceneNew : Routes.automationNew);

  @override
  Widget build(BuildContext context) {
    final homes = ref.watch(homesProvider);
    final home = ref.watch(currentHomeProvider);
    return Scaffold(
      appBar: AppBar(
        title: Text(context.tr(fr: 'Scènes', en: 'Scenes')),
        actions: [
          IconButton(
            icon: const Icon(Icons.add),
            tooltip: context.tr(fr: 'Créer', en: 'Create'),
            onPressed: home == null ? null : _create,
          ),
        ],
        bottom: TabBar(
          controller: _tabs,
          tabs: [
            Tab(text: context.tr(fr: 'Exécuter', en: 'Tap-to-Run')),
            Tab(text: context.tr(fr: 'Automatiser', en: 'Automation')),
          ],
        ),
      ),
      body: home == null
          ? NoHomeView(homes: homes)
          : TabBarView(
              controller: _tabs,
              children: [
                _TapToRunTab(homeId: home.id),
                _AutomationsTab(homeId: home.id),
              ],
            ),
    );
  }
}

// ---------------------------------------------------------------- tap-to-run
class _TapToRunTab extends ConsumerStatefulWidget {
  const _TapToRunTab({required this.homeId});

  final String homeId;

  @override
  ConsumerState<_TapToRunTab> createState() => _TapToRunTabState();
}

class _TapToRunTabState extends ConsumerState<_TapToRunTab> {
  final Set<String> _running = {};

  Future<void> _run(Scene scene) async {
    if (_running.contains(scene.id)) return;
    setState(() => _running.add(scene.id));
    try {
      await ref.read(scenesProvider(widget.homeId).notifier).run(scene.id);
      if (mounted) showSnack(context, context.tr(fr: 'Scène exécutée', en: 'Scene executed'));
    } catch (error) {
      if (mounted) showErrorSnack(context, error);
    } finally {
      if (mounted) setState(() => _running.remove(scene.id));
    }
  }

  Future<void> _menu(Scene scene) async {
    final choice = await showEditDeleteSheet(context, title: scene.name);
    if (!mounted || choice == null) return;
    if (choice == 'edit') {
      context.push(Routes.scene(scene.id));
      return;
    }
    final confirmed = await confirmDelete(
      context,
      title: context.tr(fr: 'Supprimer la scène ?', en: 'Delete this scene?'),
      message: context.tr(fr: '« ${scene.name} » sera supprimée définitivement.', en: '“${scene.name}” will be permanently deleted.'),
    );
    if (!confirmed || !mounted) return;
    try {
      await ref.read(scenesProvider(widget.homeId).notifier).delete(scene.id);
      if (mounted) showSnack(context, context.tr(fr: 'Scène supprimée', en: 'Scene deleted'));
    } catch (error) {
      if (mounted) showErrorSnack(context, error);
    }
  }

  @override
  Widget build(BuildContext context) {
    final scenesAsync = ref.watch(scenesProvider(widget.homeId));
    return scenesAsync.when(
      loading: () => const LoadingView(),
      error: (error, _) => ErrorView(error: error, onRetry: () => ref.read(scenesProvider(widget.homeId).notifier).refresh()),
      data: (scenes) {
        if (scenes.isEmpty) {
          return EmptyState(
            icon: Icons.auto_awesome_outlined,
            title: context.tr(fr: 'Aucune scène', en: 'No scenes yet'),
            subtitle: context.tr(fr: 'Regroupez plusieurs actions et lancez-les en un tap.', en: 'Group several actions and run them with one tap.'),
            actionLabel: context.tr(fr: 'Créer une scène', en: 'Create a scene'),
            onAction: () => context.push(Routes.sceneNew),
          );
        }
        return RefreshIndicator(
          onRefresh: () => ref.read(scenesProvider(widget.homeId).notifier).refresh(),
          child: GridView.builder(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 96),
            gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(crossAxisCount: 2, crossAxisSpacing: 12, mainAxisSpacing: 12, childAspectRatio: 1.3),
            itemCount: scenes.length,
            itemBuilder: (context, index) {
              final scene = scenes[index];
              return SceneCard(
                scene: scene,
                running: _running.contains(scene.id),
                onTap: () => _run(scene),
                onLongPress: () => _menu(scene),
              );
            },
          ),
        );
      },
    );
  }
}

// ---------------------------------------------------------------- automations
class _AutomationsTab extends ConsumerStatefulWidget {
  const _AutomationsTab({required this.homeId});

  final String homeId;

  @override
  ConsumerState<_AutomationsTab> createState() => _AutomationsTabState();
}

class _AutomationsTabState extends ConsumerState<_AutomationsTab> {
  /// Items hidden locally while their deletion is in flight (keeps Dismissible happy).
  final Set<String> _hidden = {};

  AutomationsNotifier get _notifier => ref.read(automationsProvider(widget.homeId).notifier);

  Future<void> _toggle(Automation automation, bool enabled) async {
    try {
      await _notifier.setEnabled(automation.id, enabled);
    } catch (error) {
      if (mounted) showErrorSnack(context, error);
    }
  }

  Future<void> _test(Automation automation) async {
    try {
      await _notifier.trigger(automation.id);
      if (mounted) showSnack(context, context.tr(fr: 'Automatisation testée', en: 'Automation triggered'));
    } catch (error) {
      if (mounted) showErrorSnack(context, error);
    }
  }

  Future<bool> _confirm(Automation automation) => confirmDelete(
        context,
        title: context.tr(fr: "Supprimer l'automatisation ?", en: 'Delete this automation?'),
        message: context.tr(fr: '« ${automation.name} » sera supprimée définitivement.', en: '“${automation.name}” will be permanently deleted.'),
      );

  Future<void> _delete(Automation automation) async {
    setState(() => _hidden.add(automation.id));
    try {
      await _notifier.delete(automation.id);
      if (mounted) showSnack(context, context.tr(fr: 'Automatisation supprimée', en: 'Automation deleted'));
    } catch (error) {
      if (mounted) showErrorSnack(context, error);
    } finally {
      if (mounted) setState(() => _hidden.remove(automation.id));
    }
  }

  Future<void> _menu(Automation automation) async {
    final choice = await showEditDeleteSheet(context, title: automation.name);
    if (!mounted || choice == null) return;
    if (choice == 'edit') {
      context.push(Routes.automation(automation.id));
      return;
    }
    if (await _confirm(automation) && mounted) await _delete(automation);
  }

  @override
  Widget build(BuildContext context) {
    final automationsAsync = ref.watch(automationsProvider(widget.homeId));
    final devices = ref.watch(devicesProvider(widget.homeId)).value ?? const <Device>[];
    final scenes = ref.watch(scenesProvider(widget.homeId)).value ?? const <Scene>[];
    return automationsAsync.when(
      loading: () => const LoadingView(),
      error: (error, _) => ErrorView(error: error, onRetry: _notifier.refresh),
      data: (all) {
        final automations = all.where((a) => !_hidden.contains(a.id)).toList();
        if (automations.isEmpty) {
          return EmptyState(
            icon: Icons.bolt_outlined,
            title: context.tr(fr: 'Aucune automatisation', en: 'No automations yet'),
            subtitle: context.tr(fr: 'Laissez la maison réagir seule : « Si mouvement, alors allumer ».', en: 'Let the home react on its own: “If motion, then turn on”.'),
            actionLabel: context.tr(fr: 'Créer une automatisation', en: 'Create an automation'),
            onAction: () => context.push(Routes.automationNew),
          );
        }
        return RefreshIndicator(
          onRefresh: _notifier.refresh,
          child: ListView.separated(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 96),
            itemCount: automations.length,
            separatorBuilder: (_, __) => const SizedBox(height: 12),
            itemBuilder: (context, index) {
              final automation = automations[index];
              return Dismissible(
                key: ValueKey('automation-${automation.id}'),
                direction: DismissDirection.endToStart,
                confirmDismiss: (_) => _confirm(automation),
                onDismissed: (_) => _delete(automation),
                background: Container(
                  alignment: Alignment.centerRight,
                  padding: const EdgeInsets.symmetric(horizontal: 24),
                  decoration: BoxDecoration(color: SafeRColors.danger, borderRadius: BorderRadius.circular(16)),
                  child: const Icon(Icons.delete_outline, color: Colors.white),
                ),
                child: AutomationCard(
                  automation: automation,
                  devices: devices,
                  scenes: scenes,
                  onTap: () => context.push(Routes.automation(automation.id)),
                  onLongPress: () => _menu(automation),
                  onToggle: (enabled) => _toggle(automation, enabled),
                  onTest: () => _test(automation),
                ),
              );
            },
          ),
        );
      },
    );
  }
}
