import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/models/device.dart';
import '../../../core/providers/providers.dart';
import '../../../core/widgets/widgets.dart';

/// Send one command through the devices notifier (optimistic update, rollback on
/// failure) and surface errors as a snackbar. Returns true on success.
Future<bool> sendDeviceCommand(BuildContext context, WidgetRef ref, Device device, String code, dynamic value) async {
  try {
    await ref.read(devicesProvider(device.homeId).notifier).sendCommand(device.id, code, value);
    return true;
  } catch (e) {
    if (context.mounted) showErrorSnack(context, e);
    return false;
  }
}

/// Send several commands one after the other (multi-gang "all on/off").
Future<bool> sendDeviceCommands(BuildContext context, WidgetRef ref, Device device, Map<String, dynamic> commands) async {
  for (final entry in commands.entries) {
    if (!await sendDeviceCommand(context, ref, device, entry.key, entry.value)) return false;
    if (!context.mounted) return false;
  }
  return true;
}

/// Writable capability of the given type, or null.
Capability? writableCapability(Device device, String code, {String? type}) {
  final cap = device.capability(code);
  if (cap == null || !cap.writable) return null;
  if (type != null && cap.type != type) return null;
  return cap;
}
