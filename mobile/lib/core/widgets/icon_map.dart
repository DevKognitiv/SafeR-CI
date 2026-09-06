import 'package:flutter/material.dart';

/// Resolve Material icon names sent by the hub (capabilities.py / BrandInfo.icon) to IconData.
IconData iconFromName(String? name, {IconData fallback = Icons.devices_other}) {
  if (name == null) return fallback;
  return _icons[name] ?? fallback;
}

/// Names accepted by [iconFromName] (for icon pickers).
List<String> get iconNames => _icons.keys.toList(growable: false);

/// Default icon for a device category.
IconData categoryIcon(String category) {
  switch (category) {
    case 'switch':
      return Icons.toggle_on;
    case 'plug':
      return Icons.power;
    case 'light':
      return Icons.lightbulb;
    case 'cover':
      return Icons.blinds;
    case 'thermostat':
      return Icons.thermostat;
    case 'sensor_contact':
      return Icons.door_front_door;
    case 'sensor_motion':
      return Icons.motion_photos_on;
    case 'sensor_temperature':
      return Icons.device_thermostat;
    case 'sensor_humidity':
      return Icons.water_drop;
    case 'sensor_smoke':
      return Icons.local_fire_department;
    case 'sensor_water':
      return Icons.water;
    case 'sensor_gas':
      return Icons.gas_meter;
    case 'sensor_multi':
      return Icons.sensors;
    case 'camera':
      return Icons.videocam;
    case 'nvr':
      return Icons.dns;
    case 'doorbell':
      return Icons.doorbell;
    case 'lock':
      return Icons.lock;
    case 'siren':
      return Icons.campaign;
    case 'alarm_panel':
      return Icons.shield;
    case 'alarm_zone':
      return Icons.radar;
    case 'gateway':
      return Icons.hub;
    case 'remote':
      return Icons.settings_remote;
    default:
      return Icons.devices_other;
  }
}

const Map<String, IconData> _icons = {
  'toggle_on': Icons.toggle_on,
  'power': Icons.power,
  'lightbulb': Icons.lightbulb,
  'light': Icons.light,
  'blinds': Icons.blinds,
  'thermostat': Icons.thermostat,
  'door_front': Icons.door_front_door,
  'door_front_door': Icons.door_front_door,
  'motion_photos_on': Icons.motion_photos_on,
  'device_thermostat': Icons.device_thermostat,
  'water_drop': Icons.water_drop,
  'local_fire_department': Icons.local_fire_department,
  'water': Icons.water,
  'gas_meter': Icons.gas_meter,
  'sensors': Icons.sensors,
  'videocam': Icons.videocam,
  'dns': Icons.dns,
  'doorbell': Icons.doorbell,
  'lock': Icons.lock,
  'campaign': Icons.campaign,
  'shield': Icons.shield,
  'radar': Icons.radar,
  'hub': Icons.hub,
  'settings_remote': Icons.settings_remote,
  'devices_other': Icons.devices_other,
  'devices': Icons.devices,
  'electrical_services': Icons.electrical_services,
  'ac_unit': Icons.ac_unit,
  'security': Icons.security,
  'science': Icons.science,
  'cloud': Icons.cloud,
  'cloud_queue': Icons.cloud_queue,
  'wb_sunny': Icons.wb_sunny,
  'sunny': Icons.sunny,
  'wb_cloudy': Icons.wb_cloudy,
  'cloudy_snowing': Icons.cloudy_snowing,
  'severe_cold': Icons.severe_cold,
  'snowing': Icons.snowing,
  'storm': Icons.storm,
  'air': Icons.air,
  'nights_stay': Icons.nights_stay,
  'umbrella': Icons.umbrella,
  'thunderstorm': Icons.thunderstorm,
  'foggy': Icons.foggy,
  'grain': Icons.grain,
  'wifi': Icons.wifi,
  'bluetooth': Icons.bluetooth,
  'qr_code_scanner': Icons.qr_code_scanner,
  'qr_code': Icons.qr_code,
  'key': Icons.key,
  'router': Icons.router,
  'home': Icons.home,
  'home_work': Icons.home_work,
  'cable': Icons.cable,
  'cell_tower': Icons.cell_tower,
  'account_circle': Icons.account_circle,
  'link': Icons.link,
  'dialpad': Icons.dialpad,
  'lan': Icons.lan,
  'camera': Icons.camera,
  'videocam_outlined': Icons.videocam_outlined,
  'apartment': Icons.apartment,
  'sos': Icons.sos,
  'warning': Icons.warning,
  'notifications': Icons.notifications,
  'auto_awesome': Icons.auto_awesome,
  'play_circle': Icons.play_circle,
  'schedule': Icons.schedule,
  'bolt': Icons.bolt,
  'bedtime': Icons.bedtime,
  'wb_twilight': Icons.wb_twilight,
  'movie': Icons.movie,
  'celebration': Icons.celebration,
  'flight_takeoff': Icons.flight_takeoff,
  'directions_walk': Icons.directions_walk,
};
