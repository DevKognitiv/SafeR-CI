import 'package:flutter/material.dart';

import '../../../core/i18n.dart';
import '../../../core/models/scene.dart';
import '../../../core/widgets/widgets.dart';
import 'scene_style.dart';

/// Colourful tap-to-run card (Tuya style): icon, name, action count and last run.
class SceneCard extends StatelessWidget {
  const SceneCard({super.key, required this.scene, this.running = false, this.onTap, this.onLongPress});

  final Scene scene;
  final bool running;
  final VoidCallback? onTap;
  final VoidCallback? onLongPress;

  @override
  Widget build(BuildContext context) {
    final color = colorFromHex(scene.color);
    final count = scene.actions.length;
    final actions = count > 1 ? context.tr(fr: '$count actions', en: '$count actions') : context.tr(fr: '$count action', en: '$count action');
    final lastRun = scene.lastRunAt == null ? context.tr(fr: 'Jamais exécutée', en: 'Never run') : timeAgo(context, scene.lastRunAt);
    final textTheme = Theme.of(context).textTheme;
    return Material(
      color: color,
      borderRadius: BorderRadius.circular(16),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        onLongPress: onLongPress,
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Container(
                    width: 40,
                    height: 40,
                    decoration: BoxDecoration(color: Colors.white.withValues(alpha: 0.22), borderRadius: BorderRadius.circular(12)),
                    child: Icon(iconFromName(scene.icon, fallback: Icons.play_circle), color: Colors.white, size: 22),
                  ),
                  const Spacer(),
                  if (running)
                    const SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                  else
                    Icon(Icons.play_arrow_rounded, color: Colors.white.withValues(alpha: 0.85), size: 26),
                ],
              ),
              const Spacer(),
              Text(scene.name, maxLines: 1, overflow: TextOverflow.ellipsis, style: textTheme.titleSmall?.copyWith(color: Colors.white, fontWeight: FontWeight.w700)),
              const SizedBox(height: 2),
              Text('$actions · $lastRun', maxLines: 1, overflow: TextOverflow.ellipsis, style: textTheme.bodySmall?.copyWith(color: Colors.white.withValues(alpha: 0.85))),
            ],
          ),
        ),
      ),
    );
  }
}
