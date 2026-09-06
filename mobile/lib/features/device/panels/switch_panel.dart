import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/i18n.dart';
import '../../../core/models/device.dart';
import '../../../core/theme.dart';
import '../widgets/big_power_button.dart';
import '../widgets/capability_format.dart';
import '../widgets/device_command.dart';
import '../widgets/generic_controls.dart';
import '../widgets/info_rows.dart';
import '../widgets/panel_card.dart';

final _gangPattern = RegExp(r'^switch_(\d+)$');

/// Switch / plug / siren: big power button, per-gang switches and power readouts.
class SwitchPanel extends ConsumerWidget {
  const SwitchPanel({super.key, required this.device});

  final Device device;

  List<Capability> get _gangs {
    final gangs = device.capabilities.where((c) => c.writable && c.type == 'bool' && _gangPattern.hasMatch(c.code)).toList();
    gangs.sort((a, b) => int.parse(_gangPattern.firstMatch(a.code)!.group(1)!).compareTo(int.parse(_gangPattern.firstMatch(b.code)!.group(1)!)));
    return gangs;
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final gangs = _gangs;
    final mainCode = device.primaryToggleCode;
    final mainCap = mainCode == null ? null : writableCapability(device, mainCode, type: 'bool');
    final anyGangOn = gangs.any((g) => device.boolValue(g.code) ?? false);
    final on = mainCode == 'switch' || mainCode == 'siren' ? (device.boolValue(mainCode!) ?? false) : anyGangOn;
    final isSiren = device.category == 'siren';
    final power = device.hasCapability('power') ? device.numValue('power') : null;
    final energy = device.hasCapability('energy') ? device.numValue('energy') : null;

    Future<void> toggle() async {
      if (mainCode == 'switch' || mainCode == 'siren') {
        await sendDeviceCommand(context, ref, device, mainCode!, !on);
      } else if (gangs.isNotEmpty) {
        await sendDeviceCommands(context, ref, device, {for (final g in gangs) g.code: !anyGangOn});
      }
    }

    final handled = <String>{'switch', 'power', 'energy', if (isSiren) 'siren', for (final g in gangs) g.code};
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (mainCap != null || gangs.isNotEmpty)
          PanelCard(
            padding: const EdgeInsets.symmetric(vertical: 28, horizontal: 16),
            child: Center(
              child: BigPowerButton(
                active: on,
                icon: isSiren ? Icons.campaign : Icons.power_settings_new,
                activeColor: isSiren ? SafeRColors.danger : SafeRColors.primary,
                semanticsLabel: isSiren ? context.tr(fr: 'Sirène', en: 'Siren') : context.tr(fr: 'Alimentation', en: 'Power'),
                caption: on ? context.tr(fr: 'ALLUMÉ', en: 'ON') : context.tr(fr: 'ÉTEINT', en: 'OFF'),
                onPressed: device.online ? toggle : null,
              ),
            ),
          ),
        if (gangs.length > 1 || (gangs.length == 1 && mainCode != gangs.first.code)) ...[
          const SizedBox(height: 12),
          PanelCard(
            title: context.tr(fr: 'Voies', en: 'Gangs'),
            padding: const EdgeInsets.fromLTRB(16, 16, 8, 8),
            child: Column(
              children: [
                for (final gang in gangs)
                  SwitchListTile.adaptive(
                    contentPadding: EdgeInsets.zero,
                    title: Text(capabilityLabel(context, gang)),
                    subtitle: Text((device.boolValue(gang.code) ?? false) ? context.tr(fr: 'Allumé', en: 'On') : context.tr(fr: 'Éteint', en: 'Off'),
                        style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
                    value: device.boolValue(gang.code) ?? false,
                    onChanged: device.online ? (v) => sendDeviceCommand(context, ref, device, gang.code, v) : null,
                  ),
              ],
            ),
          ),
        ],
        if (power != null || energy != null) ...[
          const SizedBox(height: 12),
          PanelCard(
            title: context.tr(fr: 'Consommation', en: 'Consumption'),
            child: Row(
              children: [
                if (power != null)
                  Expanded(
                      child: ReadoutTile(
                          value: formatNumber(power, decimals: 1),
                          unit: device.capability('power')?.unit ?? 'W',
                          label: context.tr(fr: 'Puissance', en: 'Power'),
                          icon: Icons.bolt,
                          color: SafeRColors.warning)),
                if (power != null && energy != null) const SizedBox(width: 12),
                if (energy != null)
                  Expanded(
                      child: ReadoutTile(
                          value: formatNumber(energy, decimals: 2),
                          unit: device.capability('energy')?.unit ?? 'kWh',
                          label: context.tr(fr: 'Énergie', en: 'Energy'),
                          icon: Icons.electric_meter_outlined,
                          color: SafeRColors.success)),
              ],
            ),
          ),
        ],
        GenericControls(device: device, exclude: handled),
      ],
    );
  }
}
