import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../core/i18n.dart';
import '../../../core/widgets/widgets.dart';

/// Opens the phone dialer with a number (`tel:` URI). Overridable in tests.
class PhoneDialer {
  const PhoneDialer();

  Future<bool> call(String number) async {
    try {
      return await launchUrl(Uri(scheme: 'tel', path: number));
    } catch (_) {
      return false;
    }
  }
}

final phoneDialerProvider = Provider<PhoneDialer>((_) => const PhoneDialer());

/// Dial [number] and report a failure with a snackbar.
Future<void> dialNumber(BuildContext context, WidgetRef ref, String number) async {
  final ok = await ref.read(phoneDialerProvider).call(number);
  if (!ok && context.mounted) {
    showErrorSnack(context, context.tr(fr: "Impossible d'ouvrir le téléphone pour le $number", en: 'Could not open the phone app for $number'));
  }
}
