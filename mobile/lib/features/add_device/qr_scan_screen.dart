import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../../core/api/api_exception.dart';
import '../../core/i18n.dart';
import '../../core/models/brand.dart';
import '../../core/providers/providers.dart';
import '../../core/router.dart';
import '../../core/widgets/widgets.dart';
import 'matter_payload.dart';
import 'widgets/scan_overlay.dart';

/// Builds the camera preview; [onCode] must be called with the raw code text.
typedef QrScannerBuilder = Widget Function(BuildContext context, ValueChanged<String> onCode);

/// Override to replace the real camera (widget tests, desktop previews).
final qrScannerBuilderProvider = Provider<QrScannerBuilder?>((_) => null);

/// Query parameter that makes the scanner pop with the code instead of navigating.
const String kScanResultQuery = 'result';

/// Location to push when the caller wants the raw code back (`context.push<String>`).
String scanForResultLocation() => '${Routes.scan}?$kScanResultQuery=1';

/// Full-screen QR scanner with viewfinder, torch and manual entry.
///
/// Standalone: the code is parsed by the hub and the wizard is opened
/// (`pushReplacement`). Opened via [scanForResultLocation] (or with
/// [popWithResult]): pops with the raw code for the caller's form field.
class QrScanScreen extends ConsumerStatefulWidget {
  const QrScanScreen({super.key, this.scannerBuilder, this.popWithResult = false});

  final QrScannerBuilder? scannerBuilder;
  final bool popWithResult;

  @override
  ConsumerState<QrScanScreen> createState() => _QrScanScreenState();
}

class _QrScanScreenState extends ConsumerState<QrScanScreen> with WidgetsBindingObserver {
  MobileScannerController? _controller;
  bool _handling = false;
  bool _torchOn = false;
  Timer? _rearm;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    if (widget.scannerBuilder == null && ref.read(qrScannerBuilderProvider) == null) {
      _controller = MobileScannerController(formats: const [BarcodeFormat.qrCode, BarcodeFormat.dataMatrix]);
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _rearm?.cancel();
    unawaited(_controller?.dispose());
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    final controller = _controller;
    if (controller == null || !controller.value.hasCameraPermission) return;
    switch (state) {
      case AppLifecycleState.detached:
      case AppLifecycleState.hidden:
      case AppLifecycleState.paused:
        unawaited(controller.stop());
      case AppLifecycleState.resumed:
        unawaited(controller.start());
      case AppLifecycleState.inactive:
        break;
    }
  }

  bool get _forResult {
    if (widget.popWithResult) return true;
    try {
      return GoRouterState.of(context).uri.queryParameters[kScanResultQuery] == '1';
    } catch (_) {
      return false;
    }
  }

  Future<void> _onCode(String raw) async {
    final code = raw.trim();
    if (_handling || code.isEmpty) return;
    _handling = true;
    if (_forResult) {
      context.pop(code);
      return;
    }
    try {
      final parsed = await ref.read(hubClientProvider).parseCode(code);
      if (!mounted) return;
      if (_openWizard(parsed, code)) return;
      showSnack(context, context.tr(fr: 'Code non reconnu', en: 'Unrecognised code'));
    } on ApiException catch (e) {
      if (!mounted) return;
      // Hub unreachable: Matter codes can still be decoded on the phone.
      final local = tryParseMatterCode(code);
      if (local != null) {
        context.pushReplacement(Routes.pair('matter', method: isMatterQr(code) ? 'qr_code' : 'manual_code'), extra: {'code': code, ...local.toJson()});
        return;
      }
      showErrorSnack(context, e);
    }
    // Let the user point the camera elsewhere before accepting a new detection.
    _rearm = Timer(const Duration(seconds: 2), () => _handling = false);
  }

  /// Route a parsed code to the right wizard; false when unknown.
  bool _openWizard(ParsedCode parsed, String raw) {
    final extra = <String, dynamic>{'code': raw, ...parsed.data};
    if (parsed.kind.startsWith('matter_')) {
      context.pushReplacement(Routes.pair('matter', method: parsed.method ?? (parsed.kind == 'matter_manual' ? 'manual_code' : 'qr_code')), extra: extra);
      return true;
    }
    if (parsed.kind == 'tuya_qr') {
      context.pushReplacement(Routes.pair('tuya', method: parsed.method ?? 'cloud_project'), extra: extra);
      return true;
    }
    if (parsed.isKnown && parsed.brand != null && parsed.brand!.isNotEmpty) {
      context.pushReplacement(Routes.pair(parsed.brand!, method: parsed.method), extra: extra);
      return true;
    }
    return false;
  }

  Future<void> _toggleTorch() async {
    final controller = _controller;
    if (controller != null) {
      await controller.toggleTorch();
      if (!mounted) return;
      setState(() => _torchOn = controller.value.torchState == TorchState.on);
    } else {
      setState(() => _torchOn = !_torchOn);
    }
  }

  Future<void> _enterManually() async {
    final code = await showDialog<String>(context: context, builder: (_) => const _ManualCodeDialog());
    if (!mounted || code == null) return;
    await _onCode(code);
  }

  Widget _buildScanner(BuildContext context) {
    final builder = widget.scannerBuilder ?? ref.watch(qrScannerBuilderProvider);
    if (builder != null) return builder(context, _onCode);
    return MobileScanner(
      controller: _controller,
      onDetect: (BarcodeCapture capture) {
        for (final barcode in capture.barcodes) {
          final raw = barcode.rawValue ?? barcode.displayValue;
          if (raw != null && raw.isNotEmpty) {
            _onCode(raw);
            return;
          }
        }
      },
      errorBuilder: (context, error, _) => _CameraError(error: error, onManual: _enterManually),
    );
  }

  @override
  Widget build(BuildContext context) {
    final forResult = _forResult;
    return Scaffold(
      backgroundColor: Colors.black,
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        foregroundColor: Colors.white,
        title: Text(context.tr(fr: 'Scanner un code', en: 'Scan a code')),
        actions: [
          IconButton(
            tooltip: _torchOn ? context.tr(fr: 'Éteindre la lampe torche', en: 'Turn torch off') : context.tr(fr: 'Allumer la lampe torche', en: 'Turn torch on'),
            icon: Icon(_torchOn ? Icons.flash_on : Icons.flash_off),
            onPressed: _toggleTorch,
          ),
        ],
      ),
      body: Stack(
        fit: StackFit.expand,
        children: [
          _buildScanner(context),
          const ScanOverlay(),
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            child: SafeArea(
              top: false,
              child: Padding(
                padding: const EdgeInsets.fromLTRB(24, 16, 24, 24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      context.tr(fr: 'Placez le code QR dans le cadre', en: 'Place the QR code inside the frame'),
                      textAlign: TextAlign.center,
                      style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      forResult
                          ? context.tr(fr: 'Le code sera reporté dans le formulaire.', en: 'The code will be filled into the form.')
                          : context.tr(fr: 'Matter (MT:…), Tuya Smart Life, ou étiquette de l\'appareil', en: 'Matter (MT:…), Tuya Smart Life, or the device label'),
                      textAlign: TextAlign.center,
                      style: const TextStyle(color: Colors.white70, fontSize: 13),
                    ),
                    const SizedBox(height: 16),
                    OutlinedButton.icon(
                      onPressed: _enterManually,
                      style: OutlinedButton.styleFrom(
                        foregroundColor: Colors.white,
                        side: const BorderSide(color: Colors.white70),
                        minimumSize: const Size.fromHeight(48),
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                      ),
                      icon: const Icon(Icons.keyboard_alt_outlined),
                      label: Text(context.tr(fr: 'Saisir manuellement', en: 'Enter manually')),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Shown instead of the preview when the camera is unavailable (permission denied…).
class _CameraError extends StatelessWidget {
  const _CameraError({required this.error, required this.onManual});

  final MobileScannerException error;
  final VoidCallback onManual;

  @override
  Widget build(BuildContext context) {
    final denied = error.errorCode == MobileScannerErrorCode.permissionDenied;
    return ColoredBox(
      color: Colors.black,
      child: Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.no_photography_outlined, color: Colors.white70, size: 56),
              const SizedBox(height: 16),
              Text(
                denied
                    ? context.tr(fr: "Autorisez l'accès à la caméra dans les réglages pour scanner un code.", en: 'Allow camera access in the settings to scan a code.')
                    : context.tr(fr: 'Caméra indisponible.', en: 'Camera unavailable.'),
                textAlign: TextAlign.center,
                style: const TextStyle(color: Colors.white),
              ),
              const SizedBox(height: 16),
              TextButton(onPressed: onManual, child: Text(context.tr(fr: 'Saisir le code manuellement', en: 'Enter the code manually'))),
            ],
          ),
        ),
      ),
    );
  }
}

class _ManualCodeDialog extends StatefulWidget {
  const _ManualCodeDialog();

  @override
  State<_ManualCodeDialog> createState() => _ManualCodeDialogState();
}

class _ManualCodeDialogState extends State<_ManualCodeDialog> {
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _submit() {
    final value = _controller.text.trim();
    if (value.isEmpty) return;
    Navigator.of(context).pop(value);
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text(context.tr(fr: 'Saisir le code', en: 'Enter the code')),
        content: ValueListenableBuilder<TextEditingValue>(
          valueListenable: _controller,
          builder: (_, value, __) => TextField(
            controller: _controller,
            autofocus: true,
            autocorrect: false,
            textInputAction: TextInputAction.done,
            decoration: InputDecoration(
              hintText: context.tr(fr: 'MT:… ou code à 11 chiffres', en: 'MT:… or 11-digit code'),
              helperText: looksLikeMatterCode(value.text) && tryParseMatterCode(value.text) == null ? context.tr(fr: 'Code Matter invalide', en: 'Invalid Matter code') : null,
            ),
            onSubmitted: (_) => _submit(),
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.of(context).pop(), child: Text(context.tr(fr: 'Annuler', en: 'Cancel'))),
          FilledButton(onPressed: _submit, style: FilledButton.styleFrom(minimumSize: const Size(88, 44)), child: Text(context.tr(fr: 'Valider', en: 'Confirm'))),
        ],
      );
}
