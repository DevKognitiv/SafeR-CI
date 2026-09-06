import 'package:flutter/material.dart';

import '../../../core/api/api_exception.dart';
import '../../../core/i18n.dart';
import '../../../core/theme.dart';

/// Normalised hub error code for an error (falls back on the HTTP status).
String? pairingErrorCode(Object error) {
  if (error is! ApiException) return null;
  if (error.code != null && error.code!.isNotEmpty) return error.code;
  switch (error.status) {
    case null:
    case 502:
    case 503:
    case 504:
      return 'unreachable';
    case 401:
      return 'auth_failed';
    case 400:
    case 422:
      return 'invalid_input';
    case 404:
      return 'not_found';
    case 501:
      return 'unsupported';
    default:
      return null;
  }
}

/// Human hint for a pairing failure, tailored to the hub's error code.
String? pairingErrorHint(BuildContext context, Object error) {
  switch (pairingErrorCode(error)) {
    case 'unreachable':
      return context.tr(
        fr: "Vérifiez l'adresse IP et le port, et assurez-vous que l'appareil est allumé et sur le même réseau que le hub SafeR.",
        en: 'Check the IP address and port, and make sure the device is powered on and on the same network as the SafeR hub.',
      );
    case 'auth_failed':
      return context.tr(
        fr: "Vérifiez le nom d'utilisateur et le mot de passe de l'appareil (ou les identifiants du compte).",
        en: 'Check the device username and password (or the account credentials).',
      );
    case 'invalid_input':
      return context.tr(fr: 'Vérifiez les informations saisies.', en: 'Check the information you entered.');
    case 'not_found':
      return context.tr(fr: "L'appareil est introuvable. Vérifiez son identifiant ou relancez la recherche.", en: 'The device could not be found. Check its identifier or search again.');
    case 'unsupported':
      return context.tr(fr: "Cette méthode n'est pas encore prise en charge par le hub.", en: 'This method is not supported by the hub yet.');
    default:
      return null;
  }
}

/// Message of any error without the `ApiException(...)` prefix.
String pairingErrorMessage(Object error) => error is ApiException ? error.message : error.toString().replaceFirst(RegExp(r'^\w+Exception[^:]*: '), '');

/// Inline error card with the hub's message, a tailored hint and retry/edit actions.
class PairingErrorCard extends StatelessWidget {
  const PairingErrorCard({super.key, required this.error, required this.onRetry, this.onEdit});

  final Object error;
  final VoidCallback onRetry;
  final VoidCallback? onEdit;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final hint = pairingErrorHint(context, error);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Container(
                  width: 40,
                  height: 40,
                  decoration: BoxDecoration(color: SafeRColors.danger.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(12)),
                  child: const Icon(Icons.error_outline, color: SafeRColors.danger),
                ),
                const SizedBox(width: 12),
                Expanded(child: Text(context.tr(fr: "Échec de l'ajout", en: 'Pairing failed'), style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700))),
              ],
            ),
            const SizedBox(height: 12),
            Text(pairingErrorMessage(error), style: theme.textTheme.bodyMedium),
            if (hint != null) ...[
              const SizedBox(height: 12),
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(color: SafeRColors.warning.withValues(alpha: 0.10), borderRadius: BorderRadius.circular(12)),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(Icons.lightbulb_outline, size: 20, color: SafeRColors.warning),
                    const SizedBox(width: 8),
                    Expanded(child: Text(hint, style: theme.textTheme.bodySmall)),
                  ],
                ),
              ),
            ],
            const SizedBox(height: 16),
            FilledButton.icon(onPressed: onRetry, icon: const Icon(Icons.refresh), label: Text(context.tr(fr: 'Réessayer', en: 'Retry'))),
            if (onEdit != null) TextButton(onPressed: onEdit, child: Text(context.tr(fr: 'Modifier les informations', en: 'Edit the information'))),
          ],
        ),
      ),
    );
  }
}
