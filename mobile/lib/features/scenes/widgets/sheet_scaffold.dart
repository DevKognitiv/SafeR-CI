import 'package:flutter/material.dart';

/// Rounded modal bottom sheet used by every picker of the Scenes tab.
Future<T?> showSafeRSheet<T>(BuildContext context, {required WidgetBuilder builder}) {
  final height = MediaQuery.sizeOf(context).height;
  return showModalBottomSheet<T>(
    context: context,
    isScrollControlled: true,
    useSafeArea: true,
    constraints: BoxConstraints(maxHeight: height * 0.88),
    shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
    builder: builder,
  );
}

/// Drag handle + title + body + optional primary action, keyboard aware.
class SheetScaffold extends StatelessWidget {
  const SheetScaffold({super.key, required this.title, this.subtitle, this.action, this.scrollable = true, required this.child});

  final String title;
  final String? subtitle;
  final Widget? action;

  /// When false the child manages its own scrolling (e.g. a shrink-wrapped ListView).
  final bool scrollable;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const SizedBox(height: 10),
          Center(
            child: Container(
              width: 36,
              height: 4,
              decoration: BoxDecoration(color: theme.colorScheme.outlineVariant, borderRadius: BorderRadius.circular(2)),
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 16, 20, 8),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700)),
                if (subtitle != null) ...[
                  const SizedBox(height: 4),
                  Text(subtitle!, style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
                ],
              ],
            ),
          ),
          Flexible(child: scrollable ? SingleChildScrollView(child: child) : child),
          if (action != null) Padding(padding: const EdgeInsets.fromLTRB(16, 12, 16, 16), child: action),
        ],
      ),
    );
  }
}

/// Simple choice list used for "what kind of …" steps.
class SheetOption {
  const SheetOption({required this.id, required this.icon, required this.title, this.subtitle});

  final String id;
  final IconData icon;
  final String title;
  final String? subtitle;
}

class SheetOptionList extends StatelessWidget {
  const SheetOptionList({super.key, required this.options});

  final List<SheetOption> options;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return ListView(
      shrinkWrap: true,
      padding: const EdgeInsets.only(bottom: 16),
      children: [
        for (final option in options)
          ListTile(
            minTileHeight: 56,
            leading: CircleAvatar(backgroundColor: scheme.primary.withValues(alpha: 0.12), child: Icon(option.icon, color: scheme.primary)),
            title: Text(option.title),
            subtitle: option.subtitle == null ? null : Text(option.subtitle!),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => Navigator.of(context).pop(option.id),
          ),
      ],
    );
  }
}
