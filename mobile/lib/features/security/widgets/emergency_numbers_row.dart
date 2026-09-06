import 'package:flutter/material.dart';

import '../../../core/config.dart';
import '../../../core/i18n.dart';
import '../../../core/theme.dart';

/// Tappable tiles for the national emergency numbers (Police 170, Pompiers 180...).
class EmergencyNumbersRow extends StatelessWidget {
  const EmergencyNumbersRow({super.key, required this.onCall});

  final ValueChanged<String> onCall;

  @override
  Widget build(BuildContext context) => Row(
        children: [
          for (final (index, n) in AppConfig.emergencyNumbers.indexed) ...[
            if (index > 0) const SizedBox(width: 10),
            Expanded(
              child: Semantics(
                button: true,
                label: context.tr(fr: 'Appeler ${n.label} au ${n.number}', en: 'Call ${n.label} at ${n.number}'),
                child: Material(
                  key: ValueKey('emergency-${n.number}'),
                  color: SafeRColors.cardDark,
                  borderRadius: BorderRadius.circular(16),
                  child: InkWell(
                    borderRadius: BorderRadius.circular(16),
                    onTap: () => onCall(n.number),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 4),
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          const Icon(Icons.phone_in_talk, color: SafeRColors.danger, size: 22),
                          const SizedBox(height: 6),
                          Text(n.number, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w800, fontSize: 18)),
                          const SizedBox(height: 2),
                          Text(n.label, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(color: Colors.white70, fontSize: 11.5)),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ],
        ],
      );
}
