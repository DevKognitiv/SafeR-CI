"""Tuya adapter: Tuya OpenAPI cloud projects (``tuya_cloud``) and LAN control via tinytuya (``tuya_local``).

Cloud protocol (Tuya OpenAPI v1.0, signature v2)
------------------------------------------------
Every request carries the headers ``client_id``, ``sign``, ``t`` (unix ms), ``sign_method=HMAC-SHA256``,
``access_token`` (business endpoints only) and an optional ``nonce``::

    stringToSign = METHOD + "\\n" + sha256(body) + "\\n" + "" + "\\n" + path[?key=value&... sorted by key]
    sign         = HMAC-SHA256(client_id + [access_token] + t + [nonce] + stringToSign, access_secret).upper()

Endpoints used:
    GET  /v1.0/token?grant_type=1                      -> {access_token, refresh_token, uid, expire_time}
    GET  /v1.0/token/{refresh_token}                   -> same shape (refresh)
    GET  /v1.0/users/{uid}/devices                     -> [device]
    GET  /v1.0/iot-01/associated-users/devices         -> {devices, has_more, last_row_key} (paginated)
    GET  /v1.0/devices/{id}                            -> {online, status:[{code,value}], ...}
    GET  /v1.0/devices/{id}/status                     -> [{code, value}]
    GET  /v1.0/devices/{id}/functions                  -> {category, functions:[{code, type, values}]}
    POST /v1.0/devices/{id}/commands                   -> {commands:[{code, value}]}
    POST /v1.0/devices/{id}/stream/actions             -> {url} (camera live stream)

Local protocol
--------------
``tuya_local`` devices are driven with the optional ``tinytuya`` package (device id + 16-char local key +
IP + protocol version). Data points ("DPS") are translated to Tuya function codes with a per-category
table (``LOCAL_DPS_TABLES``, overridable per device via ``config["dps_map"]``) and then go through the very
same code mapping as cloud devices.

All Tuya function codes are normalised to the canonical capability codes of ``app.hub.capabilities``;
unknown codes surface as ``raw_<code>``.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx

from app.hub.adapters.base import (
    AdapterContext, AdapterError, BrandAdapter, BrandInfo, DeviceDraft, DeviceRef, DeviceState, DiscoveredDevice,
    FormField, IntegrationDraft, PairResult, PairingMethod, StreamInfo, require,
)
from app.hub.adapters.registry import registry
from app.hub.capabilities import CATEGORIES, CATEGORY_INFO, cap

logger = logging.getLogger("safer.hub.tuya")

BRAND_ID = "tuya"
PROTOCOL_CLOUD = "tuya_cloud"
PROTOCOL_LOCAL = "tuya_local"
METHOD_CLOUD = "cloud_project"
METHOD_LOCAL = "local_key"

REGIONS: Dict[str, str] = {
    "us": "https://openapi.tuyaus.com",
    "eu": "https://openapi.tuyaeu.com",
    "cn": "https://openapi.tuyacn.com",
    "in": "https://openapi.tuyain.com",
}
LOCAL_VERSIONS: Tuple[str, ...] = ("3.1", "3.3", "3.4", "3.5")
LOCAL_KEY_LENGTH = 16
EMPTY_BODY_SHA256 = hashlib.sha256(b"").hexdigest()
TOKEN_MARGIN_SECONDS = 60  # refresh a little before Tuya expires the token
MAX_DEVICE_PAGES = 50
LOCAL_TIMEOUT_SECONDS = 5

# Tuya OpenAPI response codes (https://developer.tuya.com/en/docs/iot/error-code).
AUTH_ERROR_CODES = {1001, 1002, 1003, 1004, 1005, 1010, 1011, 1012, 1013, 1106, 1400, 28841002, 28841101, 28841105}
TOKEN_ERROR_CODES = {1002, 1010, 1011, 1012, 1400}  # token missing/invalid/expired -> re-authenticate once
NOT_FOUND_CODES = {1108, 2006}  # uri path invalid / user does not exist
UNREACHABLE_CODES = {1000, 2001}  # system error / device offline
FUNCTIONS_OPTIONAL_CODES = {2008, 2009, 2010}  # "not supported" style answers of /functions on read-only devices

# tinytuya error numbers (tinytuya.error_json)
LOCAL_UNREACHABLE = {"901", "902", "905"}
LOCAL_AUTH = {"900", "904", "914"}  # bad json / payload / wrong key or version
LOCAL_INVALID = {"903", "907", "912"}


# ================================================================== category tables
TUYA_CATEGORY_MAP: Dict[str, str] = {
    "kg": "switch", "tdq": "switch", "dlq": "switch",
    "cz": "plug", "pc": "plug",
    "dj": "light", "dd": "light", "xdd": "light", "fwd": "light", "dc": "light", "tgq": "light", "tgkg": "light",
    "cl": "cover", "clkg": "cover", "ckmkzq": "cover",
    "wk": "thermostat", "wkf": "thermostat", "kt": "thermostat",
    "mcs": "sensor_contact",
    "pir": "sensor_motion", "hps": "sensor_motion",
    "wsdcg": "sensor_temperature",
    "ywbj": "sensor_smoke",
    "sj": "sensor_water",
    "rqbj": "sensor_gas", "jwbj": "sensor_gas", "cobj": "sensor_gas",
    "sp": "camera",
    "ms": "lock", "mk": "lock", "jtmspro": "lock",
    "sgbj": "siren",
    "mal": "alarm_panel",
    "wg2": "gateway", "wgsxj": "gateway", "zigbee": "gateway",
    "wxkg": "remote", "wnykq": "remote",
}


def map_category(tuya_category: Optional[str]) -> str:
    """Tuya product category code -> SafeR category (``generic`` when unknown)."""
    code = (tuya_category or "").strip().lower()
    if code in TUYA_CATEGORY_MAP:
        return TUYA_CATEGORY_MAP[code]
    if code.startswith("wg") or "zigbee" in code:
        return "gateway"
    return "generic"


# ================================================================== value codecs
Codec = Callable[[Any, Dict[str, Any], str], Any]

FALSE_WORDS = {"normal", "none", "0", "false", "off", "", "no", "close", "closed"}
BRIGHT_RANGE_V1 = (25, 255)
BRIGHT_RANGE_V2 = (10, 1000)
COLOR_TEMP_RANGE = (2700, 6500)
ARM_MODE_FROM_TUYA = {"disarmed": "disarmed", "arm": "armed_away", "home": "armed_home"}
ARM_MODE_TO_TUYA = {v: k for k, v in ARM_MODE_FROM_TUYA.items()}
BATTERY_STATE = {"low": 10, "middle": 50, "high": 100}
NIGHT_VISION_FROM_TUYA = {"0": "auto", "1": "off", "2": "on"}
NIGHT_VISION_TO_TUYA = {v: k for k, v in NIGHT_VISION_FROM_TUYA.items()}
PTZ_TO_TUYA = {"up": "0", "right": "2", "down": "4", "left": "6"}
TEMP_SIBLINGS = {"temp_current": "temp_set", "temp_set": "temp_current"}


def _num(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _round_half_up(value: float) -> int:
    """Deterministic rounding for device values (Python's round() is half-to-even)."""
    return int(value + 0.5) if value >= 0 else -int(-value + 0.5)


def _scale_of(meta: Dict[str, Any], default: int) -> int:
    scale = _num(meta.get("scale"))
    return int(scale) if scale is not None else default


def _range_of(meta: Dict[str, Any], default: Tuple[float, float]) -> Tuple[float, float]:
    low = _num(meta.get("min"), default[0])
    high = _num(meta.get("max"), default[1])
    if high is None or low is None or high <= low:
        return default
    return low, high


def _flag(value: Any, _meta: Dict[str, Any], _code: str) -> bool:
    """Tuya alarm-ish values ("alarm"/"normal", "pir"/"none", true/false, 1/0) -> bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() not in FALSE_WORDS


def _scaled(default_scale: int) -> Codec:
    def decode(value: Any, meta: Dict[str, Any], _code: str) -> Any:
        number = _num(value)
        if number is None:
            return value
        scale = _scale_of(meta, default_scale)
        return round(number / (10 ** scale), 3) if scale > 0 else number
    return decode


def _unscaled(default_scale: int) -> Codec:
    def encode(value: Any, meta: Dict[str, Any], _code: str) -> Any:
        number = _num(value)
        if number is None:
            return value
        scale = _scale_of(meta, default_scale)
        return int(round(number * (10 ** scale)))
    return encode


def _bright_range(meta: Dict[str, Any], code: str) -> Tuple[float, float]:
    return _range_of(meta, BRIGHT_RANGE_V1 if code == "bright_value" else BRIGHT_RANGE_V2)


def _decode_brightness(value: Any, meta: Dict[str, Any], code: str) -> Any:
    number = _num(value)
    if number is None:
        return value
    low, high = _bright_range(meta, code)
    return int(_clamp(round((number - low) / (high - low) * 100), 0, 100))


def _encode_brightness(value: Any, meta: Dict[str, Any], code: str) -> int:
    low, high = _bright_range(meta, code)
    pct = _clamp(_num(value, 0.0) or 0.0, 0, 100)
    return _round_half_up(low + pct / 100 * (high - low))


def _decode_color_temp(value: Any, meta: Dict[str, Any], _code: str) -> Any:
    number = _num(value)
    if number is None:
        return value
    low, high = _range_of(meta, (0, 1000))
    ratio = _clamp((number - low) / (high - low), 0, 1)
    return int(round(COLOR_TEMP_RANGE[0] + ratio * (COLOR_TEMP_RANGE[1] - COLOR_TEMP_RANGE[0])))


def _encode_color_temp(value: Any, meta: Dict[str, Any], _code: str) -> int:
    low, high = _range_of(meta, (0, 1000))
    kelvin = _clamp(_num(value, COLOR_TEMP_RANGE[0]) or COLOR_TEMP_RANGE[0], *COLOR_TEMP_RANGE)
    ratio = (kelvin - COLOR_TEMP_RANGE[0]) / (COLOR_TEMP_RANGE[1] - COLOR_TEMP_RANGE[0])
    return _round_half_up(low + ratio * (high - low))


def _colour_scale(meta: Dict[str, Any], code: str, sample: Optional[float] = None) -> float:
    for key in ("s", "v"):
        sub = meta.get(key)
        if isinstance(sub, dict) and _num(sub.get("max")):
            return float(sub["max"])
    if code.endswith("_v2") or (sample is not None and sample > 255):
        return 1000.0
    return 255.0


def _decode_colour(value: Any, meta: Dict[str, Any], code: str) -> Any:
    data: Any = value
    if isinstance(value, str):
        text = value.strip()
        try:
            data = json.loads(text)
        except ValueError:
            data = None
        if data is None and re.fullmatch(r"[0-9a-fA-F]{12,14}", text):  # v1 "RRGGBBHHHHSSVV"
            hue = int(text[6:10], 16) if len(text) >= 14 else int(text[6:8], 16)
            sat = int(text[-4:-2], 16)
            val = int(text[-2:], 16)
            return {"h": float(hue % 360), "s": round(sat / 255 * 100, 1), "v": round(val / 255 * 100, 1)}
    if not isinstance(data, dict):
        return value
    sat, val = _num(data.get("s"), 0.0) or 0.0, _num(data.get("v"), 0.0) or 0.0
    scale = _colour_scale(meta, code, max(sat, val))
    return {
        "h": float(_num(data.get("h"), 0.0) or 0.0) % 360,
        "s": round(_clamp(sat / scale * 100, 0, 100), 1),
        "v": round(_clamp(val / scale * 100, 0, 100), 1),
    }


def _encode_colour(value: Any, meta: Dict[str, Any], code: str) -> str:
    if not isinstance(value, dict):
        raise AdapterError("color expects {h, s, v}", "invalid_input")
    scale = _colour_scale(meta, code)
    return json.dumps({
        "h": _round_half_up(float(_num(value.get("h"), 0.0) or 0.0) % 360),
        "s": _round_half_up(_clamp(_num(value.get("s"), 0.0) or 0.0, 0, 100) / 100 * scale),
        "v": _round_half_up(_clamp(_num(value.get("v"), 0.0) or 0.0, 0, 100) / 100 * scale),
    }, separators=(",", ":"))


def _decode_temperature(value: Any, meta: Dict[str, Any], _code: str) -> Any:
    """Thermostat temperatures: ``scale`` from the function metadata, else a plausibility heuristic."""
    number = _num(value)
    if number is None:
        return value
    if "scale" in meta:
        return round(number / (10 ** _scale_of(meta, 0)), 2)
    return round(number / 10, 1) if abs(number) > 60 else number


def _encode_temperature(value: Any, meta: Dict[str, Any], _code: str) -> Any:
    number = _num(value)
    if number is None:
        return value
    scale = _scale_of(meta, 0)
    return int(round(number * (10 ** scale))) if scale > 0 else number


def _decode_position(value: Any, _meta: Dict[str, Any], _code: str) -> Any:
    number = _num(value)
    return int(_clamp(round(number), 0, 100)) if number is not None else value


def _encode_position(value: Any, _meta: Dict[str, Any], _code: str) -> int:
    return int(_clamp(round(_num(value, 0.0) or 0.0), 0, 100))


def _decode_battery_state(value: Any, _meta: Dict[str, Any], _code: str) -> Any:
    return BATTERY_STATE.get(str(value).lower(), value)


def _decode_arm_mode(value: Any, _meta: Dict[str, Any], _code: str) -> Any:
    return ARM_MODE_FROM_TUYA.get(str(value).lower(), value)


def _encode_arm_mode(value: Any, _meta: Dict[str, Any], _code: str) -> Any:
    return ARM_MODE_TO_TUYA.get(str(value), value)


def _decode_night_vision(value: Any, _meta: Dict[str, Any], _code: str) -> Any:
    return NIGHT_VISION_FROM_TUYA.get(str(value), value)


def _encode_night_vision(value: Any, _meta: Dict[str, Any], _code: str) -> Any:
    return NIGHT_VISION_TO_TUYA.get(str(value), value)


def _encode_int(value: Any, _meta: Dict[str, Any], _code: str) -> Any:
    number = _num(value)
    return int(round(number)) if number is not None else value


# ================================================================== function code table
@dataclass(frozen=True)
class CodeSpec:
    """How one Tuya function/status code maps to a canonical capability."""

    canonical: str
    type: Optional[str] = None  # None -> inferred (raw codes)
    writable: bool = False  # default for local devices (cloud uses the /functions list)
    unit: Optional[str] = None
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    values: Optional[Tuple[str, ...]] = None
    decode: Optional[Codec] = None
    encode: Optional[Codec] = None
    values_from_meta: bool = False  # enum range comes from the device's function metadata when present
    range_from_meta: bool = False  # min/max come from the (scaled) function metadata when present

    @property
    def is_raw(self) -> bool:
        """True for pass-through ``raw_<code>`` specs."""
        return self.canonical.startswith("raw_")


_SWITCH = CodeSpec("switch", "bool", True)
_BATTERY = CodeSpec("battery", "int", unit="%", min=0, max=100)
_BRIGHTNESS = CodeSpec("brightness", "int", True, unit="%", min=0, max=100, step=1, decode=_decode_brightness, encode=_encode_brightness)
_COLOR_TEMP = CodeSpec("color_temp", "int", True, unit="K", min=2700, max=6500, step=50, decode=_decode_color_temp, encode=_encode_color_temp)
_COLOR = CodeSpec("color", "color", True, decode=_decode_colour, encode=_encode_colour)
_SMOKE = CodeSpec("smoke", "bool", decode=_flag)
_GAS = CodeSpec("gas", "bool", decode=_flag)
_CO = CodeSpec("co", "bool", decode=_flag)
_MOTION = CodeSpec("motion", "bool", decode=_flag)
_SIREN = CodeSpec("siren", "bool", True)

FUNCTION_MAP: Dict[str, CodeSpec] = {
    # switches / plugs
    "switch": _SWITCH, "switch_led": _SWITCH,
    "cur_power": CodeSpec("power", "float", unit="W", decode=_scaled(1)),
    "add_ele": CodeSpec("energy", "float", unit="kWh", decode=_scaled(3)),
    # lights
    "bright_value": _BRIGHTNESS, "bright_value_v2": _BRIGHTNESS,
    "temp_value": _COLOR_TEMP, "temp_value_v2": _COLOR_TEMP,
    "colour_data": _COLOR, "colour_data_v2": _COLOR,
    "work_mode": CodeSpec("work_mode", "enum", True, values=("white", "colour", "scene"), values_from_meta=True),
    # covers
    "percent_control": CodeSpec("position", "int", True, unit="%", min=0, max=100, decode=_decode_position, encode=_encode_position),
    "position": CodeSpec("position", "int", True, unit="%", min=0, max=100, decode=_decode_position, encode=_encode_position),
    "percent_state": CodeSpec("position", "int", unit="%", min=0, max=100, decode=_decode_position),
    "control": CodeSpec("control", "enum", True, values=("open", "close", "stop"), values_from_meta=True),
    # thermostats
    "temp_current": CodeSpec("temp_current", "float", unit="°C", decode=_decode_temperature),
    "temp_set": CodeSpec("temp_set", "float", True, unit="°C", min=5, max=35, step=0.5, decode=_decode_temperature,
                         encode=_encode_temperature, range_from_meta=True),
    "mode": CodeSpec("mode", "enum", True, values=("off", "heat", "cool", "auto"), values_from_meta=True),
    "humidity_value": CodeSpec("humidity", "float", unit="%", decode=_scaled(0)),
    # sensors
    "doorcontact_state": CodeSpec("contact", "bool", decode=_flag),
    "pir": _MOTION, "presence_state": _MOTION,
    "va_temperature": CodeSpec("temperature", "float", unit="°C", decode=_scaled(1)),
    "va_humidity": CodeSpec("humidity", "float", unit="%", decode=_scaled(0)),
    "smoke_sensor_status": _SMOKE, "smoke_sensor_state": _SMOKE,
    "watersensor_state": CodeSpec("water_leak", "bool", decode=_flag),
    "gas_sensor_status": _GAS, "gas_sensor_state": _GAS,
    "co_status": _CO, "co_state": _CO,
    "battery_percentage": _BATTERY, "battery": _BATTERY, "va_battery": _BATTERY, "battery_value": _BATTERY,
    "battery_state": CodeSpec("battery", "int", unit="%", decode=_decode_battery_state),
    "temper_alarm": CodeSpec("tamper", "bool", decode=_flag),
    # sirens / alarm panels
    "alarm_switch": _SIREN,
    "alarm_volume": CodeSpec("volume", "enum", True, values=("low", "middle", "high"), values_from_meta=True),
    "master_mode": CodeSpec("arm_mode", "enum", True, values=("disarmed", "armed_home", "armed_away"),
                            decode=_decode_arm_mode, encode=_encode_arm_mode),
    "sos_state": CodeSpec("alarm", "bool", decode=_flag),
    # cameras / doorbells
    "basic_private": CodeSpec("privacy_mode", "bool", True),
    "basic_nightvision": CodeSpec("night_vision", "enum", True, values=("auto", "on", "off"),
                                  decode=_decode_night_vision, encode=_encode_night_vision),
    "siren_switch": _SIREN,
    "floodlight_switch": CodeSpec("light", "bool", True),
    "record_switch": CodeSpec("recording", "bool", True),
    "ptz_control": CodeSpec("ptz", "enum", True, values=("up", "down", "left", "right", "zoom_in", "zoom_out", "stop")),
    "doorbell_ring_exist": CodeSpec("doorbell_pressed", "bool", decode=_flag),
}
for _gang in range(1, 9):
    FUNCTION_MAP[f"switch_{_gang}"] = CodeSpec(f"switch_{_gang}", "bool", True)

SENSOR_CATEGORIES = tuple(c for c in CATEGORIES if c.startswith("sensor_"))
# Same Tuya code, different meaning depending on the product category.
CATEGORY_OVERRIDES: Dict[str, Dict[str, CodeSpec]] = {
    "thermostat": {
        "humidity_value": CodeSpec("humidity_current", "float", unit="%", decode=_scaled(0)),
        "va_humidity": CodeSpec("humidity_current", "float", unit="%", decode=_scaled(0)),
    },
}
for _category in SENSOR_CATEGORIES:
    CATEGORY_OVERRIDES[_category] = {
        "temp_current": CodeSpec("temperature", "float", unit="°C", decode=_scaled(1)),
        "bright_value": CodeSpec("illuminance", "float", unit="lx"),
    }

# When several Tuya codes feed the same canonical code, which one wins (lower index = preferred).
READ_PRIORITY: Dict[str, Tuple[str, ...]] = {
    "position": ("percent_state", "position", "percent_control"),
    "brightness": ("bright_value_v2", "bright_value"),
    "color_temp": ("temp_value_v2", "temp_value"),
    "color": ("colour_data_v2", "colour_data"),
    "battery": ("battery_percentage", "va_battery", "battery_value", "battery", "battery_state"),
    "siren": ("alarm_switch", "siren_switch"),
}
WRITE_PRIORITY: Dict[str, Tuple[str, ...]] = {
    "position": ("percent_control", "position"),
    "brightness": ("bright_value_v2", "bright_value"),
    "color_temp": ("temp_value_v2", "temp_value"),
    "color": ("colour_data_v2", "colour_data"),
    "switch": ("switch_led", "switch"),
    "siren": ("alarm_switch", "siren_switch"),
}

TUYA_TYPE_MAP = {"boolean": "bool", "integer": "int", "enum": "enum", "string": "string", "json": "json",
                 "raw": "string", "bitmap": "int"}

# Local DPS id -> Tuya function code, per SafeR category (common Tuya defaults; override with config["dps_map"]).
LOCAL_DPS_TABLES: Dict[str, Dict[str, str]] = {
    "switch": {str(i): f"switch_{i}" for i in range(1, 7)},
    "plug": {"1": "switch", "9": "countdown_1", "17": "add_ele", "18": "cur_current", "19": "cur_power", "20": "cur_voltage"},
    "light": {"20": "switch_led", "21": "work_mode", "22": "bright_value_v2", "23": "temp_value_v2",
              "24": "colour_data_v2", "25": "scene_data_v2", "26": "countdown"},
    "cover": {"1": "control", "2": "percent_control", "3": "percent_state", "7": "work_state"},
    "thermostat": {"1": "switch", "2": "temp_set", "3": "temp_current", "4": "mode", "5": "child_lock"},
    "sensor_contact": {"1": "doorcontact_state", "15": "battery_percentage"},
    "sensor_motion": {"1": "pir", "15": "battery_percentage"},
    "sensor_smoke": {"1": "smoke_sensor_status", "15": "battery_percentage"},
    "sensor_water": {"1": "watersensor_state", "15": "battery_percentage"},
    "sensor_gas": {"1": "gas_sensor_status", "15": "battery_percentage"},
    "sensor_temperature": {"1": "va_temperature", "2": "va_humidity", "15": "battery_percentage"},
    "siren": {"5": "alarm_volume", "13": "alarm_switch", "15": "battery_percentage"},
    "alarm_panel": {"1": "master_mode", "26": "sos_state"},
}


# ================================================================== mapping functions
def parse_values(values: Any) -> Dict[str, Any]:
    """Parse the ``values`` metadata of a Tuya function (JSON string or dict)."""
    if isinstance(values, dict):
        return values
    if isinstance(values, str) and values.strip():
        try:
            data = json.loads(values)
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}
    return {}


def functions_meta(functions: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """``/functions`` list -> {tuya_code: {"type": str, **values}}."""
    meta: Dict[str, Dict[str, Any]] = {}
    for item in functions or []:
        code = item.get("code")
        if not code:
            continue
        entry = dict(parse_values(item.get("values")))
        if item.get("type"):
            entry["type"] = str(item["type"])
        meta[str(code)] = entry
    return meta


def resolve_spec(tuya_code: str, category: str = "generic") -> CodeSpec:
    """Tuya function code -> CodeSpec (category-aware; unknown codes become ``raw_<code>``)."""
    spec = CATEGORY_OVERRIDES.get(category, {}).get(tuya_code) or FUNCTION_MAP.get(tuya_code)
    if spec is not None:
        return spec
    match = re.fullmatch(r"switch_(\d+)", tuya_code)
    if match:
        return CodeSpec(f"switch_{match.group(1)}", "bool", True)
    return CodeSpec(f"raw_{tuya_code}")


def meta_for(tuya_code: str, meta: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Function metadata for a code; temperatures borrow the sibling's ``scale`` (temp_current <-> temp_set)."""
    entry = meta.get(tuya_code)
    if entry is not None:
        return entry
    sibling = TEMP_SIBLINGS.get(tuya_code)
    if sibling and sibling in meta and "scale" in meta[sibling]:
        return {"scale": meta[sibling]["scale"]}
    return {}


def _infer_type(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, (dict, list)):
        return "json"
    return "string"


def _priority(canonical: str, tuya_code: str, table: Dict[str, Tuple[str, ...]]) -> int:
    order = table.get(canonical)
    if order and tuya_code in order:
        return order.index(tuya_code)
    return len(order) if order else 0


def capability_for(tuya_code: str, category: str, meta: Dict[str, Any], writable: bool, sample: Any = None) -> Dict[str, Any]:
    """Build one capability dict for a Tuya code from its spec + function metadata."""
    spec = resolve_spec(tuya_code, category)
    scale = _scale_of(meta, 0)
    if spec.is_raw:
        ctype = TUYA_TYPE_MAP.get(str(meta.get("type", "")).lower())
        if ctype is None:
            ctype = _infer_type(sample) if sample is not None else "string"
        if ctype == "int" and scale > 0:
            ctype = "float"
        extra: Dict[str, Any] = {"label": tuya_code}
        if ctype in ("int", "float"):
            for key in ("min", "max", "step"):
                number = _num(meta.get(key))
                if number is not None:
                    extra[key] = number / (10 ** scale) if scale > 0 else number
            if meta.get("unit"):
                extra["unit"] = str(meta["unit"])
        if ctype == "enum" and isinstance(meta.get("range"), list):
            extra["values"] = [str(v) for v in meta["range"]]
        return cap(spec.canonical, ctype, writable, **extra)

    ctype = spec.type or (_infer_type(sample) if sample is not None else "string")
    low, high, step = spec.min, spec.max, spec.step
    if spec.range_from_meta and _num(meta.get("min")) is not None and _num(meta.get("max")) is not None:
        low = _num(meta["min"]) / (10 ** scale)
        high = _num(meta["max"]) / (10 ** scale)
        if _num(meta.get("step")) is not None:
            step = _num(meta["step"]) / (10 ** scale)
    values: Optional[List[str]] = list(spec.values) if spec.values else None
    if spec.values_from_meta and isinstance(meta.get("range"), list) and meta["range"]:
        values = [str(v) for v in meta["range"]]
    return cap(spec.canonical, ctype, writable, unit=spec.unit, min=low, max=high, step=step, values=values)


def build_capabilities(functions: List[Dict[str, Any]], status: List[Dict[str, Any]], category: str) -> List[Dict[str, Any]]:
    """Capabilities from ``/functions`` (writable) + ``/status`` codes (read-only), deduplicated per canonical code."""
    if category not in CATEGORIES:
        category = map_category(category)
    meta = functions_meta(functions)
    caps: Dict[str, Dict[str, Any]] = {}
    chosen: Dict[str, str] = {}
    samples = {str(item.get("code")): item.get("value") for item in status or [] if item.get("code")}
    for item in functions or []:
        code = str(item.get("code") or "")
        if not code:
            continue
        canonical = resolve_spec(code, category).canonical
        if canonical in caps and _priority(canonical, code, WRITE_PRIORITY) >= _priority(canonical, chosen[canonical], WRITE_PRIORITY):
            continue
        caps[canonical] = capability_for(code, category, meta_for(code, meta), True, samples.get(code))
        chosen[canonical] = code
    for item in status or []:
        code = str(item.get("code") or "")
        if not code:
            continue
        canonical = resolve_spec(code, category).canonical
        if canonical in caps:
            continue
        caps[canonical] = capability_for(code, category, meta_for(code, meta), False, item.get("value"))
        chosen[canonical] = code
    return list(caps.values())


def build_code_map(functions: List[Dict[str, Any]], category: str) -> Dict[str, str]:
    """{canonical code: Tuya function code} for the writable functions of a device."""
    code_map: Dict[str, str] = {}
    for item in functions or []:
        code = str(item.get("code") or "")
        if not code:
            continue
        canonical = resolve_spec(code, category).canonical
        if canonical not in code_map or _priority(canonical, code, WRITE_PRIORITY) < _priority(canonical, code_map[canonical], WRITE_PRIORITY):
            code_map[canonical] = code
    return code_map


def map_status(status: List[Dict[str, Any]], category: str, meta: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Tuya ``[{code, value}]`` -> canonical state dict."""
    if category not in CATEGORIES:
        category = map_category(category)
    meta = meta or {}
    state: Dict[str, Any] = {}
    chosen: Dict[str, str] = {}
    for item in status or []:
        code = str(item.get("code") or "")
        if not code or "value" not in item:
            continue
        spec = resolve_spec(code, category)
        entry = meta_for(code, meta)
        value = item["value"]
        if spec.decode is not None:
            decoded = spec.decode(value, entry, code)
        elif spec.is_raw and _scale_of(entry, 0) > 0 and _num(value) is not None and not isinstance(value, bool):
            decoded = _scaled(0)(value, entry, code)
        else:
            decoded = value
        canonical = spec.canonical
        if canonical in state and _priority(canonical, code, READ_PRIORITY) >= _priority(canonical, chosen[canonical], READ_PRIORITY):
            continue
        state[canonical] = decoded
        chosen[canonical] = code
    return state


def encode_command(code: str, value: Any, code_map: Dict[str, str], category: str,
                   meta: Optional[Dict[str, Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """Canonical command -> Tuya ``[{code, value}]`` (reverse mapping)."""
    meta = meta or {}
    if code == "ptz":
        if value == "stop":
            return [{"code": "ptz_stop", "value": True}]
        if value in ("zoom_in", "zoom_out"):
            return [{"code": "zoom_control", "value": "0" if value == "zoom_in" else "1"}]
        if value not in PTZ_TO_TUYA:
            raise AdapterError(f"Unsupported PTZ direction '{value}'", "invalid_input")
        return [{"code": "ptz_control", "value": PTZ_TO_TUYA[value]}]
    tuya_code = code_map.get(code)
    if tuya_code is None:
        if code.startswith("raw_"):
            tuya_code = code[4:]
        elif code in FUNCTION_MAP:  # local devices without an explicit map: canonical == tuya code
            tuya_code = code
        else:
            raise AdapterError(f"Capability '{code}' is not writable on this Tuya device", "unsupported")
    spec = resolve_spec(tuya_code, category)
    entry = meta_for(tuya_code, meta)
    if spec.encode is not None:
        tuya_value = spec.encode(value, entry, tuya_code)
    elif spec.is_raw and _scale_of(entry, 0) > 0 and _num(value) is not None and not isinstance(value, bool):
        tuya_value = _unscaled(0)(value, entry, tuya_code)
    elif str(entry.get("type", "")).lower() == "integer" and not isinstance(value, bool):
        tuya_value = _encode_int(value, entry, tuya_code)
    else:
        tuya_value = value
    return [{"code": tuya_code, "value": tuya_value}]


def dps_to_status(dps: Dict[str, Any], dps_map: Dict[str, str]) -> List[Dict[str, Any]]:
    """Local DPS dict -> Tuya-style status list (unknown DPS become ``dps_<id>`` codes)."""
    return [{"code": dps_map.get(str(key), f"dps_{key}"), "value": value} for key, value in (dps or {}).items()]


def local_dps_map(category: str, dps: Optional[Dict[str, Any]] = None, override: Any = None) -> Dict[str, str]:
    """DPS table for a category (+ per-device override); a single-gang switch collapses ``switch_1`` -> ``switch``."""
    table = dict(LOCAL_DPS_TABLES.get(category, {}))
    if isinstance(override, str) and override.strip():
        try:
            override = json.loads(override)
        except ValueError as exc:
            raise AdapterError("dps_map must be a JSON object {dps: code}", "invalid_input") from exc
    if isinstance(override, dict):
        table.update({str(k): str(v) for k, v in override.items()})
    if category == "switch" and dps:
        gangs = [k for k in dps if table.get(str(k), "").startswith("switch_")]
        if gangs == ["1"]:
            table["1"] = "switch"
    return table


def _invert_position(state: Dict[str, Any], invert: bool) -> None:
    """Covers that report 0 = open: flip ``position`` so that 100 always means open (``config.invert_position``)."""
    if invert and isinstance(state.get("position"), (int, float)) and not isinstance(state["position"], bool):
        state["position"] = 100 - int(state["position"])


def local_functions(dps_map: Dict[str, str], dps: Optional[Dict[str, Any]], category: str) -> List[Dict[str, Any]]:
    """Synthesise a ``/functions``-like list for local devices (writable codes of the DPS table)."""
    items: List[Dict[str, Any]] = []
    for dps_id, code in dps_map.items():
        if dps and str(dps_id) not in {str(k) for k in dps}:
            continue
        if resolve_spec(code, category).writable:
            items.append({"code": code, "type": None, "values": {}})
    return items


def cloud_error(code: Any, msg: Any) -> AdapterError:
    """Tuya ``{success:false, code, msg}`` -> AdapterError with the right hub error code."""
    try:
        number = int(code)
    except (TypeError, ValueError):
        number = 0
    text = str(msg or "unknown error")
    message = f"Tuya cloud error {number}: {text}"
    if number in AUTH_ERROR_CODES or "permission" in text.lower() or "sign invalid" in text.lower():
        return AdapterError(message, "auth_failed")
    if number in NOT_FOUND_CODES or "not exist" in text.lower():
        return AdapterError(message, "not_found")
    if number in UNREACHABLE_CODES or number >= 500000 or "offline" in text.lower():
        return AdapterError(message, "unreachable")
    return AdapterError(message, "invalid_input")


# ================================================================== cloud client
@dataclass
class TokenBundle:
    """Cached OpenAPI token."""

    access_token: str
    refresh_token: str
    expires_at: float
    uid: str = ""

    def expired(self, now: float) -> bool:
        """True when the access token is missing or (nearly) expired."""
        return not self.access_token or now >= self.expires_at

    def as_credentials(self) -> Dict[str, Any]:
        """Fields stored in the integration credentials."""
        return {"access_token": self.access_token, "refresh_token": self.refresh_token, "expires_at": self.expires_at}

    @classmethod
    def from_credentials(cls, credentials: Dict[str, Any]) -> Optional["TokenBundle"]:
        """Rebuild from stored credentials (None when nothing cached)."""
        token = credentials.get("access_token")
        if not token:
            return None
        return cls(access_token=str(token), refresh_token=str(credentials.get("refresh_token") or ""),
                   expires_at=float(_num(credentials.get("expires_at"), 0.0) or 0.0), uid=str(credentials.get("uid") or ""))

    @classmethod
    def from_result(cls, result: Dict[str, Any], now: float) -> "TokenBundle":
        """Build from a ``/v1.0/token`` result."""
        expire = _num(result.get("expire_time"), 7200.0) or 7200.0
        return cls(access_token=str(result.get("access_token") or ""), refresh_token=str(result.get("refresh_token") or ""),
                   expires_at=now + max(0.0, expire - TOKEN_MARGIN_SECONDS), uid=str(result.get("uid") or ""))


def string_to_sign(method: str, path: str, params: Optional[Dict[str, Any]], body: str) -> str:
    """Tuya ``stringToSign``: METHOD, sha256(body), signed headers (none), url with sorted query."""
    url = path
    if params:
        url += "?" + "&".join(f"{key}={params[key]}" for key in sorted(params))
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest() if body else EMPTY_BODY_SHA256
    return f"{method.upper()}\n{digest}\n\n{url}"


def sign_request(method: str, path: str, params: Optional[Dict[str, Any]], body: str, access_id: str, access_secret: str,
                 t: str, access_token: str = "", nonce: str = "") -> Dict[str, str]:
    """Authentication headers for one Tuya OpenAPI request."""
    payload = access_id + access_token + t + nonce + string_to_sign(method, path, params, body)
    sign = hmac.new(access_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest().upper()
    headers = {"client_id": access_id, "sign": sign, "t": t, "sign_method": "HMAC-SHA256", "Content-Type": "application/json"}
    if access_token:
        headers["access_token"] = access_token
    if nonce:
        headers["nonce"] = nonce
    return headers


class TuyaCloudClient:
    """Signed Tuya OpenAPI requests over an ``httpx.AsyncClient`` bound to the region base URL."""

    def __init__(self, client: httpx.AsyncClient, access_id: str, access_secret: str, token: Optional[TokenBundle] = None,
                 clock: Callable[[], float] = time.time, nonce_factory: Optional[Callable[[], str]] = None):
        self.client = client
        self.access_id = access_id
        self.access_secret = access_secret
        self.token = token
        self.clock = clock
        self.nonce_factory = nonce_factory or (lambda: uuid.uuid4().hex)

    # ---------------------------------------------------------------- auth
    async def ensure_token(self) -> TokenBundle:
        """Return a valid token: cached, refreshed, or newly issued."""
        now = self.clock()
        if self.token is not None and not self.token.expired(now):
            return self.token
        if self.token is not None and self.token.refresh_token:
            try:
                return await self.refresh_token()
            except AdapterError as exc:
                logger.info("Tuya token refresh failed (%s); requesting a new token", exc.message)
        return await self.fetch_token()

    async def fetch_token(self) -> TokenBundle:
        """GET /v1.0/token?grant_type=1"""
        result = await self.request("GET", "/v1.0/token", params={"grant_type": 1}, auth=False)
        self.token = TokenBundle.from_result(result or {}, self.clock())
        if not self.token.access_token:
            raise AdapterError("Tuya cloud returned no access token", "auth_failed")
        return self.token

    async def refresh_token(self) -> TokenBundle:
        """GET /v1.0/token/{refresh_token}"""
        if self.token is None or not self.token.refresh_token:
            raise AdapterError("No Tuya refresh token cached", "auth_failed")
        result = await self.request("GET", f"/v1.0/token/{self.token.refresh_token}", auth=False)
        self.token = TokenBundle.from_result(result or {}, self.clock())
        if not self.token.access_token:
            raise AdapterError("Tuya cloud returned no access token on refresh", "auth_failed")
        return self.token

    # ---------------------------------------------------------------- transport
    async def request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None, body: Optional[Any] = None,
                      auth: bool = True, retry: bool = True) -> Any:
        """Signed request; returns ``result``. Re-authenticates once on token errors."""
        access_token = (await self.ensure_token()).access_token if auth else ""
        t = str(int(self.clock() * 1000))
        body_text = json.dumps(body) if body is not None else ""
        headers = sign_request(method, path, params, body_text, self.access_id, self.access_secret, t, access_token, self.nonce_factory())
        try:
            response = await self.client.request(method, path, params=params, content=body_text.encode("utf-8") if body_text else None,
                                                 headers=headers)
        except httpx.HTTPError as exc:
            raise AdapterError(f"Tuya cloud unreachable: {exc}", "unreachable") from exc
        if response.status_code >= 500:
            raise AdapterError(f"Tuya cloud error HTTP {response.status_code}", "unreachable")
        if response.status_code in (401, 403):
            raise AdapterError(f"Tuya cloud rejected the request (HTTP {response.status_code})", "auth_failed")
        try:
            data = response.json()
        except ValueError as exc:
            raise AdapterError("Tuya cloud returned a non-JSON response", "unreachable") from exc
        if response.status_code >= 400 and not isinstance(data, dict):
            raise AdapterError(f"Tuya cloud error HTTP {response.status_code}", "invalid_input")
        if not isinstance(data, dict):
            raise AdapterError("Unexpected Tuya cloud response", "unreachable")
        if not data.get("success", False):
            code = data.get("code")
            if auth and retry and _num(code) in TOKEN_ERROR_CODES:
                logger.info("Tuya token rejected (%s); re-authenticating", code)
                self.token = None
                return await self.request(method, path, params=params, body=body, auth=auth, retry=False)
            raise cloud_error(code, data.get("msg"))
        return data.get("result")

    # ---------------------------------------------------------------- business endpoints
    async def list_devices(self, uid: Optional[str] = None) -> List[Dict[str, Any]]:
        """Devices of the linked app account (``uid``) or of every associated user (paginated)."""
        if uid:
            result = await self.request("GET", f"/v1.0/users/{uid}/devices")
            return list(result or [])
        devices: List[Dict[str, Any]] = []
        last_row_key: Optional[str] = None
        for _ in range(MAX_DEVICE_PAGES):
            params = {"last_row_key": last_row_key} if last_row_key else None
            result = await self.request("GET", "/v1.0/iot-01/associated-users/devices", params=params) or {}
            devices.extend(result.get("devices") or [])
            last_row_key = result.get("last_row_key")
            if not result.get("has_more") or not last_row_key:
                break
        return devices

    async def get_device(self, device_id: str) -> Dict[str, Any]:
        """GET /v1.0/devices/{id}"""
        return await self.request("GET", f"/v1.0/devices/{device_id}") or {}

    async def get_status(self, device_id: str) -> List[Dict[str, Any]]:
        """GET /v1.0/devices/{id}/status"""
        return list(await self.request("GET", f"/v1.0/devices/{device_id}/status") or [])

    async def get_functions(self, device_id: str) -> List[Dict[str, Any]]:
        """GET /v1.0/devices/{id}/functions (empty for devices without writable functions)."""
        try:
            result = await self.request("GET", f"/v1.0/devices/{device_id}/functions") or {}
        except AdapterError as exc:
            if exc.code == "auth_failed":
                raise
            logger.info("Tuya /functions unavailable for %s: %s", device_id, exc.message)
            return []
        return list(result.get("functions") or [])

    async def send_commands(self, device_id: str, commands: List[Dict[str, Any]]) -> None:
        """POST /v1.0/devices/{id}/commands"""
        await self.request("POST", f"/v1.0/devices/{device_id}/commands", body={"commands": commands})

    async def stream_url(self, device_id: str, kind: str = "rtsp") -> Optional[str]:
        """POST /v1.0/devices/{id}/stream/actions -> live stream url."""
        result = await self.request("POST", f"/v1.0/devices/{device_id}/stream/actions", body={"type": kind}) or {}
        return result.get("url") or None


# ================================================================== local helpers (tinytuya)
def _load_tinytuya() -> Any:
    """Import tinytuya lazily (optional dependency). Tests monkeypatch this with a fake module."""
    try:
        import tinytuya  # pylint: disable=import-outside-toplevel
    except ImportError:
        return None
    return tinytuya


def _require_tinytuya() -> Any:
    module = _load_tinytuya()
    if module is None:
        raise AdapterError("Install tinytuya for local control", "unsupported")
    return module


def _local_error(data: Any) -> Optional[AdapterError]:
    if not isinstance(data, dict):
        return AdapterError("Unexpected reply from local Tuya device", "unreachable")
    if "Error" not in data:
        return None
    err = str(data.get("Err") or "")
    message = f"Local Tuya error {err}: {data.get('Error')}"
    if err in LOCAL_AUTH:
        return AdapterError(message + " (check local key / protocol version)", "auth_failed")
    if err in LOCAL_INVALID:
        return AdapterError(message, "invalid_input")
    return AdapterError(message, "unreachable")


def _local_device(module: Any, device_id: str, host: str, local_key: str, version: str) -> Any:
    device = module.Device(dev_id=device_id, address=host, local_key=local_key, version=float(version))
    if hasattr(device, "set_socketTimeout"):
        device.set_socketTimeout(LOCAL_TIMEOUT_SECONDS)
    if hasattr(device, "set_socketRetryLimit"):
        device.set_socketRetryLimit(1)
    return device


def _local_status_sync(module: Any, device_id: str, host: str, local_key: str, version: str) -> Dict[str, Any]:
    """Blocking: read all DPS of a local device."""
    try:
        data = _local_device(module, device_id, host, local_key, version).status()
    except AdapterError:
        raise
    except Exception as exc:  # pylint: disable=broad-except
        raise AdapterError(f"Local Tuya device unreachable: {exc}", "unreachable") from exc
    error = _local_error(data)
    if error is not None:
        raise error
    return {str(k): v for k, v in (data.get("dps") or {}).items()}


def _local_set_sync(module: Any, device_id: str, host: str, local_key: str, version: str, dps_id: str, value: Any) -> Dict[str, Any]:
    """Blocking: write one DPS; returns the DPS echoed by the device (may be empty)."""
    try:
        data = _local_device(module, device_id, host, local_key, version).set_value(int(dps_id), value)
    except AdapterError:
        raise
    except Exception as exc:  # pylint: disable=broad-except
        raise AdapterError(f"Local Tuya device unreachable: {exc}", "unreachable") from exc
    if data is None:
        return {}
    error = _local_error(data)
    if error is not None:
        raise error
    return {str(k): v for k, v in (data.get("dps") or {}).items()}


# ================================================================== adapter
class TuyaAdapter(BrandAdapter):
    """Tuya cloud projects + local LAN devices."""

    brand_id = BRAND_ID

    def __init__(self) -> None:
        self._tokens: Dict[str, TokenBundle] = {}  # access_id -> freshest token (adapters cannot write back credentials)

    build_capabilities = staticmethod(build_capabilities)
    map_status = staticmethod(map_status)
    encode_command = staticmethod(encode_command)
    map_category = staticmethod(map_category)

    # ---------------------------------------------------------------- catalogue
    def info(self) -> BrandInfo:
        region_options = [{"value": "eu", "label": "Europe (openapi.tuyaeu.com)"}, {"value": "us", "label": "Amériques (openapi.tuyaus.com)"},
                          {"value": "cn", "label": "Chine (openapi.tuyacn.com)"}, {"value": "in", "label": "Inde (openapi.tuyain.com)"}]
        category_options = [{"value": c, "label": CATEGORY_INFO.get(c, {}).get("name", c)} for c in CATEGORIES]
        return BrandInfo(
            id=BRAND_ID,
            name="Tuya / Smart Life",
            vendor="Tuya Inc.",
            description="Appareils Tuya, Smart Life et marques compatibles (via un projet Tuya IoT Cloud ou en local avec la clé locale).",
            protocols=[PROTOCOL_CLOUD, PROTOCOL_LOCAL],
            categories=sorted(set(TUYA_CATEGORY_MAP.values())),
            methods=[
                PairingMethod(
                    id=METHOD_CLOUD,
                    title="Projet Tuya IoT Cloud",
                    description="Importe tous les appareils liés à votre compte Smart Life/Tuya via un projet cloud (Access ID / Secret).",
                    fields=[
                        FormField(name="region", label="Région du data center", type="select", options=region_options, default="eu"),
                        FormField(name="access_id", label="Access ID / Client ID", type="text", placeholder="xxxxxxxxxxxxxxxxxxxx"),
                        FormField(name="access_secret", label="Access Secret", type="password"),
                        FormField(name="uid", label="UID du compte lié", type="text", required=False,
                                  help="UID du compte Smart Life lié au projet. Laissez vide pour importer les appareils de tous les comptes liés."),
                    ],
                    supports_discovery=True,
                    requires_integration=True,
                    icon="cloud",
                ),
                PairingMethod(
                    id=METHOD_LOCAL,
                    title="Clé locale (LAN)",
                    description="Contrôle direct sur le réseau local avec l'identifiant, la clé locale et l'adresse IP de l'appareil.",
                    fields=[
                        FormField(name="device_id", label="Device ID", type="text"),
                        FormField(name="local_key", label="Clé locale", type="password", help="16 caractères (obtenue via le projet Tuya IoT ou tinytuya wizard)."),
                        FormField(name="host", label="Adresse IP", type="text", placeholder="192.168.1.50"),
                        FormField(name="version", label="Version du protocole", type="select", default="3.3",
                                  options=[{"value": v, "label": v} for v in LOCAL_VERSIONS]),
                        FormField(name="name", label="Nom", type="text", required=False),
                        FormField(name="category", label="Type d'appareil", type="select", options=category_options, default="switch"),
                    ],
                    icon="lan",
                ),
            ],
            icon="hub",
            docs_url="https://developer.tuya.com/en/docs/iot",
            color="#FF4800",
        )

    # ---------------------------------------------------------------- cloud plumbing
    @staticmethod
    def _cloud_settings(payload: Dict[str, Any]) -> Tuple[str, str, str, str, Optional[str]]:
        require(payload, "region", "access_id", "access_secret")
        region = str(payload["region"]).strip().lower()
        if region not in REGIONS:
            raise AdapterError(f"Unknown Tuya region '{region}' (expected one of {', '.join(REGIONS)})", "invalid_input")
        uid = str(payload.get("uid") or "").strip() or None
        return region, REGIONS[region], str(payload["access_id"]).strip(), str(payload["access_secret"]).strip(), uid

    def _cloud_client(self, client: httpx.AsyncClient, access_id: str, access_secret: str, credentials: Optional[Dict[str, Any]] = None) -> TuyaCloudClient:
        """Client seeded with the freshest known token (in-memory cache beats stored credentials)."""
        cached = self._tokens.get(access_id)
        stored = TokenBundle.from_credentials(credentials or {})
        token = cached
        if stored is not None and (cached is None or stored.expires_at > cached.expires_at):
            token = stored
        return TuyaCloudClient(client, access_id, access_secret, token=token)

    def _remember(self, cloud: TuyaCloudClient) -> None:
        if cloud.token is not None:
            self._tokens[cloud.access_id] = cloud.token

    def _cloud_from_ref(self, device: DeviceRef) -> Tuple[str, str, str, Dict[str, Any]]:
        region = str(device.cfg("region") or "").lower()
        access_id = str(device.cfg("access_id") or device.cred("access_id") or "")
        access_secret = str(device.cred("access_secret") or "")
        if region not in REGIONS or not access_id or not access_secret:
            raise AdapterError("Tuya cloud integration is incomplete (region/access_id/access_secret)", "auth_failed")
        credentials = dict(device.integration_credentials)
        credentials.update(device.credentials)
        return REGIONS[region], access_id, access_secret, credentials

    @staticmethod
    def _draft_from_cloud(item: Dict[str, Any], region: str, functions: List[Dict[str, Any]], status: List[Dict[str, Any]]) -> DeviceDraft:
        tuya_category = str(item.get("category") or "")
        category = map_category(tuya_category)
        meta = functions_meta(functions)
        return DeviceDraft(
            external_id=str(item.get("id")),
            name=str(item.get("name") or item.get("product_name") or f"Tuya {category}"),
            category=category,
            protocol=PROTOCOL_CLOUD,
            model=item.get("product_name") or item.get("model") or None,
            manufacturer="Tuya",
            capabilities=build_capabilities(functions, status, category),
            state=map_status(status, category, meta),
            config={"region": region, "device_id": str(item.get("id")), "tuya_category": tuya_category,
                    "product_id": item.get("product_id"), "functions": meta, "code_map": build_code_map(functions, category)},
            credentials={},
            online=bool(item.get("online", True)),
            icon=CATEGORY_INFO.get(category, {}).get("icon"),
        )

    # ---------------------------------------------------------------- discovery / pairing
    async def discover(self, method_id: str, payload: Dict[str, Any], ctx: AdapterContext) -> List[DiscoveredDevice]:
        method = self.method(method_id)
        if method.id != METHOD_CLOUD:
            return []
        _region, base_url, access_id, access_secret, uid = self._cloud_settings(payload)
        async with ctx.http(base_url=base_url) as client:
            cloud = self._cloud_client(client, access_id, access_secret)
            devices = await cloud.list_devices(uid)
            self._remember(cloud)
        found: List[DiscoveredDevice] = []
        for item in devices:
            tuya_category = str(item.get("category") or "")
            found.append(DiscoveredDevice(
                external_id=str(item.get("id")), name=str(item.get("name") or item.get("product_name") or "Tuya"),
                category=map_category(tuya_category), model=item.get("product_name") or None, manufacturer="Tuya",
                address=item.get("ip") or None,
                extra={"tuya_category": tuya_category, "online": bool(item.get("online", True)), "product_id": item.get("product_id")},
            ))
        return found

    async def pair(self, method_id: str, payload: Dict[str, Any], ctx: AdapterContext) -> PairResult:
        method = self.method(method_id)
        if method.id == METHOD_CLOUD:
            return await self._pair_cloud(payload, ctx)
        return await self._pair_local(payload)

    async def _pair_cloud(self, payload: Dict[str, Any], ctx: AdapterContext) -> PairResult:
        region, base_url, access_id, access_secret, uid = self._cloud_settings(payload)
        selected = payload.get("selected_external_ids")
        wanted = {str(x) for x in selected} if isinstance(selected, list) and selected else None
        drafts: List[DeviceDraft] = []
        async with ctx.http(base_url=base_url) as client:
            cloud = self._cloud_client(client, access_id, access_secret)
            token = await cloud.ensure_token()
            devices = await cloud.list_devices(uid)
            for item in devices:
                device_id = str(item.get("id") or "")
                if not device_id or (wanted is not None and device_id not in wanted):
                    continue
                functions = await cloud.get_functions(device_id)
                status = item.get("status")
                if not isinstance(status, list):
                    status = await cloud.get_status(device_id)
                drafts.append(self._draft_from_cloud(item, region, functions, status))
            self._remember(cloud)
            token = cloud.token or token
        config: Dict[str, Any] = {"region": region, "access_id": access_id}
        if uid:
            config["uid"] = uid
        elif token.uid:
            config["uid"] = token.uid
        integration = IntegrationDraft(
            key=f"{PROTOCOL_CLOUD}:{access_id}",
            name=f"Tuya Cloud ({region})",
            config=config,
            credentials={"access_secret": access_secret, **token.as_credentials()},
        )
        return PairResult(devices=drafts, integration=integration, message=f"{len(drafts)} appareil(s) Tuya importé(s)")

    async def _pair_local(self, payload: Dict[str, Any]) -> PairResult:
        require(payload, "device_id", "local_key", "host", "category")
        device_id = str(payload["device_id"]).strip()
        local_key = str(payload["local_key"]).strip()
        host = str(payload["host"]).strip()
        version = str(payload.get("version") or "3.3").strip()
        category = str(payload["category"]).strip()
        if len(local_key) != LOCAL_KEY_LENGTH:
            raise AdapterError(f"local_key must be {LOCAL_KEY_LENGTH} characters", "invalid_input")
        if version not in LOCAL_VERSIONS:
            raise AdapterError(f"Unsupported Tuya protocol version '{version}' (expected {', '.join(LOCAL_VERSIONS)})", "invalid_input")
        if category not in CATEGORIES:
            raise AdapterError(f"Unknown category '{category}'", "invalid_input")
        module = _require_tinytuya()
        dps = await asyncio.to_thread(_local_status_sync, module, device_id, host, local_key, version)
        dps_map = local_dps_map(category, dps, payload.get("dps_map"))
        status = dps_to_status(dps, dps_map)
        functions = local_functions(dps_map, dps, category)
        invert = bool(payload.get("invert_position", False))
        state = map_status(status, category)
        _invert_position(state, invert)
        draft = DeviceDraft(
            external_id=device_id,
            name=str(payload.get("name") or "").strip() or f"Tuya {CATEGORY_INFO.get(category, {}).get('name', category)}",
            category=category,
            protocol=PROTOCOL_LOCAL,
            manufacturer="Tuya",
            capabilities=build_capabilities(functions, status, category),
            state=state,
            config={"host": host, "version": version, "device_id": device_id, "dps_map": dps_map, "invert_position": invert},
            credentials={"local_key": local_key},
            icon=CATEGORY_INFO.get(category, {}).get("icon"),
        )
        return PairResult(devices=[draft], message="Appareil Tuya local ajouté")

    # ---------------------------------------------------------------- state
    async def refresh(self, device: DeviceRef, ctx: AdapterContext) -> DeviceState:
        if device.protocol == PROTOCOL_LOCAL:
            return await self._refresh_local(device)
        return await self._refresh_cloud(device, ctx)

    async def _refresh_cloud(self, device: DeviceRef, ctx: AdapterContext) -> DeviceState:
        base_url, access_id, access_secret, credentials = self._cloud_from_ref(device)
        device_id = str(device.cfg("device_id") or device.external_id)
        async with ctx.http(base_url=base_url) as client:
            cloud = self._cloud_client(client, access_id, access_secret, credentials)
            try:
                detail = await cloud.get_device(device_id)
                status = detail.get("status")
                if not isinstance(status, list):
                    status = await cloud.get_status(device_id)
                online = bool(detail.get("online", True))
            finally:
                self._remember(cloud)
        state = map_status(status, device.category, device.cfg("functions") or {})
        self._apply_inversion(device, state)
        return DeviceState(online=online, state=state)

    async def _refresh_local(self, device: DeviceRef) -> DeviceState:
        module = _require_tinytuya()
        device_id, host, local_key, version = self._local_params(device)
        dps = await asyncio.to_thread(_local_status_sync, module, device_id, host, local_key, version)
        dps_map = local_dps_map(device.category, dps, device.cfg("dps_map"))
        state = map_status(dps_to_status(dps, dps_map), device.category)
        self._apply_inversion(device, state)
        return DeviceState(online=True, state=state)

    @staticmethod
    def _local_params(device: DeviceRef) -> Tuple[str, str, str, str]:
        host = str(device.cfg("host") or "")
        local_key = str(device.cred("local_key") or "")
        if not host or not local_key:
            raise AdapterError("Local Tuya device is missing host/local_key", "invalid_input")
        return str(device.cfg("device_id") or device.external_id), host, local_key, str(device.cfg("version") or "3.3")

    @staticmethod
    def _apply_inversion(device: DeviceRef, state: Dict[str, Any]) -> None:
        _invert_position(state, bool(device.cfg("invert_position")))

    # ---------------------------------------------------------------- commands
    async def send_command(self, device: DeviceRef, code: str, value: Any, ctx: AdapterContext) -> Dict[str, Any]:
        if code == "position" and device.cfg("invert_position") and _num(value) is not None:
            value = 100 - int(round(float(value)))
        if device.protocol == PROTOCOL_LOCAL:
            return await self._command_local(device, code, value)
        return await self._command_cloud(device, code, value, ctx)

    async def _command_cloud(self, device: DeviceRef, code: str, value: Any, ctx: AdapterContext) -> Dict[str, Any]:
        base_url, access_id, access_secret, credentials = self._cloud_from_ref(device)
        commands = encode_command(code, value, device.cfg("code_map") or {}, device.category, device.cfg("functions") or {})
        device_id = str(device.cfg("device_id") or device.external_id)
        async with ctx.http(base_url=base_url) as client:
            cloud = self._cloud_client(client, access_id, access_secret, credentials)
            try:
                await cloud.send_commands(device_id, commands)
            finally:
                self._remember(cloud)
        return {} if code == "ptz" else {code: value}

    async def _command_local(self, device: DeviceRef, code: str, value: Any) -> Dict[str, Any]:
        module = _require_tinytuya()
        device_id, host, local_key, version = self._local_params(device)
        dps_map = local_dps_map(device.category, None, device.cfg("dps_map"))
        if code.startswith("raw_dps_"):
            dps_map.setdefault(code[len("raw_dps_"):], f"dps_{code[len('raw_dps_'):]}")
        code_map = {resolve_spec(tuya_code, device.category).canonical: tuya_code for tuya_code in dps_map.values()}
        commands = encode_command(code, value, code_map, device.category)
        reverse = {tuya_code: dps_id for dps_id, tuya_code in dps_map.items()}
        partial: Dict[str, Any] = {}
        for command in commands:
            dps_id = reverse.get(command["code"])
            if dps_id is None:
                raise AdapterError(f"No DPS mapped for '{code}' on this device", "unsupported")
            echoed = await asyncio.to_thread(_local_set_sync, module, device_id, host, local_key, version, dps_id, command["value"])
            partial.update(map_status(dps_to_status(echoed, dps_map), device.category))
        partial[code] = value
        self._apply_inversion(device, partial)
        return partial

    # ---------------------------------------------------------------- cameras
    async def stream(self, device: DeviceRef, quality: str, ctx: AdapterContext) -> Optional[StreamInfo]:
        if device.protocol != PROTOCOL_CLOUD or device.category not in ("camera", "doorbell", "nvr"):
            return None
        base_url, access_id, access_secret, credentials = self._cloud_from_ref(device)
        kind = "hls" if quality == "sub" else "rtsp"
        async with ctx.http(base_url=base_url) as client:
            cloud = self._cloud_client(client, access_id, access_secret, credentials)
            try:
                url = await cloud.stream_url(str(device.cfg("device_id") or device.external_id), kind)
            finally:
                self._remember(cloud)
        if not url:
            return None
        return StreamInfo(url=url, type=kind)


registry.register(TuyaAdapter())
