import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../core/api/api_exception.dart';
import '../../../core/i18n.dart';
import '../../../core/routes.dart';
import '../../../core/theme.dart';
import '../../../core/widgets/widgets.dart';

/// Project page opened by "Aide & FAQ" and the about screen.
const String kSafeRRepoUrl = 'https://github.com/DevKognitiv/SafeR-CI';

/// Issue tracker linked from the about screen.
const String kSafeRIssuesUrl = '$kSafeRRepoUrl/issues';

/// Opens external links in the browser. Overridable in tests.
class LinkOpener {
  const LinkOpener();

  Future<bool> open(Uri uri) async {
    try {
      return await launchUrl(uri, mode: LaunchMode.externalApplication);
    } catch (_) {
      return false;
    }
  }
}

final linkOpenerProvider = Provider<LinkOpener>((_) => const LinkOpener());

/// Open [url] and report a failure with a snackbar.
Future<void> openExternalLink(BuildContext context, WidgetRef ref, String url) async {
  final ok = await ref.read(linkOpenerProvider).open(Uri.parse(url));
  if (!ok && context.mounted) {
    showErrorSnack(context, context.tr(fr: "Impossible d'ouvrir le lien", en: 'Could not open the link'));
  }
}

/// Initials for an avatar ("Alice Kouassi" -> "AK", "bob@safer.ci" -> "B").
String initialsFor(String name, [String email = '']) {
  final source = name.trim().isNotEmpty ? name.trim() : email.split('@').first.trim();
  if (source.isEmpty) return '?';
  final parts = source.split(RegExp(r'[\s._\-]+')).where((p) => p.isNotEmpty).toList();
  if (parts.length >= 2) return '${parts[0][0]}${parts[1][0]}'.toUpperCase();
  return source[0].toUpperCase();
}

const List<Color> _avatarPalette = [
  SafeRColors.primary,
  Color(0xFF7C3AED),
  Color(0xFF0891B2),
  Color(0xFFDB2777),
  SafeRColors.success,
  SafeRColors.warning,
];

/// Deterministic accent colour for an avatar.
Color avatarColorFor(String seed) {
  var hash = 0;
  for (final unit in seed.codeUnits) {
    hash = (hash * 31 + unit) & 0x7fffffff;
  }
  return _avatarPalette[hash % _avatarPalette.length];
}

/// Round avatar showing the initials of a person.
class InitialsAvatar extends StatelessWidget {
  const InitialsAvatar({super.key, required this.name, this.email = '', this.radius = 22});

  final String name;
  final String email;
  final double radius;

  @override
  Widget build(BuildContext context) {
    final color = avatarColorFor(email.isNotEmpty ? email : name);
    return CircleAvatar(
      radius: radius,
      backgroundColor: color.withValues(alpha: 0.16),
      child: Text(
        initialsFor(name, email),
        style: TextStyle(color: color, fontWeight: FontWeight.w700, fontSize: radius * 0.8),
      ),
    );
  }
}

/// Human label for a home role.
String roleLabel(BuildContext context, String role) {
  switch (role) {
    case 'owner':
      return context.tr(fr: 'Propriétaire', en: 'Owner');
    case 'admin':
      return context.tr(fr: 'Administrateur', en: 'Admin');
    default:
      return context.tr(fr: 'Membre', en: 'Member');
  }
}

Color roleColor(String role) {
  switch (role) {
    case 'owner':
      return SafeRColors.warning;
    case 'admin':
      return SafeRColors.primary;
    default:
      return const Color(0xFF64748B);
  }
}

IconData roleIcon(String role) {
  switch (role) {
    case 'owner':
      return Icons.star_rounded;
    case 'admin':
      return Icons.admin_panel_settings_outlined;
    default:
      return Icons.person_outline;
  }
}

/// Small chip showing a member role.
class RoleChip extends StatelessWidget {
  const RoleChip({super.key, required this.role});

  final String role;

  @override
  Widget build(BuildContext context) => StateChip(label: roleLabel(context, role), color: roleColor(role), icon: roleIcon(role));
}

/// Parse a `#RRGGBB` / `#AARRGGBB` hex string sent by the hub (BrandInfo.color).
Color colorFromHex(String? hex, {Color fallback = SafeRColors.primary}) {
  if (hex == null) return fallback;
  var value = hex.trim().replaceFirst('#', '').replaceFirst('0x', '');
  if (value.length == 3) value = value.split('').map((c) => '$c$c').join();
  if (value.length == 6) value = 'FF$value';
  if (value.length != 8) return fallback;
  final parsed = int.tryParse(value, radix: 16);
  return parsed == null ? fallback : Color(parsed);
}

/// Message of an exception without the `ApiException(...)` prefix.
String errorMessage(Object error) {
  if (error is ApiException) return error.message;
  return error.toString().replaceFirst(RegExp(r'^ApiException\([^)]*\): '), '');
}

/// Yes/no confirmation dialog. Resolves to true when confirmed.
Future<bool> confirmDialog(
  BuildContext context, {
  required String title,
  String? message,
  required String confirmLabel,
  bool destructive = false,
}) async {
  final result = await showDialog<bool>(
    context: context,
    builder: (dialogContext) => AlertDialog(
      title: Text(title),
      content: message == null ? null : Text(message),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(dialogContext).pop(false),
          child: Text(dialogContext.tr(fr: 'Annuler', en: 'Cancel')),
        ),
        FilledButton(
          style: FilledButton.styleFrom(
            minimumSize: const Size(88, 44),
            backgroundColor: destructive ? SafeRColors.danger : null,
          ),
          onPressed: () => Navigator.of(dialogContext).pop(true),
          child: Text(confirmLabel),
        ),
      ],
    ),
  );
  return result ?? false;
}

/// Empty state shown by screens that need a current home.
class NoHomeView extends StatelessWidget {
  const NoHomeView({super.key});

  @override
  Widget build(BuildContext context) => EmptyState(
        icon: Icons.home_work_outlined,
        title: context.tr(fr: 'Aucune maison', en: 'No home yet'),
        subtitle: context.tr(fr: 'Créez une maison pour gérer vos appareils, vos membres et vos messages.', en: 'Create a home to manage your devices, members and messages.'),
        actionLabel: context.tr(fr: 'Créer une maison', en: 'Create a home'),
        onAction: () => context.push(Routes.homes),
      );
}

/// Tuya-style grouped list: a card whose rows are separated by thin dividers.
class GroupedCard extends StatelessWidget {
  const GroupedCard({super.key, required this.children, this.dividerIndent = 56});

  final List<Widget> children;
  final double dividerIndent;

  @override
  Widget build(BuildContext context) => Card(
        clipBehavior: Clip.antiAlias,
        child: Column(
          children: [
            for (var i = 0; i < children.length; i++) ...[
              if (i > 0) Divider(height: 1, indent: dividerIndent),
              children[i],
            ],
          ],
        ),
      );
}

/// Rounded icon box used as a leading widget in lists and tiles.
class IconBox extends StatelessWidget {
  const IconBox({super.key, required this.icon, this.color, this.size = 40});

  final IconData icon;
  final Color? color;
  final double size;

  @override
  Widget build(BuildContext context) {
    final c = color ?? Theme.of(context).colorScheme.primary;
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(color: c.withValues(alpha: 0.14), borderRadius: BorderRadius.circular(size * 0.3)),
      child: Icon(icon, color: c, size: size * 0.55),
    );
  }
}

/// Plural-aware count labels shared by the Me screens.
String membersLabel(BuildContext context, int count) =>
    context.tr(fr: count == 1 ? '1 membre' : '$count membres', en: count == 1 ? '1 member' : '$count members');

String devicesLabel(BuildContext context, int count) =>
    context.tr(fr: count == 1 ? '1 appareil' : '$count appareils', en: count == 1 ? '1 device' : '$count devices');
