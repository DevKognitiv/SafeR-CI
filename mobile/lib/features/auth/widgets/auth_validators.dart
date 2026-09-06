import 'package:flutter/widgets.dart';

import '../../../core/i18n.dart';

/// Minimum password length accepted by the hub (`RegisterIn.password`).
const int kMinPasswordLength = 6;

final RegExp _emailRegExp = RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]{2,}$');
final RegExp _phoneRegExp = RegExp(r'^\+?[0-9]{8,15}$');
final RegExp _phoneSeparators = RegExp(r'[\s.\-()]');

/// Form validators shared by the login and register screens (messages via `context.tr`).
class AuthValidators {
  AuthValidators._();

  static String? email(BuildContext context, String? value) {
    final v = value?.trim() ?? '';
    if (v.isEmpty) return context.tr(fr: 'Saisissez votre e-mail', en: 'Enter your e-mail');
    if (!_emailRegExp.hasMatch(v)) return context.tr(fr: 'Adresse e-mail invalide', en: 'Invalid e-mail address');
    return null;
  }

  /// `strict` enforces the hub minimum length (registration only).
  static String? password(BuildContext context, String? value, {bool strict = false}) {
    final v = value ?? '';
    if (v.isEmpty) return context.tr(fr: 'Saisissez votre mot de passe', en: 'Enter your password');
    if (strict && v.length < kMinPasswordLength) {
      return context.tr(fr: 'Au moins $kMinPasswordLength caractères', en: 'At least $kMinPasswordLength characters');
    }
    return null;
  }

  static String? confirmPassword(BuildContext context, String? value, String password) {
    if ((value ?? '').isEmpty) return context.tr(fr: 'Confirmez votre mot de passe', en: 'Confirm your password');
    if (value != password) return context.tr(fr: 'Les mots de passe ne correspondent pas', en: 'Passwords do not match');
    return null;
  }

  static String? name(BuildContext context, String? value) {
    final v = value?.trim() ?? '';
    if (v.isEmpty) return context.tr(fr: 'Saisissez votre nom', en: 'Enter your name');
    if (v.length < 2) return context.tr(fr: 'Nom trop court', en: 'Name is too short');
    return null;
  }

  /// Optional phone number: 8–15 digits once separators are removed.
  static String? phone(BuildContext context, String? value) {
    final v = normalizePhone(value);
    if (v == null) return null;
    if (!_phoneRegExp.hasMatch(v)) return context.tr(fr: 'Numéro de téléphone invalide', en: 'Invalid phone number');
    return null;
  }

  /// Strip separators and add the Côte d'Ivoire prefix when missing; null when empty.
  static String? normalizePhone(String? value) {
    final digits = (value ?? '').replaceAll(_phoneSeparators, '');
    if (digits.isEmpty) return null;
    if (digits.startsWith('+')) return digits;
    if (digits.startsWith('00')) return '+${digits.substring(2)}';
    return '+225$digits';
  }

  static String? hubUrl(BuildContext context, String? value) {
    final v = value?.trim() ?? '';
    if (v.isEmpty) return context.tr(fr: "Saisissez l'URL du hub", en: 'Enter the hub URL');
    final uri = Uri.tryParse(v);
    if (uri == null || (uri.scheme != 'http' && uri.scheme != 'https') || uri.host.isEmpty) {
      return context.tr(fr: 'URL invalide (ex. http://192.168.1.20:8000)', en: 'Invalid URL (e.g. http://192.168.1.20:8000)');
    }
    return null;
  }

  /// Trimmed URL without trailing slashes.
  static String normalizeHubUrl(String value) => value.trim().replaceAll(RegExp(r'/+$'), '');
}
