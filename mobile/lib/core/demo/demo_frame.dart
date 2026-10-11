import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../providers/auth_provider.dart';
import '../router.dart';
import 'demo_overrides.dart';
import 'ready_signal.dart';

/// Time dilation applied when `?animations=off`: transitions finish twenty
/// times faster, so a capture taken after the readiness signal never shows a
/// half-way page transition or switch.
const double kDemoTimeDilation = 0.05;

/// `MaterialApp.builder` of the demo build: wraps the navigator in a
/// [DemoFrame]. Kept as a top-level function so `app.dart` only references
/// it behind `kDemoMode`.
Widget demoFrameBuilder(BuildContext context, Widget? child) => DemoFrame(child: child);

/// Applies the capture hooks that live above the navigator (text scale,
/// animation hint), steers the router to `?route=` once the session is
/// restored and raises the readiness signal after the target screen has
/// painted.
class DemoFrame extends ConsumerStatefulWidget {
  const DemoFrame({super.key, required this.child});

  final Widget? child;

  @override
  ConsumerState<DemoFrame> createState() => _DemoFrameState();
}

class _DemoFrameState extends ConsumerState<DemoFrame> {
  late final GoRouter _router;
  bool _navigated = false;
  bool _ready = false;
  Timer? _fallback;

  @override
  void initState() {
    super.initState();
    if (ref.read(demoOptionsProvider).animationsOff) timeDilation = kDemoTimeDilation;
    _router = ref.read(routerProvider);
    _router.routerDelegate.addListener(_schedule);
    ref.listenManual(authProvider, (_, __) => _schedule());
    _schedule();
  }

  @override
  void dispose() {
    _fallback?.cancel();
    _router.routerDelegate.removeListener(_schedule);
    super.dispose();
  }

  void _schedule() {
    if (_ready) return;
    WidgetsBinding.instance.addPostFrameCallback((_) => _tick());
  }

  /// Runs after each frame that follows a route or auth change. Waits for the
  /// session to be restored and the splash redirect to be applied, navigates
  /// once to the requested route, then signals readiness.
  void _tick() {
    if (!mounted || _ready) return;
    if (ref.read(authProvider).status == AuthStatus.unknown) return;
    final current = _router.routerDelegate.currentConfiguration.uri;
    if (current.path == Routes.splash) return;
    final target = Uri.parse(ref.read(demoOptionsProvider).route);
    if (!_navigated && current.path != target.path) {
      _navigated = true;
      _router.go(target.toString());
      // A route the redirect refuses (e.g. Home while logged out) never
      // notifies the delegate: report what is on screen instead of hanging.
      _fallback = Timer(const Duration(milliseconds: 1500), _tick);
      return;
    }
    _fallback?.cancel();
    _ready = true;
    _signalWhenPainted();
  }

  /// Two frames after the route settled: the demo hub answers in microtasks,
  /// so the screen's first data is painted by then.
  Future<void> _signalWhenPainted() async {
    await WidgetsBinding.instance.endOfFrame;
    await WidgetsBinding.instance.endOfFrame;
    signalDemoReady();
  }

  @override
  Widget build(BuildContext context) {
    final options = ref.watch(demoOptionsProvider);
    final media = MediaQuery.of(context);
    return MediaQuery(
      data: media.copyWith(
        textScaler: TextScaler.linear(options.textScale),
        disableAnimations: options.animationsOff || media.disableAnimations,
      ),
      child: widget.child ?? const SizedBox.shrink(),
    );
  }
}
