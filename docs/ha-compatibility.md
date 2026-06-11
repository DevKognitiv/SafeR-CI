# SafeR Mobile — Smart-Device & Protocol Compatibility

## How "all devices, all protocols" actually works

A phone has no Zigbee, Z-Wave, Thread or Matter radio, so no mobile app can
talk to those devices directly. The SafeR mobile app gets universal device
support the same way every serious smart-home app does: **Home Assistant is
the protocol hub**, and the app speaks HA's WebSocket/REST API. Any device HA
can integrate — across 2 800+ integrations — appears in the app as an entity.

```
 Zigbee ─┐
 Z-Wave ─┤
 Matter ─┤
 Thread ─┼─▶ Home Assistant ─▶ WebSocket API ─▶ SafeR mobile (HaClient)
 WiFi   ─┤        │
 BLE    ─┤        └────────────▶ MQTT broker ──▶ SafeR mobile (HomeAssistantService)
 KNX    ─┤                       (safer/* topics, SOS + push bridge)
 Modbus ─┘
```

Protocols covered transitively via HA integrations include (not exhaustive):
Matter, Thread, Zigbee (ZHA / zigbee2mqtt), Z-Wave (Z-Wave JS), WiFi/LAN,
Bluetooth/BLE, MQTT, KNX, Modbus, ONVIF, ESPHome, HomeKit-bridged devices,
Tuya, Shelly, Sonoff, Xiaomi, Philips Hue, IKEA, Aqara, and cloud services.

## What the app implements (entity-layer coverage)

`mobile/lib/services/ha_client.dart`:

- Long-lived-token auth over the HA WebSocket API
- `get_states` snapshot + live `state_changed` subscription
- Area, device and entity registries — with live re-sync on
  `*_registry_updated` events (areas/renames/visibility never go stale)
- Dashboard visibility honoring `entity_category` (diagnostic/config),
  `hidden_by` and `disabled_by`, exactly like HA's own UI
- Area resolution like HA: entity area, else its device's area
- Automatic reconnect (exponential backoff, 1 s → 60 s cap, jitter),
  heartbeat ping every 25 s to detect half-dead links
- REST fallback for service calls when the socket is down, plus a
  REST-based connection test in the settings sheet

### Per-domain actions (correct semantics, not blanket turn_on/off)

| Domain | Tile tap | Detail sheet |
|---|---|---|
| light | toggle | brightness slider |
| switch / input_boolean / siren / remote / humidifier | toggle | switch |
| fan | toggle | speed (percentage) |
| cover / valve | toggle (open↔close) | open / stop / close + position |
| lock | lock ↔ unlock | lock / unlock (+ code) |
| climate | on/off toggle | target temp stepper + HVAC modes |
| water_heater | detail | on/off |
| media_player | play/pause | transport + volume |
| vacuum | start ↔ dock | start / pause / dock |
| lawn_mower | start ↔ dock | — |
| alarm_control_panel | detail only (safety) | disarm / arm home / away / night + code |
| scene | activate | activate |
| script / automation | run / toggle | run now + enable switch |
| button / input_button | press | press |
| select / input_select | detail | option dropdown |
| number / input_number | detail | value slider |
| sensor / binary_sensor / weather / camera / anything else | detail | attribute view |

**Unknown domains never break the app**: anything not listed renders with a
generic tile and a read-only attribute sheet, so a brand-new HA integration
is usable on day one.

### SafeR MQTT bridge

`mobile/lib/services/ha_service.dart` connects to the HA Mosquitto broker
(`mqtt_client`, optional TLS) for the SafeR-specific channels:
`safer/app/updates`, `safer/app/status` (inbound) and `safer/mobile/sos`
(outbound SOS with GPS), matching the automations in `ha-config/`.

## Honest limitations / roadmap

- **Camera streaming** — state/attributes only; no HLS/WebRTC player yet.
- **Light color control** — brightness only; color temp / RGB pickers next.
- **Token storage** — SharedPreferences today; move to
  `flutter_secure_storage`.
- **No local-radio fallback** — without an HA instance the dashboard cannot
  control devices (the SafeR MQTT bridge still works against a bare broker).
- Validation note: this environment has no Flutter SDK, so the suite was not
  run through `flutter analyze` here — run it in CI / locally before release.
