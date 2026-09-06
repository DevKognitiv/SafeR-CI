import 'package:flutter/material.dart';

import '../../../core/i18n.dart';
import '../../../core/theme.dart';
import '../../../core/widgets/widgets.dart';

/// Battery percentage chip with a level-aware icon and colour.
class BatteryChip extends StatelessWidget {
  const BatteryChip({super.key, required this.level});

  final num level;

  @override
  Widget build(BuildContext context) {
    final pct = level.round();
    final icon = pct >= 90
        ? Icons.battery_full
        : pct >= 60
            ? Icons.battery_5_bar
            : pct >= 35
                ? Icons.battery_3_bar
                : pct >= 15
                    ? Icons.battery_2_bar
                    : Icons.battery_alert;
    final color = pct <= 15 ? SafeRColors.danger : (pct <= 35 ? SafeRColors.warning : SafeRColors.success);
    return Semantics(label: context.tr(fr: 'Batterie $pct%', en: 'Battery $pct%'), child: StateChip(label: '$pct%', icon: icon, color: color));
  }
}

/// Signal strength chip.
class SignalChip extends StatelessWidget {
  const SignalChip({super.key, required this.level});

  final num level;

  @override
  Widget build(BuildContext context) {
    final pct = level.round();
    final icon = pct >= 75
        ? Icons.signal_cellular_alt
        : pct >= 40
            ? Icons.signal_cellular_alt_2_bar
            : Icons.signal_cellular_alt_1_bar;
    final color = pct < 30 ? SafeRColors.warning : SafeRColors.primary;
    return Semantics(label: context.tr(fr: 'Signal $pct%', en: 'Signal $pct%'), child: StateChip(label: '$pct%', icon: icon, color: color));
  }
}

/// Two-state chip (motion / recording / tamper...).
class BoolChip extends StatelessWidget {
  const BoolChip({super.key, required this.active, required this.activeLabel, required this.inactiveLabel, this.activeColor, this.inactiveColor, this.icon});

  final bool active;
  final String activeLabel;
  final String inactiveLabel;
  final Color? activeColor;
  final Color? inactiveColor;
  final IconData? icon;

  @override
  Widget build(BuildContext context) => StateChip(
        label: active ? activeLabel : inactiveLabel,
        icon: icon,
        color: active ? (activeColor ?? SafeRColors.warning) : (inactiveColor ?? Theme.of(context).colorScheme.onSurfaceVariant),
      );
}

/// Online / offline chip.
class OnlineChip extends StatelessWidget {
  const OnlineChip({super.key, required this.online});

  final bool online;

  @override
  Widget build(BuildContext context) => StateChip(
        label: online ? context.tr(fr: 'EN LIGNE', en: 'ONLINE') : context.tr(fr: 'HORS LIGNE', en: 'OFFLINE'),
        icon: online ? Icons.cloud_done_outlined : Icons.cloud_off,
        color: online ? SafeRColors.success : Theme.of(context).colorScheme.onSurfaceVariant,
      );
}
