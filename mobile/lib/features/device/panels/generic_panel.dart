import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/models/device.dart';
import '../widgets/generic_controls.dart';

/// Fallback panel: auto-generated controls from the capability list.
class GenericPanel extends ConsumerWidget {
  const GenericPanel({super.key, required this.device});

  final Device device;

  @override
  Widget build(BuildContext context, WidgetRef ref) => GenericControls(device: device, showEmpty: true);
}
