"""Home Assistant bridge adapter: surfaces HA entities (Zigbee, Z-Wave, MQTT, LoRa gateways, SafeR CI
nodes...) as hub devices through the HA REST API, and follows them live over the HA WebSocket API.

* ``GET  /api/states``                          -> discovery / import (``pair`` filters to the selected ids)
* ``GET  /api/states/{entity_id}``              -> ``refresh``
* ``POST /api/services/{domain}/{service}``     -> ``send_command`` (turn_on, set_cover_position, alarm_arm_away...)
* ``GET  /api/camera_proxy/{entity_id}``        -> snapshot;  ``/api/camera_proxy_stream/{entity_id}`` -> MJPEG stream
* ``ws(s)://.../api/websocket``                 -> ``subscribe_events`` ``state_changed`` (push, reconnecting)

Authentication: long-lived access token (``Authorization: Bearer``). One integration per HA instance
(``key = "ha:<url>"``) holds the url + token; devices carry ``entity_id``/``domain`` in their config.
Every HA entity is mapped to the hub's canonical categories and capability codes.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import quote, urlsplit

import httpx

from app.hub.adapters.base import (
    AdapterContext, AdapterError, BrandAdapter, BrandInfo, DeviceDraft, DeviceRef, DeviceState, DiscoveredDevice,
    FormField, IntegrationDraft, PairResult, PairingMethod, StreamInfo, Unsubscribe, require,
)
from app.hub.adapters.registry import registry
from app.hub.capabilities import (
    alarm_panel_caps, camera_caps, cap, cover_caps, light_caps, lock_caps, thermostat_caps,
)

logger = logging.getLogger("safer.hub.home_assistant")

BRAND_ID = "home_assistant"
PROTOCOL = "ha_rest"
METHOD_TOKEN = "long_lived_token"

WS_PATH = "/api/websocket"
SUBSCRIBE_ID = 1
CONNECT_TIMEOUT = 10.0
UNAVAILABLE_STATES = frozenset({"unavailable", "unknown"})

SWITCH_DOMAINS = frozenset({"switch", "fan", "input_boolean"})
SUPPORTED_DOMAINS = SWITCH_DOMAINS | {
    "light", "binary_sensor", "sensor", "lock", "cover", "climate", "alarm_control_panel", "camera", "siren",
}
COLOR_MODES = frozenset({"hs", "rgb", "rgbw", "rgbww", "xy"})
WHITE_MODES = frozenset({"color_temp", "white"})

# binary_sensor device_class -> (category, capability code)
BINARY_SENSOR_MAP: Dict[str, Tuple[str, str]] = {
    "door": ("sensor_contact", "contact"),
    "window": ("sensor_contact", "contact"),
    "opening": ("sensor_contact", "contact"),
    "garage_door": ("sensor_contact", "contact"),
    "motion": ("sensor_motion", "motion"),
    "occupancy": ("sensor_motion", "motion"),
    "presence": ("sensor_motion", "motion"),
    "smoke": ("sensor_smoke", "smoke"),
    "carbon_monoxide": ("sensor_gas", "co"),
    "moisture": ("sensor_water", "water_leak"),
    "gas": ("sensor_gas", "gas"),
    "vibration": ("sensor_multi", "tamper"),
    "tamper": ("sensor_multi", "tamper"),
}
# sensor device_class -> (category, capability code, unit)
SENSOR_MAP: Dict[str, Tuple[str, str, str]] = {
    "temperature": ("sensor_temperature", "temperature", "°C"),
    "humidity": ("sensor_humidity", "humidity", "%"),
    "illuminance": ("generic", "illuminance", "lx"),
    "battery": ("generic", "battery", "%"),
    "power": ("generic", "power", "W"),
    "energy": ("generic", "energy", "kWh"),
}
HVAC_TO_MODE = {"off": "off", "heat": "heat", "cool": "cool", "heat_cool": "auto", "auto": "auto"}
ALARM_TO_ARM = {
    "disarmed": "disarmed", "armed_home": "armed_home", "armed_away": "armed_away", "armed_night": "armed_night",
    "armed_vacation": "armed_away", "armed_custom_bypass": "armed_home",
}
ARM_TO_SERVICE = {
    "disarmed": "alarm_disarm", "armed_home": "alarm_arm_home", "armed_away": "alarm_arm_away",
    "armed_night": "alarm_arm_night",
}
COVER_CONTROL_SERVICE = {"open": "open_cover", "close": "close_cover", "stop": "stop_cover"}

Connector = Callable[[str], Awaitable[Any]]


# =============================================================================== helpers
def normalize_url(value: Any) -> str:
    """``http://homeassistant.local:8123`` from whatever the user typed (no trailing slash, no ``/api``)."""
    text = str(value or "").strip()
    if not text:
        raise AdapterError("Missing Home Assistant URL", "invalid_input")
    if "://" not in text:
        text = "http://" + text
    parts = urlsplit(text)
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        raise AdapterError(f"Invalid Home Assistant URL '{value}'", "invalid_input")
    path = parts.path.rstrip("/")
    if path.endswith("/api"):
        path = path[:-4]
    return f"{parts.scheme.lower()}://{parts.netloc}{path}"


def websocket_url(base_url: str) -> str:
    """``ws(s)://host:port/api/websocket`` for a REST base URL."""
    scheme, rest = base_url.split("://", 1)
    return f"{'wss' if scheme == 'https' else 'ws'}://{rest}{WS_PATH}"


def split_entity_id(entity_id: str) -> Tuple[str, str]:
    """``light.salon`` -> ``("light", "salon")``."""
    domain, _, object_id = entity_id.partition(".")
    return domain, object_id


def is_online(raw_state: Any) -> bool:
    """HA ``unavailable``/``unknown`` states mean the entity is not reporting."""
    return str(raw_state) not in UNAVAILABLE_STATES


def _float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> Optional[int]:
    number = _float(value)
    return None if number is None else int(round(number))


def _selected_ids(payload: Dict[str, Any]) -> Optional[Set[str]]:
    for key in ("selected_external_ids", "entity_ids", "external_ids"):
        value = payload.get(key)
        if isinstance(value, (list, tuple, set)) and value:
            return {str(item) for item in value}
    return None


# =============================================================================== entity mapping
@dataclass
class EntityInfo:
    """An HA entity translated into the hub model."""

    entity_id: str
    domain: str
    device_class: Optional[str]
    name: str
    category: str
    capabilities: List[Dict[str, Any]]
    state: Dict[str, Any]
    online: bool
    raw_state: str = ""
    attributes: Dict[str, Any] = field(default_factory=dict)


def map_category(domain: str, device_class: Optional[str]) -> Optional[str]:
    """Hub category for an HA entity, or None when the entity is not imported."""
    if domain == "light":
        return "light"
    if domain in ("switch", "input_boolean"):
        return "plug" if device_class == "outlet" else "switch"
    if domain == "fan":
        return "switch"
    if domain == "binary_sensor":
        return BINARY_SENSOR_MAP.get(device_class or "", ("generic", ""))[0]
    if domain == "sensor":
        entry = SENSOR_MAP.get(device_class or "")
        return entry[0] if entry else None
    return {
        "lock": "lock", "cover": "cover", "climate": "thermostat", "alarm_control_panel": "alarm_panel",
        "camera": "camera", "siren": "siren",
    }.get(domain)


def build_capabilities(domain: str, device_class: Optional[str], attributes: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Canonical capabilities for an HA entity (from its domain, device_class and attributes)."""
    caps: List[Dict[str, Any]] = []
    if domain == "light":
        modes = [str(m) for m in (attributes.get("supported_color_modes") or [])]
        dimmable = any(mode != "onoff" for mode in modes) or attributes.get("brightness") is not None
        caps = light_caps(dimmable=dimmable, color_temp="color_temp" in modes, color=any(m in COLOR_MODES for m in modes))
        for item in caps:
            if item["code"] == "color_temp":
                low, high = _int(attributes.get("min_color_temp_kelvin")), _int(attributes.get("max_color_temp_kelvin"))
                if low and high and low < high:
                    item["min"], item["max"] = low, high
    elif domain in SWITCH_DOMAINS:
        caps = [cap("switch", "bool", True)]
        if attributes.get("current_power_w") is not None:
            caps.append(cap("power", "float", unit="W"))
    elif domain == "binary_sensor":
        code = BINARY_SENSOR_MAP.get(device_class or "", ("", ""))[1] or f"raw_{device_class or 'state'}"
        caps = [cap(code, "bool", label=device_class)]
    elif domain == "sensor":
        entry = SENSOR_MAP.get(device_class or "")
        code, unit = (entry[1], entry[2]) if entry else ("raw_value", attributes.get("unit_of_measurement"))
        caps = [cap(code, "float", unit=unit)]
    elif domain == "lock":
        caps = lock_caps()
    elif domain == "cover":
        caps = cover_caps()
    elif domain == "climate":
        caps = thermostat_caps()
        for item in caps:
            if item["code"] == "temp_set":
                low, high = _float(attributes.get("min_temp")), _float(attributes.get("max_temp"))
                if low is not None and high is not None and low < high:
                    item["min"], item["max"] = low, high
                step = _float(attributes.get("target_temp_step"))
                if step:
                    item["step"] = step
    elif domain == "alarm_control_panel":
        caps = alarm_panel_caps()
    elif domain == "camera":
        caps = camera_caps()
    elif domain == "siren":
        caps = [cap("siren", "bool", True)]
    battery = attributes.get("battery_level", attributes.get("battery"))
    if _float(battery) is not None and not any(item["code"] == "battery" for item in caps):
        caps.append(cap("battery", "int", unit="%"))
    return caps


def map_state(entity_id: str, domain: str, device_class: Optional[str], raw_state: str, attributes: Dict[str, Any], base_url: str) -> Dict[str, Any]:
    """Canonical hub state for an HA state object."""
    on = raw_state == "on"
    state: Dict[str, Any] = {}
    if domain == "light":
        state["switch"] = on
        brightness = _float(attributes.get("brightness"))
        if brightness is not None:
            state["brightness"] = int(round(brightness * 100 / 255))
        kelvin = _int(attributes.get("color_temp_kelvin"))
        if kelvin:
            state["color_temp"] = kelvin
        else:
            mireds = _float(attributes.get("color_temp"))
            if mireds:
                state["color_temp"] = int(round(1_000_000 / mireds))
        hs_color = attributes.get("hs_color")
        if isinstance(hs_color, (list, tuple)) and len(hs_color) >= 2 and _float(hs_color[0]) is not None:
            state["color"] = {"h": round(float(hs_color[0]), 1), "s": round(float(hs_color[1]), 1), "v": state.get("brightness", 100)}
        color_mode = attributes.get("color_mode")
        if color_mode in WHITE_MODES:
            state["work_mode"] = "white"
        elif color_mode in COLOR_MODES:
            state["work_mode"] = "colour"
    elif domain in SWITCH_DOMAINS:
        state["switch"] = on
        power = _float(attributes.get("current_power_w"))
        if power is not None:
            state["power"] = power
    elif domain == "binary_sensor":
        code = BINARY_SENSOR_MAP.get(device_class or "", ("", ""))[1] or f"raw_{device_class or 'state'}"
        state[code] = on
    elif domain == "sensor":
        entry = SENSOR_MAP.get(device_class or "")
        code = entry[1] if entry else "raw_value"
        value = _float(raw_state)
        if value is not None:
            if code == "temperature" and str(attributes.get("unit_of_measurement", "")).upper().endswith("F"):
                value = round((value - 32) * 5 / 9, 1)
            state[code] = value
    elif domain == "lock":
        state["locked"] = raw_state == "locked"
    elif domain == "cover":
        position = _int(attributes.get("current_position"))
        if position is not None:
            state["position"] = max(0, min(100, position))
        elif raw_state in ("open", "closed"):
            state["position"] = 100 if raw_state == "open" else 0
        if raw_state in ("opening", "closing"):
            state["control"] = "open" if raw_state == "opening" else "close"
    elif domain == "climate":
        current = _float(attributes.get("current_temperature"))
        if current is not None:
            state["temp_current"] = current
        target = _float(attributes.get("temperature"))
        if target is not None:
            state["temp_set"] = target
        mode = HVAC_TO_MODE.get(raw_state)
        if mode:
            state["mode"] = mode
        humidity = _float(attributes.get("current_humidity"))
        if humidity is not None:
            state["humidity_current"] = humidity
    elif domain == "alarm_control_panel":
        arm_mode = ALARM_TO_ARM.get(raw_state)
        if arm_mode:
            state["arm_mode"] = arm_mode
        state["alarm"] = raw_state == "triggered"
        state["ready"] = raw_state in ALARM_TO_ARM
    elif domain == "camera":
        state["stream_main"] = f"{base_url}/api/camera_proxy_stream/{entity_id}"
        state["stream_sub"] = state["stream_main"]
        state["snapshot"] = f"{base_url}/api/camera_proxy/{entity_id}"
        state["recording"] = raw_state == "recording"
    elif domain == "siren":
        state["siren"] = on
    battery = _int(attributes.get("battery_level", attributes.get("battery")))
    if battery is not None:
        state["battery"] = max(0, min(100, battery))
    return state


def describe_entity(entity: Dict[str, Any], base_url: str, force: bool = False) -> Optional[EntityInfo]:
    """Translate one HA state object. Returns None for entities the hub does not import
    (unless ``force`` is set, in which case they land in the ``generic`` category)."""
    entity_id = entity.get("entity_id")
    if not isinstance(entity_id, str) or "." not in entity_id:
        return None
    domain, _ = split_entity_id(entity_id)
    attributes = entity.get("attributes") if isinstance(entity.get("attributes"), dict) else {}
    device_class = attributes.get("device_class") or attributes.get("original_device_class") or None
    category = map_category(domain, device_class)
    if category is None:
        if not force:
            return None
        category = "generic"
    raw_state = str(entity.get("state", ""))
    return EntityInfo(
        entity_id=entity_id,
        domain=domain,
        device_class=device_class,
        name=str(attributes.get("friendly_name") or entity_id),
        category=category,
        capabilities=build_capabilities(domain, device_class, attributes),
        state=map_state(entity_id, domain, device_class, raw_state, attributes, base_url),
        online=is_online(raw_state),
        raw_state=raw_state,
        attributes=attributes,
    )


def mode_to_hvac(mode: str, hvac_modes: Optional[List[str]]) -> str:
    """Hub thermostat mode -> HA hvac_mode (``auto`` becomes ``heat_cool`` when the device offers it)."""
    supported = [str(m) for m in (hvac_modes or [])]
    if mode == "auto":
        if "heat_cool" in supported or "auto" not in supported:
            return "heat_cool"
        return "auto"
    return mode


def build_service_call(domain: str, code: str, value: Any, device: DeviceRef) -> Tuple[str, str, Dict[str, Any], Dict[str, Any]]:
    """(service domain, service, extra data, derived partial state) for a hub command."""
    if code == "switch":
        return domain, "turn_on" if value else "turn_off", {}, {}
    if code == "brightness":
        level = max(0, min(100, int(value)))
        if level == 0:
            return "light", "turn_off", {}, {"switch": False}
        return "light", "turn_on", {"brightness_pct": level}, {"switch": True}
    if code == "color_temp":
        return "light", "turn_on", {"color_temp_kelvin": int(value)}, {"switch": True, "work_mode": "white"}
    if code == "color":
        hue, sat, val = float(value["h"]), float(value["s"]), float(value.get("v", 100))
        data = {"hs_color": [round(hue, 2), round(sat, 2)], "brightness_pct": int(round(max(1.0, min(100.0, val))))}
        return "light", "turn_on", data, {"switch": True, "brightness": data["brightness_pct"], "work_mode": "colour"}
    if code == "work_mode":
        if value == "white":
            kelvin = _int(device.state.get("color_temp")) or 4000
            return "light", "turn_on", {"color_temp_kelvin": kelvin}, {"switch": True}
        if value == "colour":
            color = device.state.get("color") if isinstance(device.state.get("color"), dict) else {}
            data = {"hs_color": [float(color.get("h", 0)), float(color.get("s", 100))]}
            return "light", "turn_on", data, {"switch": True}
        raise AdapterError("Home Assistant lights have no scene mode", "unsupported")
    if code == "locked":
        return "lock", "lock" if value else "unlock", {}, {}
    if code == "position":
        return "cover", "set_cover_position", {"position": max(0, min(100, int(value)))}, {}
    if code == "control":
        service = COVER_CONTROL_SERVICE.get(str(value))
        if service is None:
            raise AdapterError(f"Unknown cover control '{value}'", "invalid_input")
        return "cover", service, {}, {}
    if code == "temp_set":
        return "climate", "set_temperature", {"temperature": float(value)}, {}
    if code == "mode":
        return "climate", "set_hvac_mode", {"hvac_mode": mode_to_hvac(str(value), device.cfg("hvac_modes"))}, {}
    if code == "arm_mode":
        service = ARM_TO_SERVICE.get(str(value))
        if service is None:
            raise AdapterError(f"Unknown arm mode '{value}'", "invalid_input")
        data: Dict[str, Any] = {}
        alarm_code = device.cred("alarm_code") or device.cfg("alarm_code")
        if alarm_code:
            data["code"] = str(alarm_code)
        return "alarm_control_panel", service, data, {"alarm": False} if value == "disarmed" else {}
    if code == "siren":
        return "siren", "turn_on" if value else "turn_off", {}, {}
    raise AdapterError(f"Home Assistant entities do not accept '{code}' commands", "unsupported")


# =============================================================================== REST client
class HomeAssistantClient:
    """Thin REST client with hub error mapping."""

    def __init__(self, base_url: str, token: str, http: httpx.AsyncClient):
        self.base_url = base_url
        self.token = token
        self.http = http

    @property
    def headers(self) -> Dict[str, str]:
        """Bearer auth + JSON headers."""
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json", "Accept": "application/json"}

    async def request(self, method: str, path: str, json_body: Optional[Dict[str, Any]] = None) -> httpx.Response:
        """Perform one request; HTTP/network errors become ``AdapterError``."""
        url = f"{self.base_url}{path}"
        try:
            response = await self.http.request(method, url, json=json_body, headers=self.headers)
        except httpx.TimeoutException as exc:
            raise AdapterError(f"Home Assistant at {self.base_url} did not answer in time", "unreachable") from exc
        except httpx.HTTPError as exc:
            raise AdapterError(f"Cannot reach Home Assistant at {self.base_url}: {exc}", "unreachable") from exc
        status = response.status_code
        if status in (401, 403):
            raise AdapterError("Home Assistant rejected the access token (create a long-lived token in your profile)", "auth_failed")
        if status == 404:
            raise AdapterError(f"Home Assistant: {self._message(response) or 'not found'} ({path})", "not_found")
        if status == 400:
            raise AdapterError(f"Home Assistant refused the request: {self._message(response) or 'bad request'}", "invalid_input")
        if status >= 500:
            raise AdapterError(f"Home Assistant error HTTP {status} on {path}", "unreachable")
        if status >= 400:
            raise AdapterError(f"Home Assistant answered HTTP {status} on {path}", "invalid_input")
        return response

    @staticmethod
    def _message(response: httpx.Response) -> str:
        try:
            data = response.json()
        except ValueError:
            return response.text[:200].strip()
        if isinstance(data, dict):
            return str(data.get("message") or data.get("error") or "")
        return ""

    async def get_json(self, path: str) -> Any:
        """GET and decode JSON (non-JSON answers mean this is not a Home Assistant API)."""
        response = await self.request("GET", path)
        try:
            return response.json()
        except ValueError as exc:
            raise AdapterError(f"{self.base_url} did not answer with JSON - is this a Home Assistant instance?", "invalid_input") from exc

    async def states(self) -> List[Dict[str, Any]]:
        """All entity states."""
        data = await self.get_json("/api/states")
        if not isinstance(data, list):
            raise AdapterError("Unexpected /api/states answer from Home Assistant", "invalid_input")
        return [item for item in data if isinstance(item, dict)]

    async def state(self, entity_id: str) -> Dict[str, Any]:
        """One entity state (404 -> not_found)."""
        data = await self.get_json(f"/api/states/{quote(entity_id, safe='.')}")
        if not isinstance(data, dict):
            raise AdapterError("Unexpected entity state answer from Home Assistant", "invalid_input")
        return data

    async def call_service(self, domain: str, service: str, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """POST a service call; returns the states HA reports as changed."""
        response = await self.request("POST", f"/api/services/{domain}/{service}", json_body=data)
        try:
            result = response.json()
        except ValueError:
            return []
        return [item for item in result if isinstance(item, dict)] if isinstance(result, list) else []

    async def camera_snapshot(self, entity_id: str) -> bytes:
        """JPEG from the camera proxy."""
        response = await self.request("GET", f"/api/camera_proxy/{quote(entity_id, safe='.')}")
        if not response.content:
            raise AdapterError("Home Assistant returned an empty snapshot", "invalid_input")
        return response.content


# =============================================================================== websocket push
async def websockets_connector(url: str, open_timeout: float = CONNECT_TIMEOUT) -> Any:
    """Default connector: open a WebSocket with the ``websockets`` package (ships with uvicorn[standard])."""
    try:
        import websockets  # pylint: disable=import-outside-toplevel
        from websockets.exceptions import WebSocketException  # pylint: disable=import-outside-toplevel
    except ImportError as exc:  # pragma: no cover - dependency of uvicorn[standard]
        raise AdapterError("The 'websockets' package is required for Home Assistant push updates", "unsupported") from exc
    try:
        return await websockets.connect(url, open_timeout=open_timeout, max_size=None)
    except (OSError, asyncio.TimeoutError, TimeoutError, ValueError, WebSocketException) as exc:
        raise AdapterError(f"Cannot reach the Home Assistant WebSocket at {url}: {exc or exc.__class__.__name__}", "unreachable") from exc


async def _close_quietly(connection: Any) -> None:
    close = getattr(connection, "close", None)
    if close is None:
        return
    try:
        result = close()
        if inspect.isawaitable(result):
            await result
    except Exception:  # pylint: disable=broad-except
        logger.debug("Ignoring error while closing a Home Assistant WebSocket", exc_info=True)


class _InstanceSubscription:
    """One ``state_changed`` subscription per Home Assistant instance, reconnecting with back-off."""

    def __init__(self, adapter: "HomeAssistantAdapter", base_url: str, token: str, entity_ids: List[str], ctx: AdapterContext):
        self.adapter = adapter
        self.base_url = base_url
        self.ws_url = websocket_url(base_url)
        self.token = token
        self.entity_ids: Set[str] = set(entity_ids)
        self.ctx = ctx
        self.connected = asyncio.Event()
        self.connections = 0
        self.ha_version = ""
        self._stop = asyncio.Event()
        self._task: Optional["asyncio.Task[None]"] = None

    def start(self) -> None:
        """Spawn the background task."""
        self._task = asyncio.create_task(self._run(), name=f"home-assistant-subscription:{self.base_url}")

    async def stop(self) -> None:
        """Stop the task (cancels any back-off sleep) and close the socket."""
        self._stop.set()
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # pylint: disable=broad-except
                pass

    async def _run(self) -> None:
        backoff = self.adapter.reconnect_min
        while not self._stop.is_set():
            connection: Any = None
            delay = backoff
            try:
                connection = await self.adapter.connector(self.ws_url)
                await self._session(connection)
            except asyncio.CancelledError:
                raise
            except AdapterError as exc:
                if exc.code == "auth_failed":
                    logger.error("Home Assistant %s refused the token: %s (retrying in %.0fs)", self.base_url, exc.message, self.adapter.auth_failure_delay)
                    delay = self.adapter.auth_failure_delay
                else:
                    logger.warning("Home Assistant subscription %s failed: %s", self.base_url, exc.message)
            except Exception as exc:  # pylint: disable=broad-except
                if not self._stop.is_set():
                    logger.warning("Home Assistant WebSocket %s closed: %s; reconnecting", self.base_url, exc or exc.__class__.__name__)
            finally:
                was_connected = self.connected.is_set()
                self.connected.clear()
                if connection is not None:
                    await _close_quietly(connection)
            if was_connected:
                backoff = self.adapter.reconnect_min
                delay = backoff
            else:
                backoff = min(backoff * 2, self.adapter.reconnect_max)
            if await self._sleep(delay):
                break

    async def _sleep(self, seconds: float) -> bool:
        """Sleep unless stopped first; returns True when stopped."""
        if self._stop.is_set():
            return True
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=seconds)
            return True
        except asyncio.TimeoutError:
            return False

    async def _recv(self, connection: Any) -> Dict[str, Any]:
        """Next JSON object from the socket (non-JSON / non-object frames are skipped)."""
        while True:
            raw = await connection.recv()
            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode("utf-8", "replace")
            try:
                message = json.loads(raw)
            except (TypeError, ValueError):
                logger.debug("Ignoring non-JSON frame from %s", self.ws_url)
                continue
            if isinstance(message, dict):
                return message

    async def _session(self, connection: Any) -> None:
        """Authenticate, subscribe to ``state_changed`` and pump events until the socket closes."""
        message = await self._recv(connection)
        if message.get("type") == "auth_required":
            await connection.send(json.dumps({"type": "auth", "access_token": self.token}))
            message = await self._recv(connection)
        mtype = message.get("type")
        if mtype == "auth_invalid":
            raise AdapterError(str(message.get("message") or "invalid access token"), "auth_failed")
        if mtype != "auth_ok":
            raise AdapterError(f"Unexpected Home Assistant handshake message '{mtype}'", "invalid_input")
        self.ha_version = str(message.get("ha_version") or "")
        await connection.send(json.dumps({"id": SUBSCRIBE_ID, "type": "subscribe_events", "event_type": "state_changed"}))
        self.connections += 1
        self.connected.set()
        logger.info("Home Assistant push subscription active on %s (HA %s, %d entities)", self.base_url, self.ha_version or "?", len(self.entity_ids))
        while not self._stop.is_set():
            message = await self._recv(connection)
            mtype = message.get("type")
            if mtype == "event":
                await self._on_event(message.get("event") or {})
            elif mtype == "result" and message.get("id") == SUBSCRIBE_ID and not message.get("success", True):
                error = message.get("error") or {}
                raise AdapterError(f"subscribe_events failed: {error.get('message') or error}", "invalid_input")

    async def _on_event(self, event: Dict[str, Any]) -> None:
        if event.get("event_type") != "state_changed":
            return
        data = event.get("data") or {}
        entity_id = data.get("entity_id")
        if not isinstance(entity_id, str) or entity_id not in self.entity_ids:
            return
        new_state = data.get("new_state")
        if not isinstance(new_state, dict):
            await self.ctx.emit("state", entity_id, {"state": {}, "online": False})
            return
        info = describe_entity(new_state, self.base_url, force=True)
        if info is None:
            return
        try:
            await self.ctx.emit("state", entity_id, {"state": info.state, "online": info.online})
        except Exception:  # pylint: disable=broad-except
            logger.exception("Failed to apply Home Assistant state for %s", entity_id)


# =============================================================================== adapter
class HomeAssistantAdapter(BrandAdapter):
    """Home Assistant bridge: REST for import/refresh/commands, WebSocket for push."""

    brand_id = BRAND_ID

    def __init__(
        self,
        connector: Optional[Connector] = None,
        reconnect_min: float = 2.0,
        reconnect_max: float = 60.0,
        auth_failure_delay: float = 300.0,
    ):
        self.connector: Connector = connector or websockets_connector
        self.reconnect_min = reconnect_min
        self.reconnect_max = reconnect_max
        self.auth_failure_delay = auth_failure_delay

    def info(self) -> BrandInfo:
        return BrandInfo(
            id=BRAND_ID,
            name="Home Assistant",
            vendor="Open Home Foundation",
            description="Importe les appareils d'une instance Home Assistant (Zigbee, Z-Wave, MQTT, LoRa, nœuds SafeR CI...).",
            protocols=[PROTOCOL],
            categories=[
                "light", "switch", "plug", "sensor_contact", "sensor_motion", "sensor_smoke", "sensor_water", "sensor_gas",
                "sensor_multi", "sensor_temperature", "sensor_humidity", "lock", "cover", "thermostat", "alarm_panel",
                "camera", "siren", "generic",
            ],
            methods=[
                PairingMethod(
                    id=METHOD_TOKEN,
                    title="Jeton d'accès longue durée",
                    description="Connecte une instance Home Assistant et choisit les entités à importer.",
                    fields=[
                        FormField(name="url", label="Adresse de Home Assistant", type="text", placeholder="http://homeassistant.local:8123"),
                        FormField(name="token", label="Jeton d'accès", type="password", help="Long-lived access token from your HA profile"),
                    ],
                    supports_discovery=True,
                    requires_integration=True,
                    icon="home",
                )
            ],
            icon="home",
            docs_url="https://developers.home-assistant.io/docs/api/rest/",
            color="#03A9F4",
        )

    # ------------------------------------------------------------------ connection helpers
    @staticmethod
    def connection_from_payload(payload: Dict[str, Any]) -> Tuple[str, str]:
        """(url, token) from the pairing form."""
        require(payload, "url", "token")
        return normalize_url(payload["url"]), str(payload["token"]).strip()

    @staticmethod
    def connection_from_device(device: DeviceRef) -> Tuple[str, str]:
        """(url, token) from a device + its integration."""
        url = device.cfg("url")
        token = device.cred("token")
        if not url or not token:
            raise AdapterError("Home Assistant integration is missing its URL or token", "invalid_input")
        return normalize_url(url), str(token)

    @staticmethod
    def entity_id_for(device: DeviceRef) -> str:
        """Entity id of a paired device."""
        return str(device.cfg("entity_id") or device.external_id)

    # ------------------------------------------------------------------ onboarding
    async def discover(self, method_id: str, payload: Dict[str, Any], ctx: AdapterContext) -> List[DiscoveredDevice]:
        self.method(method_id)
        url, token = self.connection_from_payload(payload)
        async with ctx.http() as http:
            entities = await HomeAssistantClient(url, token, http).states()
        found: List[DiscoveredDevice] = []
        for entity in entities:
            info = describe_entity(entity, url)
            if info is None:
                continue
            found.append(
                DiscoveredDevice(
                    external_id=info.entity_id,
                    name=info.name,
                    category=info.category,
                    model=str(info.attributes.get("model") or "") or None,
                    address=url,
                    extra={"domain": info.domain, "device_class": info.device_class, "state": info.raw_state, "online": info.online},
                )
            )
        return found

    async def pair(self, method_id: str, payload: Dict[str, Any], ctx: AdapterContext) -> PairResult:
        self.method(method_id)
        url, token = self.connection_from_payload(payload)
        selected = _selected_ids(payload)
        async with ctx.http() as http:
            entities = await HomeAssistantClient(url, token, http).states()
        drafts: List[DeviceDraft] = []
        for entity in entities:
            info = describe_entity(entity, url)
            if info is None or (selected is not None and info.entity_id not in selected):
                continue
            drafts.append(self._draft(info))
        if selected is not None:
            missing = selected - {draft.external_id for draft in drafts}
            if missing:
                logger.warning("Home Assistant entities not importable/unknown, skipped: %s", ", ".join(sorted(missing)))
            if not drafts:
                raise AdapterError("None of the selected entities exist on this Home Assistant instance", "not_found")
        host = urlsplit(url).hostname or url
        integration = IntegrationDraft(key=f"ha:{url}", name=f"Home Assistant ({host})", config={"url": url}, credentials={"token": token})
        return PairResult(devices=drafts, integration=integration, message=f"{len(drafts)} entité(s) importée(s) depuis Home Assistant")

    @staticmethod
    def _draft(info: EntityInfo) -> DeviceDraft:
        config: Dict[str, Any] = {"entity_id": info.entity_id, "domain": info.domain}
        if info.device_class:
            config["device_class"] = info.device_class
        if info.domain == "climate" and isinstance(info.attributes.get("hvac_modes"), list):
            config["hvac_modes"] = [str(m) for m in info.attributes["hvac_modes"]]
        if info.domain == "light" and isinstance(info.attributes.get("supported_color_modes"), list):
            config["supported_color_modes"] = [str(m) for m in info.attributes["supported_color_modes"]]
        if info.domain == "alarm_control_panel":
            config["code_arm_required"] = bool(info.attributes.get("code_arm_required", False))
        return DeviceDraft(
            external_id=info.entity_id,
            name=info.name,
            category=info.category,
            protocol=PROTOCOL,
            model=str(info.attributes.get("model") or "") or None,
            capabilities=info.capabilities,
            state=info.state,
            config=config,
            online=info.online,
        )

    # ------------------------------------------------------------------ runtime
    async def refresh(self, device: DeviceRef, ctx: AdapterContext) -> DeviceState:
        url, token = self.connection_from_device(device)
        entity_id = self.entity_id_for(device)
        async with ctx.http() as http:
            entity = await HomeAssistantClient(url, token, http).state(entity_id)
        info = describe_entity(entity, url, force=True)
        if info is None:
            raise AdapterError(f"Unexpected state answer for {entity_id}", "invalid_input")
        return DeviceState(online=info.online, state=info.state)

    async def send_command(self, device: DeviceRef, code: str, value: Any, ctx: AdapterContext) -> Dict[str, Any]:
        url, token = self.connection_from_device(device)
        entity_id = self.entity_id_for(device)
        domain = str(device.cfg("domain") or split_entity_id(entity_id)[0])
        service_domain, service, data, derived = build_service_call(domain, code, value, device)
        body = {"entity_id": entity_id, **data}
        async with ctx.http() as http:
            await HomeAssistantClient(url, token, http).call_service(service_domain, service, body)
        partial: Dict[str, Any] = {code: value}
        partial.update(derived)
        return partial

    async def stream(self, device: DeviceRef, quality: str, ctx: AdapterContext) -> Optional[StreamInfo]:
        if device.category not in ("camera", "doorbell", "nvr"):
            return None
        url, token = self.connection_from_device(device)
        entity_id = self.entity_id_for(device)
        # The long-lived token is the whole integration's admin credential: it must never leave the hub.
        # Home Assistant issues a rotating per-camera ``access_token`` accepted as ``?token=`` by the proxy.
        async with ctx.http() as http:
            entity = await HomeAssistantClient(url, token, http).state(entity_id)
        access_token = str((entity.get("attributes") or {}).get("access_token") or "").strip()
        if not access_token:
            return None
        return StreamInfo(url=f"{url}/api/camera_proxy_stream/{quote(entity_id, safe='.')}?token={quote(access_token, safe='')}", type="mjpeg")

    async def snapshot(self, device: DeviceRef, ctx: AdapterContext) -> Optional[bytes]:
        if device.category not in ("camera", "doorbell", "nvr"):
            return None
        url, token = self.connection_from_device(device)
        async with ctx.http() as http:
            return await HomeAssistantClient(url, token, http).camera_snapshot(self.entity_id_for(device))

    async def subscribe(self, devices: List[DeviceRef], ctx: AdapterContext) -> Optional[Unsubscribe]:
        groups: Dict[Tuple[str, str], List[str]] = {}
        for device in devices:
            try:
                url, token = self.connection_from_device(device)
            except AdapterError as exc:
                logger.warning("Skipping Home Assistant device %s: %s", device.external_id, exc.message)
                continue
            groups.setdefault((url, token), []).append(self.entity_id_for(device))
        if not groups:
            return None
        subscriptions = [_InstanceSubscription(self, url, token, ids, ctx) for (url, token), ids in groups.items()]
        for subscription in subscriptions:
            subscription.start()

        async def _unsubscribe() -> None:
            for subscription in subscriptions:
                await subscription.stop()

        return _unsubscribe


registry.register(HomeAssistantAdapter())
