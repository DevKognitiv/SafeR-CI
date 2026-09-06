import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../../core/i18n.dart';
import '../../../core/theme.dart';

enum SosButtonState { idle, sending, sent }

/// Big pulsing red SOS button. Disabled while sending; turns green with a check once sent.
class SosButton extends StatefulWidget {
  const SosButton({super.key, required this.state, required this.onPressed, this.size = 200});

  final SosButtonState state;
  final VoidCallback onPressed;
  final double size;

  @override
  State<SosButton> createState() => _SosButtonState();
}

class _SosButtonState extends State<SosButton> with SingleTickerProviderStateMixin {
  late final AnimationController _pulse = AnimationController(vsync: this, duration: const Duration(milliseconds: 1800));

  @override
  void initState() {
    super.initState();
    _syncAnimation();
  }

  @override
  void didUpdateWidget(covariant SosButton oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.state != widget.state) _syncAnimation();
  }

  void _syncAnimation() {
    if (widget.state == SosButtonState.sent) {
      _pulse.stop();
      _pulse.value = 0;
    } else if (!_pulse.isAnimating) {
      _pulse.repeat();
    }
  }

  @override
  void dispose() {
    _pulse.dispose();
    super.dispose();
  }

  Color get _color => switch (widget.state) {
        SosButtonState.idle => SafeRColors.danger,
        SosButtonState.sending => SafeRColors.danger.withValues(alpha: 0.75),
        SosButtonState.sent => SafeRColors.success,
      };

  @override
  Widget build(BuildContext context) {
    final enabled = widget.state == SosButtonState.idle;
    final size = widget.size;
    final outer = size * 1.7;
    final label = switch (widget.state) {
      SosButtonState.idle => context.tr(fr: 'Bouton SOS : envoyer une alerte aux secours', en: 'SOS button: send an alert to emergency services'),
      SosButtonState.sending => context.tr(fr: 'Envoi de l\'alerte en cours', en: 'Sending the alert'),
      SosButtonState.sent => context.tr(fr: 'Alerte envoyée', en: 'Alert sent'),
    };
    return Semantics(
      button: true,
      enabled: enabled,
      label: label,
      child: SizedBox(
        width: outer,
        height: outer,
        child: Stack(
          alignment: Alignment.center,
          children: [
            AnimatedBuilder(
              animation: _pulse,
              builder: (context, _) => CustomPaint(
                size: Size.square(outer),
                painter: _PulsePainter(progress: _pulse.value, color: _color, radius: size / 2, maxRadius: outer / 2),
              ),
            ),
            Material(
              color: _color,
              shape: const CircleBorder(),
              elevation: enabled ? 10 : 2,
              shadowColor: _color.withValues(alpha: 0.6),
              child: InkWell(
                customBorder: const CircleBorder(),
                onTap: enabled ? widget.onPressed : null,
                child: SizedBox(
                  width: size,
                  height: size,
                  child: Center(child: _content(size)),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _content(double size) {
    switch (widget.state) {
      case SosButtonState.sending:
        return SizedBox(
          width: size * 0.3,
          height: size * 0.3,
          child: const CircularProgressIndicator(color: Colors.white, strokeWidth: 5),
        );
      case SosButtonState.sent:
        return Icon(Icons.check_rounded, color: Colors.white, size: size * 0.45);
      case SosButtonState.idle:
        return Text(
          'SOS',
          style: TextStyle(color: Colors.white, fontSize: size * 0.28, fontWeight: FontWeight.w900, letterSpacing: 4),
        );
    }
  }
}

/// Two expanding rings fading out, half a period apart.
class _PulsePainter extends CustomPainter {
  const _PulsePainter({required this.progress, required this.color, required this.radius, required this.maxRadius});

  final double progress;
  final Color color;
  final double radius;
  final double maxRadius;

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    for (final phase in const [0.0, 0.5]) {
      final t = (progress + phase) % 1.0;
      final eased = Curves.easeOut.transform(t);
      final r = radius + (maxRadius - radius) * eased;
      final paint = Paint()..color = color.withValues(alpha: (1 - t) * 0.35);
      canvas.drawCircle(center, r, paint);
    }
    // Static halo so the button reads as "live" even between pulses.
    canvas.drawCircle(center, radius + 10, Paint()..color = color.withValues(alpha: 0.18));
    canvas.drawCircle(center, radius + 4, Paint()..color = color.withValues(alpha: math.min(0.3, 0.3)));
  }

  @override
  bool shouldRepaint(covariant _PulsePainter oldDelegate) =>
      oldDelegate.progress != progress || oldDelegate.color != color || oldDelegate.radius != radius;
}
