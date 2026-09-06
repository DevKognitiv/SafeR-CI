import 'package:flutter/material.dart';

import '../../../core/i18n.dart';
import '../../../core/widgets/widgets.dart';
import 'scene_style.dart';

/// Grid of scene icons; the selected one is filled with [color].
class SceneIconPicker extends StatelessWidget {
  const SceneIconPicker({super.key, required this.selected, required this.color, required this.onSelected});

  final String selected;
  final Color color;
  final ValueChanged<String> onSelected;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Wrap(
      spacing: 10,
      runSpacing: 10,
      children: [
        for (final name in kSceneIconNames)
          Semantics(
            label: context.tr(fr: 'Icône $name', en: 'Icon $name'),
            button: true,
            selected: name == selected,
            child: InkWell(
              borderRadius: BorderRadius.circular(14),
              onTap: () => onSelected(name),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 150),
                width: 48,
                height: 48,
                decoration: BoxDecoration(
                  color: name == selected ? color : scheme.surfaceContainerHighest,
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Icon(iconFromName(name, fallback: Icons.play_circle), color: name == selected ? Colors.white : scheme.onSurfaceVariant),
              ),
            ),
          ),
      ],
    );
  }
}

/// Row of preset colour swatches.
class SceneColorPicker extends StatelessWidget {
  const SceneColorPicker({super.key, required this.selected, required this.onSelected});

  final String selected;
  final ValueChanged<String> onSelected;

  @override
  Widget build(BuildContext context) => Wrap(
        spacing: 10,
        runSpacing: 10,
        children: [
          for (final hex in kSceneColors)
            Semantics(
              label: context.tr(fr: 'Couleur $hex', en: 'Colour $hex'),
              button: true,
              selected: hex.toUpperCase() == selected.toUpperCase(),
              child: InkWell(
                customBorder: const CircleBorder(),
                onTap: () => onSelected(hex),
                child: Container(
                  width: 44,
                  height: 44,
                  decoration: BoxDecoration(color: colorFromHex(hex), shape: BoxShape.circle),
                  child: hex.toUpperCase() == selected.toUpperCase() ? const Icon(Icons.check, color: Colors.white) : null,
                ),
              ),
            ),
        ],
      );
}
