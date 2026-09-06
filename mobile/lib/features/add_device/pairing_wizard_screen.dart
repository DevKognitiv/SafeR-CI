import 'package:flutter/material.dart';

/// Placeholder — replaced by the PairingWizardScreen workstream.
class PairingWizardScreen extends StatelessWidget {
  const PairingWizardScreen({super.key, required this.brandId, this.method, this.prefill});

  final String brandId;
  final String? method;
  final Map<String, dynamic>? prefill;

  @override
  Widget build(BuildContext context) => Scaffold(appBar: AppBar(title: const Text('PairingWizardScreen')), body: const Center(child: Text('PairingWizardScreen (à implémenter)')));
}
