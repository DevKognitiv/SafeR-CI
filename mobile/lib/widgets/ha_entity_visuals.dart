import 'package:flutter/material.dart';

import '../services/ha_client.dart';

/// Icon for an HA domain. Every domain gets something sensible; unknown
/// domains fall back to a generic device icon so any integration renders.
IconData haDomainIcon(String domain) {
  switch (domain) {
    case 'light':
      return Icons.lightbulb;
    case 'switch':
    case 'input_boolean':
      return Icons.toggle_on;
    case 'cover':
      return Icons.blinds;
    case 'valve':
      return Icons.water_damage;
    case 'climate':
      return Icons.thermostat;
    case 'water_heater':
      return Icons.hot_tub;
    case 'humidifier':
      return Icons.water;
    case 'media_player':
      return Icons.speaker;
    case 'fan':
      return Icons.air;
    case 'lock':
      return Icons.lock;
    case 'alarm_control_panel':
      return Icons.shield;
    case 'camera':
      return Icons.videocam;
    case 'binary_sensor':
      return Icons.sensors;
    case 'sensor':
      return Icons.show_chart;
    case 'vacuum':
      return Icons.cleaning_services;
    case 'lawn_mower':
      return Icons.grass;
    case 'scene':
      return Icons.palette;
    case 'script':
      return Icons.play_circle_outline;
    case 'automation':
      return Icons.auto_mode;
    case 'button':
    case 'input_button':
      return Icons.touch_app;
    case 'select':
    case 'input_select':
      return Icons.list;
    case 'number':
    case 'input_number':
      return Icons.tune;
    case 'siren':
      return Icons.campaign;
    case 'remote':
      return Icons.settings_remote;
    case 'weather':
      return Icons.cloud;
    case 'device_tracker':
    case 'person':
      return Icons.person_pin_circle;
    case 'group':
      return Icons.workspaces;
    default:
      return Icons.devices_other;
  }
}

/// Accent color per domain.
Color haDomainColor(String domain) {
  switch (domain) {
    case 'light':
      return Colors.amber;
    case 'switch':
    case 'input_boolean':
    case 'fan':
      return Colors.blueAccent;
    case 'cover':
    case 'valve':
      return Colors.purple;
    case 'climate':
    case 'water_heater':
      return Colors.redAccent;
    case 'humidifier':
      return Colors.lightBlue;
    case 'media_player':
      return Colors.deepPurple;
    case 'lock':
    case 'alarm_control_panel':
      return Colors.brown;
    case 'camera':
      return Colors.blueGrey;
    case 'binary_sensor':
    case 'sensor':
      return Colors.green;
    case 'vacuum':
    case 'lawn_mower':
      return Colors.teal;
    case 'scene':
    case 'script':
    case 'automation':
    case 'button':
    case 'input_button':
      return Colors.orange;
    case 'siren':
      return Colors.red;
    default:
      return Colors.indigo;
  }
}

/// Human-readable state label for tiles and the detail sheet header.
String haStateLabel(HaState e) {
  if (e.isUnavailable) return 'unavailable';
  if (e.domain == 'light' && e.isOn && e.brightness != null) {
    final pct = (e.brightness! / 255 * 100).round();
    return '$pct%';
  }
  if (e.domain == 'cover' && e.coverPosition != null) {
    return '${e.state} · ${e.coverPosition}%';
  }
  if (e.domain == 'climate') {
    final target = e.targetTemperature;
    if (target != null) return '${e.state} · ${target.toStringAsFixed(1)}°';
  }
  final unit = e.unit;
  if (unit != null && unit.isNotEmpty) return '${e.state} $unit';
  return e.state;
}
