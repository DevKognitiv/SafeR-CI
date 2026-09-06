import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/i18n.dart';
import '../../core/models/device.dart';
import '../../core/providers/providers.dart';
import '../../core/routes.dart';
import '../../core/theme.dart';
import '../../core/widgets/widgets.dart';
import 'widgets/device_events_list.dart';
import 'widgets/device_resolver.dart';
import 'widgets/dialogs.dart';
import 'widgets/info_rows.dart';
import 'widgets/picker_sheets.dart';
import 'widgets/status_chips.dart';

/// Device settings: rename, room, icon, information, history, refresh and removal.
class DeviceSettingsScreen extends StatelessWidget {
  const DeviceSettingsScreen({super.key, required this.deviceId});

  final String deviceId;

  @override
  Widget build(BuildContext context) => DeviceResolver(
        deviceId: deviceId,
        title: context.tr(fr: "Paramètres de l'appareil", en: 'Device settings'),
        builder: (context, device) => _SettingsBody(device: device),
      );
}

class _SettingsBody extends ConsumerStatefulWidget {
  const _SettingsBody({required this.device});

  final Device device;

  @override
  ConsumerState<_SettingsBody> createState() => _SettingsBodyState();
}

class _SettingsBodyState extends ConsumerState<_SettingsBody> {
  bool _busy = false;

  Device get device => widget.device;

  DevicesNotifier get _notifier => ref.read(devicesProvider(device.homeId).notifier);

  Future<void> _run(Future<void> Function() action, {String? success}) async {
    setState(() => _busy = true);
    try {
      await action();
      if (mounted && success != null) showSnack(context, success);
    } catch (e) {
      if (mounted) showErrorSnack(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _rename() async {
    final name = await showTextPromptDialog(
      context,
      title: context.tr(fr: "Renommer l'appareil", en: 'Rename device'),
      confirmLabel: context.tr(fr: 'Enregistrer', en: 'Save'),
      initialValue: device.name,
      hint: context.tr(fr: 'Nouveau nom', en: 'New name'),
    );
    if (name == null || name == device.name || !mounted) return;
    await _run(() => _notifier.updateDevice(device.id, name: name), success: context.tr(fr: 'Appareil renommé', en: 'Device renamed'));
  }

  Future<void> _pickRoom() async {
    final rooms = ref.read(roomsProvider(device.homeId));
    final choice = await showRoomPickerSheet(context, rooms: rooms, currentRoomId: device.roomId);
    if (choice == null || choice.roomId == device.roomId || !mounted) return;
    await _run(
      () => _notifier.updateDevice(device.id, roomId: choice.roomId, clearRoom: choice.roomId == null),
      success: context.tr(fr: 'Appareil déplacé', en: 'Device moved'),
    );
  }

  Future<void> _pickIcon() async {
    final icon = await showIconPickerSheet(context, current: device.icon);
    if (icon == null || icon == device.icon || !mounted) return;
    await _run(() => _notifier.updateDevice(device.id, icon: icon), success: context.tr(fr: 'Icône mise à jour', en: 'Icon updated'));
  }

  Future<void> _refresh() => _run(() async {
        await _notifier.refreshDevice(device.id);
        ref.invalidate(deviceEventsProvider(device.id));
      }, success: context.tr(fr: 'Appareil actualisé', en: 'Device refreshed'));

  Future<void> _remove() async {
    final confirmed = await showConfirmDialog(
      context,
      icon: Icons.delete_outline,
      title: context.tr(fr: "Supprimer l'appareil ?", en: 'Remove device?'),
      message: context.tr(
        fr: '${device.name} sera retiré de SafeR ainsi que ses appareils rattachés. Vous pourrez le réappairer plus tard.',
        en: '${device.name} and its attached devices will be removed from SafeR. You can pair it again later.',
      ),
      confirmLabel: context.tr(fr: 'Supprimer', en: 'Remove'),
      destructive: true,
    );
    if (!confirmed || !mounted) return;
    // The screen is rebuilt without its device once the list shrinks: capture what we need first.
    final router = GoRouter.of(context);
    final messenger = ScaffoldMessenger.of(context);
    final removedMessage = context.tr(fr: 'Appareil supprimé', en: 'Device removed');
    setState(() => _busy = true);
    try {
      await _notifier.remove(device.id);
      messenger.showSnackBar(SnackBar(content: Text(removedMessage)));
      router.go(Routes.home);
    } catch (e) {
      if (mounted) {
        setState(() => _busy = false);
        showErrorSnack(context, e);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final rooms = ref.watch(roomsProvider(device.homeId));
    final room = rooms.where((r) => r.id == device.roomId).firstOrNull;
    final brand = ref.watch(brandProvider(device.brand));
    final lastSeen = device.lastSeenAt ?? device.updatedAt;
    final none = context.tr(fr: 'Non renseigné', en: 'Not provided');
    // PATCH/DELETE /devices are admin-only on the hub; members keep refresh and the read-only rows.
    final canManage = ref.watch(homesProvider).valueOrNull?.where((h) => h.id == device.homeId).firstOrNull?.canManage ?? false;
    final editable = !_busy && canManage;

    return Scaffold(
      appBar: AppBar(title: Text(context.tr(fr: "Paramètres de l'appareil", en: 'Device settings'))),
      body: Stack(
        children: [
          SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Row(
                      children: [
                        Semantics(
                          button: true,
                          label: context.tr(fr: "Changer l'icône", en: 'Change icon'),
                          child: InkWell(
                            borderRadius: BorderRadius.circular(16),
                            onTap: editable ? _pickIcon : null,
                            child: Container(
                              width: 64,
                              height: 64,
                              decoration: BoxDecoration(color: SafeRColors.primary.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(16)),
                              child: Icon(iconFromName(device.icon, fallback: categoryIcon(device.category)), color: SafeRColors.primary, size: 32),
                            ),
                          ),
                        ),
                        const SizedBox(width: 14),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(device.name,
                                  style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700), maxLines: 2, overflow: TextOverflow.ellipsis),
                              const SizedBox(height: 4),
                              Text([categoryLabel(context, device.category), brand?.name ?? device.brand].join(' · '),
                                  style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
                              const SizedBox(height: 8),
                              OnlineChip(online: device.online),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                Card(
                  child: Column(
                    children: [
                      ValueRow(icon: Icons.edit_outlined, label: context.tr(fr: 'Nom', en: 'Name'), value: device.name, onTap: editable ? _rename : null),
                      const Divider(indent: 48),
                      ValueRow(
                          icon: Icons.meeting_room_outlined,
                          label: context.tr(fr: 'Pièce', en: 'Room'),
                          value: room?.name ?? context.tr(fr: 'Aucune pièce', en: 'No room'),
                          onTap: editable ? _pickRoom : null),
                      const Divider(indent: 48),
                      ValueRow(
                          icon: Icons.emoji_objects_outlined,
                          label: context.tr(fr: 'Icône', en: 'Icon'),
                          value: device.icon ?? context.tr(fr: 'Par défaut', en: 'Default'),
                          onTap: editable ? _pickIcon : null),
                    ],
                  ),
                ),
                if (!canManage)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(4, 8, 4, 0),
                    child: Text(
                      context.tr(fr: "Seuls les administrateurs peuvent renommer, déplacer ou supprimer l'appareil.", en: 'Only administrators can rename, move or remove the device.'),
                      style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                    ),
                  ),
                SectionHeader(title: context.tr(fr: 'Informations', en: 'Information'), padding: const EdgeInsets.fromLTRB(4, 20, 4, 8)),
                Card(
                  child: Column(
                    children: [
                      ValueRow(label: context.tr(fr: 'Marque', en: 'Brand'), value: brand?.name ?? device.brand),
                      const Divider(indent: 16, endIndent: 16),
                      ValueRow(label: context.tr(fr: 'Protocole', en: 'Protocol'), value: device.protocol.isEmpty ? none : device.protocol),
                      const Divider(indent: 16, endIndent: 16),
                      ValueRow(label: context.tr(fr: 'Modèle', en: 'Model'), value: device.model ?? none),
                      const Divider(indent: 16, endIndent: 16),
                      ValueRow(label: context.tr(fr: 'Fabricant', en: 'Manufacturer'), value: device.manufacturer ?? none),
                      const Divider(indent: 16, endIndent: 16),
                      ValueRow(label: context.tr(fr: 'Firmware', en: 'Firmware'), value: device.firmware ?? none),
                      const Divider(indent: 16, endIndent: 16),
                      ValueRow(label: context.tr(fr: 'Identifiant', en: 'External ID'), value: device.externalId.isEmpty ? none : device.externalId),
                      const Divider(indent: 16, endIndent: 16),
                      ValueRow(
                        label: context.tr(fr: 'État', en: 'Status'),
                        value: device.online ? context.tr(fr: 'En ligne', en: 'Online') : context.tr(fr: 'Hors ligne', en: 'Offline'),
                        valueColor: device.online ? SafeRColors.success : SafeRColors.danger,
                      ),
                      const Divider(indent: 16, endIndent: 16),
                      ValueRow(label: context.tr(fr: 'Dernière activité', en: 'Last seen'), value: lastSeen == null ? none : timeAgo(context, lastSeen)),
                    ],
                  ),
                ),
                SectionHeader(title: context.tr(fr: 'Historique', en: 'History'), padding: const EdgeInsets.fromLTRB(4, 20, 4, 8)),
                DeviceEventsList(deviceId: device.id, limit: 10),
                const SizedBox(height: 12),
                Card(
                  child: ListTile(
                    leading: const Icon(Icons.refresh),
                    title: Text(context.tr(fr: 'Actualiser', en: 'Refresh')),
                    subtitle: Text(context.tr(fr: "Interroger l'appareil maintenant", en: 'Query the device now')),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: _busy ? null : _refresh,
                  ),
                ),
                if (canManage) ...[
                  SectionHeader(title: context.tr(fr: 'Zone de danger', en: 'Danger zone'), padding: const EdgeInsets.fromLTRB(4, 20, 4, 8)),
                  Card(
                    child: ListTile(
                      leading: const Icon(Icons.delete_outline, color: SafeRColors.danger),
                      title: Text(context.tr(fr: "Supprimer l'appareil", en: 'Remove device'),
                          style: const TextStyle(color: SafeRColors.danger, fontWeight: FontWeight.w600)),
                      subtitle: Text(context.tr(fr: 'Retire l\'appareil de cette maison', en: 'Removes the device from this home')),
                      onTap: _busy ? null : _remove,
                    ),
                  ),
                ],
              ],
            ),
          ),
          if (_busy) const Positioned(left: 0, right: 0, top: 0, child: LinearProgressIndicator(minHeight: 2)),
        ],
      ),
    );
  }
}
