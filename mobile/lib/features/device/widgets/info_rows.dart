import 'package:flutter/material.dart';

/// Label / value row used for read-only state and device information.
class ValueRow extends StatelessWidget {
  const ValueRow({super.key, required this.label, this.value, this.icon, this.trailing, this.valueColor, this.onTap});

  final String label;
  final String? value;
  final IconData? icon;
  final Widget? trailing;
  final Color? valueColor;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final row = Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      child: Row(
        children: [
          if (icon != null) ...[Icon(icon, size: 20, color: theme.colorScheme.onSurfaceVariant), const SizedBox(width: 12)],
          Expanded(child: Text(label, style: theme.textTheme.bodyMedium)),
          if (value != null)
            Flexible(
              child: Text(
                value!,
                textAlign: TextAlign.end,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w600, color: valueColor ?? theme.colorScheme.onSurfaceVariant),
              ),
            ),
          if (trailing != null) ...[const SizedBox(width: 8), trailing!],
          if (onTap != null) ...[const SizedBox(width: 4), Icon(Icons.chevron_right, color: theme.colorScheme.onSurfaceVariant)],
        ],
      ),
    );
    return onTap == null ? row : InkWell(onTap: onTap, child: row);
  }
}

/// Big number with unit and caption (power, energy, humidity...).
class ReadoutTile extends StatelessWidget {
  const ReadoutTile({super.key, required this.value, required this.label, this.unit, this.icon, this.color});

  final String value;
  final String label;
  final String? unit;
  final IconData? icon;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final c = color ?? theme.colorScheme.primary;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(color: c.withValues(alpha: 0.08), borderRadius: BorderRadius.circular(12)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (icon != null) ...[Icon(icon, size: 18, color: c), const SizedBox(height: 6)],
          Text.rich(
            TextSpan(children: [
              TextSpan(text: value, style: theme.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800, color: theme.colorScheme.onSurface)),
              if (unit != null) TextSpan(text: ' $unit', style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
            ]),
          ),
          const SizedBox(height: 2),
          Text(label, style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant), maxLines: 1, overflow: TextOverflow.ellipsis),
        ],
      ),
    );
  }
}

/// Circular gauge with the value in the centre (temperature, humidity, illuminance).
class GaugeTile extends StatelessWidget {
  const GaugeTile({super.key, required this.value, required this.min, required this.max, required this.label, required this.text, this.icon, this.color});

  final double value;
  final double min;
  final double max;
  final String label;
  final String text;
  final IconData? icon;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final c = color ?? theme.colorScheme.primary;
    final progress = max > min ? ((value - min) / (max - min)).clamp(0.0, 1.0) : 0.0;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        SizedBox(
          width: 88,
          height: 88,
          child: Stack(
            alignment: Alignment.center,
            children: [
              SizedBox.expand(
                child: CircularProgressIndicator(
                    value: progress, strokeWidth: 8, color: c, backgroundColor: c.withValues(alpha: 0.15), strokeCap: StrokeCap.round),
              ),
              Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (icon != null) Icon(icon, size: 16, color: c),
                  Text(text, style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w800), textAlign: TextAlign.center),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 6),
        Text(label, style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
      ],
    );
  }
}
