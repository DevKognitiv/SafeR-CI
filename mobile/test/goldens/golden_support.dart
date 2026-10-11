// Shared pieces of the golden harness: the phone frame, the variant matrix and the overflow
// tolerance used while capturing. Every screen golden builds on these so the matrix stays
// identical across screens. See docs/qa/golden-harness.md.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:safer_ci/core/theme.dart';

/// Phone frame used by every golden: 360x780 logical px at device pixel ratio 1.
const Size kGoldenPhone = Size(360, 780);

/// One cell of the variant matrix: {light, dark} x {fr, en} x {text scale 1.0, 2.0}.
class GoldenVariant {
  const GoldenVariant({required this.brightness, required this.locale, required this.textScale});

  final Brightness brightness;
  final Locale locale;
  final double textScale;

  /// File stem, e.g. `light_fr_1.0` or `dark_en_2.0`.
  String get name => '${brightness == Brightness.dark ? 'dark' : 'light'}_${locale.languageCode}_${textScale.toStringAsFixed(1)}';

  ThemeData get theme => brightness == Brightness.dark ? SafeRTheme.darkTheme : SafeRTheme.lightTheme;

  TextScaler get textScaler => TextScaler.linear(textScale);
}

/// The eight variants every screen golden is captured in.
final List<GoldenVariant> kGoldenVariants = List.unmodifiable([
  for (final brightness in [Brightness.light, Brightness.dark])
    for (final locale in const [Locale('fr'), Locale('en')])
      for (final textScale in [1.0, 2.0]) GoldenVariant(brightness: brightness, locale: locale, textScale: textScale),
]);

/// Runs [body] while `RenderFlex overflowed` errors are recorded instead of failing the test.
///
/// A golden must still be captured when a fixed-height layout overflows at text scale 2.0:
/// the overflow stripes then appear in the PNG and the list is returned so the test can
/// report it. Every other error still reaches the test binding and fails the test as usual.
Future<List<String>> runAllowingOverflow(Future<void> Function() body) async {
  final overflows = <String>[];
  final previous = FlutterError.onError;
  FlutterError.onError = (details) {
    if (isRenderOverflow(details)) {
      overflows.add(details.exceptionAsString().split('\n').first);
      return;
    }
    previous?.call(details);
  };
  try {
    await body();
  } finally {
    FlutterError.onError = previous;
  }
  return overflows;
}

final RegExp _overflowPattern = RegExp(r'^A Render\w+ overflowed by ');

/// True for the error the rendering library reports when a flex or box overflows.
bool isRenderOverflow(FlutterErrorDetails details) =>
    details.library == 'rendering library' && _overflowPattern.hasMatch(details.exceptionAsString());

/// Prints the overflows tolerated while capturing [golden], so CI logs name the layouts
/// Phase 1 has to fix (the baseline list lives in docs/qa/a11y-baseline.md).
void reportOverflows(String golden, List<String> overflows) {
  if (overflows.isEmpty) return;
  debugPrint('[golden] $golden tolerated ${overflows.length} overflow(s): ${overflows.toSet().join(' | ')}');
}
