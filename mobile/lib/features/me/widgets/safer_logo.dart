import 'package:flutter/material.dart';

import '../../../core/theme.dart';

/// SafeR mark: a rounded blue tile with a shield, drawn with widgets (no asset needed).
class SafeRLogo extends StatelessWidget {
  const SafeRLogo({super.key, this.size = 88});

  final double size;

  @override
  Widget build(BuildContext context) => Semantics(
        label: 'SafeR',
        image: true,
        child: Container(
          width: size,
          height: size,
          decoration: BoxDecoration(
            gradient: const LinearGradient(begin: Alignment.topLeft, end: Alignment.bottomRight, colors: [SafeRColors.primary, SafeRColors.primaryDark]),
            borderRadius: BorderRadius.circular(size * 0.28),
            boxShadow: [BoxShadow(color: SafeRColors.primary.withValues(alpha: 0.35), blurRadius: size * 0.25, offset: Offset(0, size * 0.1))],
          ),
          child: Icon(Icons.shield_rounded, color: Colors.white, size: size * 0.55),
        ),
      );
}
