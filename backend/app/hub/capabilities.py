"""Canonical capability codes and device categories shared by every adapter."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

CATEGORIES: List[str] = [
    "switch", "plug", "light", "cover", "thermostat",
    "sensor_contact", "sensor_motion", "sensor_temperature", "sensor_humidity", "sensor_smoke",
    "sensor_water", "sensor_gas", "sensor_multi",
    "camera", "nvr", "doorbell", "lock", "siren", "alarm_panel", "alarm_zone", "gateway", "remote", "generic",
]

SECURITY_MODES: List[str] = ["disarmed", "armed_home", "armed_away", "armed_night"]

# Category metadata used by the app's "Add manually" grid and default icons.
CATEGORY_INFO: Dict[str, Dict[str, str]] = {
    "switch": {"name": "Interrupteur", "name_en": "Switch", "icon": "toggle_on", "group": "electrical"},
    "plug": {"name": "Prise", "name_en": "Plug", "icon": "power", "group": "electrical"},
    "light": {"name": "Éclairage", "name_en": "Lighting", "icon": "lightbulb", "group": "lighting"},
    "cover": {"name": "Volet / Rideau", "name_en": "Cover", "icon": "blinds", "group": "electrical"},
    "thermostat": {"name": "Thermostat", "name_en": "Thermostat", "icon": "thermostat", "group": "climate"},
    "sensor_contact": {"name": "Capteur porte/fenêtre", "name_en": "Door/window sensor", "icon": "door_front", "group": "sensors"},
    "sensor_motion": {"name": "Détecteur de mouvement", "name_en": "Motion sensor", "icon": "motion_photos_on", "group": "sensors"},
    "sensor_temperature": {"name": "Capteur de température", "name_en": "Temperature sensor", "icon": "device_thermostat", "group": "sensors"},
    "sensor_humidity": {"name": "Capteur d'humidité", "name_en": "Humidity sensor", "icon": "water_drop", "group": "sensors"},
    "sensor_smoke": {"name": "Détecteur de fumée", "name_en": "Smoke detector", "icon": "local_fire_department", "group": "sensors"},
    "sensor_water": {"name": "Capteur d'inondation", "name_en": "Water leak sensor", "icon": "water", "group": "sensors"},
    "sensor_gas": {"name": "Détecteur de gaz", "name_en": "Gas detector", "icon": "gas_meter", "group": "sensors"},
    "sensor_multi": {"name": "Capteur multi", "name_en": "Multi sensor", "icon": "sensors", "group": "sensors"},
    "camera": {"name": "Caméra", "name_en": "Camera", "icon": "videocam", "group": "cameras"},
    "nvr": {"name": "Enregistreur NVR/DVR", "name_en": "NVR/DVR", "icon": "dns", "group": "cameras"},
    "doorbell": {"name": "Sonnette vidéo", "name_en": "Video doorbell", "icon": "doorbell", "group": "cameras"},
    "lock": {"name": "Serrure", "name_en": "Lock", "icon": "lock", "group": "security"},
    "siren": {"name": "Sirène", "name_en": "Siren", "icon": "campaign", "group": "security"},
    "alarm_panel": {"name": "Centrale d'alarme", "name_en": "Alarm panel", "icon": "shield", "group": "security"},
    "alarm_zone": {"name": "Zone d'alarme", "name_en": "Alarm zone", "icon": "radar", "group": "security"},
    "gateway": {"name": "Passerelle / Hub", "name_en": "Gateway / Hub", "icon": "hub", "group": "gateway"},
    "remote": {"name": "Télécommande", "name_en": "Remote", "icon": "settings_remote", "group": "electrical"},
    "generic": {"name": "Autre appareil", "name_en": "Other device", "icon": "devices_other", "group": "other"},
}

CATEGORY_GROUPS: Dict[str, Dict[str, str]] = {
    "electrical": {"name": "Électrique", "name_en": "Electrical", "icon": "electrical_services"},
    "lighting": {"name": "Éclairage", "name_en": "Lighting", "icon": "light"},
    "climate": {"name": "Climat", "name_en": "Climate", "icon": "ac_unit"},
    "sensors": {"name": "Capteurs", "name_en": "Sensors", "icon": "sensors"},
    "cameras": {"name": "Caméras & vidéo", "name_en": "Cameras & video", "icon": "videocam"},
    "security": {"name": "Sécurité", "name_en": "Security", "icon": "security"},
    "gateway": {"name": "Passerelles", "name_en": "Gateways", "icon": "hub"},
    "other": {"name": "Autres", "name_en": "Others", "icon": "devices_other"},
}

# Codes whose transitions produce a DeviceEvent (and, for alarm-class codes, a Message).
NOTABLE_CODES: Dict[str, Dict[str, Any]] = {
    "motion": {"kind": "alarm", "severity": "warning", "when": True, "title": "Mouvement détecté"},
    "contact": {"kind": "alarm", "severity": "warning", "when": True, "title": "Ouverture détectée"},
    "smoke": {"kind": "alarm", "severity": "critical", "when": True, "title": "Fumée détectée"},
    "co": {"kind": "alarm", "severity": "critical", "when": True, "title": "Monoxyde de carbone détecté"},
    "water_leak": {"kind": "alarm", "severity": "critical", "when": True, "title": "Fuite d'eau détectée"},
    "gas": {"kind": "alarm", "severity": "critical", "when": True, "title": "Fuite de gaz détectée"},
    "alarm": {"kind": "alarm", "severity": "critical", "when": True, "title": "Alarme déclenchée"},
    "tamper": {"kind": "alarm", "severity": "warning", "when": True, "title": "Sabotage détecté"},
    "doorbell_pressed": {"kind": "home", "severity": "info", "when": True, "title": "Quelqu'un sonne à la porte"},
    "locked": {"kind": "home", "severity": "info", "when": None, "title": "Serrure"},
    "arm_mode": {"kind": "home", "severity": "info", "when": None, "title": "Mode de sécurité"},
    "online": {"kind": "notice", "severity": "info", "when": False, "title": "Appareil hors ligne"},
}


def cap(code: str, type_: str, writable: bool = False, **extra: Any) -> Dict[str, Any]:
    """Build a capability dict (helper for adapters)."""
    data: Dict[str, Any] = {"code": code, "type": type_, "writable": writable}
    for key, value in extra.items():
        if value is not None:
            data[key] = value
    return data


# Handy presets -----------------------------------------------------------------
def switch_caps(gangs: int = 1) -> List[Dict[str, Any]]:
    """Capabilities for a 1..n gang switch."""
    if gangs <= 1:
        return [cap("switch", "bool", True)]
    return [cap(f"switch_{i}", "bool", True) for i in range(1, gangs + 1)]


def light_caps(dimmable: bool = True, color_temp: bool = False, color: bool = False) -> List[Dict[str, Any]]:
    """Capabilities for lights."""
    caps = [cap("switch", "bool", True)]
    if dimmable:
        caps.append(cap("brightness", "int", True, min=0, max=100, step=1, unit="%"))
    if color_temp:
        caps.append(cap("color_temp", "int", True, min=2700, max=6500, step=50, unit="K"))
    if color:
        caps.append(cap("color", "color", True))
        caps.append(cap("work_mode", "enum", True, values=["white", "colour", "scene"]))
    return caps


def camera_caps(ptz: bool = False, siren: bool = False, light: bool = False) -> List[Dict[str, Any]]:
    """Capabilities for cameras / NVR channels."""
    caps = [
        cap("stream_main", "string", False),
        cap("stream_sub", "string", False),
        cap("snapshot", "string", False),
        cap("motion", "bool", False),
        cap("recording", "bool", False),
    ]
    if ptz:
        caps.append(cap("ptz", "enum", True, values=["up", "down", "left", "right", "zoom_in", "zoom_out", "stop"]))
    if siren:
        caps.append(cap("siren", "bool", True))
    if light:
        caps.append(cap("light", "bool", True))
    return caps


def alarm_panel_caps() -> List[Dict[str, Any]]:
    """Capabilities for alarm panels."""
    return [
        cap("arm_mode", "enum", True, values=SECURITY_MODES),
        cap("alarm", "bool", False),
        cap("triggered_zone", "string", False),
        cap("ready", "bool", False),
    ]


def alarm_zone_caps() -> List[Dict[str, Any]]:
    """Capabilities for alarm zones / sensors attached to a panel."""
    return [
        cap("open", "bool", False),
        cap("alarm", "bool", False),
        cap("bypass", "bool", True),
        cap("tamper", "bool", False),
        cap("battery", "int", False, unit="%"),
        cap("signal", "int", False, unit="%"),
    ]


def sensor_caps(category: str) -> List[Dict[str, Any]]:
    """Capabilities for the sensor_* categories."""
    mapping = {
        "sensor_contact": [cap("contact", "bool")],
        "sensor_motion": [cap("motion", "bool")],
        "sensor_temperature": [cap("temperature", "float", unit="°C")],
        "sensor_humidity": [cap("humidity", "float", unit="%")],
        "sensor_smoke": [cap("smoke", "bool")],
        "sensor_water": [cap("water_leak", "bool")],
        "sensor_gas": [cap("gas", "bool")],
        "sensor_multi": [cap("motion", "bool"), cap("temperature", "float", unit="°C"), cap("humidity", "float", unit="%"), cap("illuminance", "float", unit="lx")],
    }
    caps = list(mapping.get(category, []))
    caps.append(cap("battery", "int", unit="%"))
    return caps


def lock_caps() -> List[Dict[str, Any]]:
    """Capabilities for locks."""
    return [cap("locked", "bool", True), cap("door", "bool"), cap("battery", "int", unit="%")]


def thermostat_caps() -> List[Dict[str, Any]]:
    """Capabilities for thermostats."""
    return [
        cap("temp_current", "float", unit="°C"),
        cap("temp_set", "float", True, min=5, max=35, step=0.5, unit="°C"),
        cap("mode", "enum", True, values=["off", "heat", "cool", "auto"]),
        cap("humidity_current", "float", unit="%"),
    ]


def cover_caps() -> List[Dict[str, Any]]:
    """Capabilities for covers."""
    return [cap("position", "int", True, min=0, max=100, unit="%"), cap("control", "enum", True, values=["open", "close", "stop"])]


def find_capability(capabilities: List[Dict[str, Any]], code: str) -> Optional[Dict[str, Any]]:
    """Look up a capability by code."""
    for item in capabilities or []:
        if item.get("code") == code:
            return item
    return None


def coerce_value(capability: Dict[str, Any], value: Any) -> Any:
    """Validate/coerce a command value against a capability. Raises ValueError."""
    ctype = capability.get("type", "string")
    if ctype == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str) and value.lower() in ("true", "on", "1", "false", "off", "0"):
            return value.lower() in ("true", "on", "1")
        raise ValueError(f"{capability['code']} expects a boolean")
    if ctype in ("int", "float"):
        try:
            number = int(value) if ctype == "int" else float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{capability['code']} expects a number") from exc
        if "min" in capability and number < capability["min"]:
            raise ValueError(f"{capability['code']} below minimum {capability['min']}")
        if "max" in capability and number > capability["max"]:
            raise ValueError(f"{capability['code']} above maximum {capability['max']}")
        return number
    if ctype == "enum":
        values = capability.get("values") or []
        if values and value not in values:
            raise ValueError(f"{capability['code']} must be one of {values}")
        return value
    if ctype == "color":
        if not isinstance(value, dict) or not {"h", "s", "v"} <= set(value.keys()):
            raise ValueError("color expects {h, s, v}")
        return {"h": float(value["h"]) % 360, "s": max(0.0, min(100.0, float(value["s"]))), "v": max(0.0, min(100.0, float(value["v"])))}
    return value
