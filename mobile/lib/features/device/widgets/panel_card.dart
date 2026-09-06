import 'package:flutter/material.dart';

/// Rounded card used by every panel section (16px radius, generous padding).
class PanelCard extends StatelessWidget {
  const PanelCard({super.key, required this.child, this.title, this.trailing, this.padding = const EdgeInsets.all(16), this.color});

  final Widget child;
  final String? title;
  final Widget? trailing;
  final EdgeInsets padding;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      color: color,
      child: Padding(
        padding: padding,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (title != null) ...[
              Row(
                children: [
                  Expanded(child: Text(title!, style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700))),
                  if (trailing != null) trailing!,
                ],
              ),
              const SizedBox(height: 12),
            ],
            child,
          ],
        ),
      ),
    );
  }
}
