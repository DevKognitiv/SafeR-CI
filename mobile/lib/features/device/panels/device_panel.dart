import 'package:flutter/widgets.dart';

import '../../../core/models/device.dart';
import 'alarm_panel.dart';
import 'camera_panel.dart';
import 'cover_panel.dart';
import 'gateway_panel.dart';
import 'generic_panel.dart';
import 'light_panel.dart';
import 'lock_panel.dart';
import 'sensor_panel.dart';
import 'switch_panel.dart';
import 'thermostat_panel.dart';

/// Pick the control panel for a device category (Tuya-style "product panel").
Widget panelForDevice(Device device) {
  switch (device.category) {
    case 'switch':
    case 'plug':
    case 'siren':
      return SwitchPanel(device: device);
    case 'light':
      return LightPanel(device: device);
    case 'cover':
      return CoverPanel(device: device);
    case 'thermostat':
      return ThermostatPanel(device: device);
    case 'sensor_contact':
    case 'sensor_motion':
    case 'sensor_temperature':
    case 'sensor_humidity':
    case 'sensor_smoke':
    case 'sensor_water':
    case 'sensor_gas':
    case 'sensor_multi':
    case 'alarm_zone':
      return SensorPanel(device: device);
    case 'camera':
    case 'doorbell':
      return CameraPanel(device: device);
    case 'nvr':
      return device.hasCapability('stream_main') ? CameraPanel(device: device) : GatewayPanel(device: device);
    case 'lock':
      return LockPanel(device: device);
    case 'alarm_panel':
      return AlarmPanel(device: device);
    case 'gateway':
      return GatewayPanel(device: device);
    default:
      return GenericPanel(device: device);
  }
}
