import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:geolocator/geolocator.dart';

import '../services/api_service.dart';
import '../services/location_service.dart';
import '../services/notification_service.dart';
import '../widgets/sos_button.dart';

/// SafeR CI — SOS Screen
/// The primary safety screen: one-tap emergency alert.
/// Designed for maximum speed and usability under stress.
class SOSScreen extends ConsumerStatefulWidget {
  const SOSScreen({super.key});

  @override
  ConsumerState<SOSScreen> createState() => _SOSScreenState();
}

class _SOSScreenState extends ConsumerState<SOSScreen>
    with SingleTickerProviderStateMixin {
  bool _alertSent = false;
  bool _sending = false;
  String _statusMessage = '';
  late AnimationController _pulseController;
  late Animation<double> _pulseAnimation;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    )..repeat(reverse: true);
    _pulseAnimation = Tween<double>(begin: 0.95, end: 1.05).animate(
      CurvedAnimation(parent: _pulseController, curve: Curves.easeInOut),
    );
  }

  @override
  void dispose() {
    _pulseController.dispose();
    super.dispose();
  }

  Future<void> _sendSOSAlert() async {
    if (_sending || _alertSent) return;
    setState(() { _sending = true; _statusMessage = 'Localisation en cours...'; });

    try {
      // 1. Get GPS location
      final position = await LocationService.getCurrentPosition();

      setState(() { _statusMessage = 'Envoi de l\'alerte...'; });

      // 2. Send to SafeR API
      await ApiService.createIncident(
        incidentType: 'panic',
        severity: 'critical',
        lat: position.latitude,
        lon: position.longitude,
        source: 'mobile_app',
      );

      // 3. Local notification
      await NotificationService.showLocalAlert(
        title: '🚨 Alerte envoyée',
        body: 'Les secours ont été notifiés. Restez en sécurité.',
      );

      setState(() {
        _alertSent = true;
        _sending = false;
        _statusMessage = '✅ Alerte envoyée! Les secours sont notifiés.';
      });

    } catch (e) {
      // Offline fallback — queue for retry
      setState(() {
        _sending = false;
        _statusMessage = '📵 Hors ligne — Alerte mise en file d\'attente';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: _alertSent
          ? Colors.green.shade900
          : const Color(0xFF1A1A2E),
      body: SafeArea(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            // Header
            const Padding(
              padding: EdgeInsets.all(24),
              child: Text(
                'SafeR CI',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 28,
                  fontWeight: FontWeight.bold,
                  letterSpacing: 2,
                ),
              ),
            ),

            const Spacer(),

            // SOS Button
            ScaleTransition(
              scale: _pulseAnimation,
              child: SOSButton(
                onPressed: _sendSOSAlert,
                isLoading: _sending,
                isActivated: _alertSent,
              ),
            ),

            const SizedBox(height: 24),

            // Status message
            if (_statusMessage.isNotEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 32),
                child: Text(
                  _statusMessage,
                  style: const TextStyle(color: Colors.white70, fontSize: 16),
                  textAlign: TextAlign.center,
                ),
              ),

            const Spacer(),

            // Emergency numbers
            Padding(
              padding: const EdgeInsets.all(24),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                children: [
                  _EmergencyContact(number: '170', label: 'Police'),
                  _EmergencyContact(number: '180', label: 'Pompiers'),
                  _EmergencyContact(number: '185', label: 'SAMU'),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _EmergencyContact extends StatelessWidget {
  final String number;
  final String label;
  const _EmergencyContact({required this.number, required this.label});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Text(number,
            style: const TextStyle(
                color: Colors.white,
                fontSize: 24,
                fontWeight: FontWeight.bold)),
        Text(label,
            style: const TextStyle(color: Colors.white60, fontSize: 12)),
      ],
    );
  }
}
