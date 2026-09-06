import 'package:flutter/widgets.dart';

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
