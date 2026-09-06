import 'package:flutter/material.dart';

import '../../../core/i18n.dart';
import '../../../core/theme.dart';

/// Prominent SafeR CI SOS entry point at the bottom of the Security tab.
class SosCard extends StatelessWidget {
  const SosCard({super.key, required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.fromLTRB(16, 20, 16, 8),
        child: Semantics(
          button: true,
          label: context.tr(fr: 'Ouvrir l\'écran SOS', en: 'Open the SOS screen'),
          child: Material(
            key: const Key('sos-card'),
            borderRadius: BorderRadius.circular(16),
            clipBehavior: Clip.antiAlias,
            child: Ink(
              decoration: const BoxDecoration(
                gradient: LinearGradient(begin: Alignment.topLeft, end: Alignment.bottomRight, colors: [Color(0xFFB91C1C), SafeRColors.danger]),
              ),
              child: InkWell(
                onTap: onTap,
                child: Padding(
                  padding: const EdgeInsets.all(18),
                  child: Row(
                    children: [
                      Container(
                        width: 60,
                        height: 60,
                        decoration: BoxDecoration(color: Colors.white.withValues(alpha: 0.18), shape: BoxShape.circle, border: Border.all(color: Colors.white54, width: 2)),
                        child: const Center(child: Text('SOS', style: TextStyle(color: Colors.white, fontWeight: FontWeight.w900, fontSize: 18, letterSpacing: 1.5))),
                      ),
                      const SizedBox(width: 16),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(context.tr(fr: 'Urgence ? Appuyez ici', en: 'Emergency? Tap here'), style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w800, fontSize: 17)),
                            const SizedBox(height: 4),
                            Text(
                              context.tr(fr: 'Alerte immédiate aux secours et à vos proches, avec votre position.', en: 'Instantly alert emergency services and your contacts, with your location.'),
                              style: const TextStyle(color: Colors.white70, fontSize: 12.5),
                            ),
                          ],
                        ),
                      ),
                      const Icon(Icons.chevron_right, color: Colors.white),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      );
}
