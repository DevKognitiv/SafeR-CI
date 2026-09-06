import 'package:flutter/material.dart';

import '../../../core/theme.dart';

/// Tuya-style large circular action button (power, lock...).
class BigPowerButton extends StatelessWidget {
  const BigPowerButton({
    super.key,
    required this.active,
    required this.onPressed,
    required this.semanticsLabel,
    this.icon = Icons.power_settings_new,
    this.activeColor,
    this.caption,
    this.size = 128,
  });

  final bool active;
  final VoidCallback? onPressed;
  final String semanticsLabel;
  final IconData icon;
  final Color? activeColor;
  final String? caption;
  final double size;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final color = activeColor ?? SafeRColors.primary;
    final enabled = onPressed != null;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Semantics(
          container: true,
          button: true,
          enabled: enabled,
          toggled: active,
          label: semanticsLabel,
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 250),
            width: size,
            height: size,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: active ? color : theme.colorScheme.surfaceContainerHighest,
              boxShadow: active ? [BoxShadow(color: color.withValues(alpha: 0.35), blurRadius: 24, offset: const Offset(0, 8))] : const [],
            ),
            child: Material(
              color: Colors.transparent,
              shape: const CircleBorder(),
              child: InkWell(
                customBorder: const CircleBorder(),
                onTap: onPressed,
                child: Icon(icon, size: size * 0.42, color: active ? Colors.white : theme.colorScheme.onSurfaceVariant.withValues(alpha: enabled ? 1 : 0.5)),
              ),
            ),
          ),
        ),
        if (caption != null) ...[
          const SizedBox(height: 12),
          Text(
            caption!,
            style: theme.textTheme.titleMedium
                ?.copyWith(fontWeight: FontWeight.w700, color: active ? color : theme.colorScheme.onSurfaceVariant, letterSpacing: 1),
          ),
        ],
      ],
    );
  }
}
