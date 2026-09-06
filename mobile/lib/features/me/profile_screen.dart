import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/i18n.dart';
import '../../core/providers/providers.dart';
import '../../core/widgets/widgets.dart';
import 'widgets/me_common.dart';

/// Account profile: avatar, read-only e-mail, editable name, phone and account language.
class ProfileScreen extends ConsumerStatefulWidget {
  const ProfileScreen({super.key});

  @override
  ConsumerState<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends ConsumerState<ProfileScreen> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _name;
  late final TextEditingController _phone;
  late String _locale;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    final user = ref.read(authProvider).user;
    _name = TextEditingController(text: user?.name ?? '');
    _phone = TextEditingController(text: user?.phone ?? '');
    _locale = user?.locale == 'en' ? 'en' : 'fr';
  }

  @override
  void dispose() {
    _name.dispose();
    _phone.dispose();
    super.dispose();
  }

  bool get _dirty {
    final user = ref.read(authProvider).user;
    return _name.text.trim() != (user?.name ?? '') || _phone.text.trim() != (user?.phone ?? '') || _locale != (user?.locale == 'en' ? 'en' : 'fr');
  }

  Future<void> _save() async {
    if (_saving || !(_formKey.currentState?.validate() ?? false)) return;
    setState(() => _saving = true);
    try {
      await ref.read(authProvider.notifier).updateProfile(name: _name.text.trim(), phone: _phone.text.trim(), locale: _locale);
      if (!mounted) return;
      showSnack(context, context.tr(fr: 'Profil mis à jour', en: 'Profile updated'));
      Navigator.of(context).maybePop();
    } catch (e) {
      if (mounted) showErrorSnack(context, errorMessage(e));
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final muted = theme.colorScheme.onSurfaceVariant;
    final user = ref.watch(authProvider).user;
    final email = user?.email ?? '';
    return Scaffold(
      appBar: AppBar(
        title: Text(context.tr(fr: 'Mon profil', en: 'My profile')),
        actions: [
          TextButton(
            key: const Key('profile-save'),
            onPressed: _saving ? null : _save,
            child: Text(context.tr(fr: 'Enregistrer', en: 'Save')),
          ),
        ],
      ),
      body: Form(
        key: _formKey,
        onChanged: () => setState(() {}),
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
          children: [
            Center(child: InitialsAvatar(name: _name.text.trim().isEmpty ? (user?.displayName ?? '') : _name.text, email: email, radius: 44)),
            const SizedBox(height: 8),
            Center(
              child: Text(
                context.tr(fr: 'Les initiales servent d\'avatar', en: 'Initials are used as avatar'),
                style: theme.textTheme.bodySmall?.copyWith(color: muted),
              ),
            ),
            SectionHeader(title: context.tr(fr: 'Compte', en: 'Account'), padding: const EdgeInsets.fromLTRB(4, 20, 4, 8)),
            Card(
              child: ListTile(
                leading: const IconBox(icon: Icons.mail_outline, size: 36),
                title: Text(context.tr(fr: 'E-mail', en: 'E-mail')),
                subtitle: Text(email.isEmpty ? '—' : email, style: theme.textTheme.bodyMedium),
                trailing: Icon(Icons.lock_outline, size: 18, color: muted),
              ),
            ),
            const SizedBox(height: 12),
            TextFormField(
              key: const Key('profile-name'),
              controller: _name,
              textCapitalization: TextCapitalization.words,
              textInputAction: TextInputAction.next,
              decoration: InputDecoration(labelText: context.tr(fr: 'Nom complet', en: 'Full name'), prefixIcon: const Icon(Icons.person_outline)),
              validator: (v) => (v ?? '').trim().isEmpty ? context.tr(fr: 'Saisissez votre nom', en: 'Enter your name') : null,
            ),
            const SizedBox(height: 12),
            TextFormField(
              key: const Key('profile-phone'),
              controller: _phone,
              keyboardType: TextInputType.phone,
              textInputAction: TextInputAction.done,
              onFieldSubmitted: (_) => _save(),
              decoration: InputDecoration(
                labelText: context.tr(fr: 'Téléphone (facultatif)', en: 'Phone (optional)'),
                hintText: '+225 07 00 00 00 00',
                prefixIcon: const Icon(Icons.phone_outlined),
              ),
            ),
            SectionHeader(title: context.tr(fr: 'Langue du compte', en: 'Account language'), padding: const EdgeInsets.fromLTRB(4, 20, 4, 8)),
            SegmentedButton<String>(
              style: SegmentedButton.styleFrom(minimumSize: const Size(0, 44)),
              segments: [
                ButtonSegment(value: 'fr', label: Text(context.tr(fr: 'Français', en: 'French')), icon: const Icon(Icons.language)),
                ButtonSegment(value: 'en', label: Text(context.tr(fr: 'English', en: 'English')), icon: const Icon(Icons.translate)),
              ],
              selected: {_locale},
              onSelectionChanged: (selection) => setState(() => _locale = selection.first),
            ),
            const SizedBox(height: 8),
            Text(
              context.tr(fr: 'Utilisée pour les notifications et les e-mails du hub. La langue de l\'application se règle dans Paramètres.', en: 'Used for hub notifications and e-mails. The app language is set in Settings.'),
              style: theme.textTheme.bodySmall?.copyWith(color: muted),
            ),
            const SizedBox(height: 28),
            FilledButton(
              onPressed: _saving || !_dirty ? null : _save,
              child: _saving
                  ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                  : Text(context.tr(fr: 'Enregistrer', en: 'Save')),
            ),
          ],
        ),
      ),
    );
  }
}
