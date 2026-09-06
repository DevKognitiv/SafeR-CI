import 'package:flutter/material.dart';

import '../../../core/i18n.dart';
import '../../../core/models/models.dart';

/// The four home security modes, in display order.
const List<String> kSecurityModes = ['disarmed', 'armed_home', 'armed_away', 'armed_night'];

/// Operators accepted by `device_state` triggers and conditions.
const List<String> kRuleOps = ['eq', 'ne', 'gt', 'lt', 'gte', 'lte', 'changed'];

IconData securityModeIcon(String mode) {
  switch (mode) {
    case 'armed_away':
      return Icons.shield;
    case 'armed_home':
      return Icons.home;
    case 'armed_night':
      return Icons.bedtime;
    default:
      return Icons.lock_open;
  }
}

Device? findDevice(List<Device> devices, String? id) {
  if (id == null) return null;
  for (final d in devices) {
    if (d.id == id) return d;
  }
  return null;
}

Scene? findScene(List<Scene> scenes, String? id) {
  if (id == null) return null;
  for (final s in scenes) {
    if (s.id == id) return s;
  }
  return null;
}

String deviceName(BuildContext context, List<Device> devices, String? id) =>
    findDevice(devices, id)?.name ?? context.tr(fr: 'Appareil inconnu', en: 'Unknown device');

const Map<String, (String, String)> _capabilityLabels = {
  'switch': ('Interrupteur', 'Switch'),
  'power': ('Puissance', 'Power'),
  'energy': ('Énergie', 'Energy'),
  'brightness': ('Luminosité', 'Brightness'),
  'color_temp': ('Température de couleur', 'Colour temperature'),
  'color': ('Couleur', 'Colour'),
  'work_mode': ('Mode', 'Mode'),
  'position': ('Position', 'Position'),
  'control': ('Commande', 'Control'),
  'temp_current': ('Température', 'Temperature'),
  'temp_set': ('Consigne', 'Target temperature'),
  'mode': ('Mode', 'Mode'),
  'humidity_current': ('Humidité', 'Humidity'),
  'contact': ('Ouverture', 'Contact'),
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
  'snapshot': ('Capture', 'Snapshot'),
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
  'ready': ('Prêt', 'Ready'),
  'bypass': ('Exclusion', 'Bypass'),
  'open': ('Ouvert', 'Open'),
  'child_count': ('Appareils enfants', 'Child devices'),
};

const Map<String, Map<String, (String, String)>> _enumLabels = {
  'control': {'open': ('Ouvrir', 'Open'), 'close': ('Fermer', 'Close'), 'stop': ('Stop', 'Stop')},
  'mode': {'off': ('Arrêt', 'Off'), 'heat': ('Chauffage', 'Heat'), 'cool': ('Refroidissement', 'Cool'), 'auto': ('Auto', 'Auto')},
  'work_mode': {'white': ('Blanc', 'White'), 'colour': ('Couleur', 'Colour'), 'scene': ('Scène', 'Scene')},
  'night_vision': {'auto': ('Auto', 'Auto'), 'on': ('Activée', 'On'), 'off': ('Désactivée', 'Off')},
  'volume': {'low': ('Faible', 'Low'), 'middle': ('Moyen', 'Medium'), 'high': ('Fort', 'High')},
  'ptz': {
    'up': ('Haut', 'Up'),
    'down': ('Bas', 'Down'),
    'left': ('Gauche', 'Left'),
    'right': ('Droite', 'Right'),
    'zoom_in': ('Zoom +', 'Zoom in'),
    'zoom_out': ('Zoom −', 'Zoom out'),
    'stop': ('Stop', 'Stop'),
  },
};

/// Human label of a capability code ("brightness" -> "Luminosité").
String capabilityLabel(BuildContext context, String code, {Capability? capability}) {
  final entry = _capabilityLabels[code];
  if (entry != null) return context.tr(fr: entry.$1, en: entry.$2);
  final gang = RegExp(r'^switch_(\d+)$').firstMatch(code);
  if (gang != null) return context.tr(fr: 'Interrupteur ${gang[1]}', en: 'Switch ${gang[1]}');
  final label = capability?.label;
  if (label != null && label.isNotEmpty) return label;
  return code.replaceAll('_', ' ');
}

/// Human label of an enum value for a given code ("cool" -> "Refroidissement").
String enumLabel(BuildContext context, String code, String value) {
  if (code == 'arm_mode' || kSecurityModes.contains(value)) return securityModeLabel(context, value);
  final entry = _enumLabels[code]?[value];
  if (entry != null) return context.tr(fr: entry.$1, en: entry.$2);
  return value;
}

bool isTruthy(dynamic value) => value == true || value == 1 || value == 'true' || value == 'on';

String _inferType(dynamic value) {
  if (value is bool) return 'bool';
  if (value is int) return 'int';
  if (value is num) return 'float';
  if (value is Map && value.containsKey('h')) return 'color';
  return 'string';
}

String _formatNumber(num n) => n == n.roundToDouble() ? '${n.round()}' : n.toStringAsFixed(1);

String _boolVerb(BuildContext context, String code, bool on) {
  if (code == 'switch' || code.startsWith('switch_') || code == 'light' || code == 'siren') {
    return on ? context.tr(fr: 'allumer', en: 'turn on') : context.tr(fr: 'éteindre', en: 'turn off');
  }
  if (code == 'locked') return on ? context.tr(fr: 'verrouiller', en: 'lock') : context.tr(fr: 'déverrouiller', en: 'unlock');
  if (code == 'bypass') return on ? context.tr(fr: 'exclure', en: 'bypass') : context.tr(fr: 'inclure', en: 'include');
  return on ? context.tr(fr: 'activer', en: 'enable') : context.tr(fr: 'désactiver', en: 'disable');
}

/// Human label of a value. With [command] true, booleans become verbs ("allumer"),
/// otherwise they read as states ("oui" / "non").
String valueLabel(BuildContext context, {required String code, required dynamic value, Capability? capability, bool command = false}) {
  final type = capability?.type ?? _inferType(value);
  switch (type) {
    case 'bool':
      final on = isTruthy(value);
      if (!command) return on ? context.tr(fr: 'oui', en: 'yes') : context.tr(fr: 'non', en: 'no');
      return _boolVerb(context, code, on);
    case 'int':
    case 'float':
      final n = value is num ? value : num.tryParse('$value');
      final text = n == null ? '$value' : _formatNumber(n);
      final unit = capability?.unit;
      if (unit == null || unit.isEmpty) return text;
      return unit == '%' ? '$text%' : '$text $unit';
    case 'enum':
      return enumLabel(context, code, '$value');
    case 'color':
      if (value is Map) return context.tr(fr: 'teinte ${value['h']}°', en: 'hue ${value['h']}°');
      return '$value';
    default:
      return '$value';
  }
}

String opSymbol(String op) {
  switch (op) {
    case 'ne':
      return '≠';
    case 'gt':
      return '>';
    case 'lt':
      return '<';
    case 'gte':
      return '≥';
    case 'lte':
      return '≤';
    default:
      return '=';
  }
}

String opLabel(BuildContext context, String op) {
  switch (op) {
    case 'ne':
      return context.tr(fr: 'Différent de', en: 'Not equal to');
    case 'gt':
      return context.tr(fr: 'Supérieur à', en: 'Greater than');
    case 'lt':
      return context.tr(fr: 'Inférieur à', en: 'Less than');
    case 'gte':
      return context.tr(fr: 'Supérieur ou égal', en: 'At least');
    case 'lte':
      return context.tr(fr: 'Inférieur ou égal', en: 'At most');
    case 'changed':
      return context.tr(fr: 'Change', en: 'Changes');
    default:
      return context.tr(fr: 'Égal à', en: 'Equal to');
  }
}

/// "45 s", "2 min", "1 min 30 s".
String formatSeconds(BuildContext context, num seconds) {
  final s = seconds.round();
  if (s < 60) return '$s s';
  final m = s ~/ 60;
  final r = s % 60;
  return r == 0 ? '$m min' : '$m min $r s';
}

const List<(String, String)> _dayLabels = [('Lun', 'Mon'), ('Mar', 'Tue'), ('Mer', 'Wed'), ('Jeu', 'Thu'), ('Ven', 'Fri'), ('Sam', 'Sat'), ('Dim', 'Sun')];

/// Short weekday label; the hub uses 0 = Monday … 6 = Sunday.
String dayLabel(BuildContext context, int day) {
  final entry = _dayLabels[day.clamp(0, 6)];
  return context.tr(fr: entry.$1, en: entry.$2);
}

String daysLabel(BuildContext context, List<int> days) {
  final set = days.toSet();
  if (set.isEmpty) return context.tr(fr: 'Jamais', en: 'Never');
  if (set.length >= 7) return context.tr(fr: 'Tous les jours', en: 'Every day');
  if (set.length == 5 && set.containsAll(const [0, 1, 2, 3, 4])) return context.tr(fr: 'En semaine', en: 'Weekdays');
  if (set.length == 2 && set.containsAll(const [5, 6])) return context.tr(fr: 'Week-end', en: 'Weekend');
  return (set.toList()..sort()).map((d) => dayLabel(context, d)).join(', ');
}

String actionTypeLabel(BuildContext context, String type) {
  switch (type) {
    case 'delay':
      return context.tr(fr: 'Délai', en: 'Delay');
    case 'security_mode':
      return context.tr(fr: 'Sécurité', en: 'Security');
    case 'notify':
      return context.tr(fr: 'Notification', en: 'Notification');
    case 'run_scene':
      return context.tr(fr: 'Scène', en: 'Scene');
    default:
      return context.tr(fr: 'Appareil', en: 'Device');
  }
}

IconData actionIcon(String type) {
  switch (type) {
    case 'delay':
      return Icons.timer_outlined;
    case 'security_mode':
      return Icons.shield_outlined;
    case 'notify':
      return Icons.notifications_outlined;
    case 'run_scene':
      return Icons.play_circle_outline;
    default:
      return Icons.devices;
  }
}

String ruleTypeLabel(BuildContext context, String type) {
  switch (type) {
    case 'schedule':
      return context.tr(fr: 'Programmation', en: 'Schedule');
    case 'security_mode':
      return context.tr(fr: 'Mode de sécurité', en: 'Security mode');
    case 'time_range':
      return context.tr(fr: 'Plage horaire', en: 'Time range');
    default:
      return context.tr(fr: "État d'un appareil", en: 'Device state');
  }
}

IconData ruleIcon(String type) {
  switch (type) {
    case 'schedule':
      return Icons.schedule;
    case 'security_mode':
      return Icons.shield_outlined;
    case 'time_range':
      return Icons.timelapse;
    default:
      return Icons.sensors;
  }
}

/// One-line human summary of an action ("Lampe salon allumer", "Attendre 30 s").
String actionSummary(BuildContext context, SceneAction action, {required List<Device> devices, List<Scene> scenes = const []}) {
  switch (action.type) {
    case 'device_command':
      final device = findDevice(devices, action.deviceId);
      final name = device?.name ?? context.tr(fr: 'Appareil inconnu', en: 'Unknown device');
      final code = action.code ?? '';
      final cap = device?.capability(code);
      final type = cap?.type ?? _inferType(action.value);
      final value = valueLabel(context, code: code, value: action.value, capability: cap, command: true);
      if (type == 'bool') return '$name $value';
      return '$name ${capabilityLabel(context, code, capability: cap).toLowerCase()} = $value';
    case 'delay':
      final duration = formatSeconds(context, action.seconds ?? 0);
      return context.tr(fr: 'Attendre $duration', en: 'Wait $duration');
    case 'security_mode':
      final mode = securityModeLabel(context, action.mode ?? 'disarmed');
      return context.tr(fr: 'Mode sécurité : $mode', en: 'Security mode: $mode');
    case 'notify':
      final title = action.title ?? '';
      return context.tr(fr: 'Notification « $title »', en: 'Notification “$title”');
    case 'run_scene':
      final name = findScene(scenes, action.sceneId)?.name ?? context.tr(fr: 'scène inconnue', en: 'unknown scene');
      return context.tr(fr: 'Exécuter la scène $name', en: 'Run scene $name');
    default:
      return action.type;
  }
}

/// One-line human summary of a trigger/condition ("Détecteur couloir mouvement = oui").
String ruleSummary(BuildContext context, Rule rule, {required List<Device> devices}) {
  switch (rule.type) {
    case 'device_state':
      final device = findDevice(devices, rule.deviceId);
      final name = device?.name ?? context.tr(fr: 'Appareil inconnu', en: 'Unknown device');
      final code = rule.code ?? '';
      final cap = device?.capability(code);
      final label = capabilityLabel(context, code, capability: cap).toLowerCase();
      if (rule.op == 'changed') return '$name $label ${context.tr(fr: 'change', en: 'changes')}';
      return '$name $label ${opSymbol(rule.op)} ${valueLabel(context, code: code, value: rule.value, capability: cap)}';
    case 'schedule':
      final time = rule.time ?? '--:--';
      return context.tr(fr: 'À $time · ${daysLabel(context, rule.days)}', en: 'At $time · ${daysLabel(context, rule.days)}');
    case 'security_mode':
      final mode = securityModeLabel(context, rule.mode ?? 'disarmed');
      return context.tr(fr: 'Mode sécurité = $mode', en: 'Security mode = $mode');
    case 'time_range':
      return context.tr(fr: 'Entre ${rule.start ?? '--:--'} et ${rule.end ?? '--:--'}', en: 'Between ${rule.start ?? '--:--'} and ${rule.end ?? '--:--'}');
    default:
      return rule.type;
  }
}
