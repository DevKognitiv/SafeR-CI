import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/models/device.dart';
import '../../../core/providers/providers.dart';

/// Fallback fetch for a device that is not in the cached list of the current home.
final fetchedDeviceProvider = FutureProvider.autoDispose.family<Device, String>((ref, deviceId) => ref.read(hubClientProvider).device(deviceId));

/// Child devices of a parent (NVR channels, alarm zones, gateway nodes).
final deviceChildrenProvider = FutureProvider.autoDispose.family<List<Device>, String>((ref, deviceId) => ref.read(hubClientProvider).children(deviceId));

typedef CameraStreamKey = ({String deviceId, String quality});

/// Stream descriptor for a camera at the given quality (main | sub).
final cameraStreamProvider =
    FutureProvider.autoDispose.family<StreamInfo, CameraStreamKey>((ref, key) => ref.read(hubClientProvider).stream(key.deviceId, quality: key.quality));
