import 'package:flutter/material.dart';

import '../../../core/i18n.dart';
import '../../../core/theme.dart';

/// The four home security modes, in display order.
const List<({String mode, IconData icon})> kArmModes = [
  (mode: 'disarmed', icon: Icons.lock_open),
  (mode: 'armed_home', icon: Icons.home),
  (mode: 'armed_away', icon: Icons.directions_walk),
  (mode: 'armed_night', icon: Icons.bedtime),
];

IconData armModeIcon(String mode) => kArmModes.firstWhere((m) => m.mode == mode, orElse: () => kArmModes.first).icon;

/// Row of four big arm-mode buttons (Désarmé · Présent · Absent · Nuit).
class ArmModeSelector extends StatelessWidget {
  const ArmModeSelector({super.key, required this.mode, required this.onSelected, this.enabled = true});

  final String mode;
  final ValueChanged<String> onSelected;
  final bool enabled;

  @override
  Widget build(BuildContext context) => Row(
        children: [
          for (final (index, m) in kArmModes.indexed) ...[
            if (index > 0) const SizedBox(width: 8),
            Expanded(
              child: ArmModeButton(
                mode: m.mode,
                icon: m.icon,
                selected: m.mode == mode,
                onTap: enabled ? () => onSelected(m.mode) : null,
              ),
            ),
          ],
        ],
      );
}

/// One arm-mode button: coloured icon disc + label, filled when selected.
class ArmModeButton extends StatelessWidget {
  const ArmModeButton({super.key, required this.mode, required this.icon, required this.selected, this.onTap});

  final String mode;
  final IconData icon;
  final bool selected;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final color = SafeRColors.forSecurityMode(mode);
    final label = securityModeLabel(context, mode);
    return Semantics(
      button: true,
      selected: selected,
      enabled: onTap != null,
      label: label,
      child: Material(
        color: selected ? color : color.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(16),
        child: InkWell(
          key: ValueKey('arm-mode-$mode'),
          borderRadius: BorderRadius.circular(16),
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 4),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: 44,
                  height: 44,
                  decoration: BoxDecoration(
                    color: selected ? Colors.white.withValues(alpha: 0.2) : color.withValues(alpha: 0.16),
                    shape: BoxShape.circle,
                  ),
                  child: Icon(icon, color: selected ? Colors.white : color, size: 24),
                ),
                const SizedBox(height: 8),
                Text(
                  label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.labelMedium?.copyWith(
                    color: selected ? Colors.white : theme.colorScheme.onSurface,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
