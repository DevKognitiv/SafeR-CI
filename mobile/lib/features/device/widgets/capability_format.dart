import 'dart:convert';

import 'package:flutter/widgets.dart';

import '../../../core/i18n.dart';
import '../../../core/models/device.dart';

const _gangPattern = r'^switch_(\d+)$';

/// Human label for a capability code (FR/EN), falling back to the hub label or a humanised code.
String capabilityLabel(BuildContext context, Capability cap) {
  const labels = <String, (String, String)>{
    'switch': ('Alimentation', 'Power'),
    'brightness': ('Luminosité', 'Brightness'),
    'color_temp': ('Température de couleur', 'Colour temperature'),
    'color': ('Couleur', 'Colour'),
    'work_mode': ('Mode', 'Mode'),
    'power': ('Puissance', 'Power'),
    'energy': ('Énergie', 'Energy'),
    'position': ('Position', 'Position'),
    'control': ('Commande', 'Control'),
    'temp_current': ('Température actuelle', 'Current temperature'),
    'temp_set': ('Consigne', 'Setpoint'),
    'mode': ('Mode', 'Mode'),
    'humidity_current': ('Humidité', 'Humidity'),
    'contact': ('Contact', 'Contact'),
    'motion': ('Mouvement', 'Motion'),
    'temperature': ('Température', 'Temperature'),
    'humidity': ('Humidité', 'Humidity'),
    'illuminance': ('Luminosité ambiante', 'Illuminance'),
    'smoke': ('Fumée', 'Smoke'),
    'co': ('Monoxyde de carbone', 'Carbon monoxide'),
    'water_leak': ("Fuite d'eau", 'Water leak'),
    'gas': ('Gaz', 'Gas'),
    'battery': ('Batterie', 'Battery'),
    'tamper': ('Sabotage', 'Tamper'),
    'signal': ('Signal', 'Signal'),
    'stream_main': ('Flux principal', 'Main stream'),
    'stream_sub': ('Flux secondaire', 'Sub stream'),
    'snapshot': ('Instantané', 'Snapshot'),
    'ptz': ('PTZ', 'PTZ'),
    'recording': ('Enregistrement', 'Recording'),
    'privacy_mode': ('Mode privé', 'Privacy mode'),
    'night_vision': ('Vision nocturne', 'Night vision'),
    'siren': ('Sirène', 'Siren'),
    'light': ('Lumière', 'Light'),
    'doorbell_pressed': ('Sonnette', 'Doorbell'),
    'locked': ('Verrouillage', 'Lock'),
    'door': ('Porte', 'Door'),
    'volume': ('Volume', 'Volume'),
    'arm_mode': ("Mode d'armement", 'Arm mode'),
    'alarm': ('Alarme', 'Alarm'),
    'triggered_zone': ('Zone déclenchée', 'Triggered zone'),
    'ready': ('Prêt à armer', 'Ready to arm'),
    'bypass': ('Exclusion', 'Bypass'),
    'open': ('Ouverture', 'Open'),
    'child_count': ('Appareils connectés', 'Connected devices'),
  };
  final entry = labels[cap.code];
  if (entry != null) return context.tr(fr: entry.$1, en: entry.$2);
  final gang = RegExp(_gangPattern).firstMatch(cap.code);
  if (gang != null) return context.tr(fr: 'Voie ${gang.group(1)}', en: 'Gang ${gang.group(1)}');
  final label = cap.label;
  if (label != null && label.trim().isNotEmpty) return label;
  return humanize(cap.code);
}

/// Human label for an enum value (open/close/heat/cool/white/colour...).
String enumValueLabel(BuildContext context, String value) {
  const labels = <String, (String, String)>{
    'open': ('Ouvrir', 'Open'),
    'close': ('Fermer', 'Close'),
    'stop': ('Stop', 'Stop'),
    'off': ('Arrêt', 'Off'),
    'on': ('Activé', 'On'),
    'auto': ('Auto', 'Auto'),
    'heat': ('Chauffage', 'Heat'),
    'cool': ('Climatisation', 'Cool'),
    'white': ('Blanc', 'White'),
    'colour': ('Couleur', 'Colour'),
    'color': ('Couleur', 'Colour'),
    'scene': ('Scène', 'Scene'),
    'low': ('Faible', 'Low'),
    'middle': ('Moyen', 'Medium'),
    'high': ('Fort', 'High'),
    'up': ('Haut', 'Up'),
    'down': ('Bas', 'Down'),
    'left': ('Gauche', 'Left'),
    'right': ('Droite', 'Right'),
    'zoom_in': ('Zoom +', 'Zoom in'),
    'zoom_out': ('Zoom −', 'Zoom out'),
  };
  final entry = labels[value];
  if (entry != null) return context.tr(fr: entry.$1, en: entry.$2);
  if (value == 'disarmed' || value.startsWith('armed_')) return securityModeLabel(context, value);
  return humanize(value);
}

/// "temp_current" -> "Temp current".
String humanize(String code) {
  final words = code.replaceAll(RegExp(r'^raw_'), '').split(RegExp(r'[_\s]+')).where((w) => w.isNotEmpty).toList();
  if (words.isEmpty) return code;
  final first = words.first;
  return [first[0].toUpperCase() + first.substring(1), ...words.skip(1)].join(' ');
}

/// Format a state value for display ("24.5 °C", "Oui", "open").
String formatCapabilityValue(BuildContext context, Capability cap, dynamic value) {
  if (value == null) return '—';
  switch (cap.type) {
    case 'bool':
      final on = value == true || value == 1 || value == 'true' || value == 'on';
      return on ? context.tr(fr: 'Oui', en: 'Yes') : context.tr(fr: 'Non', en: 'No');
    case 'int':
    case 'float':
      final n = value is num ? value : num.tryParse(value.toString());
      if (n == null) return value.toString();
      final text = cap.type == 'int' || n == n.roundToDouble() && (cap.step ?? 1) >= 1 ? n.round().toString() : n.toStringAsFixed(1);
      return cap.unit == null ? text : '$text ${cap.unit}';
    case 'enum':
      return enumValueLabel(context, value.toString());
    case 'json':
    case 'color':
      if (value is Map || value is List) return jsonEncode(value);
      return value.toString();
    default:
      return value.toString();
  }
}

/// Format a plain number with a unit.
String formatNumber(num? value, {String? unit, int decimals = 1}) {
  if (value == null) return '—';
  final text = value == value.roundToDouble() ? value.round().toString() : value.toStringAsFixed(decimals);
  return unit == null ? text : '$text $unit';
}
