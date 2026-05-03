# Home Assistant Integration Guide for SafeR CI

This document describes the HA to Mobile App integration.

## Architecture

HA Node (Raspberry Pi 4) controls all SafeR mobile app entities via:
1. MQTT bidirectional messaging
2. REST commands to FastAPI/Next.js backends
3. Webhooks from mobile app to HA

## Files

- configuration.yaml - Master HA config
- rest_commands.yaml - HTTP calls to SafeR API
- secrets.yaml.example - Credentials template
- entities/safer_entities.yaml - 50+ entity definitions
- dashboards/safer_dashboard.yaml - 6-view Lovelace UI
- automations/mobile_app_control.yaml - 9 bidirectional automations
- scripts/safer_scripts.yaml - 7 emergency scripts

## MQTT Topics

Incoming (sensors to HA):
- safer/cocody/panic -> binary_sensor.panic_button_zone_cocody
- safer/sensors/fire_smoke -> binary_sensor.fire_smoke_sensor
- safer/sensors/flood -> binary_sensor.flood_sensor
- safer/mobile/sos -> Triggers SOS automation
- safer/mobile/all_clear -> Triggers end-of-alert

Outgoing (HA to mobile app):
- safer/app/updates -> Real-time Flutter updates
- safer/app/status -> Global status (ALL_CLEAR etc)
- safer/system/mode -> OFFLINE_MODE if internet lost

## Quick Setup

1. Flash HAOS on Raspberry Pi 4
2. Install Mosquitto MQTT broker add-on
3. Clone SafeR-CI repo and copy ha-config/
4. Copy secrets.yaml.example to secrets.yaml and fill in values
5. Import safer_dashboard.yaml into Lovelace
6. Test: mosquitto_pub -h localhost -t safer/cocody/panic -m ALERT

## Emergency Services Integration

- Police (170): script.safer_notify_police
- Pompiers (180): script.safer_notify_pompiers
- SAMU (185): script.safer_notify_samu
- Gendarmerie (111): script.safer_notify_gendarmerie

All scripts send SMS via Twilio and update the FastAPI backend.

## Vercel Dashboard Integration

HA calls rest_command.safer_notify_dashboard on every alert:
POST https://safe-r-ci.vercel.app/api/incidents/webhook/ha

This updates the map and stats in real-time on the Vercel dashboard.
