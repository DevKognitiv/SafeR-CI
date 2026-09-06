import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:media_kit/media_kit.dart';

import 'app.dart';
import 'core/providers/providers.dart';
import 'core/storage.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  try {
    MediaKit.ensureInitialized(); // camera streams (RTSP/HLS)
  } catch (_) {
    // media_kit is optional on platforms without native libs (e.g. tests)
  }
  final storage = await AppStorage.create();
  runApp(ProviderScope(
    overrides: [storageProvider.overrideWithValue(storage)],
    child: const SafeRApp(),
  ));
}
