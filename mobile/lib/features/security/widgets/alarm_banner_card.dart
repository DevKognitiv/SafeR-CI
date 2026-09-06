import 'package:flutter/material.dart';

import '../../../core/i18n.dart';
import '../../../core/theme.dart';

/// Red "alarm triggered" card with acknowledge and call-the-police actions.
class SecurityAlarmBanner extends StatelessWidget {
  const SecurityAlarmBanner({
    super.key,
    required this.deviceName,
    required this.policeNumber,
    required this.onAcknowledge,
    required this.onCallPolice,
    this.busy = false,
  });

  final String? deviceName;
  final String policeNumber;
  final VoidCallback onAcknowledge;
  final VoidCallback onCallPolice;
  final bool busy;

  @override
  Widget build(BuildContext context) {
    final name = deviceName;
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
      child: Card(
        color: SafeRColors.danger,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  Container(
                    width: 44,
                    height: 44,
                    decoration: BoxDecoration(color: Colors.white.withValues(alpha: 0.2), shape: BoxShape.circle),
                    child: const Icon(Icons.notifications_active, color: Colors.white),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          context.tr(fr: '🚨 Alarme déclenchée', en: '🚨 Alarm triggered'),
                          style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w800, fontSize: 17),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          name == null || name.isEmpty
                              ? context.tr(fr: 'Un capteur de votre maison a déclenché l\'alarme.', en: 'A sensor in your home triggered the alarm.')
                              : context.tr(fr: 'Déclenchée par : $name', en: 'Triggered by: $name'),
                          style: const TextStyle(color: Colors.white, fontSize: 13),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 14),
              FilledButton.icon(
                onPressed: busy ? null : onAcknowledge,
                style: FilledButton.styleFrom(backgroundColor: Colors.white, foregroundColor: SafeRColors.danger),
                icon: const Icon(Icons.check),
                label: Text(context.tr(fr: 'Acquitter', en: 'Acknowledge')),
              ),
              const SizedBox(height: 8),
              OutlinedButton.icon(
                onPressed: onCallPolice,
                style: OutlinedButton.styleFrom(
                  minimumSize: const Size.fromHeight(48),
                  foregroundColor: Colors.white,
                  side: const BorderSide(color: Colors.white70),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                ),
                icon: const Icon(Icons.phone),
                label: Text(context.tr(fr: 'Appeler la police $policeNumber', en: 'Call the police $policeNumber')),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
