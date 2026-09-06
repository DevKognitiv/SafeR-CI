import 'package:flutter/material.dart';

/// Slider bound to a device value: keeps a local value while dragging and only
/// commits on release so optimistic updates never fight the gesture.
class CapabilitySlider extends StatefulWidget {
  const CapabilitySlider({
    super.key,
    required this.label,
    required this.value,
    required this.min,
    required this.max,
    required this.onCommit,
    this.icon,
    this.divisions,
    this.unit,
    this.format,
    this.gradient,
    this.activeColor,
    this.enabled = true,
  });

  final String label;
  final double value;
  final double min;
  final double max;
  final ValueChanged<double> onCommit;
  final IconData? icon;
  final int? divisions;
  final String? unit;
  final String Function(double value)? format;
  final Gradient? gradient;
  final Color? activeColor;
  final bool enabled;

  @override
  State<CapabilitySlider> createState() => _CapabilitySliderState();
}

class _CapabilitySliderState extends State<CapabilitySlider> {
  double? _dragValue;

  double get _shown => (_dragValue ?? widget.value).clamp(widget.min, widget.max).toDouble();

  String _text(double v) {
    if (widget.format != null) return widget.format!(v);
    final rounded = widget.divisions != null || v == v.roundToDouble() ? v.round().toString() : v.toStringAsFixed(1);
    return widget.unit == null ? rounded : '$rounded${widget.unit == '%' ? '' : ' '}${widget.unit}';
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final max = widget.max > widget.min ? widget.max : widget.min + 1;
    final gradient = widget.gradient;
    Widget slider = Slider(
      value: _shown,
      min: widget.min,
      max: max,
      divisions: widget.divisions,
      label: _text(_shown),
      semanticFormatterCallback: (v) => '${widget.label} ${_text(v)}',
      onChanged: widget.enabled ? (v) => setState(() => _dragValue = v) : null,
      onChangeEnd: widget.enabled
          ? (v) {
              setState(() => _dragValue = null);
              widget.onCommit(v);
            }
          : null,
    );
    if (gradient != null) {
      slider = SliderTheme(
        data: SliderTheme.of(context).copyWith(
          trackHeight: 16,
          trackShape: _GradientTrackShape(gradient),
          thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 12, elevation: 3),
          thumbColor: Colors.white,
          overlayColor: Colors.black12,
          showValueIndicator: ShowValueIndicator.onDrag,
        ),
        child: slider,
      );
    } else if (widget.activeColor != null) {
      slider = SliderTheme(data: SliderTheme.of(context).copyWith(activeTrackColor: widget.activeColor, thumbColor: widget.activeColor), child: slider);
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            if (widget.icon != null) ...[Icon(widget.icon, size: 20, color: theme.colorScheme.onSurfaceVariant), const SizedBox(width: 8)],
            Expanded(child: Text(widget.label, style: theme.textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w600))),
            Text(_text(_shown), style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700, color: theme.colorScheme.primary)),
          ],
        ),
        slider,
      ],
    );
  }
}

/// Track painted with a gradient (hue / saturation / colour temperature).
class _GradientTrackShape extends SliderTrackShape with BaseSliderTrackShape {
  const _GradientTrackShape(this.gradient);

  final Gradient gradient;

  @override
  void paint(
    PaintingContext context,
    Offset offset, {
    required RenderBox parentBox,
    required SliderThemeData sliderTheme,
    required Animation<double> enableAnimation,
    required TextDirection textDirection,
    required Offset thumbCenter,
    Offset? secondaryOffset,
    bool isDiscrete = false,
    bool isEnabled = false,
  }) {
    final rect = getPreferredRect(parentBox: parentBox, offset: offset, sliderTheme: sliderTheme, isEnabled: isEnabled, isDiscrete: isDiscrete);
    final rrect = RRect.fromRectAndRadius(rect, Radius.circular(rect.height / 2));
    context.canvas.drawRRect(rrect, Paint()..shader = gradient.createShader(rect));
  }
}

/// Rainbow gradient for a 0-360 hue slider.
const LinearGradient kHueGradient = LinearGradient(colors: [
  Color(0xFFFF0000),
  Color(0xFFFFFF00),
  Color(0xFF00FF00),
  Color(0xFF00FFFF),
  Color(0xFF0000FF),
  Color(0xFFFF00FF),
  Color(0xFFFF0000),
]);

/// Warm (2700K) to cool (6500K) gradient for colour temperature sliders.
const LinearGradient kColorTempGradient = LinearGradient(colors: [Color(0xFFFFB46B), Color(0xFFFFE9C8), Color(0xFFFFFFFF), Color(0xFFCFE3FF)]);
