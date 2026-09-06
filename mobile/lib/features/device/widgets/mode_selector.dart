import 'package:flutter/material.dart';

/// One choice of a [ModeSelector].
class ModeOption<T> {
  const ModeOption({required this.value, required this.label, this.icon, this.color});

  final T value;
  final String label;
  final IconData? icon;
  final Color? color;
}

/// Segmented control with equal-width segments (work mode, thermostat mode, arm mode...).
class ModeSelector<T> extends StatelessWidget {
  const ModeSelector({super.key, required this.options, required this.selected, required this.onSelected, this.enabled = true});

  final List<ModeOption<T>> options;
  final T? selected;
  final ValueChanged<T> onSelected;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final hasIcons = options.any((o) => o.icon != null);
    return Container(
      padding: const EdgeInsets.all(4),
      decoration: BoxDecoration(color: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.6), borderRadius: BorderRadius.circular(14)),
      child: Row(
        children: [
          for (final option in options)
            Expanded(
              child: Semantics(
                button: true,
                selected: option.value == selected,
                label: option.label,
                child: InkWell(
                  borderRadius: BorderRadius.circular(11),
                  onTap: enabled ? () => onSelected(option.value) : null,
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 200),
                    height: hasIcons ? 64 : 44,
                    decoration: BoxDecoration(
                      color: option.value == selected ? (option.color ?? theme.colorScheme.primary) : Colors.transparent,
                      borderRadius: BorderRadius.circular(11),
                    ),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        if (option.icon != null) ...[
                          Icon(option.icon, size: 22, color: option.value == selected ? Colors.white : (option.color ?? theme.colorScheme.onSurfaceVariant)),
                          const SizedBox(height: 4),
                        ],
                        Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 4),
                          child: Text(
                            option.label,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              fontSize: 12,
                              fontWeight: FontWeight.w700,
                              color: option.value == selected ? Colors.white : theme.colorScheme.onSurface,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
