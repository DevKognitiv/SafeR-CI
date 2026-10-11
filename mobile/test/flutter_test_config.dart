// Suite-wide configuration. flutter_test calls [testExecutable] once per test file, before
// that file's `main`, so this is where the golden harness is wired in:
//
// * test/goldens/** get a tolerant golden comparator (0.1 % of pixels may differ) and the
//   real fonts a phone would render with;
// * test/a11y/** get the real fonts, so measured sizes match a device;
// * every other test keeps the stock flutter_test behaviour (placeholder font, exact
//   comparator), so nothing changes for the existing widget tests.
//
// See docs/qa/golden-harness.md.
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

/// Fraction of differing pixels a golden may drift before the comparison fails (0.1 %).
///
/// Absorbs sub-pixel anti-aliasing differences between engine builds without hiding real
/// layout changes: a 2 px padding change on the Home screen moves well over 1 % of pixels.
const double kGoldenTolerance = 0.001;

Future<void> testExecutable(FutureOr<void> Function() testMain) async {
  final comparator = goldenFileComparator;
  if (comparator is LocalFileComparator) {
    final directory = comparator.basedir.toFilePath();
    final golden = _isUnderTestDirectory(directory, 'goldens');
    final a11y = _isUnderTestDirectory(directory, 'a11y');
    if (golden) {
      // LocalFileComparator derives its base directory from a test file path; any file name
      // inside the original directory reproduces the same base directory.
      goldenFileComparator = TolerantGoldenFileComparator(
        comparator.basedir.resolve('golden_test.dart'),
        tolerance: kGoldenTolerance,
      );
    }
    if (golden || a11y) await loadRealFonts();
  }
  await testMain();
}

bool _isUnderTestDirectory(String directory, String name) {
  final sep = Platform.pathSeparator;
  return directory.contains('${sep}test$sep$name$sep');
}

/// [LocalFileComparator] that accepts a golden when at most [tolerance] of the pixels differ.
///
/// Anything above the tolerance fails exactly like the stock comparator and writes the
/// master / test / diff images to `failures/` next to the test file.
class TolerantGoldenFileComparator extends LocalFileComparator {
  TolerantGoldenFileComparator(super.testFile, {required this.tolerance});

  /// Allowed fraction (0..1) of differing pixels.
  final double tolerance;

  @override
  Future<bool> compare(Uint8List imageBytes, Uri golden) async {
    final result = await GoldenFileComparator.compareLists(imageBytes, await getGoldenBytes(golden));
    try {
      if (result.passed || result.diffPercent <= tolerance) return true;
      final error = await generateFailureOutput(result, golden, basedir);
      throw FlutterError(
        '$error\n'
        'Pixel difference ${_percent(result.diffPercent)} exceeds the golden tolerance of ${_percent(tolerance)}.',
      );
    } finally {
      result.dispose();
    }
  }

  static String _percent(double fraction) => '${(fraction * 100).toStringAsFixed(2)}%';
}

/// Registers the fonts a device renders with, so goldens show real glyphs instead of the
/// flutter_test placeholder font: every family in FontManifest.json (the bundled Manrope and
/// Inter, MaterialIcons, package icon fonts) and Roboto, Material's default, from the Flutter
/// SDK cache (`bin/cache/artifacts/material_fonts`).
///
/// Throws when Roboto cannot be found: a golden captured with the placeholder font would
/// silently differ from every other machine.
Future<void> loadRealFonts() async {
  TestWidgetsFlutterBinding.ensureInitialized();
  final manifest = json.decode(await rootBundle.loadString('FontManifest.json')) as List<dynamic>;
  for (final entry in manifest.cast<Map<String, dynamic>>()) {
    final loader = FontLoader(entry['family'] as String);
    for (final font in (entry['fonts'] as List<dynamic>).cast<Map<String, dynamic>>()) {
      loader.addFont(rootBundle.load(font['asset'] as String));
    }
    await loader.load();
  }

  final materialFonts = Directory(materialFontsPath());
  final robotoFiles = materialFonts.existsSync()
      ? (materialFonts.listSync().whereType<File>().where((file) {
          final name = file.uri.pathSegments.last;
          return name.startsWith('Roboto-') && name.endsWith('.ttf');
        }).toList()
        ..sort((a, b) => a.path.compareTo(b.path)))
      : const <File>[];
  if (robotoFiles.isEmpty) {
    throw StateError('Roboto not found in ${materialFonts.path}: run `flutter precache` or set FLUTTER_ROOT.');
  }
  final roboto = FontLoader('Roboto');
  for (final file in robotoFiles) {
    roboto.addFont(file.readAsBytes().then(ByteData.sublistView));
  }
  await roboto.load();
}

/// Directory holding Roboto and MaterialIcons in the Flutter SDK cache.
///
/// Uses `FLUTTER_ROOT` when the `flutter` launcher exported it, otherwise walks up from the
/// `flutter_tester` binary (`<root>/bin/cache/artifacts/engine/<platform>/flutter_tester`).
String materialFontsPath() {
  final sep = Platform.pathSeparator;
  var root = Platform.environment['FLUTTER_ROOT'];
  if (root == null || root.isEmpty) {
    final executable = Platform.resolvedExecutable;
    final marker = '${sep}bin${sep}cache$sep';
    final index = executable.indexOf(marker);
    root = index < 0 ? '' : executable.substring(0, index);
  }
  return [root, 'bin', 'cache', 'artifacts', 'material_fonts'].join(sep);
}
