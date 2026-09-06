import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/i18n.dart';
import '../../core/models/models.dart';
import '../../core/providers/providers.dart';
import '../../core/routes.dart';
import '../../core/widgets/widgets.dart';
import 'widgets/action_list.dart';
import 'widgets/action_picker.dart';
import 'widgets/common_sheets.dart';
import 'widgets/no_home_view.dart';
import 'widgets/rule_picker.dart';

/// Create or edit an automation: "Si" triggers, "Et si" conditions, "Alors" actions.
class AutomationEditorScreen extends ConsumerStatefulWidget {
  const AutomationEditorScreen({super.key, this.automationId});

  final String? automationId;

  @override
  ConsumerState<AutomationEditorScreen> createState() => _AutomationEditorScreenState();
}

class _AutomationEditorScreenState extends ConsumerState<AutomationEditorScreen> {
  final _name = TextEditingController();
  bool _enabled = true;
  String _match = 'all';
  List<Rule> _triggers = [];
  List<Rule> _conditions = [];
  List<SceneAction> _actions = [];
  bool _hydrated = false;
  bool _busy = false;

  bool get _isNew => widget.automationId == null;

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  void _hydrate(Automation automation) {
    if (_hydrated) return;
    _hydrated = true;
    _name.text = automation.name;
    _enabled = automation.enabled;
    _match = automation.match == 'any' ? 'any' : 'all';
    _triggers = List.of(automation.triggers);
    _conditions = List.of(automation.conditions);
    _actions = List.of(automation.actions);
  }

  /// Back to the automations list. `go` (not `pop`) so the list opens on the
  /// "Automatiser" tab even when the editor was opened from a deep link.
  void _close() => context.go('${Routes.scenes}?tab=automations');

  Future<void> _addTrigger(String homeId) async {
    final rule = await showTriggerPicker(context, homeId: homeId);
    if (rule == null || !mounted) return;
    setState(() => _triggers = [..._triggers, rule]);
  }

  Future<void> _addCondition(String homeId) async {
    final rule = await showConditionPicker(context, homeId: homeId);
    if (rule == null || !mounted) return;
    setState(() => _conditions = [..._conditions, rule]);
  }

  Future<void> _addAction(String homeId) async {
    final action = await showActionPicker(context, homeId: homeId);
    if (action == null || !mounted) return;
    setState(() => _actions = [..._actions, action]);
  }

  Future<void> _save(String homeId) async {
    final name = _name.text.trim();
    if (name.isEmpty) {
      showErrorSnack(context, context.tr(fr: "Donnez un nom à l'automatisation", en: 'Give the automation a name'));
      return;
    }
    if (_triggers.isEmpty) {
      showErrorSnack(context, context.tr(fr: 'Ajoutez au moins un déclencheur', en: 'Add at least one trigger'));
      return;
    }
    if (_actions.isEmpty) {
      showErrorSnack(context, context.tr(fr: 'Ajoutez au moins une action', en: 'Add at least one action'));
      return;
    }
    setState(() => _busy = true);
    final body = Automation(
      id: widget.automationId ?? '',
      homeId: homeId,
      name: name,
      enabled: _enabled,
      match: _match,
      triggers: _triggers,
      conditions: _conditions,
      actions: _actions,
    ).toJson();
    try {
      final notifier = ref.read(automationsProvider(homeId).notifier);
      if (_isNew) {
        await notifier.create(body);
      } else {
        await notifier.updateAutomation(widget.automationId!, body);
      }
      if (!mounted) return;
      showSnack(context, context.tr(fr: 'Automatisation enregistrée', en: 'Automation saved'));
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
      title: context.tr(fr: "Supprimer l'automatisation ?", en: 'Delete this automation?'),
      message: context.tr(fr: 'Cette action est irréversible.', en: 'This cannot be undone.'),
    );
    if (!confirmed || !mounted) return;
    setState(() => _busy = true);
    try {
      await ref.read(automationsProvider(homeId).notifier).delete(widget.automationId!);
      if (!mounted) return;
      showSnack(context, context.tr(fr: 'Automatisation supprimée', en: 'Automation deleted'));
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
    final title = Text(_isNew ? context.tr(fr: 'Nouvelle automatisation', en: 'New automation') : context.tr(fr: "Modifier l'automatisation", en: 'Edit automation'));
    if (home == null) return Scaffold(appBar: AppBar(title: title), body: NoHomeView(homes: homes));
    final homeId = home.id;
    // Automation create/update/delete are admin-only on the hub: members get a read-only view.
    final canManage = home.canManage;
    if (_isNew && !canManage) return Scaffold(appBar: AppBar(title: title), body: const AdminOnlyEditorView());
    if (!_isNew) {
      final automationsAsync = ref.watch(automationsProvider(homeId));
      final found = automationsAsync.valueOrNull?.where((a) => a.id == widget.automationId);
      if (found == null || found.isEmpty) {
        return Scaffold(
          appBar: AppBar(title: title),
          body: automationsAsync.when(
            loading: () => const LoadingView(),
            error: (error, _) => ErrorView(error: error, onRetry: () => ref.read(automationsProvider(homeId).notifier).refresh()),
            data: (_) => EmptyState(
              icon: Icons.search_off,
              title: context.tr(fr: 'Automatisation introuvable', en: 'Automation not found'),
              actionLabel: context.tr(fr: 'Retour', en: 'Back'),
              onAction: _close,
            ),
          ),
        );
      }
      _hydrate(found.first);
    }
    final devices = ref.watch(devicesProvider(homeId)).valueOrNull ?? const <Device>[];
    final scenes = ref.watch(scenesProvider(homeId)).valueOrNull ?? const <Scene>[];
    final theme = Theme.of(context);
    final hint = theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant);
    return Scaffold(
      appBar: AppBar(
        title: title,
        actions: [
          if (!_isNew && canManage)
            IconButton(
              icon: const Icon(Icons.delete_outline),
              tooltip: context.tr(fr: "Supprimer l'automatisation", en: 'Delete automation'),
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
                  TextField(
                    controller: _name,
                    textCapitalization: TextCapitalization.sentences,
                    textInputAction: TextInputAction.done,
                    decoration: InputDecoration(
                      labelText: context.tr(fr: "Nom de l'automatisation", en: 'Automation name'),
                      hintText: context.tr(fr: 'Ex. : Lumière si mouvement', en: 'E.g. Light on motion'),
                    ),
                  ),
                  const SizedBox(height: 8),
                  SwitchListTile(
                    contentPadding: const EdgeInsets.symmetric(horizontal: 4),
                    title: Text(context.tr(fr: 'Activée', en: 'Enabled')),
                    subtitle: Text(context.tr(fr: 'Désactivez pour mettre en pause sans supprimer', en: 'Turn off to pause without deleting'), style: hint),
                    value: _enabled,
                    onChanged: (v) => setState(() => _enabled = v),
                  ),
                ],
              ),
            ),
          ),
          // ---- Si
          SliverToBoxAdapter(child: SectionHeader(title: context.tr(fr: 'Si', en: 'If'), padding: const EdgeInsets.fromLTRB(16, 12, 16, 4))),
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
              child: _triggers.isNotEmpty
                  ? SegmentedButton<String>(
                      showSelectedIcon: false,
                      segments: [
                        ButtonSegment(value: 'all', label: Text(context.tr(fr: 'Toutes les conditions', en: 'All conditions'))),
                        ButtonSegment(value: 'any', label: Text(context.tr(fr: "L'une des conditions", en: 'Any condition'))),
                      ],
                      selected: {_match},
                      onSelectionChanged: (s) => setState(() => _match = s.first),
                    )
                  : Text(context.tr(fr: 'Quand se déclenche-t-elle ?', en: 'When does it fire?'), style: hint),
            ),
          ),
          SliverList.list(children: [for (var i = 0; i < _triggers.length; i++) RuleTile(rule: _triggers[i], devices: devices, onRemove: () => setState(() => _triggers = [..._triggers]..removeAt(i)))]),
          SliverToBoxAdapter(child: AddItemButton(label: context.tr(fr: 'Ajouter un déclencheur', en: 'Add a trigger'), onPressed: _busy ? null : () => _addTrigger(homeId))),
          // ---- Et si
          SliverToBoxAdapter(child: SectionHeader(title: context.tr(fr: 'Et si', en: 'And if'), padding: const EdgeInsets.fromLTRB(16, 12, 16, 4))),
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
              child: Text(context.tr(fr: 'Conditions optionnelles vérifiées au déclenchement', en: 'Optional conditions checked when it fires'), style: hint),
            ),
          ),
          SliverList.list(children: [for (var i = 0; i < _conditions.length; i++) RuleTile(rule: _conditions[i], devices: devices, onRemove: () => setState(() => _conditions = [..._conditions]..removeAt(i)))]),
          SliverToBoxAdapter(child: AddItemButton(label: context.tr(fr: 'Ajouter une condition', en: 'Add a condition'), onPressed: _busy ? null : () => _addCondition(homeId))),
          // ---- Alors
          SliverToBoxAdapter(child: SectionHeader(title: context.tr(fr: 'Alors', en: 'Then'), padding: const EdgeInsets.fromLTRB(16, 12, 16, 4))),
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
              child: Text(context.tr(fr: 'Que doit faire la maison ?', en: 'What should the home do?'), style: hint),
            ),
          ),
          SliverActionList(
            actions: _actions,
            devices: devices,
            scenes: scenes,
            onReorder: (oldIndex, newIndex) => setState(() => _actions = reorderedList(_actions, oldIndex, newIndex)),
            onRemove: (index) => setState(() => _actions = [..._actions]..removeAt(index)),
          ),
          SliverToBoxAdapter(child: AddItemButton(label: context.tr(fr: 'Ajouter une action', en: 'Add an action'), onPressed: _busy ? null : () => _addAction(homeId))),
          const SliverToBoxAdapter(child: SizedBox(height: 24)),
        ],
      ),
      bottomNavigationBar: canManage ? SaveBar(label: context.tr(fr: 'Enregistrer', en: 'Save'), busy: _busy, onPressed: () => _save(homeId)) : const ReadOnlyEditorBar(),
    );
  }
}
