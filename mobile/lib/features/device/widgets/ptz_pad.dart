import 'package:flutter/material.dart';

import '../../../core/i18n.dart';

/// PTZ D-pad + zoom buttons. [onStart] fires on press, [onStop] on release.
class PtzPad extends StatelessWidget {
  const PtzPad({super.key, required this.onStart, required this.onStop, this.supported = const {}, this.enabled = true});

  final ValueChanged<String> onStart;
  final VoidCallback onStop;
  final Set<String> supported;
  final bool enabled;

  bool _has(String value) => supported.isEmpty || supported.contains(value);

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    Widget key(String value, IconData icon, String label) => _PtzKey(
          icon: icon,
          label: label,
          enabled: enabled && _has(value),
          onStart: () => onStart(value),
          onStop: onStop,
        );
    return Column(
      children: [
        Container(
          width: 176,
          height: 176,
          decoration: BoxDecoration(shape: BoxShape.circle, color: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.6)),
          child: Stack(
            alignment: Alignment.center,
            children: [
              Align(alignment: Alignment.topCenter, child: key('up', Icons.keyboard_arrow_up, context.tr(fr: 'PTZ haut', en: 'PTZ up'))),
              Align(alignment: Alignment.bottomCenter, child: key('down', Icons.keyboard_arrow_down, context.tr(fr: 'PTZ bas', en: 'PTZ down'))),
              Align(alignment: Alignment.centerLeft, child: key('left', Icons.keyboard_arrow_left, context.tr(fr: 'PTZ gauche', en: 'PTZ left'))),
              Align(alignment: Alignment.centerRight, child: key('right', Icons.keyboard_arrow_right, context.tr(fr: 'PTZ droite', en: 'PTZ right'))),
              Container(
                width: 48,
                height: 48,
                decoration: BoxDecoration(shape: BoxShape.circle, color: theme.colorScheme.surface),
                child: Icon(Icons.control_camera, color: theme.colorScheme.onSurfaceVariant),
              ),
            ],
          ),
        ),
        const SizedBox(height: 12),
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            key('zoom_out', Icons.zoom_out, context.tr(fr: 'Zoom arrière', en: 'Zoom out')),
            const SizedBox(width: 24),
            key('zoom_in', Icons.zoom_in, context.tr(fr: 'Zoom avant', en: 'Zoom in')),
          ],
        ),
      ],
    );
  }
}

class _PtzKey extends StatelessWidget {
  const _PtzKey({required this.icon, required this.label, required this.enabled, required this.onStart, required this.onStop});

  final IconData icon;
  final String label;
  final bool enabled;
  final VoidCallback onStart;
  final VoidCallback onStop;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Semantics(
      container: true,
      button: true,
      enabled: enabled,
      label: label,
      child: GestureDetector(
        onTapDown: enabled ? (_) => onStart() : null,
        onTapUp: enabled ? (_) => onStop() : null,
        onTapCancel: enabled ? onStop : null,
        child: Container(
          width: 52,
          height: 52,
          margin: const EdgeInsets.all(4),
          decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: theme.colorScheme.surface,
              boxShadow: const [BoxShadow(color: Colors.black12, blurRadius: 4, offset: Offset(0, 2))]),
          child: Icon(icon, size: 30, color: enabled ? theme.colorScheme.primary : theme.colorScheme.onSurfaceVariant.withValues(alpha: 0.4)),
        ),
      ),
    );
  }
}
