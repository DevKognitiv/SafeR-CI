import 'package:flutter/material.dart';

import '../i18n.dart';
import '../../features/device/widgets/stream_player.dart';

/// Camera surface of the demo build: a deterministic synthetic frame (no
/// network image, no media player) with the state chips the real surface
/// shows, so the camera panel can be reviewed from a capture.
class DemoCameraSurface extends StatelessWidget {
  const DemoCameraSurface({super.key, required this.request});

  final CameraSurfaceRequest request;

  @override
  Widget build(BuildContext context) {
    final info = request.info;
    final label = request.snapshotOnly
        ? context.tr(fr: 'Aperçu hub', en: 'Hub snapshot')
        : info == null
            ? context.tr(fr: 'Flux indisponible', en: 'Stream unavailable')
            : '${info.type.toUpperCase()} · ${context.tr(fr: 'Démo', en: 'Demo')}';
    return Stack(
      fit: StackFit.expand,
      children: [
        const DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(begin: Alignment.topCenter, end: Alignment.bottomCenter, colors: [Color(0xFF334155), Color(0xFF0F172A)]),
          ),
        ),
        CustomPaint(painter: const _DemoScenePainter()),
        Positioned(
          left: 12,
          top: 12,
          child: DecoratedBox(
            decoration: BoxDecoration(color: Colors.black54, borderRadius: BorderRadius.circular(8)),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.fiber_manual_record, color: Color(0xFFDC2626), size: 10),
                  const SizedBox(width: 6),
                  Text(label, style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.w600)),
                ],
              ),
            ),
          ),
        ),
        if (request.loading) const Center(child: Icon(Icons.hourglass_top, color: Colors.white54, size: 36)),
      ],
    );
  }
}

/// A doorway, a floor line and a parked scooter drawn with flat shapes: enough
/// for a reviewer to tell "camera image" from "black box".
class _DemoScenePainter extends CustomPainter {
  const _DemoScenePainter();

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width;
    final h = size.height;
    final floor = Paint()..color = const Color(0xFF1E293B);
    canvas.drawRect(Rect.fromLTWH(0, h * 0.68, w, h * 0.32), floor);
    final wall = Paint()..color = const Color(0xFF475569);
    canvas.drawRect(Rect.fromLTWH(w * 0.38, h * 0.18, w * 0.24, h * 0.5), wall);
    final door = Paint()..color = const Color(0xFF94A3B8);
    canvas.drawRect(Rect.fromLTWH(w * 0.42, h * 0.22, w * 0.16, h * 0.46), door);
    final handle = Paint()..color = const Color(0xFFE2E8F0);
    canvas.drawCircle(Offset(w * 0.55, h * 0.47), w * 0.008, handle);
    final light = Paint()..color = const Color(0x33FDE68A);
    canvas.drawCircle(Offset(w * 0.5, h * 0.1), w * 0.07, light);
    final body = Paint()..color = const Color(0xFF64748B);
    canvas.drawRRect(RRect.fromRectAndRadius(Rect.fromLTWH(w * 0.12, h * 0.58, w * 0.16, h * 0.08), const Radius.circular(6)), body);
    final wheel = Paint()..color = const Color(0xFF0F172A);
    canvas.drawCircle(Offset(w * 0.15, h * 0.7), w * 0.025, wheel);
    canvas.drawCircle(Offset(w * 0.26, h * 0.7), w * 0.025, wheel);
    final line = Paint()
      ..color = const Color(0xFF334155)
      ..strokeWidth = 1;
    for (var i = 1; i < 4; i++) {
      final y = h * 0.68 + (h * 0.32 / 4) * i;
      canvas.drawLine(Offset(0, y), Offset(w, y), line);
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
