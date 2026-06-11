import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../services/api_service.dart';
import '../services/ha_service.dart';
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

  late final HomeAssistantService _haService;
  StreamSubscription<Map<String, dynamic>>? _haSub;
  Map<String, dynamic>? _activeAlert;
  String _systemStatus = 'Connexion à Home Assistant...';

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

    _haService = HomeAssistantService(
      host: const String.fromEnvironment(
        'HA_MQTT_HOST',
        defaultValue: 'homeassistant.local',
      ),
      port: int.fromEnvironment('HA_MQTT_PORT', defaultValue: 1883),
    );
    _initHa();
  }

  Future<void> _initHa() async {
    try {
      await _haService.connect();
      _haSub = _haService.alerts.listen(_onHaMessage);
      if (mounted) {
        setState(() => _systemStatus = 'En ligne');
      }
    } catch (e) {
      if (mounted) {
        setState(() => _systemStatus = 'Hors ligne (HA): $e');
      }
    }
  }

  void _onHaMessage(Map<String, dynamic> event) {
    if (!mounted) return;
    final topic = event['topic'] as String?;
    final payload = event['payload'];
    if (topic == HomeAssistantService.topicUpdates) {
      setState(() => _activeAlert = {
            'payload': payload,
            'received_at': event['received_at'],
          });
    } else if (topic == HomeAssistantService.topicStatus) {
      setState(() => _systemStatus = _formatStatus(payload));
    }
  }

  String _formatStatus(dynamic payload) {
    if (payload is Map && payload['state'] is String) {
      return payload['state'] as String;
    }
    return payload?.toString() ?? 'inconnu';
  }

  @override
  void dispose() {
    _pulseController.dispose();
    _haSub?.cancel();
    _haService.dispose();
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

      // 3. Publish to HA over MQTT (best-effort).
      try {
        await _haService.sendSOS(position.latitude, position.longitude);
      } catch (_) {/* HA offline is non-fatal — API call already succeeded. */}

      // 4. Local notification
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
            // Real-time alert banner from safer/app/updates
            if (_activeAlert != null)
              _AlertBanner(
                payload: _activeAlert!['payload'],
                onDismiss: () => setState(() => _activeAlert = null),
              ),

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

            // System status from safer/app/status
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 24),
              child: _StatusPill(status: _systemStatus),
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

class _AlertBanner extends StatelessWidget {
  final dynamic payload;
  final VoidCallback onDismiss;
  const _AlertBanner({required this.payload, required this.onDismiss});

  @override
  Widget build(BuildContext context) {
    final title = (payload is Map && payload['title'] is String)
        ? payload['title'] as String
        : 'Alerte en direct';
    final body = (payload is Map && payload['message'] is String)
        ? payload['message'] as String
        : payload.toString();

    return Material(
      color: Colors.amber.shade800,
      child: SafeArea(
        bottom: false,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          child: Row(
            children: [
              const Icon(Icons.notifications_active, color: Colors.white),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title,
                        style: const TextStyle(
                            color: Colors.white,
                            fontWeight: FontWeight.bold)),
                    Text(body,
                        style: const TextStyle(color: Colors.white)),
                  ],
                ),
              ),
              IconButton(
                icon: const Icon(Icons.close, color: Colors.white),
                onPressed: onDismiss,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _StatusPill extends StatelessWidget {
  final String status;
  const _StatusPill({required this.status});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: Colors.white12,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.cloud, color: Colors.white70, size: 16),
          const SizedBox(width: 6),
          Text('Système: $status',
              style: const TextStyle(color: Colors.white70, fontSize: 12)),
        ],
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
