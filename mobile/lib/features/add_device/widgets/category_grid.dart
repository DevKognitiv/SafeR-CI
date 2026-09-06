import 'package:flutter/material.dart';

import '../../../core/i18n.dart';
import '../../../core/models/brand.dart';
import '../../../core/theme.dart';
import '../../../core/widgets/widgets.dart';

/// Localised name of a category group.
String categoryGroupName(BuildContext context, CategoryGroup group) => context.isEnglish ? group.nameEn : group.name;

/// Localised name of a category entry of the "add manually" catalogue.
String categoryInfoName(BuildContext context, DeviceCategoryInfo category) => context.isEnglish ? category.nameEn : category.name;

/// Horizontal chips of category groups (Électrique, Éclairage, Capteurs…).
class CategoryGroupChips extends StatelessWidget {
  const CategoryGroupChips({super.key, required this.groups, required this.selectedId, required this.onSelected});

  final List<CategoryGroup> groups;
  final String? selectedId;
  final ValueChanged<String> onSelected;

  @override
  Widget build(BuildContext context) => SizedBox(
        height: 48,
        child: SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: Row(
            children: [
              for (var i = 0; i < groups.length; i++) ...[
                if (i > 0) const SizedBox(width: 8),
                _GroupChip(group: groups[i], selected: groups[i].id == selectedId, onSelected: () => onSelected(groups[i].id)),
              ],
            ],
          ),
        ),
      );
}

class _GroupChip extends StatelessWidget {
  const _GroupChip({required this.group, required this.selected, required this.onSelected});

  final CategoryGroup group;
  final bool selected;
  final VoidCallback onSelected;

  @override
  Widget build(BuildContext context) => ChoiceChip(
        avatar: Icon(iconFromName(group.icon, fallback: Icons.category), size: 18, color: selected ? SafeRColors.primary : null),
        label: Text(categoryGroupName(context, group)),
        selected: selected,
        showCheckmark: false,
        onSelected: (_) => onSelected(),
      );
}

/// One category of the grid, listing the brands that support it.
class CategoryTile extends StatelessWidget {
  const CategoryTile({super.key, required this.category, required this.brandNames, this.selected = false, this.onTap});

  final DeviceCategoryInfo category;
  final List<String> brandNames;
  final bool selected;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final accent = selected ? SafeRColors.primary : theme.colorScheme.onSurfaceVariant;
    final brands = brandNames.isEmpty ? context.tr(fr: 'Aucune marque', en: 'No brand') : brandNames.join(' · ');
    return Card(
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: selected ? const BorderSide(color: SafeRColors.primary, width: 1.5) : BorderSide.none,
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(8, 12, 8, 10),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(color: accent.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(12)),
                child: Icon(iconFromName(category.icon, fallback: categoryIcon(category.id)), color: accent, size: 22),
              ),
              const SizedBox(height: 8),
              Text(
                categoryInfoName(context, category),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                textAlign: TextAlign.center,
                style: theme.textTheme.labelMedium?.copyWith(fontWeight: FontWeight.w600, height: 1.15),
              ),
              const SizedBox(height: 4),
              Text(
                brands,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                textAlign: TextAlign.center,
                style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant, fontSize: 10.5),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
