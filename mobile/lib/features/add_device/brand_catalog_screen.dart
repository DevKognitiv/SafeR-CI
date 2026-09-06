import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/i18n.dart';
import '../../core/models/brand.dart';
import '../../core/providers/providers.dart';
import '../../core/router.dart';
import '../../core/widgets/widgets.dart';
import 'widgets/brand_card.dart';
import 'widgets/category_grid.dart';
import 'widgets/scan_card.dart';

bool _matches(String query, Iterable<String> haystack) {
  final q = query.trim().toLowerCase();
  if (q.isEmpty) return true;
  return haystack.any((s) => s.toLowerCase().contains(q));
}

/// Brands matching [query] and, when set, supporting [categoryId].
List<BrandInfo> filterBrands(List<BrandInfo> brands, {String query = '', String? categoryId, List<CategoryGroup> groups = const []}) {
  final categoryBrands = <String>{};
  if (categoryId != null) {
    for (final group in groups) {
      for (final category in group.categories) {
        if (category.id == categoryId) categoryBrands.addAll(category.brands);
      }
    }
  }
  return brands.where((b) {
    if (categoryId != null && !categoryBrands.contains(b.id) && !b.categories.contains(categoryId)) return false;
    return _matches(query, [b.name, b.vendor, b.id, b.description, ...b.protocols]);
  }).toList();
}

/// Categories of [groupId] (or of every group when a query is typed).
List<DeviceCategoryInfo> filterCategories(List<CategoryGroup> groups, {String query = '', String? groupId}) {
  final searching = query.trim().isNotEmpty;
  return [
    for (final group in groups)
      if (searching || groupId == null || group.id == groupId)
        for (final category in group.categories)
          if (_matches(query, [category.name, category.nameEn, category.id, group.name, group.nameEn])) category,
  ];
}

/// Tuya-style "Add device" catalogue: search, QR scan, category grid and brand list.
class BrandCatalogScreen extends ConsumerStatefulWidget {
  const BrandCatalogScreen({super.key});

  @override
  ConsumerState<BrandCatalogScreen> createState() => _BrandCatalogScreenState();
}

class _BrandCatalogScreenState extends ConsumerState<BrandCatalogScreen> {
  final _search = TextEditingController();
  String _query = '';
  String? _groupId;
  String? _categoryId;

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  void _clearFilters() {
    _search.clear();
    setState(() {
      _query = '';
      _categoryId = null;
    });
  }

  DeviceCategoryInfo? _category(List<CategoryGroup> groups, String? id) {
    if (id == null) return null;
    for (final group in groups) {
      for (final category in group.categories) {
        if (category.id == id) return category;
      }
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final brandsAsync = ref.watch(brandsProvider);
    final categoriesAsync = ref.watch(categoriesProvider);
    final groups = categoriesAsync.value ?? const <CategoryGroup>[];
    final brandNames = {for (final b in brandsAsync.value ?? const <BrandInfo>[]) b.id: b.name};
    final selectedCategory = _category(groups, _categoryId);

    return Scaffold(
      appBar: AppBar(
        title: Text(context.tr(fr: 'Ajouter un appareil', en: 'Add device')),
        actions: [
          IconButton(
            tooltip: context.tr(fr: 'Scanner un code', en: 'Scan a code'),
            icon: const Icon(Icons.qr_code_scanner),
            onPressed: () => context.push(Routes.scan),
          ),
        ],
      ),
      body: CustomScrollView(
        slivers: [
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
              child: TextField(
                controller: _search,
                textInputAction: TextInputAction.search,
                onChanged: (value) => setState(() => _query = value),
                decoration: InputDecoration(
                  hintText: context.tr(fr: 'Rechercher une marque ou un appareil', en: 'Search a brand or a device'),
                  prefixIcon: const Icon(Icons.search),
                  suffixIcon: _query.isEmpty
                      ? null
                      : IconButton(
                          tooltip: context.tr(fr: 'Effacer', en: 'Clear'),
                          icon: const Icon(Icons.close),
                          onPressed: _clearFilters,
                        ),
                ),
              ),
            ),
          ),
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
              child: ScanQrCard(onTap: () => context.push(Routes.scan)),
            ),
          ),
          SliverToBoxAdapter(child: SectionHeader(title: context.tr(fr: 'Ajouter manuellement', en: 'Add manually'))),
          ..._categorySlivers(context, categoriesAsync, brandNames),
          SliverToBoxAdapter(
            child: SectionHeader(
              title: context.tr(fr: 'Marques', en: 'Brands'),
              trailing: selectedCategory == null
                  ? null
                  : InputChip(
                      avatar: Icon(iconFromName(selectedCategory.icon, fallback: categoryIcon(selectedCategory.id)), size: 16),
                      label: Text(categoryInfoName(context, selectedCategory)),
                      deleteButtonTooltipMessage: context.tr(fr: 'Retirer le filtre', en: 'Remove filter'),
                      onDeleted: () => setState(() => _categoryId = null),
                    ),
            ),
          ),
          ..._brandSlivers(context, brandsAsync, groups),
          const SliverPadding(padding: EdgeInsets.only(bottom: 32)),
        ],
      ),
    );
  }

  List<Widget> _categorySlivers(BuildContext context, AsyncValue<List<CategoryGroup>> async, Map<String, String> brandNames) {
    return async.when(
      loading: () => const [SliverToBoxAdapter(child: SizedBox(height: 140, child: LoadingView()))],
      error: (error, _) => [SliverToBoxAdapter(child: ErrorView(error: error, onRetry: () => ref.invalidate(categoriesProvider)))],
      data: (groups) {
        if (groups.isEmpty) return const [];
        final searching = _query.trim().isNotEmpty;
        final groupId = _groupId != null && groups.any((g) => g.id == _groupId) ? _groupId! : groups.first.id;
        final categories = filterCategories(groups, query: _query, groupId: searching ? null : groupId);
        return [
          if (!searching)
            SliverToBoxAdapter(
              child: CategoryGroupChips(groups: groups, selectedId: groupId, onSelected: (id) => setState(() => _groupId = id)),
            ),
          if (categories.isEmpty)
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
                child: Text(
                  context.tr(fr: 'Aucune catégorie ne correspond à votre recherche', en: 'No category matches your search'),
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(color: Theme.of(context).colorScheme.onSurfaceVariant),
                ),
              ),
            )
          else
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
              sliver: SliverGrid(
                gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(crossAxisCount: 3, mainAxisSpacing: 10, crossAxisSpacing: 10, childAspectRatio: 0.86),
                delegate: SliverChildBuilderDelegate(
                  (context, index) {
                    final category = categories[index];
                    final names = [for (final id in category.brands) brandNames[id] ?? id];
                    return CategoryTile(
                      category: category,
                      brandNames: names,
                      selected: category.id == _categoryId,
                      onTap: () => setState(() => _categoryId = _categoryId == category.id ? null : category.id),
                    );
                  },
                  childCount: categories.length,
                ),
              ),
            ),
        ];
      },
    );
  }

  List<Widget> _brandSlivers(BuildContext context, AsyncValue<List<BrandInfo>> async, List<CategoryGroup> groups) {
    return async.when(
      loading: () => const [SliverToBoxAdapter(child: SizedBox(height: 140, child: LoadingView()))],
      error: (error, _) => [SliverToBoxAdapter(child: ErrorView(error: error, onRetry: () => ref.invalidate(brandsProvider)))],
      data: (brands) {
        final filtered = filterBrands(brands, query: _query, categoryId: _categoryId, groups: groups);
        if (filtered.isEmpty) {
          return [
            SliverToBoxAdapter(
              child: EmptyState(
                icon: Icons.search_off,
                title: context.tr(fr: 'Aucune marque trouvée', en: 'No brand found'),
                subtitle: context.tr(fr: 'Essayez un autre mot-clé ou scannez le code QR de l\'appareil.', en: 'Try another keyword or scan the device QR code.'),
                actionLabel: context.tr(fr: 'Effacer les filtres', en: 'Clear filters'),
                onAction: _clearFilters,
              ),
            ),
          ];
        }
        return [
          SliverPadding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            sliver: SliverList.separated(
              itemCount: filtered.length,
              separatorBuilder: (_, __) => const SizedBox(height: 10),
              itemBuilder: (context, index) {
                final brand = filtered[index];
                return BrandCard(brand: brand, onTap: () => context.push(Routes.pair(brand.id)));
              },
            ),
          ),
        ];
      },
    );
  }
}
