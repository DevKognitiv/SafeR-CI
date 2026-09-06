import 'package:flutter/widgets.dart';

import 'models/device.dart';

/// Minimal French/English localisation without code generation.
///
/// Usage: `context.tr(fr: 'Accueil', en: 'Home')`. French is the default
/// language of SafeR CI; English is the fallback for everything else.
extension SafeRL10n on BuildContext {
  bool get isEnglish => Localizations.maybeLocaleOf(this)?.languageCode == 'en';

  String tr({required String fr, required String en}) => isEnglish ? en : fr;
}

/// Supported locales.
const List<Locale> kSupportedLocales = [Locale('fr', 'CI'), Locale('fr'), Locale('en')];

/// Human labels for categories (FR/EN).
String categoryLabel(BuildContext context, String category) {
  const labels = <String, (String, String)>{
    'switch': ('Interrupteur', 'Switch'),
    'plug': ('Prise', 'Plug'),
    'light': ('Éclairage', 'Light'),
    'cover': ('Volet', 'Cover'),
    'thermostat': ('Thermostat', 'Thermostat'),
    'sensor_contact': ('Capteur d\'ouverture', 'Contact sensor'),
    'sensor_motion': ('Détecteur de mouvement', 'Motion sensor'),
    'sensor_temperature': ('Température', 'Temperature'),
    'sensor_humidity': ('Humidité', 'Humidity'),
    'sensor_smoke': ('Détecteur de fumée', 'Smoke detector'),
    'sensor_water': ('Capteur inondation', 'Water leak sensor'),
    'sensor_gas': ('Détecteur de gaz', 'Gas detector'),
    'sensor_multi': ('Capteur multi', 'Multi sensor'),
    'camera': ('Caméra', 'Camera'),
    'nvr': ('Enregistreur', 'NVR'),
    'doorbell': ('Sonnette', 'Doorbell'),
    'lock': ('Serrure', 'Lock'),
    'siren': ('Sirène', 'Siren'),
    'alarm_panel': ('Centrale d\'alarme', 'Alarm panel'),
    'alarm_zone': ('Zone', 'Zone'),
    'gateway': ('Passerelle', 'Gateway'),
    'remote': ('Télécommande', 'Remote'),
    'generic': ('Appareil', 'Device'),
  };
  final entry = labels[category];
  if (entry == null) return category;
  return context.tr(fr: entry.$1, en: entry.$2);
}

/// Human labels for security modes (FR/EN).
String securityModeLabel(BuildContext context, String mode) {
  switch (mode) {
    case 'armed_away':
      return context.tr(fr: 'Absent', en: 'Away');
    case 'armed_home':
      return context.tr(fr: 'Présent', en: 'Home');
    case 'armed_night':
      return context.tr(fr: 'Nuit', en: 'Night');
    default:
      return context.tr(fr: 'Désarmé', en: 'Disarmed');
  }
}

/// Relative time ("il y a 5 min").
String timeAgo(BuildContext context, DateTime? time) {
  if (time == null) return '';
  final diff = DateTime.now().difference(time.isUtc ? time.toLocal() : time);
  if (diff.inSeconds < 60) return context.tr(fr: "À l'instant", en: 'Just now');
  if (diff.inMinutes < 60) {
    return context.tr(fr: 'Il y a ${diff.inMinutes} min', en: '${diff.inMinutes} min ago');
  }
  if (diff.inHours < 24) {
    return context.tr(fr: 'Il y a ${diff.inHours} h', en: '${diff.inHours} h ago');
  }
  return context.tr(fr: 'Il y a ${diff.inDays} j', en: '${diff.inDays} d ago');
}

/// Localised short summary of a device state for tiles and rows
/// ("ON · 80%", "FERMÉ"/"CLOSED", "26.5 °C"). Numeric-only summaries come
/// from [Device.stateSummary]; the word-based ones are translated here.
String deviceStateSummary(BuildContext context, Device device) {
  String tr(String fr, String en) => context.tr(fr: fr, en: en);
  final offline = tr('HORS LIGNE', 'OFFLINE');
  switch (device.category) {
    case 'sensor_contact':
      return (device.boolValue('contact') ?? false) ? tr('OUVERT', 'OPEN') : tr('FERMÉ', 'CLOSED');
    case 'sensor_motion':
      return (device.boolValue('motion') ?? false) ? tr('MOUVEMENT', 'MOTION') : tr('CALME', 'CLEAR');
    case 'sensor_smoke':
      return (device.boolValue('smoke') ?? false) ? tr('FUMÉE !', 'SMOKE!') : 'OK';
    case 'sensor_water':
      return (device.boolValue('water_leak') ?? false) ? tr('FUITE !', 'LEAK!') : 'OK';
    case 'sensor_gas':
      return (device.boolValue('gas') ?? false) ? tr('GAZ !', 'GAS!') : 'OK';
    case 'lock':
      return (device.boolValue('locked') ?? false) ? tr('VERROUILLÉE', 'LOCKED') : tr('OUVERTE', 'UNLOCKED');
    case 'alarm_panel':
      return (device.boolValue('alarm') ?? false) ? tr('ALARME !', 'ALARM!') : (device.stringValue('arm_mode') ?? '').toUpperCase();
    case 'alarm_zone':
      if (device.boolValue('alarm') ?? false) return tr('ALARME !', 'ALARM!');
      return (device.boolValue('open') ?? false) ? tr('OUVERT', 'OPEN') : 'OK';
    case 'camera':
    case 'doorbell':
    case 'nvr':
      if (device.boolValue('motion') ?? false) return tr('MOUVEMENT', 'MOTION');
      return device.online ? tr('EN LIGNE', 'ONLINE') : offline;
    case 'light':
    case 'switch':
    case 'plug':
    case 'siren':
    case 'cover':
    case 'thermostat':
    case 'sensor_temperature':
    case 'sensor_humidity':
      return device.stateSummary;
    default:
      return device.online ? '' : offline;
  }
}
