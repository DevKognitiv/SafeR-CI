"""Ajax Systems adapter: Ajax cloud (Enterprise API) and SIA DC-09 monitoring-station reports.

Two pairing methods:

* ``cloud_account`` — the Ajax Enterprise API (``https://api.ajax.systems/api``). Requires an API
  key issued by Ajax Systems plus the login/password of the Ajax account:

    - ``POST /login``  ``X-Api-Key`` + ``{"login", "passwordHash": sha256(password), "userRole": "USER"}``
      -> ``{"sessionToken", "refreshToken", "userId"}``; every other call sends ``X-Api-Key`` and
      ``X-Session-Token``; on 401 the session is refreshed once with ``POST /refresh``.
    - ``GET /user/{userId}/hubs`` / ``.../hubs/{hubId}`` / ``.../hubs/{hubId}/devices`` /
      ``.../groups`` (best effort) build the device tree: the hub becomes an ``alarm_panel`` and
      every Ajax device a child mapped by ``deviceType`` (MotionProtect -> ``sensor_motion``,
      DoorProtect -> ``sensor_contact``, FireProtect -> ``sensor_smoke``, Socket -> ``plug``...).
    - ``PUT .../hubs/{hubId}/commands/arming`` arms/disarms; ``POST .../devices/{id}/command``
      switches sockets/relays.

  Limitation: Ajax has no "stay" mode. ``armed_home`` arms the hub (or, when the hub runs in group
  mode, every group in turn — best effort); ``PARTIALLY_ARMED`` reported by the hub is mapped back
  to ``armed_home``. Rotated session tokens live in the adapter's memory: the persisted
  ``session_token`` is only a bootstrap and the stored ``refresh_token``/``password_hash`` are used
  to recover after a restart.

* ``sia_receiver`` — no network: creates an ``alarm_panel`` fed by ``services/sia_receiver.py``
  (any panel speaking SIA DC-09: Ajax hub, Hikvision AX PRO, Paradox, DSC...). SIA is one-way:
  arming must be done from the panel's own app.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

import httpx

from app.hub.adapters.base import (
    AdapterContext, AdapterError, BrandAdapter, BrandInfo, DeviceDraft, DeviceRef, DeviceState, DiscoveredDevice,
    FormField, IntegrationDraft, PairResult, PairingMethod, require,
)
from app.hub.adapters.registry import registry
from app.hub.capabilities import alarm_panel_caps, alarm_zone_caps, cap
from app.hub.services.sia_receiver import map_sia_code

logger = logging.getLogger("safer.hub.ajax")

BRAND_ID = "ajax"
PROTOCOL_CLOUD = "ajax_cloud"
PROTOCOL_SIA = "sia_dc09"
METHOD_CLOUD = "cloud_account"
METHOD_SIA = "sia_receiver"
MANUFACTURER = "Ajax Systems"
DEFAULT_BASE_URL = "https://api.ajax.systems/api"
ACCOUNT_RE = re.compile(r"^[0-9A-Fa-f]{3,16}$")

# Hub "state" values <-> hub security modes
ARM_FROM_AJAX: Dict[str, str] = {
    "ARMED": "armed_away", "NIGHT_MODE": "armed_night", "PARTIALLY_ARMED": "armed_home", "DISARMED": "disarmed",
}
ARM_TO_AJAX: Dict[str, str] = {
    "armed_away": "ARM", "armed_home": "ARM", "armed_night": "NIGHT_MODE_ON", "disarmed": "DISARM",
}
SIGNAL_LEVELS: Dict[str, Optional[int]] = {
    "STRONG": 100, "HIGH": 100, "GOOD": 75, "NORMAL": 66, "MEDIUM": 50, "WEAK": 33, "LOW": 33, "POOR": 25,
    "NO_SIGNAL": 0, "NONE": 0, "UNKNOWN": None,
}
# (normalised substring of deviceType, hub category) — order matters (first match wins)
DEVICE_TYPE_CATEGORIES: List[Tuple[str, str]] = [
    ("motioncam", "sensor_motion"), ("motionprotect", "sensor_motion"), ("combiprotect", "sensor_motion"),
    ("curtain", "sensor_motion"), ("motion", "sensor_motion"),
    ("doorprotect", "sensor_contact"), ("door", "sensor_contact"),
    ("glassprotect", "sensor_multi"), ("glass", "sensor_multi"),
    ("fireprotect", "sensor_smoke"), ("fire", "sensor_smoke"), ("smoke", "sensor_smoke"),
    ("leaksprotect", "sensor_water"), ("leak", "sensor_water"), ("waterstop", "switch"), ("water", "sensor_water"),
    ("homesiren", "siren"), ("streetsiren", "siren"), ("siren", "siren"),
    ("socket", "plug"), ("wallswitch", "switch"), ("lightswitch", "switch"), ("relay", "switch"),
    ("spacecontrol", "remote"), ("doublebutton", "remote"), ("button", "remote"), ("keypad", "remote"),
    ("rex", "gateway"), ("rangeextender", "gateway"), ("extender", "gateway"),
]
DETECTION_CODES: Dict[str, str] = {
    "sensor_motion": "motion", "sensor_contact": "contact", "sensor_smoke": "smoke", "sensor_water": "water_leak",
    "sensor_gas": "gas", "sensor_multi": "alarm", "alarm_zone": "alarm", "siren": "siren",
}
CANONICAL_STATE_KEYS = (
    "motion", "contact", "smoke", "co", "water_leak", "gas", "tamper", "battery", "signal", "switch", "siren",
    "temperature", "humidity", "alarm", "open", "bypass", "arm_mode", "triggered_zone", "ready", "power", "energy",
)
TRUE_WORDS = frozenset({"true", "on", "1", "yes", "active", "armed", "open", "opened", "enabled", "detected", "alarm"})
FALSE_WORDS = frozenset({"false", "off", "0", "no", "inactive", "closed", "disabled", "disarmed", "normal", "ok"})


# =============================================================================== helpers
def password_hash(password: str) -> str:
    """Ajax expects the SHA-256 hex digest of the password."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _first(data: Optional[Dict[str, Any]], *keys: str, default: Any = None) -> Any:
    """First non-None value among ``keys``."""
    if not isinstance(data, dict):
        return default
    for key in keys:
        value = data.get(key)
        if value is not None:
            return value
    return default


def _as_bool(value: Any, default: Optional[bool] = None) -> Optional[bool]:
    """Lenient bool coercion (bool / number / "ON" / "true" / "OPENED"...)."""
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in TRUE_WORDS:
        return True
    if text in FALSE_WORDS:
        return False
    return default


def _as_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_str(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _as_list(data: Any, *keys: str) -> List[Dict[str, Any]]:
    """Accept ``[...]`` or ``{"hubs": [...]}`` style collections."""
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in keys:
            if isinstance(data.get(key), list):
                return [item for item in data[key] if isinstance(item, dict)]
    return []


def battery_percent(value: Any) -> Optional[int]:
    """``87`` / ``"87"`` / ``{"chargeLevelPercentage": 87}`` -> 87."""
    if isinstance(value, dict):
        value = _first(value, "chargeLevelPercentage", "percentage", "level", "chargeLevel", "value")
    number = _as_int(value)
    if number is None:
        return None
    return max(0, min(100, number))


def signal_percent(value: Any) -> Optional[int]:
    """``"STRONG"`` / ``66`` / ``{"signalLevel": "WEAK"}`` -> percentage."""
    if isinstance(value, dict):
        value = _first(value, "signalLevel", "level", "signal", "strength", "value")
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return max(0, min(100, int(round(value))))
    text = str(value).strip().upper().replace(" ", "_")
    if text in SIGNAL_LEVELS:
        return SIGNAL_LEVELS[text]
    return _as_int(text) if text.isdigit() else None


def arm_mode_from_ajax(value: Any) -> Optional[str]:
    """Hub ``state`` (``ARMED``/``NIGHT_MODE``/``PARTIALLY_ARMED``/``DISARMED`` and variants) -> security mode."""
    text = _as_str(value).upper().replace("-", "_").replace(" ", "_")
    if not text:
        return None
    if text in ARM_FROM_AJAX:
        return ARM_FROM_AJAX[text]
    if "NIGHT" in text:
        return "disarmed" if text.endswith("OFF") else "armed_night"
    if "PARTIAL" in text or "STAY" in text or "HOME" in text or "PERIMETER" in text:
        return "armed_home"
    if "DISARM" in text:
        return "disarmed"
    if "ARM" in text:
        return "armed_away"
    return None


def hub_id_of(hub: Dict[str, Any]) -> str:
    """Hub identifier (``hubId`` or ``id``)."""
    return _as_str(_first(hub, "hubId", "hub_id", "id"))


def device_id_of(device: Dict[str, Any]) -> str:
    """Device identifier (``id`` or ``deviceId``)."""
    return _as_str(_first(device, "id", "deviceId", "device_id"))


def category_for(device_type: Any) -> str:
    """Ajax ``deviceType`` -> hub category (unknown types become alarm zones)."""
    normalised = re.sub(r"[^a-z0-9]", "", _as_str(device_type).lower())
    for token, category in DEVICE_TYPE_CATEGORIES:
        if token in normalised:
            return category
    return "alarm_zone"


def _contact_open(data: Dict[str, Any]) -> Optional[bool]:
    if "reedClosed" in data:
        closed = _as_bool(data.get("reedClosed"))
        return None if closed is None else not closed
    value = _first(data, "openDoor", "doorOpen", "contactOpen", "opened", "open", "isOpen")
    if value is not None:
        return _as_bool(value)
    if "externalContactClosed" in data:
        closed = _as_bool(data.get("externalContactClosed"))
        return None if closed is None else not closed
    return None


def _common_state(data: Dict[str, Any]) -> Dict[str, Any]:
    state: Dict[str, Any] = {}
    battery = battery_percent(_first(data, "batteryChargeLevelPercentage", "batteryLevel", "battery", "batteryCharge"))
    if battery is not None:
        state["battery"] = battery
    tamper = _as_bool(_first(data, "tampered", "tamper", "tamperAlarm", "lidOpen"))
    if tamper is not None:
        state["tamper"] = tamper
    signal = signal_percent(_first(data, "signalLevel", "signal", "rssi"))
    if signal is not None:
        state["signal"] = signal
    temperature = _as_float(data.get("temperature"))
    if temperature is not None:
        state["temperature"] = temperature
    return state


def map_hub_state(hub: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    """Hub JSON -> (online, alarm_panel state)."""
    state: Dict[str, Any] = {}
    mode = arm_mode_from_ajax(_first(hub, "state", "armState", "arming", "hubState", "securityState"))
    if mode is not None:
        state["arm_mode"] = mode
    alarm = _as_bool(_first(hub, "alarm", "alarmActive", "alarmState", "inAlarm"))
    if alarm is not None:
        state["alarm"] = alarm
    problems = _first(hub, "malfunctions", "problems", "troubles")
    state["ready"] = not problems if isinstance(problems, (list, dict, bool)) else True
    common = _common_state(hub)
    common.pop("temperature", None)
    state.update(common)
    if "signal" not in state:
        gsm = signal_percent(_first(hub, "gsm", "cellular"))
        if gsm is not None:
            state["signal"] = gsm
        elif _as_str(_first(hub.get("ethernet") or {}, "connectionStatus", "state")).upper() in ("CONNECTED", "ONLINE"):
            state["signal"] = 100
    online = _as_bool(_first(hub, "online", "isOnline", "connected"), True)
    return bool(online), state


def map_device_state(device: Dict[str, Any], category: str) -> Tuple[bool, Dict[str, Any]]:
    """Ajax device JSON -> (online, hub state) for a category."""
    state = _common_state(device)
    if category == "sensor_motion":
        state["motion"] = _as_bool(_first(device, "motionDetected", "motion", "motionAlarm", "alarm"), False)
    elif category == "sensor_contact":
        opened = _contact_open(device)
        state["contact"] = bool(opened)
    elif category == "sensor_multi":
        state["alarm"] = _as_bool(_first(device, "glassBreakDetected", "glassBreak", "breakDetected", "alarm"), False)
    elif category == "sensor_smoke":
        state["smoke"] = _as_bool(_first(device, "smokeDetected", "smoke", "smokeAlarm", "fireAlarm", "alarm"), False)
        state["co"] = _as_bool(_first(device, "coDetected", "co", "coAlarm", "carbonMonoxideDetected"), False)
    elif category == "sensor_water":
        state["water_leak"] = _as_bool(_first(device, "leakDetected", "leak", "waterLeak", "leakage", "alarm"), False)
    elif category == "siren":
        state["siren"] = _as_bool(_first(device, "sirenActive", "sirenState", "siren", "alarm"), False)
    elif category in ("plug", "switch"):
        state["switch"] = _as_bool(_first(device, "switchState", "relayState", "state", "isOn", "on", "enabled"), False)
        power = _as_float(_first(device, "power", "currentPower", "powerConsumption", "activePower"))
        if power is not None:
            state["power"] = power
        energy = _as_float(_first(device, "energy", "energyConsumption", "totalEnergy"))
        if energy is not None:
            state["energy"] = energy
    elif category == "gateway":
        count = _as_int(_first(device, "devicesCount", "childCount", "connectedDevices"))
        if count is not None:
            state["child_count"] = count
    elif category == "alarm_zone":
        opened = _contact_open(device)
        if opened is not None:
            state["open"] = opened
        state["alarm"] = _as_bool(_first(device, "alarm", "alarmActive", "triggered"), False)
        state["bypass"] = _as_bool(_first(device, "bypass", "bypassed", "deactivated"), False)
    online = _as_bool(_first(device, "online", "isOnline", "connected"), True)
    return bool(online), state


def device_capabilities(category: str, device: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Capabilities for a mapped Ajax device."""
    if category == "alarm_zone":
        return alarm_zone_caps()
    caps: List[Dict[str, Any]] = []
    if category == "sensor_motion":
        caps.append(cap("motion", "bool"))
    elif category == "sensor_contact":
        caps.append(cap("contact", "bool"))
    elif category == "sensor_multi":
        caps.append(cap("alarm", "bool", label="Bris de vitre"))
    elif category == "sensor_smoke":
        caps += [cap("smoke", "bool"), cap("co", "bool"), cap("temperature", "float", unit="°C")]
    elif category == "sensor_water":
        caps.append(cap("water_leak", "bool"))
    elif category == "siren":
        caps.append(cap("siren", "bool"))
    elif category in ("plug", "switch"):
        caps.append(cap("switch", "bool", True))
        if _first(device, "power", "currentPower", "powerConsumption", "activePower") is not None:
            caps.append(cap("power", "float", unit="W"))
        if _first(device, "energy", "energyConsumption", "totalEnergy") is not None:
            caps.append(cap("energy", "float", unit="kWh"))
    elif category == "gateway":
        caps.append(cap("child_count", "int"))
    if category == "sensor_motion" and device.get("temperature") is not None:
        caps.append(cap("temperature", "float", unit="°C"))
    if _first(device, "batteryChargeLevelPercentage", "batteryLevel", "battery") is not None or category.startswith("sensor_"):
        caps.append(cap("battery", "int", unit="%"))
    caps.append(cap("tamper", "bool"))
    caps.append(cap("signal", "int", unit="%"))
    return caps


def _firmware_of(data: Dict[str, Any]) -> Optional[str]:
    value = _first(data, "firmwareVersion", "firmware", "version")
    if isinstance(value, dict):
        value = _first(value, "version", "name")
    return _as_str(value) or None


def hub_draft(hub: Dict[str, Any], groups: Optional[List[Dict[str, Any]]] = None) -> DeviceDraft:
    """Ajax hub -> alarm_panel draft."""
    hub_id = hub_id_of(hub)
    online, state = map_hub_state(hub)
    state.setdefault("arm_mode", "disarmed")
    state.setdefault("alarm", False)
    state.setdefault("triggered_zone", "")
    group_list = [{"id": _as_str(_first(g, "id", "groupId")), "name": _as_str(_first(g, "groupName", "name"))} for g in groups or []]
    config: Dict[str, Any] = {"hub_id": hub_id, "groups": group_list, "group_mode": bool(_first(hub, "groupsEnabled", "groupMode", default=False))}
    return DeviceDraft(
        external_id=hub_id,
        name=_as_str(_first(hub, "name", "hubName")) or f"Ajax Hub {hub_id}",
        category="alarm_panel",
        protocol=PROTOCOL_CLOUD,
        model=_as_str(_first(hub, "hubSubtype", "hubType", "model")) or "Hub",
        manufacturer=MANUFACTURER,
        firmware=_firmware_of(hub),
        capabilities=alarm_panel_caps() + [cap("battery", "int", unit="%"), cap("tamper", "bool"), cap("signal", "int", unit="%")],
        state=state,
        config=config,
        online=online,
        icon="shield",
    )


def device_draft(device: Dict[str, Any], hub_id: str) -> DeviceDraft:
    """Ajax device -> child draft under the hub."""
    device_type = _as_str(_first(device, "deviceType", "type", "model"))
    category = category_for(device_type)
    online, state = map_device_state(device, category)
    config: Dict[str, Any] = {"hub_id": hub_id, "device_type": device_type}
    room = _as_str(_first(device, "roomName", "room"))
    if room:
        config["room"] = room
    group = _as_str(_first(device, "groupId", "group"))
    if group:
        config["group_id"] = group
    return DeviceDraft(
        external_id=device_id_of(device),
        name=_as_str(_first(device, "deviceName", "name")) or device_type or "Ajax device",
        category=category,
        protocol=PROTOCOL_CLOUD,
        model=device_type or None,
        manufacturer=MANUFACTURER,
        firmware=_firmware_of(device),
        capabilities=device_capabilities(category, device),
        state=state,
        config=config,
        parent_external_id=hub_id,
        online=online,
    )


# =============================================================================== cloud client
def _session_tokens(session: "AjaxSession") -> Tuple[str, str, str]:
    """Rotating fields of a session (used to detect token refreshes)."""
    return (session.session_token, session.refresh_token, session.user_id)


@dataclass
class AjaxSession:
    """Credentials + tokens of one Ajax account (mutable: tokens rotate)."""

    base_url: str = DEFAULT_BASE_URL
    api_key: str = ""
    login: str = ""
    user_id: str = ""
    session_token: str = ""
    refresh_token: str = ""
    password_hash: str = ""

    @property
    def key(self) -> str:
        """Cache key (one session per account per API host)."""
        return f"{self.base_url}|{self.login or self.user_id}"

    @classmethod
    def from_ref(cls, device: DeviceRef) -> "AjaxSession":
        """Session rebuilt from the integration stored with a device."""
        return cls(
            base_url=_as_str(device.cfg("base_url")).rstrip("/") or DEFAULT_BASE_URL,
            api_key=_as_str(device.cred("api_key")),
            login=_as_str(device.cred("login")),
            user_id=_as_str(device.cfg("user_id") or device.cred("user_id")),
            session_token=_as_str(device.cred("session_token")),
            refresh_token=_as_str(device.cred("refresh_token")),
            password_hash=_as_str(device.cred("password_hash")),
        )

    def headers(self, with_session: bool = True) -> Dict[str, str]:
        """HTTP headers for the Enterprise API."""
        headers = {"X-Api-Key": self.api_key, "Accept": "application/json"}
        if with_session and self.session_token:
            headers["X-Session-Token"] = self.session_token
        return headers


def _error_message(response: httpx.Response, fallback: str) -> str:
    try:
        body = response.json()
    except ValueError:
        return fallback
    if isinstance(body, dict):
        return _as_str(_first(body, "message", "error", "detail", "errorMessage")) or fallback
    return fallback


class AjaxClient:
    """Thin Enterprise API client: auth headers, one automatic session refresh, error mapping."""

    def __init__(self, client: httpx.AsyncClient, session: AjaxSession, log: Optional[logging.Logger] = None):
        self.client = client
        self.session = session
        self.log = log or logger

    def url(self, path: str) -> str:
        """Absolute URL for an API path."""
        return f"{self.session.base_url.rstrip('/')}/{path.lstrip('/')}"

    def user_path(self, suffix: str = "") -> str:
        """``/user/{userId}<suffix>``."""
        return f"/user/{self.session.user_id}{suffix}"

    async def _send(self, method: str, path: str, json_body: Any = None, with_session: bool = True) -> httpx.Response:
        try:
            return await self.client.request(method, self.url(path), headers=self.session.headers(with_session), json=json_body)
        except httpx.TimeoutException as exc:
            raise AdapterError("Ajax cloud did not answer in time", "unreachable") from exc
        except httpx.HTTPError as exc:
            raise AdapterError(f"Ajax cloud unreachable: {exc.__class__.__name__}", "unreachable") from exc

    @staticmethod
    def _raise_for(response: httpx.Response, what: str) -> None:
        status = response.status_code
        if status < 400:
            return
        if status in (401, 403):
            raise AdapterError(_error_message(response, f"Ajax refused {what} (check API key, login and password)"), "auth_failed")
        if status == 404:
            raise AdapterError(_error_message(response, f"Ajax: {what} not found"), "not_found")
        if status in (400, 405, 409, 422):
            raise AdapterError(_error_message(response, f"Ajax rejected {what}"), "invalid_input")
        if status == 429:
            raise AdapterError("Ajax cloud rate limit reached, retry later", "unreachable")
        raise AdapterError(f"Ajax cloud error {status} on {what}", "unreachable")

    @staticmethod
    def _payload(response: httpx.Response) -> Any:
        if not response.content or not response.content.strip():
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise AdapterError("Ajax cloud answered with invalid JSON", "unreachable") from exc

    async def login(self, login: str, password: str) -> None:
        """``POST /login`` and store the tokens on the session."""
        body = {"login": login, "passwordHash": password_hash(password), "userRole": "USER"}
        response = await self._send("POST", "/login", body, with_session=False)
        self._raise_for(response, "login")
        self._store_tokens(self._payload(response), "login")
        self.session.login = login
        self.session.password_hash = body["passwordHash"]

    def _store_tokens(self, data: Any, what: str) -> None:
        if not isinstance(data, dict) or not data.get("sessionToken"):
            raise AdapterError(f"Unexpected Ajax {what} response (no session token)", "auth_failed")
        self.session.session_token = _as_str(data.get("sessionToken"))
        self.session.refresh_token = _as_str(data.get("refreshToken")) or self.session.refresh_token
        user_id = _as_str(data.get("userId"))
        if user_id:
            self.session.user_id = user_id

    async def refresh_session(self) -> None:
        """``POST /refresh``; falls back to a fresh login when the stored password hash is known."""
        session = self.session
        if session.refresh_token and session.user_id:
            response = await self._send("POST", "/refresh", {"userId": session.user_id, "refreshToken": session.refresh_token})
            if response.status_code < 400:
                self._store_tokens(self._payload(response), "refresh")
                self.log.info("ajax: session refreshed for %s", session.login or session.user_id)
                return
            if response.status_code not in (400, 401, 403, 404):
                self._raise_for(response, "session refresh")
        if session.login and session.password_hash:
            body = {"login": session.login, "passwordHash": session.password_hash, "userRole": "USER"}
            response = await self._send("POST", "/login", body, with_session=False)
            self._raise_for(response, "login")
            self._store_tokens(self._payload(response), "login")
            self.log.info("ajax: re-authenticated %s", session.login)
            return
        raise AdapterError("Ajax session expired; pair the Ajax account again", "auth_failed")

    async def request(self, method: str, path: str, json_body: Any = None, what: str = "") -> Any:
        """Authenticated request; refreshes the session once on 401 and returns the JSON payload."""
        what = what or f"{method} {path}"
        response = await self._send(method, path, json_body)
        if response.status_code == 401:
            self.log.info("ajax: session token rejected on %s; refreshing", what)
            await self.refresh_session()
            response = await self._send(method, path, json_body)
        self._raise_for(response, what)
        return self._payload(response)

    async def get(self, path: str, what: str = "") -> Any:
        """GET helper."""
        return await self.request("GET", path, None, what)

    async def put(self, path: str, body: Any, what: str = "") -> Any:
        """PUT helper."""
        return await self.request("PUT", path, body, what)

    async def post(self, path: str, body: Any, what: str = "") -> Any:
        """POST helper."""
        return await self.request("POST", path, body, what)


# =============================================================================== webhook mapping
def _flatten_webhook(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8", "replace")
    if isinstance(payload, str):
        text = payload.strip()
        if not text:
            return []
        try:
            payload = json.loads(text)
        except ValueError as exc:
            raise AdapterError("Ajax webhook body is not JSON", "invalid_input") from exc
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("events", "data", "items", "notifications"):
            if isinstance(payload.get(key), list):
                return [item for item in payload[key] if isinstance(item, dict)]
        if isinstance(payload.get("event"), dict):
            return [payload["event"]]
        return [payload]
    return []


def _normalise_code(value: Any) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "_", _as_str(value)).strip("_").upper()
    return text


def _keyword_updates(code: str, name: str, category: Optional[str]) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
    """Liberal keyword mapping of an Ajax event name -> (hub state, device state, hub event types)."""
    tokens = set(code.split("_")) if code else set()
    hub_state: Dict[str, Any] = {}
    device_state: Dict[str, Any] = {}
    hub_events: List[str] = []
    restore = bool(tokens & {"RESTORE", "RESTORED", "CLEAR", "CLEARED", "RECOVER", "RECOVERED", "RECOVERY", "END",
                             "ENDED", "STOP", "STOPPED", "NORMAL", "CANCEL", "CANCELED", "CANCELLED", "RESET"})
    off = "OFF" in tokens
    on = "ON" in tokens
    detection = None if restore else True
    if tokens & {"NIGHT"}:
        hub_state["arm_mode"] = "disarmed" if off else "armed_night"
    elif tokens & {"PARTIAL", "PARTIALLY", "STAY", "PERIMETER"} or ({"HOME"} & tokens and tokens & {"ARM", "ARMED", "ARMING"}):
        hub_state["arm_mode"] = "armed_home"
    elif tokens & {"DISARM", "DISARMED", "DISARMING"}:
        hub_state["arm_mode"] = "disarmed"
        hub_state["alarm"] = False
    elif tokens & {"ARM", "ARMED", "ARMING"}:
        hub_state["arm_mode"] = "armed_away"

    if tokens & {"SMOKE", "FIRE", "HEAT", "COMBUSTION"}:
        device_state["smoke"] = not restore
        if detection:
            hub_state.update({"alarm": True, "triggered_zone": name})
            hub_events.append("fire")
    elif tokens & {"CO", "CARBON", "MONOXIDE"}:
        device_state["co"] = not restore
        if detection:
            hub_state.update({"alarm": True, "triggered_zone": name})
            hub_events.append("co")
    elif tokens & {"LEAK", "LEAKAGE", "FLOOD", "FLOODING", "WATER"}:
        device_state["water_leak"] = not restore
        if detection:
            hub_state.update({"alarm": True, "triggered_zone": name})
            hub_events.append("water")
    elif tokens & {"GAS"}:
        device_state["gas"] = not restore
        if detection:
            hub_state.update({"alarm": True, "triggered_zone": name})
            hub_events.append("gas")
    elif tokens & {"TAMPER", "TAMPERED", "LID", "SABOTAGE"}:
        device_state["tamper"] = not restore
    elif tokens & {"PANIC", "SOS", "HOLDUP", "HOLD", "DURESS", "EMERGENCY"}:
        hub_state.update({"alarm": not restore, "triggered_zone": name or "panic"})
        if detection:
            hub_events.append("panic")
    elif tokens & {"MOTION", "MOVEMENT", "PIR", "MOVE"}:
        device_state["motion"] = not restore
    elif tokens & {"GLASS", "BREAK", "BREAKAGE"}:
        device_state["alarm"] = not restore
    elif tokens & {"DOOR", "WINDOW", "OPEN", "OPENED", "OPENING", "REED", "CONTACT", "CLOSE", "CLOSED", "CLOSING"}:
        if tokens & {"CLOSE", "CLOSED", "CLOSING"} or restore:
            device_state["contact"] = False
        elif tokens & {"OPEN", "OPENED", "OPENING", "DOOR", "WINDOW", "REED", "CONTACT"}:
            device_state["contact"] = True
    if tokens & {"ALARM", "INTRUSION", "BURGLARY", "INTRUDER", "TRIGGERED"} and "alarm" not in hub_state:
        hub_state["alarm"] = not restore
        if detection:
            hub_state["triggered_zone"] = name
            hub_events.append("alarm")
            if category in DETECTION_CODES and not device_state:
                device_state[DETECTION_CODES[category]] = True
    if tokens & {"SWITCH", "SWITCHED", "SOCKET", "RELAY", "OUTLET"} and (on or off):
        device_state["switch"] = on and not off
    if "SIREN" in tokens and (on or off or restore):
        device_state["siren"] = on and not (off or restore)
    if tokens & {"BATTERY"} and tokens & {"LOW", "CRITICAL", "DISCHARGED", "EMPTY"}:
        hub_events.append("battery_low")
    return hub_state, device_state, hub_events


def webhook_event_items(event: Dict[str, Any], default_hub: str = "") -> List[Dict[str, Any]]:
    """Translate one Ajax push object into hub items (``{"external_id", "type", "payload"}``)."""
    hub_id = _as_str(_first(event, "hubId", "hub_id", "hub")) or default_hub
    device_id = _as_str(_first(event, "deviceId", "device_id", "device", "sourceId"))
    device_type = _as_str(_first(event, "deviceType", "device_type"))
    device_name = _as_str(_first(event, "deviceName", "device_name", "sourceName", "name")) or device_id
    category = category_for(device_type) if device_type else None
    raw_code = _first(event, "eventCode", "event_code", "eventType", "event_type", "type", "event", "code", "name")
    code = _normalise_code(raw_code)
    state_value = event.get("state")
    hub_state: Dict[str, Any] = {}
    device_state: Dict[str, Any] = {}
    hub_events: List[Dict[str, Any]] = []
    device_events: List[Dict[str, Any]] = []
    detail = {"code": _as_str(raw_code), "device_id": device_id, "device_name": device_name, "hub_id": hub_id}

    # Explicit state objects / strings
    if isinstance(state_value, str) and not device_id:
        mode = arm_mode_from_ajax(state_value)
        if mode:
            hub_state["arm_mode"] = mode
    elif isinstance(state_value, dict):
        if device_id:
            if category:
                _, mapped = map_device_state(state_value, category)
                device_state.update(mapped)
            device_state.update({k: state_value[k] for k in CANONICAL_STATE_KEYS if k in state_value})
        else:
            _, mapped = map_hub_state(state_value)
            mapped.pop("ready", None)
            hub_state.update(mapped)

    # Event code: SIA two-letter codes or Ajax event names
    if re.fullmatch(r"[A-Z]{2}", code):
        update = map_sia_code(code, zone=device_id, text=device_name)
        hub_state.update(update.state)
        hub_events.extend(update.events)
        if device_id and update.category in ("burglary", "fire", "water", "gas", "co", "tamper", "tamper_restore", "restore"):
            key = DETECTION_CODES.get(category or "", "alarm")
            if update.category == "tamper":
                device_state["tamper"] = True
            elif update.category == "tamper_restore":
                device_state["tamper"] = False
            elif update.category == "restore":
                device_state[key] = False
            else:
                device_state[key] = True
    elif code:
        kw_hub, kw_device, kw_events = _keyword_updates(code, device_name, category)
        hub_state.update(kw_hub)
        device_state.update(kw_device)
        hub_events.extend({"type": etype, **detail} for etype in kw_events)

    # Common flat fields
    target_state = device_state if device_id else hub_state
    target_state.update({k: v for k, v in _common_state(event).items() if k not in target_state})
    online = _as_bool(_first(event, "online", "isOnline", "connected"))
    if code and "ONLINE" in code.split("_") and "OFFLINE" not in code.split("_"):
        online = True
    elif code and code.split("_")[0] in ("OFFLINE", "LOST", "DISCONNECTED") or "OFFLINE" in code.split("_"):
        online = False
    if online is not None and not device_id and "arm_mode" not in hub_state:
        target_state = hub_state

    items: List[Dict[str, Any]] = []
    if hub_id and (hub_state or (online is not None and not device_id)):
        payload: Dict[str, Any] = {"state": hub_state}
        if online is not None and not device_id:
            payload["online"] = online
        items.append({"external_id": hub_id, "type": "state", "payload": payload})
    if device_id and (device_state or online is not None):
        payload = {"state": device_state}
        if online is not None:
            payload["online"] = online
        items.append({"external_id": device_id, "type": "state", "payload": payload})
    for hub_event in hub_events:
        if hub_id:
            items.append({"external_id": hub_id, "type": "event", "payload": hub_event})
    for device_event in device_events:
        items.append({"external_id": device_id, "type": "event", "payload": device_event})
    if not items and (device_id or hub_id):
        items.append({
            "external_id": device_id or hub_id, "type": "event",
            "payload": {"type": code.lower() or "ajax_event", **detail, "raw": {k: v for k, v in event.items() if isinstance(v, (str, int, float, bool))}},
        })
    return items


# =============================================================================== adapter
class AjaxAdapter(BrandAdapter):
    """Ajax Systems: cloud account (Enterprise API) or SIA DC-09 monitoring station."""

    brand_id = BRAND_ID

    def __init__(self) -> None:
        self._sessions: Dict[str, AjaxSession] = {}

    # ------------------------------------------------------------------ catalogue
    def info(self) -> BrandInfo:
        return BrandInfo(
            id=BRAND_ID,
            name="Ajax Systems",
            vendor="Ajax Systems",
            description="Centrales Ajax (Hub, Hub 2, Hub Plus) via le cloud Ajax ou par réception SIA DC-09.",
            protocols=[PROTOCOL_CLOUD, PROTOCOL_SIA],
            categories=[
                "alarm_panel", "alarm_zone", "sensor_motion", "sensor_contact", "sensor_smoke", "sensor_water",
                "sensor_multi", "siren", "plug", "switch", "remote", "gateway",
            ],
            methods=[
                PairingMethod(
                    id=METHOD_CLOUD,
                    title="Compte Ajax (Enterprise API)",
                    description="Importe vos hubs et appareils Ajax depuis le cloud Ajax. Nécessite une clé API délivrée par Ajax Systems.",
                    fields=[
                        FormField(name="api_key", label="Clé API", type="password",
                                  help="Ajax Enterprise API key, obtained from Ajax Systems"),
                        FormField(name="login", label="Identifiant Ajax", type="text", placeholder="email@example.com"),
                        FormField(name="password", label="Mot de passe", type="password"),
                        FormField(name="base_url", label="URL de l'API", type="text", required=False, default=DEFAULT_BASE_URL,
                                  help="Laisser la valeur par défaut sauf instruction contraire d'Ajax Systems."),
                    ],
                    supports_discovery=True,
                    requires_integration=True,
                    icon="cloud",
                ),
                PairingMethod(
                    id=METHOD_SIA,
                    title="Station de surveillance SIA DC-09",
                    description="Le hub SafeR reçoit les rapports de la centrale (Ajax, Hikvision AX PRO, Paradox, DSC...) en SIA DC-09.",
                    fields=[
                        FormField(name="account", label="Numéro de compte SIA", type="text", placeholder="1234",
                                  help="3 à 16 caractères hexadécimaux. Configurez la « Station de surveillance » de la centrale "
                                       "(hub Ajax ou toute centrale Hikvision AX PRO, Paradox, DSC...) avec le protocole SIA DC-09, "
                                       "l'adresse IP de ce hub SafeR et le port HUB_SIA_PORT, mode non chiffré (plain), "
                                       "et ce numéro de compte."),
                        FormField(name="name", label="Nom de la centrale", type="text", required=False, placeholder="Centrale Ajax"),
                    ],
                    supports_discovery=False,
                    requires_integration=False,
                    icon="settings_input_antenna",
                ),
            ],
            icon="shield",
            docs_url="https://ajax.systems/",
            color="#111827",
        )

    # ------------------------------------------------------------------ sessions
    def _session_for(self, device: DeviceRef) -> AjaxSession:
        stored = AjaxSession.from_ref(device)
        if not stored.api_key:
            raise AdapterError("Ajax integration has no API key; pair the Ajax account again", "auth_failed")
        cached = self._sessions.get(stored.key)
        if cached is not None and cached.api_key == stored.api_key:
            return cached
        self._sessions[stored.key] = stored
        return stored

    def _forget(self, session: AjaxSession) -> None:
        self._sessions.pop(session.key, None)

    @staticmethod
    async def _persist_session(device: DeviceRef, session: AjaxSession, before: Tuple[str, str, str], ctx: AdapterContext) -> None:
        """Write rotated session/refresh tokens back to the integration so they survive restarts."""
        if _session_tokens(session) == before:
            return
        await ctx.update_integration_credentials(
            device.integration_id,
            {"session_token": session.session_token, "refresh_token": session.refresh_token, "user_id": session.user_id},
        )

    async def _login_session(self, payload: Dict[str, Any], client: httpx.AsyncClient, ctx: AdapterContext) -> AjaxClient:
        require(payload, "api_key", "login", "password")
        base_url = _as_str(payload.get("base_url")).rstrip("/") or DEFAULT_BASE_URL
        session = AjaxSession(base_url=base_url, api_key=_as_str(payload["api_key"]), login=_as_str(payload["login"]))
        api = AjaxClient(client, session, ctx.logger)
        await api.login(session.login, str(payload["password"]))
        self._sessions[session.key] = session
        return api

    async def _collect(self, api: AjaxClient) -> List[DeviceDraft]:
        """Hubs + devices of the account as drafts (hub first, then its children)."""
        hubs = _as_list(await api.get(api.user_path("/hubs"), "hub list"), "hubs", "items", "content")
        if not hubs:
            raise AdapterError("No Ajax hub is linked to this account", "not_found")
        drafts: List[DeviceDraft] = []
        for entry in hubs:
            hub_id = hub_id_of(entry)
            if not hub_id:
                continue
            hub = dict(entry)
            try:
                detail = await api.get(api.user_path(f"/hubs/{hub_id}"), f"hub {hub_id}")
                if isinstance(detail, dict):
                    hub.update(detail)
            except AdapterError as exc:
                if exc.code == "auth_failed":
                    raise
                api.log.warning("ajax: hub %s details unavailable (%s)", hub_id, exc.message)
            groups: List[Dict[str, Any]] = []
            try:
                groups = _as_list(await api.get(api.user_path(f"/hubs/{hub_id}/groups"), "groups"), "groups", "items")
            except AdapterError as exc:  # groups are optional (only in group mode)
                api.log.debug("ajax: no groups for hub %s (%s)", hub_id, exc.message)
            drafts.append(hub_draft(hub, groups))
            devices = _as_list(await api.get(api.user_path(f"/hubs/{hub_id}/devices"), "devices"), "devices", "items", "content")
            for device in devices:
                if device_id_of(device):
                    drafts.append(device_draft(device, hub_id))
        return drafts

    # ------------------------------------------------------------------ discovery / pairing
    async def discover(self, method_id: str, payload: Dict[str, Any], ctx: AdapterContext) -> List[DiscoveredDevice]:
        self.method(method_id)
        if method_id != METHOD_CLOUD:
            return []
        async with ctx.http() as client:
            api = await self._login_session(payload, client, ctx)
            drafts = await self._collect(api)
        return [
            DiscoveredDevice(
                external_id=draft.external_id, name=draft.name, category=draft.category, model=draft.model,
                manufacturer=MANUFACTURER, address="cloud",
                extra={"parent_external_id": draft.parent_external_id, "device_type": draft.config.get("device_type"), "online": draft.online},
            )
            for draft in drafts
        ]

    async def pair(self, method_id: str, payload: Dict[str, Any], ctx: AdapterContext) -> PairResult:
        self.method(method_id)
        if method_id == METHOD_SIA:
            return self._pair_sia(payload, ctx)
        async with ctx.http() as client:
            api = await self._login_session(payload, client, ctx)
            drafts = await self._collect(api)
        session = api.session
        integration = IntegrationDraft(
            key=f"ajax_cloud:{session.login}",
            name=f"Ajax ({session.login})",
            config={"base_url": session.base_url, "user_id": session.user_id},
            credentials={
                "api_key": session.api_key, "login": session.login, "session_token": session.session_token,
                "refresh_token": session.refresh_token, "password_hash": session.password_hash,
            },
        )
        hubs = sum(1 for d in drafts if d.parent_external_id is None)
        logger.info("ajax: paired %s hub(s), %s device(s) for %s", hubs, len(drafts) - hubs, session.login)
        return PairResult(devices=drafts, integration=integration, message=f"{hubs} centrale(s) et {len(drafts) - hubs} appareil(s) Ajax importés")

    def _pair_sia(self, payload: Dict[str, Any], ctx: AdapterContext) -> PairResult:
        require(payload, "account")
        account = _as_str(payload["account"]).upper()
        if not ACCOUNT_RE.match(account):
            raise AdapterError("SIA account must be 3 to 16 hexadecimal characters", "invalid_input")
        port = int(getattr(ctx.settings, "HUB_SIA_PORT", 0) or 0) if ctx.settings is not None else 0
        name = _as_str(payload.get("name")) or f"Centrale SIA {account}"
        draft = DeviceDraft(
            external_id=f"sia:{account}",
            name=name,
            category="alarm_panel",
            protocol=PROTOCOL_SIA,
            model="SIA DC-09",
            manufacturer=_as_str(payload.get("manufacturer")) or None,
            capabilities=alarm_panel_caps() + [cap("tamper", "bool")],
            state={"arm_mode": "disarmed", "alarm": False, "triggered_zone": "", "ready": True, "tamper": False},
            config={"account": account, "port": port},
            online=True,
            icon="shield",
        )
        port_text = str(port) if port else "HUB_SIA_PORT (récepteur SIA désactivé pour l'instant)"
        message = (
            f"Configurez la station de surveillance de la centrale : protocole SIA DC-09, IP du hub SafeR, "
            f"port {port_text}, compte {account}, mode non chiffré."
        )
        return PairResult(devices=[draft], message=message)

    # ------------------------------------------------------------------ state
    @staticmethod
    def _is_hub(device: DeviceRef) -> bool:
        return device.category == "alarm_panel" and _as_str(device.cfg("hub_id")) in ("", device.external_id)

    async def refresh(self, device: DeviceRef, ctx: AdapterContext) -> DeviceState:
        if device.protocol == PROTOCOL_SIA:
            return DeviceState(online=True, state=dict(device.state))
        session = self._session_for(device)
        before = _session_tokens(session)
        hub_id = _as_str(device.cfg("hub_id")) or device.external_id
        async with ctx.http() as client:
            api = AjaxClient(client, session, ctx.logger)
            try:
                if self._is_hub(device):
                    hub = await api.get(api.user_path(f"/hubs/{hub_id}"), f"hub {hub_id}")
                    if not isinstance(hub, dict):
                        raise AdapterError("Unexpected hub payload from Ajax", "unreachable")
                    online, state = map_hub_state(hub)
                else:
                    data = await api.get(api.user_path(f"/hubs/{hub_id}/devices/{device.external_id}"), f"device {device.external_id}")
                    if not isinstance(data, dict):
                        raise AdapterError("Unexpected device payload from Ajax", "unreachable")
                    online, state = map_device_state(data, device.category)
            except AdapterError as exc:
                if exc.code == "auth_failed":
                    self._forget(session)
                raise
        await self._persist_session(device, session, before, ctx)
        return DeviceState(online=online, state=state)

    # ------------------------------------------------------------------ commands
    async def send_command(self, device: DeviceRef, code: str, value: Any, ctx: AdapterContext) -> Dict[str, Any]:
        if device.protocol == PROTOCOL_SIA:
            raise AdapterError("SIA is one-way; arm from the Ajax app", "unsupported")
        session = self._session_for(device)
        before = _session_tokens(session)
        result: Optional[Dict[str, Any]] = None
        async with ctx.http() as client:
            api = AjaxClient(client, session, ctx.logger)
            try:
                if code == "arm_mode":
                    result = await self._arm(api, device, value)
                elif code == "switch" and device.category in ("plug", "switch"):
                    result = await self._switch(api, device, value)
            except AdapterError as exc:
                if exc.code == "auth_failed":
                    self._forget(session)
                raise
        await self._persist_session(device, session, before, ctx)
        if result is None:
            raise AdapterError(f"'{code}' cannot be written on this Ajax device", "unsupported")
        return result

    async def _arm(self, api: AjaxClient, device: DeviceRef, value: Any) -> Dict[str, Any]:
        mode = _as_str(value)
        if mode not in ARM_TO_AJAX:
            raise AdapterError(f"Unknown arm mode '{mode}'", "invalid_input")
        hub_id = _as_str(device.cfg("hub_id")) or device.external_id
        body = {"command": ARM_TO_AJAX[mode], "ignoreProblems": True}
        groups = device.cfg("groups") or []
        if mode == "armed_home" and isinstance(groups, list) and groups and device.cfg("group_mode"):
            # Ajax has no stay mode: in group mode arm every group (best effort), else arm the whole hub.
            armed = 0
            for group in groups:
                group_id = _as_str(group.get("id")) if isinstance(group, dict) else _as_str(group)
                if not group_id:
                    continue
                try:
                    await api.put(api.user_path(f"/hubs/{hub_id}/groups/{group_id}/commands/arming"), body, f"arm group {group_id}")
                    armed += 1
                except AdapterError as exc:
                    if exc.code == "auth_failed":
                        raise
                    api.log.warning("ajax: arming group %s failed (%s)", group_id, exc.message)
            if armed:
                return {"arm_mode": mode}
        await api.put(api.user_path(f"/hubs/{hub_id}/commands/arming"), body, f"arming {ARM_TO_AJAX[mode]}")
        partial: Dict[str, Any] = {"arm_mode": mode}
        if mode == "disarmed":
            partial["alarm"] = False
        return partial

    async def _switch(self, api: AjaxClient, device: DeviceRef, value: Any) -> Dict[str, Any]:
        on = bool(_as_bool(value, False))
        hub_id = _as_str(device.cfg("hub_id"))
        if not hub_id:
            raise AdapterError("Ajax device is missing its hub id", "invalid_input")
        body = {"command": "SWITCH_ON" if on else "SWITCH_OFF"}
        await api.post(api.user_path(f"/hubs/{hub_id}/devices/{device.external_id}/command"), body, body["command"])
        return {"switch": on}

    # ------------------------------------------------------------------ webhooks
    async def handle_webhook(
        self, integration_config: Dict[str, Any], integration_credentials: Dict[str, Any], payload: Any, ctx: AdapterContext
    ) -> List[Dict[str, Any]]:
        del integration_credentials, ctx
        events = _flatten_webhook(payload)
        default_hub = _as_str((integration_config or {}).get("hub_id"))
        items: List[Dict[str, Any]] = []
        for event in events:
            try:
                items.extend(webhook_event_items(event, default_hub))
            except Exception:  # pylint: disable=broad-except
                logger.exception("ajax: webhook event could not be mapped: %r", event)
        logger.debug("ajax: webhook produced %s item(s) from %s event(s)", len(items), len(events))
        return items


def iter_ajax_devices(drafts: Iterable[DeviceDraft]) -> Iterable[DeviceDraft]:
    """Children only (helper for callers that want to skip the hub)."""
    return (draft for draft in drafts if draft.parent_external_id is not None)


registry.register(AjaxAdapter())
