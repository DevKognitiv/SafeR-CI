import 'package:flutter/material.dart';

import '../../../core/theme.dart';
import 'me_common.dart';

/// One entry of the quick-access grid on the Me tab.
class QuickAction {
  const QuickAction({required this.icon, required this.label, required this.onTap, this.badge = 0, this.color});

  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final int badge;
  final Color? color;
}

/// 2-column grid of quick actions (home management, messages, integrations, settings).
class QuickGrid extends StatelessWidget {
  const QuickGrid({super.key, required this.items});

  final List<QuickAction> items;

  @override
  Widget build(BuildContext context) => GridView.count(
        crossAxisCount: 2,
        shrinkWrap: true,
        physics: const NeverScrollableScrollPhysics(),
        childAspectRatio: 2.2,
        mainAxisSpacing: 12,
        crossAxisSpacing: 12,
        children: [for (final item in items) _QuickTile(item: item)],
      );
}

class _QuickTile extends StatelessWidget {
  const _QuickTile({required this.item});

  final QuickAction item;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: item.onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          child: Row(
            children: [
              Badge(
                isLabelVisible: item.badge > 0,
                backgroundColor: SafeRColors.danger,
                label: Text('${item.badge}'),
                child: IconBox(icon: item.icon, color: item.color),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  item.label,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w600),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
