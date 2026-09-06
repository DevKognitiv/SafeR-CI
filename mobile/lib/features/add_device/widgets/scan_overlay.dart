import 'package:flutter/material.dart';

import '../../../core/theme.dart';

/// Dimmed overlay with a rounded viewfinder cut-out, corner marks and a moving scan line.
class ScanOverlay extends StatefulWidget {
  const ScanOverlay({super.key});

  /// Side of the viewfinder square for a given layout size.
  static double windowSize(Size size) => (size.shortestSide * 0.68).clamp(180.0, 300.0);

  @override
  State<ScanOverlay> createState() => _ScanOverlayState();
}

class _ScanOverlayState extends State<ScanOverlay> with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(vsync: this, duration: const Duration(milliseconds: 1800))..repeat();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => IgnorePointer(
        child: AnimatedBuilder(
          animation: _controller,
          builder: (context, _) => CustomPaint(painter: _ViewfinderPainter(progress: _controller.value), size: Size.infinite),
        ),
      );
}

class _ViewfinderPainter extends CustomPainter {
  _ViewfinderPainter({required this.progress});

  final double progress;

  @override
  void paint(Canvas canvas, Size size) {
    final side = ScanOverlay.windowSize(size);
    final window = Rect.fromCenter(center: Offset(size.width / 2, size.height * 0.42), width: side, height: side);
    final rrect = RRect.fromRectAndRadius(window, const Radius.circular(20));

    final dim = Path()
      ..addRect(Offset.zero & size)
      ..addRRect(rrect)
      ..fillType = PathFillType.evenOdd;
    canvas.drawPath(dim, Paint()..color = Colors.black.withValues(alpha: 0.55));

    final corner = Paint()
      ..color = SafeRColors.primary
      ..style = PaintingStyle.stroke
      ..strokeWidth = 4
      ..strokeCap = StrokeCap.round;
    const len = 28.0;
    final l = window.left, r = window.right, t = window.top, b = window.bottom;
    for (final (start, mid, end) in [
      (Offset(l, t + len), Offset(l, t), Offset(l + len, t)),
      (Offset(r - len, t), Offset(r, t), Offset(r, t + len)),
      (Offset(l, b - len), Offset(l, b), Offset(l + len, b)),
      (Offset(r - len, b), Offset(r, b), Offset(r, b - len)),
    ]) {
      canvas.drawPath(Path()..moveTo(start.dx, start.dy)..lineTo(mid.dx, mid.dy)..lineTo(end.dx, end.dy), corner);
    }

    // Scan line bouncing top <-> bottom.
    final phase = progress < 0.5 ? progress * 2 : (1 - progress) * 2;
    final y = t + 12 + (side - 24) * phase;
    final line = Paint()
      ..shader = LinearGradient(colors: [SafeRColors.primary.withValues(alpha: 0), SafeRColors.primary, SafeRColors.primary.withValues(alpha: 0)]).createShader(Rect.fromLTWH(l, y - 1, side, 2))
      ..strokeWidth = 2;
    canvas.drawLine(Offset(l + 12, y), Offset(r - 12, y), line);
  }

  @override
  bool shouldRepaint(_ViewfinderPainter oldDelegate) => oldDelegate.progress != progress;
}
