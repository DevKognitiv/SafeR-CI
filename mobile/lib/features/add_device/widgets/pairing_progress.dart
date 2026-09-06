import 'package:flutter/material.dart';

import '../../../core/i18n.dart';
import '../../../core/models/brand.dart';
import '../../../core/widgets/widgets.dart';
import 'brand_color.dart';

/// "Connecting…" view with a pulsing brand icon.
class PairingProgressView extends StatefulWidget {
  const PairingProgressView({super.key, required this.brand});

  final BrandInfo brand;

  @override
  State<PairingProgressView> createState() => _PairingProgressViewState();
}

class _PairingProgressViewState extends State<PairingProgressView> with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(vsync: this, duration: const Duration(milliseconds: 900))..repeat(reverse: true);
  late final Animation<double> _scale = Tween<double>(begin: 0.88, end: 1.08).animate(CurvedAnimation(parent: _controller, curve: Curves.easeInOut));

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final color = colorFromHex(widget.brand.color);
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ScaleTransition(
              scale: _scale,
              child: Container(
                width: 112,
                height: 112,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: color.withValues(alpha: 0.14),
                  boxShadow: [BoxShadow(color: color.withValues(alpha: 0.25), blurRadius: 32, spreadRadius: 4)],
                ),
                child: Icon(iconFromName(widget.brand.icon, fallback: Icons.devices), size: 52, color: color),
              ),
            ),
            const SizedBox(height: 32),
            Text(context.tr(fr: "Connexion à l'appareil...", en: 'Connecting to the device...'), style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700), textAlign: TextAlign.center),
            const SizedBox(height: 8),
            Text(
              context.tr(fr: "Cela peut prendre jusqu'à une minute. Gardez l'appareil allumé et à proximité.", en: 'This can take up to a minute. Keep the device powered on and nearby.'),
              style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }
}
