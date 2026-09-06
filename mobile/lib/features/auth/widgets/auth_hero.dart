import 'package:flutter/material.dart';

import '../../../core/config.dart';
import '../../../core/i18n.dart';
import '../../../core/theme.dart';

/// Dark branded header shared by the auth screens: logo, wordmark and tagline.
class AuthHero extends StatelessWidget {
  const AuthHero({super.key, required this.tagline, this.onBack, this.compact = false});

  final String tagline;

  /// When set, a back arrow is shown in the top-left corner.
  final VoidCallback? onBack;

  /// Smaller variant for screens with long forms.
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final logoSize = compact ? 56.0 : 76.0;
    return Container(
      width: double.infinity,
      decoration: const BoxDecoration(
        color: SafeRColors.surfaceDark,
        borderRadius: BorderRadius.vertical(bottom: Radius.circular(28)),
      ),
      child: SafeArea(
        bottom: false,
        child: Stack(
          children: [
            Padding(
              padding: EdgeInsets.fromLTRB(24, compact ? 40 : 48, 24, compact ? 28 : 36),
              child: Column(
                children: [
                  Container(
                    width: logoSize,
                    height: logoSize,
                    decoration: BoxDecoration(
                      color: SafeRColors.primary,
                      borderRadius: BorderRadius.circular(logoSize * 0.3),
                      boxShadow: [BoxShadow(color: SafeRColors.primary.withValues(alpha: 0.4), blurRadius: 24, offset: const Offset(0, 8))],
                    ),
                    child: Icon(Icons.shield, color: Colors.white, size: logoSize * 0.6),
                  ),
                  const SizedBox(height: 16),
                  Text(
                    AppConfig.appName,
                    style: TextStyle(color: Colors.white, fontSize: compact ? 26 : 32, fontWeight: FontWeight.w800, letterSpacing: 2),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    tagline,
                    textAlign: TextAlign.center,
                    style: TextStyle(color: Colors.white.withValues(alpha: 0.72), fontSize: 14, fontWeight: FontWeight.w500),
                  ),
                ],
              ),
            ),
            if (onBack != null)
              Positioned(
                left: 4,
                top: 4,
                child: IconButton(
                  onPressed: onBack,
                  tooltip: context.tr(fr: 'Retour', en: 'Back'),
                  icon: const Icon(Icons.arrow_back, color: Colors.white),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
