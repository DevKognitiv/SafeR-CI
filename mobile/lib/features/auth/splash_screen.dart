import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/config.dart';
import '../../core/providers/providers.dart';
import '../../core/theme.dart';

/// Restores the session, then the router redirects to /login or /.
class SplashScreen extends ConsumerStatefulWidget {
  const SplashScreen({super.key});

  @override
  ConsumerState<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends ConsumerState<SplashScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => ref.read(authProvider.notifier).restore());
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        backgroundColor: SafeRColors.surfaceDark,
        body: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 88,
                height: 88,
                decoration: BoxDecoration(color: SafeRColors.primary, borderRadius: BorderRadius.circular(24)),
                child: const Icon(Icons.shield, color: Colors.white, size: 52),
              ),
              const SizedBox(height: 20),
              const Text(AppConfig.appName, style: TextStyle(color: Colors.white, fontSize: 30, fontWeight: FontWeight.w800, letterSpacing: 2)),
              const SizedBox(height: 32),
              const SizedBox(width: 28, height: 28, child: CircularProgressIndicator(color: Colors.white, strokeWidth: 3)),
            ],
          ),
        ),
      );
}
