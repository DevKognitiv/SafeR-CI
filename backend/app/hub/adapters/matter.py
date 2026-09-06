"""Matter adapter: commissions and controls Matter devices through python-matter-server.

python-matter-server (Home Assistant's open-source Matter controller) exposes a JSON WebSocket API on
``settings.MATTER_SERVER_URL`` (default ``ws://localhost:5580/ws``)::

    client -> server  {"message_id": "<id>", "command": "<name>", "args": {...}}
    server -> client  {"message_id": "<id>", "result": ...}
                      {"message_id": "<id>", "error_code": <int>, "details": "<text>"}
                      {"event": "attribute_updated", "data": [node_id, "ep/cluster/attr", value]}
                      {"event": "node_added"|"node_updated", "data": {node}} / {"event": "node_removed", "data": node_id}
    on connect        {"fabric_id", "compressed_fabric_id", "schema_version", "sdk_version",
                       "wifi_credentials_set", "thread_credentials_set", "bluetooth_enabled", ...}

A node (``get_node``) is ``{"node_id": int, "available": bool, "attributes": {"<endpoint>/<cluster>/<attribute>":
value}}``. The Descriptor cluster (29) of every endpoint lists its Matter *device types*; those are mapped to
the hub categories and the attributes of the well-known clusters are normalised to the canonical capability
codes of ``app.hub.capabilities``. Bridges (Aggregator device type) become a ``gateway`` device whose bridged
endpoints are child devices.

External ids: ``"<node_id>"`` for single-endpoint nodes and bridges, ``"<node_id>:<endpoint_id>"`` for the
endpoints of multi-endpoint nodes (bridged devices, multi-gang switches).
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from app.hub.adapters.base import (
    AdapterContext, AdapterError, BrandAdapter, BrandInfo, DeviceDraft, DeviceRef, DeviceState, FormField,
    IntegrationDraft, PairResult, PairingMethod, Unsubscribe, require,
)
from app.hub.adapters.matter_payload import is_valid_passcode, parse_onboarding_code, vendor_name
from app.hub.adapters.registry import registry
from app.hub.capabilities import cap, cover_caps, lock_caps, sensor_caps, thermostat_caps

logger = logging.getLogger("safer.hub.matter")

BRAND_ID = "matter"
PROTOCOL = "matter"
DEFAULT_SERVER_URL = "ws://localhost:5580/ws"
METHOD_QR = "qr_code"
METHOD_MANUAL = "manual_code"
METHOD_ON_NETWORK = "on_network"

COMMAND_TIMEOUT = 30.0
COMMISSION_TIMEOUT = 240.0
CONNECT_TIMEOUT = 10.0

# ----------------------------------------------------------------------------- Matter constants
# Clusters
CL_ON_OFF = 6
CL_LEVEL = 8
CL_DESCRIPTOR = 29
CL_BASIC_INFORMATION = 40
CL_POWER_SOURCE = 47
CL_BRIDGED_BASIC_INFORMATION = 57
CL_SWITCH = 59
CL_BOOLEAN_STATE = 69
CL_SMOKE_CO_ALARM = 92
CL_ELECTRICAL_POWER = 144
CL_ELECTRICAL_ENERGY = 145
CL_DOOR_LOCK = 257
CL_WINDOW_COVERING = 258
CL_THERMOSTAT = 513
CL_COLOR = 768
CL_ILLUMINANCE = 1024
CL_TEMPERATURE = 1026
CL_HUMIDITY = 1029
CL_OCCUPANCY = 1030

# Attributes (cluster, attribute)
ATTR_DEVICE_TYPE_LIST = 0  # Descriptor
ATTR_SERVER_LIST = 1  # Descriptor
ATTR_ON_OFF = 0
ATTR_CURRENT_LEVEL = 0
ATTR_CURRENT_HUE = 0
ATTR_CURRENT_SATURATION = 1
ATTR_COLOR_TEMPERATURE_MIREDS = 7
ATTR_COLOR_MODE = 8
ATTR_COLOR_CAPABILITIES = 16394
ATTR_LOCK_STATE = 0
ATTR_DOOR_STATE = 3
ATTR_STATE_VALUE = 0
ATTR_OCCUPANCY = 0
ATTR_MEASURED_VALUE = 0
ATTR_SMOKE_STATE = 1
ATTR_CO_STATE = 2
ATTR_LOCAL_TEMPERATURE = 0
ATTR_OCCUPIED_COOLING_SETPOINT = 17
ATTR_OCCUPIED_HEATING_SETPOINT = 18
ATTR_SYSTEM_MODE = 28
ATTR_COVER_OPERATIONAL_STATUS = 10
ATTR_COVER_LIFT_PERCENTAGE = 8
ATTR_COVER_LIFT_PERCENT_100THS = 14
ATTR_BAT_PERCENT_REMAINING = 12
ATTR_ACTIVE_POWER = 8
ATTR_CUMULATIVE_ENERGY_IMPORTED = 1
ATTR_BRIDGED_REACHABLE = 17
# BasicInformation / BridgedDeviceBasicInformation share these ids
ATTR_VENDOR_NAME = 1
ATTR_VENDOR_ID = 2
ATTR_PRODUCT_NAME = 3
ATTR_PRODUCT_ID = 4
ATTR_NODE_LABEL = 5
ATTR_SOFTWARE_VERSION_STRING = 10
ATTR_SERIAL_NUMBER = 15

COLOR_CAP_HUE_SATURATION = 1 << 0
COLOR_CAP_XY = 1 << 3
COLOR_CAP_COLOR_TEMPERATURE = 1 << 4

LOCK_STATE_LOCKED = 1
DOOR_STATES_OPEN = {0, 3, 5}  # open, forced open, ajar

SYSTEM_MODE_TO_HUB = {0: "off", 1: "auto", 3: "cool", 4: "heat", 5: "heat", 7: "off", 8: "cool", 9: "auto"}
HUB_TO_SYSTEM_MODE = {"off": 0, "auto": 1, "cool": 3, "heat": 4}

# Device types (Matter Device Library)
DT_DOOR_LOCK = 10
DT_DOOR_LOCK_CONTROLLER = 11
DT_AGGREGATOR = 14
DT_GENERIC_SWITCH = 15
DT_POWER_SOURCE = 17
DT_OTA_REQUESTOR = 18
DT_BRIDGED_NODE = 19
DT_OTA_PROVIDER = 20
DT_CONTACT_SENSOR = 21
DT_ROOT_NODE = 22
DT_SECONDARY_NETWORK_INTERFACE = 25
DT_AIR_QUALITY_SENSOR = 44
DT_WATER_LEAK_DETECTOR = 67
DT_SMOKE_CO_ALARM = 118
DT_ON_OFF_LIGHT = 256
DT_DIMMABLE_LIGHT = 257
DT_ON_OFF_LIGHT_SWITCH = 259
DT_DIMMER_SWITCH = 260
DT_COLOR_DIMMER_SWITCH = 261
DT_LIGHT_SENSOR = 262
DT_OCCUPANCY_SENSOR = 263
DT_ON_OFF_PLUG = 266
DT_DIMMABLE_PLUG = 267
DT_COLOR_TEMPERATURE_LIGHT = 268
DT_EXTENDED_COLOR_LIGHT = 269
DT_WINDOW_COVERING = 514
DT_THERMOSTAT = 769
DT_TEMPERATURE_SENSOR = 770
DT_HUMIDITY_SENSOR = 775
DT_DEVICE_ENERGY_MANAGEMENT = 1293
DT_ELECTRICAL_SENSOR = 1296

UTILITY_DEVICE_TYPES: Set[int] = {
    DT_ROOT_NODE, DT_POWER_SOURCE, DT_OTA_REQUESTOR, DT_OTA_PROVIDER, DT_BRIDGED_NODE,
    DT_SECONDARY_NETWORK_INTERFACE, DT_DEVICE_ENERGY_MANAGEMENT, DT_ELECTRICAL_SENSOR,
}

DEVICE_TYPE_CATEGORY: Dict[int, str] = {
    DT_ON_OFF_LIGHT: "light", DT_DIMMABLE_LIGHT: "light", DT_COLOR_TEMPERATURE_LIGHT: "light", DT_EXTENDED_COLOR_LIGHT: "light",
    DT_ON_OFF_PLUG: "plug", DT_DIMMABLE_PLUG: "plug",
    DT_ON_OFF_LIGHT_SWITCH: "remote", DT_DIMMER_SWITCH: "remote", DT_COLOR_DIMMER_SWITCH: "remote",
    DT_GENERIC_SWITCH: "remote", DT_DOOR_LOCK_CONTROLLER: "remote",
    DT_DOOR_LOCK: "lock",
    DT_CONTACT_SENSOR: "sensor_contact",
    DT_OCCUPANCY_SENSOR: "sensor_motion",
    DT_TEMPERATURE_SENSOR: "sensor_temperature",
    DT_HUMIDITY_SENSOR: "sensor_humidity",
    DT_LIGHT_SENSOR: "sensor_multi", DT_AIR_QUALITY_SENSOR: "sensor_multi",
    DT_THERMOSTAT: "thermostat",
    DT_SMOKE_CO_ALARM: "sensor_smoke",
    DT_WATER_LEAK_DETECTOR: "sensor_water",
    DT_WINDOW_COVERING: "cover",
    DT_AGGREGATOR: "gateway",
}

DEVICE_TYPE_NAMES: Dict[int, str] = {
    DT_DOOR_LOCK: "Door Lock", DT_DOOR_LOCK_CONTROLLER: "Door Lock Controller", DT_AGGREGATOR: "Aggregator",
    DT_GENERIC_SWITCH: "Generic Switch", DT_POWER_SOURCE: "Power Source", DT_OTA_REQUESTOR: "OTA Requestor",
    DT_BRIDGED_NODE: "Bridged Node", DT_OTA_PROVIDER: "OTA Provider", DT_CONTACT_SENSOR: "Contact Sensor",
    DT_ROOT_NODE: "Root Node", DT_AIR_QUALITY_SENSOR: "Air Quality Sensor", DT_WATER_LEAK_DETECTOR: "Water Leak Detector",
    DT_SMOKE_CO_ALARM: "Smoke CO Alarm", DT_ON_OFF_LIGHT: "On/Off Light", DT_DIMMABLE_LIGHT: "Dimmable Light",
    DT_ON_OFF_LIGHT_SWITCH: "On/Off Light Switch", DT_DIMMER_SWITCH: "Dimmer Switch",
    DT_COLOR_DIMMER_SWITCH: "Color Dimmer Switch", DT_LIGHT_SENSOR: "Light Sensor", DT_OCCUPANCY_SENSOR: "Occupancy Sensor",
    DT_ON_OFF_PLUG: "On/Off Plug-in Unit", DT_DIMMABLE_PLUG: "Dimmable Plug-in Unit",
    DT_COLOR_TEMPERATURE_LIGHT: "Color Temperature Light", DT_EXTENDED_COLOR_LIGHT: "Extended Color Light",
    DT_WINDOW_COVERING: "Window Covering", DT_THERMOSTAT: "Thermostat", DT_TEMPERATURE_SENSOR: "Temperature Sensor",
    DT_HUMIDITY_SENSOR: "Humidity Sensor", DT_SECONDARY_NETWORK_INTERFACE: "Secondary Network Interface",
    DT_ELECTRICAL_SENSOR: "Electrical Sensor", DT_DEVICE_ENERGY_MANAGEMENT: "Device Energy Management",
}

# When an endpoint advertises several device types, the most specific category wins.
CATEGORY_PRIORITY: List[str] = [
    "gateway", "lock", "thermostat", "cover", "light", "plug", "sensor_smoke", "sensor_water", "sensor_contact",
    "sensor_motion", "sensor_temperature", "sensor_humidity", "sensor_multi", "remote", "generic",
]

# python-matter-server error codes (matter_server/common/errors.py) -> hub error codes
SERVER_ERROR_CODES: Dict[int, str] = {
    3: "invalid_input",  # InvalidArguments
    4: "unsupported",  # InvalidCommand
    5: "invalid_input",  # NodeCommissionFailed
    6: "unreachable",  # NodeInterviewFailed
    7: "unreachable",  # NodeNotReady
    8: "not_found",  # NodeNotExists
    9: "unreachable",  # NodeNotResolving
    10: "unsupported",  # VersionMismatch
    11: "unreachable",  # SDKStackError / SDKCommandFailed
    12: "unsupported",  # InvalidServerVersion
}
UNREACHABLE_HINTS = ("unavailable", "not available", "timeout", "timed out", "unreachable", "offline", "not reachable")

Connector = Callable[[str], Awaitable[Any]]
EventHandler = Callable[[str, Any], Awaitable[None]]


# ----------------------------------------------------------------------------- errors
def unreachable_error(url: str, reason: str = "") -> AdapterError:
    """Standard "server down" error with the hint to start python-matter-server."""
    detail = f" ({reason})" if reason else ""
    return AdapterError(
        f"Serveur Matter injoignable sur {url}{detail}. Lancez le conteneur python-matter-server "
        "(docker run -d --network host ghcr.io/home-assistant-libs/python-matter-server:stable) "
        "et vérifiez MATTER_SERVER_URL.",
        "unreachable",
    )


def map_server_error(error_code: Any, details: Any) -> AdapterError:
    """Translate a ``{"error_code", "details"}`` answer into an AdapterError."""
    try:
        code_int = int(error_code)
    except (TypeError, ValueError):
        code_int = 0
    text = str(details or f"Matter server error {code_int}")
    hub_code = SERVER_ERROR_CODES.get(code_int)
    if hub_code is None:
        lowered = text.lower()
        hub_code = "unreachable" if any(hint in lowered for hint in UNREACHABLE_HINTS) else "invalid_input"
    error = AdapterError(f"Matter server: {text}", hub_code)
    error.error_code = code_int  # type: ignore[attr-defined]
    return error


# ----------------------------------------------------------------------------- websocket client
async def websockets_connector(url: str, open_timeout: float = CONNECT_TIMEOUT) -> Any:
    """Default connector: open a WebSocket with the ``websockets`` package (comes with uvicorn[standard])."""
    try:
        import websockets  # pylint: disable=import-outside-toplevel
        from websockets.exceptions import WebSocketException  # pylint: disable=import-outside-toplevel
    except ImportError as exc:  # pragma: no cover - dependency of uvicorn[standard]
        raise AdapterError("The 'websockets' package is required for Matter support", "unsupported") from exc
    try:
        return await websockets.connect(url, open_timeout=open_timeout, max_size=None)
    except (OSError, asyncio.TimeoutError, TimeoutError, ValueError, WebSocketException) as exc:
        raise unreachable_error(url, str(exc) or exc.__class__.__name__) from exc


class MatterClient:
    """Minimal python-matter-server WebSocket client (request/response + event stream).

    ``connector`` is a coroutine function ``connector(url) -> connection`` where the connection exposes
    ``send(text)``, ``recv() -> text`` and ``close()``; tests inject a fake server through it.
    """

    def __init__(
        self,
        url: str,
        connector: Optional[Connector] = None,
        timeout: float = COMMAND_TIMEOUT,
        on_event: Optional[EventHandler] = None,
    ):
        self.url = url
        self.timeout = timeout
        self.on_event = on_event
        self.server_info: Dict[str, Any] = {}
        self._connector: Connector = connector or websockets_connector
        self._conn: Any = None
        self._pending: Dict[str, "asyncio.Future[Any]"] = {}
        self._reader: Optional["asyncio.Task[None]"] = None
        self._closed = asyncio.Event()
        self._banner = asyncio.Event()
        self._close_reason: str = ""

    @property
    def connected(self) -> bool:
        """True while the socket is open."""
        return self._conn is not None and not self._closed.is_set()

    async def connect(self) -> Dict[str, Any]:
        """Open the connection and wait for the server banner (``server_info`` message)."""
        try:
            self._conn = await self._connector(self.url)
        except AdapterError:
            raise
        except Exception as exc:  # pylint: disable=broad-except
            raise unreachable_error(self.url, str(exc) or exc.__class__.__name__) from exc
        self._reader = asyncio.create_task(self._read_loop())
        try:
            await asyncio.wait_for(self._banner.wait(), timeout=min(self.timeout, 5.0))
        except asyncio.TimeoutError:
            logger.debug("No server banner received from %s within 5s; continuing", self.url)
        if self._closed.is_set() and not self.server_info:
            raise unreachable_error(self.url, self._close_reason or "connection closed during handshake")
        return self.server_info

    async def _read_loop(self) -> None:
        try:
            while True:
                raw = await self._conn.recv()
                if isinstance(raw, (bytes, bytearray)):
                    raw = raw.decode("utf-8", "replace")
                try:
                    message = json.loads(raw)
                except (TypeError, ValueError):
                    logger.debug("Ignoring non-JSON frame from %s", self.url)
                    continue
                if isinstance(message, dict):
                    await self._dispatch(message)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pylint: disable=broad-except
            self._close_reason = str(exc) or exc.__class__.__name__
            logger.debug("Matter server connection %s closed: %s", self.url, self._close_reason)
        finally:
            self._fail_pending(unreachable_error(self.url, self._close_reason or "connection closed"))
            self._closed.set()
            self._banner.set()

    async def _dispatch(self, message: Dict[str, Any]) -> None:
        message_id = message.get("message_id")
        if message_id is not None and ("result" in message or "error_code" in message):
            future = self._pending.pop(message_id, None)
            if future is None or future.done():
                return
            if "error_code" in message:
                future.set_exception(map_server_error(message.get("error_code"), message.get("details")))
            else:
                future.set_result(message.get("result"))
            return
        if "event" in message:
            if self.on_event is not None:
                try:
                    await self.on_event(str(message["event"]), message.get("data"))
                except Exception:  # pylint: disable=broad-except
                    logger.exception("Matter event handler failed for %s", message.get("event"))
            return
        if "schema_version" in message or "fabric_id" in message:
            self.server_info = message
            self._banner.set()
            return
        logger.debug("Unhandled Matter server message: %s", list(message.keys()))

    def _fail_pending(self, error: AdapterError) -> None:
        for future in list(self._pending.values()):
            if not future.done():
                future.set_exception(error)
        self._pending.clear()

    async def send_command(self, command: str, timeout: Optional[float] = None, **args: Any) -> Any:
        """Send one command and return its ``result`` (raises AdapterError on ``error_code``)."""
        if self._conn is None or self._closed.is_set():
            raise unreachable_error(self.url, self._close_reason or "not connected")
        message_id = uuid.uuid4().hex
        future: "asyncio.Future[Any]" = asyncio.get_running_loop().create_future()
        self._pending[message_id] = future
        payload = {"message_id": message_id, "command": command, "args": args}
        try:
            await self._conn.send(json.dumps(payload))
            return await asyncio.wait_for(future, timeout or self.timeout)
        except asyncio.TimeoutError as exc:
            raise AdapterError(f"Le serveur Matter n'a pas répondu à '{command}' à temps", "unreachable") from exc
        except AdapterError:
            raise
        except Exception as exc:  # pylint: disable=broad-except
            raise unreachable_error(self.url, str(exc) or exc.__class__.__name__) from exc
        finally:
            self._pending.pop(message_id, None)

    async def wait_closed(self) -> None:
        """Block until the connection is closed (by either side)."""
        await self._closed.wait()

    async def close(self) -> None:
        """Close the socket and stop the reader task."""
        reader, self._reader = self._reader, None
        if reader is not None and not reader.done():
            reader.cancel()
            try:
                await reader
            except (asyncio.CancelledError, Exception):  # pylint: disable=broad-except
                pass
        conn, self._conn = self._conn, None
        if conn is not None:
            try:
                await conn.close()
            except Exception:  # pylint: disable=broad-except
                pass
        self._fail_pending(unreachable_error(self.url, "connection closed"))
        self._closed.set()
        self._banner.set()

    async def __aenter__(self) -> "MatterClient":
        await self.connect()
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        await self.close()


# ----------------------------------------------------------------------------- node model
Attrs = Dict[int, Dict[int, Any]]  # {cluster: {attribute: value}}


@dataclass
class EndpointInfo:
    """One endpoint of a node with its classification."""

    endpoint_id: int
    device_types: List[int]
    category: str
    clusters: Set[int]
    attrs: Attrs
    bridged: bool = False

    @property
    def is_application(self) -> bool:
        """True for endpoints that expose a device (not root / utility only)."""
        if self.endpoint_id == 0:
            return False
        if DT_AGGREGATOR in self.device_types:
            return False
        return any(dt not in UTILITY_DEVICE_TYPES for dt in self.device_types) or not self.device_types

    def get(self, cluster: int, attribute: int, default: Any = None) -> Any:
        """Attribute value lookup."""
        value = self.attrs.get(cluster, {}).get(attribute)
        return default if value is None else value


@dataclass
class ParsedNode:
    """A node split into endpoints."""

    node_id: int
    available: bool
    endpoints: Dict[int, EndpointInfo] = field(default_factory=dict)

    @property
    def root(self) -> Optional[EndpointInfo]:
        return self.endpoints.get(0)

    @property
    def aggregator(self) -> Optional[EndpointInfo]:
        for endpoint in self.endpoints.values():
            if DT_AGGREGATOR in endpoint.device_types:
                return endpoint
        return None

    @property
    def is_bridge(self) -> bool:
        return self.aggregator is not None

    @property
    def application_endpoints(self) -> List[EndpointInfo]:
        return [self.endpoints[k] for k in sorted(self.endpoints) if self.endpoints[k].is_application]


def _int_or_none(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_attribute_path(path: str) -> Optional[Tuple[int, int, int]]:
    """``"1/6/0"`` -> ``(1, 6, 0)`` (endpoint, cluster, attribute)."""
    parts = str(path).split("/")
    if len(parts) != 3:
        return None
    numbers = [_int_or_none(part) for part in parts]
    if any(number is None for number in numbers):
        return None
    return numbers[0], numbers[1], numbers[2]  # type: ignore[return-value]


def group_attributes(attributes: Dict[str, Any]) -> Dict[int, Attrs]:
    """Flat ``{"ep/cluster/attr": value}`` -> ``{endpoint: {cluster: {attribute: value}}}``."""
    grouped: Dict[int, Attrs] = {}
    for path, value in (attributes or {}).items():
        parsed = parse_attribute_path(path)
        if parsed is None:
            continue
        endpoint_id, cluster_id, attribute_id = parsed
        grouped.setdefault(endpoint_id, {}).setdefault(cluster_id, {})[attribute_id] = value
    return grouped


def device_types_from(attrs: Attrs) -> List[int]:
    """Device type ids from the Descriptor cluster (list of structs, dicts or ints)."""
    raw = attrs.get(CL_DESCRIPTOR, {}).get(ATTR_DEVICE_TYPE_LIST) or []
    types: List[int] = []
    for item in raw if isinstance(raw, list) else []:
        value: Any = item
        if isinstance(item, dict):
            value = item.get("deviceType", item.get("device_type", item.get("type", item.get("0"))))
        number = _int_or_none(value)
        if number is not None and number not in types:
            types.append(number)
    return types


def category_for(device_types: List[int]) -> str:
    """Best hub category for a set of device types."""
    candidates = {DEVICE_TYPE_CATEGORY[dt] for dt in device_types if dt in DEVICE_TYPE_CATEGORY}
    for category in CATEGORY_PRIORITY:
        if category in candidates:
            return category
    return "generic"


def parse_node(node: Dict[str, Any]) -> ParsedNode:
    """Split a ``get_node`` result into classified endpoints."""
    node_id = _int_or_none(node.get("node_id"))
    if node_id is None:
        raise AdapterError("Matter node without node_id", "invalid_input")
    grouped = group_attributes(node.get("attributes") or {})
    parsed = ParsedNode(node_id=node_id, available=bool(node.get("available", True)))
    for endpoint_id, attrs in grouped.items():
        device_types = device_types_from(attrs)
        clusters: Set[int] = set(attrs.keys())
        server_list = attrs.get(CL_DESCRIPTOR, {}).get(ATTR_SERVER_LIST)
        if isinstance(server_list, list):
            clusters.update(n for n in (_int_or_none(v) for v in server_list) if n is not None)
        parsed.endpoints[endpoint_id] = EndpointInfo(
            endpoint_id=endpoint_id,
            device_types=device_types,
            category=category_for(device_types),
            clusters=clusters,
            attrs=attrs,
            bridged=DT_BRIDGED_NODE in device_types or CL_BRIDGED_BASIC_INFORMATION in attrs,
        )
    return parsed


# ----------------------------------------------------------------------------- attribute -> state
def level_to_percent(level: Any) -> Optional[int]:
    """LevelControl 0..254 -> 0..100."""
    number = _int_or_none(level)
    if number is None:
        return None
    return max(0, min(100, int(round(number * 100 / 254))))


def percent_to_level(percent: Any) -> int:
    """0..100 -> LevelControl 0..254."""
    return max(0, min(254, int(round(float(percent) * 254 / 100))))


def mireds_to_kelvin(mireds: Any) -> Optional[int]:
    """Color temperature mireds -> Kelvin."""
    number = _int_or_none(mireds)
    if not number:
        return None
    return int(round(1_000_000 / number))


def kelvin_to_mireds(kelvin: Any) -> int:
    """Kelvin -> mireds."""
    value = float(kelvin)
    return max(1, int(round(1_000_000 / value))) if value > 0 else 0


def illuminance_to_lux(value: Any) -> Optional[float]:
    """IlluminanceMeasurement MeasuredValue -> lux (``10 ** ((v - 1) / 10000)``)."""
    number = _int_or_none(value)
    if number is None:
        return None
    if number <= 0:
        return 0.0
    return round(10 ** ((number - 1) / 10000), 2)


def hundredths(value: Any) -> Optional[float]:
    """Matter int16 hundredths (temperature, humidity) -> float."""
    if value is None:
        return None
    try:
        return round(float(value) / 100, 2)
    except (TypeError, ValueError):
        return None


def _identity_attrs(endpoint: EndpointInfo, node: ParsedNode) -> Attrs:
    """BasicInformation (root) or BridgedDeviceBasicInformation (bridged endpoint) source."""
    if endpoint.bridged and CL_BRIDGED_BASIC_INFORMATION in endpoint.attrs:
        return {CL_BASIC_INFORMATION: endpoint.attrs[CL_BRIDGED_BASIC_INFORMATION]}
    root = node.root
    return root.attrs if root is not None else {}


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def endpoint_identity(endpoint: EndpointInfo, node: ParsedNode) -> Dict[str, Optional[str]]:
    """Name/model/manufacturer/firmware/serial for an endpoint."""
    basic = _identity_attrs(endpoint, node).get(CL_BASIC_INFORMATION, {})
    vendor = _text(basic.get(ATTR_VENDOR_NAME)) or vendor_name(_int_or_none(basic.get(ATTR_VENDOR_ID)))
    product = _text(basic.get(ATTR_PRODUCT_NAME))
    label = _text(basic.get(ATTR_NODE_LABEL))
    fallback = " ".join(part for part in ("Matter", vendor, product) if part)
    if not product and not vendor:
        primary = next((dt for dt in endpoint.device_types if dt in DEVICE_TYPE_NAMES and dt not in UTILITY_DEVICE_TYPES), None)
        fallback = f"Matter {DEVICE_TYPE_NAMES.get(primary, 'device')}" if primary is not None else f"Matter node {node.node_id}"
    return {
        "name": label or product or fallback,
        "model": product,
        "manufacturer": vendor,
        "firmware": _text(basic.get(ATTR_SOFTWARE_VERSION_STRING)),
        "serial": _text(basic.get(ATTR_SERIAL_NUMBER)),
    }


def endpoint_battery(endpoint: EndpointInfo, node: ParsedNode) -> Optional[int]:
    """Battery percentage from PowerSource.BatPercentRemaining (half-percent units)."""
    sources: List[Attrs] = [endpoint.attrs]
    if not endpoint.bridged:
        if node.root is not None:
            sources.append(node.root.attrs)
        sources.extend(ep.attrs for ep in node.endpoints.values() if DT_POWER_SOURCE in ep.device_types)
    for attrs in sources:
        value = attrs.get(CL_POWER_SOURCE, {}).get(ATTR_BAT_PERCENT_REMAINING)
        if value is not None:
            number = _int_or_none(value)
            if number is not None:
                return max(0, min(100, int(round(number / 2))))
    return None


def _light_features(endpoint: EndpointInfo) -> Tuple[bool, bool, bool]:
    """(dimmable, color_temp, color) from clusters + ColorCapabilities + device types."""
    dimmable = CL_LEVEL in endpoint.clusters
    color_temp = color = False
    if CL_COLOR in endpoint.clusters:
        capabilities = _int_or_none(endpoint.get(CL_COLOR, ATTR_COLOR_CAPABILITIES))
        if capabilities is not None:
            color_temp = bool(capabilities & COLOR_CAP_COLOR_TEMPERATURE)
            color = bool(capabilities & (COLOR_CAP_HUE_SATURATION | COLOR_CAP_XY))
        if DT_COLOR_TEMPERATURE_LIGHT in endpoint.device_types:
            color_temp = True
        if DT_EXTENDED_COLOR_LIGHT in endpoint.device_types:
            color = True
            color_temp = color_temp or capabilities is None
    return dimmable, color_temp, color


def endpoint_capabilities(endpoint: EndpointInfo, node: ParsedNode) -> List[Dict[str, Any]]:
    """Canonical capabilities for an endpoint."""
    category = endpoint.category
    caps: List[Dict[str, Any]] = []
    battery_known = endpoint_battery(endpoint, node) is not None
    if category == "light":
        dimmable, color_temp, color = _light_features(endpoint)
        caps.append(cap("switch", "bool", True))
        if dimmable:
            caps.append(cap("brightness", "int", True, min=0, max=100, step=1, unit="%"))
        if color_temp:
            caps.append(cap("color_temp", "int", True, min=2000, max=6500, step=50, unit="K"))
        if color:
            caps.append(cap("color", "color", True))
            caps.append(cap("work_mode", "enum", True, values=["white", "colour"]))
    elif category == "plug":
        caps.append(cap("switch", "bool", True))
        if CL_LEVEL in endpoint.clusters:
            caps.append(cap("brightness", "int", True, min=0, max=100, step=1, unit="%"))
        if CL_ELECTRICAL_POWER in endpoint.clusters:
            caps.append(cap("power", "float", False, unit="W"))
        if CL_ELECTRICAL_ENERGY in endpoint.clusters:
            caps.append(cap("energy", "float", False, unit="kWh"))
    elif category == "lock":
        caps.extend(lock_caps())
    elif category == "thermostat":
        caps.extend(thermostat_caps())
    elif category == "cover":
        caps.extend(cover_caps())
    elif category == "gateway":
        caps.append(cap("child_count", "int", False))
    elif category == "sensor_multi":
        if CL_OCCUPANCY in endpoint.clusters:
            caps.append(cap("motion", "bool"))
        if CL_TEMPERATURE in endpoint.clusters:
            caps.append(cap("temperature", "float", unit="°C"))
        if CL_HUMIDITY in endpoint.clusters:
            caps.append(cap("humidity", "float", unit="%"))
        if CL_ILLUMINANCE in endpoint.clusters:
            caps.append(cap("illuminance", "float", unit="lx"))
        caps.append(cap("battery", "int", unit="%"))
    elif category.startswith("sensor_"):
        caps.extend(sensor_caps(category))
        if category == "sensor_smoke" and ATTR_CO_STATE in endpoint.attrs.get(CL_SMOKE_CO_ALARM, {}):
            caps.insert(1, cap("co", "bool"))
        if category == "sensor_temperature" and CL_HUMIDITY in endpoint.clusters:
            caps.insert(1, cap("humidity", "float", unit="%"))
    elif category == "remote":
        if CL_ON_OFF in endpoint.attrs:
            caps.append(cap("switch", "bool", True))
        if battery_known:
            caps.append(cap("battery", "int", unit="%"))
    else:  # generic
        if CL_ON_OFF in endpoint.attrs:
            caps.append(cap("switch", "bool", True))
        if CL_LEVEL in endpoint.attrs:
            caps.append(cap("brightness", "int", True, min=0, max=100, step=1, unit="%"))
        if CL_TEMPERATURE in endpoint.clusters:
            caps.append(cap("temperature", "float", unit="°C"))
        if CL_HUMIDITY in endpoint.clusters:
            caps.append(cap("humidity", "float", unit="%"))
        if battery_known:
            caps.append(cap("battery", "int", unit="%"))
    if battery_known and category in ("light", "plug", "thermostat", "cover") and not any(c["code"] == "battery" for c in caps):
        caps.append(cap("battery", "int", unit="%"))
    return caps


def endpoint_state(endpoint: EndpointInfo, node: ParsedNode) -> Dict[str, Any]:
    """Canonical state for an endpoint (only keys whose attribute is known)."""
    category = endpoint.category
    state: Dict[str, Any] = {}
    get = endpoint.get

    def put(code: str, value: Any) -> None:
        if value is not None:
            state[code] = value

    if category in ("light", "plug", "generic", "remote"):
        on_off = get(CL_ON_OFF, ATTR_ON_OFF)
        if on_off is not None and CL_ON_OFF in endpoint.attrs:
            put("switch", bool(on_off))
        if CL_LEVEL in endpoint.attrs:
            put("brightness", level_to_percent(get(CL_LEVEL, ATTR_CURRENT_LEVEL)))
    if category == "light":
        _, color_temp, color = _light_features(endpoint)
        if color_temp:
            put("color_temp", mireds_to_kelvin(get(CL_COLOR, ATTR_COLOR_TEMPERATURE_MIREDS)))
        if color:
            hue = _int_or_none(get(CL_COLOR, ATTR_CURRENT_HUE))
            sat = _int_or_none(get(CL_COLOR, ATTR_CURRENT_SATURATION))
            if hue is not None and sat is not None:
                put("color", {
                    "h": int(round(hue * 360 / 254)) % 360,
                    "s": max(0, min(100, int(round(sat * 100 / 254)))),
                    "v": state.get("brightness", 100),
                })
            mode = _int_or_none(get(CL_COLOR, ATTR_COLOR_MODE))
            if mode is not None:
                put("work_mode", "white" if mode == 2 else "colour")
    elif category == "plug":
        power = get(CL_ELECTRICAL_POWER, ATTR_ACTIVE_POWER)
        if power is not None:
            put("power", round(float(power) / 1000, 2))  # mW -> W
        energy = get(CL_ELECTRICAL_ENERGY, ATTR_CUMULATIVE_ENERGY_IMPORTED)
        if isinstance(energy, dict) and energy.get("energy") is not None:
            put("energy", round(float(energy["energy"]) / 1_000_000, 3))  # mWh -> kWh
    elif category == "lock":
        lock_state = _int_or_none(get(CL_DOOR_LOCK, ATTR_LOCK_STATE))
        if lock_state is not None:
            put("locked", lock_state == LOCK_STATE_LOCKED)
        door = _int_or_none(get(CL_DOOR_LOCK, ATTR_DOOR_STATE))
        if door is not None:
            put("door", door in DOOR_STATES_OPEN)
    elif category == "sensor_contact":
        value = get(CL_BOOLEAN_STATE, ATTR_STATE_VALUE)
        if value is not None:
            put("contact", not bool(value))  # BooleanState true = closed
    elif category == "sensor_water":
        value = get(CL_BOOLEAN_STATE, ATTR_STATE_VALUE)
        if value is not None:
            put("water_leak", bool(value))
    elif category == "sensor_motion":
        bitmap = _int_or_none(get(CL_OCCUPANCY, ATTR_OCCUPANCY))
        if bitmap is not None:
            put("motion", bool(bitmap & 1))
    elif category == "sensor_temperature":
        put("temperature", hundredths(get(CL_TEMPERATURE, ATTR_MEASURED_VALUE)))
        put("humidity", hundredths(get(CL_HUMIDITY, ATTR_MEASURED_VALUE)))
    elif category == "sensor_humidity":
        put("humidity", hundredths(get(CL_HUMIDITY, ATTR_MEASURED_VALUE)))
    elif category == "sensor_multi":
        bitmap = _int_or_none(get(CL_OCCUPANCY, ATTR_OCCUPANCY))
        if bitmap is not None:
            put("motion", bool(bitmap & 1))
        put("temperature", hundredths(get(CL_TEMPERATURE, ATTR_MEASURED_VALUE)))
        put("humidity", hundredths(get(CL_HUMIDITY, ATTR_MEASURED_VALUE)))
        put("illuminance", illuminance_to_lux(get(CL_ILLUMINANCE, ATTR_MEASURED_VALUE)))
    elif category == "sensor_smoke":
        smoke = _int_or_none(get(CL_SMOKE_CO_ALARM, ATTR_SMOKE_STATE))
        if smoke is not None:
            put("smoke", smoke > 0)
        co = _int_or_none(get(CL_SMOKE_CO_ALARM, ATTR_CO_STATE))
        if co is not None:
            put("co", co > 0)
    elif category == "thermostat":
        put("temp_current", hundredths(get(CL_THERMOSTAT, ATTR_LOCAL_TEMPERATURE)))
        mode = SYSTEM_MODE_TO_HUB.get(_int_or_none(get(CL_THERMOSTAT, ATTR_SYSTEM_MODE)))
        put("mode", mode)
        heating = hundredths(get(CL_THERMOSTAT, ATTR_OCCUPIED_HEATING_SETPOINT))
        cooling = hundredths(get(CL_THERMOSTAT, ATTR_OCCUPIED_COOLING_SETPOINT))
        put("temp_set", cooling if mode == "cool" and cooling is not None else (heating if heating is not None else cooling))
        put("humidity_current", hundredths(get(CL_HUMIDITY, ATTR_MEASURED_VALUE)))
    elif category == "cover":
        lift = _int_or_none(get(CL_WINDOW_COVERING, ATTR_COVER_LIFT_PERCENT_100THS))
        if lift is not None:
            put("position", max(0, min(100, int(round(100 - lift / 100)))))
        else:
            lift_pct = _int_or_none(get(CL_WINDOW_COVERING, ATTR_COVER_LIFT_PERCENTAGE))
            if lift_pct is not None:
                put("position", max(0, min(100, 100 - lift_pct)))
        status = _int_or_none(get(CL_WINDOW_COVERING, ATTR_COVER_OPERATIONAL_STATUS))
        if status is not None:
            put("control", {0: "stop", 1: "open", 2: "close"}.get(status & 0x3, "stop"))
    elif category == "generic":
        put("temperature", hundredths(get(CL_TEMPERATURE, ATTR_MEASURED_VALUE)))
        put("humidity", hundredths(get(CL_HUMIDITY, ATTR_MEASURED_VALUE)))
    put("battery", endpoint_battery(endpoint, node))
    return state


def endpoint_online(endpoint: EndpointInfo, node: ParsedNode) -> bool:
    """Node availability, refined by BridgedDeviceBasicInformation.Reachable for bridged endpoints."""
    if not node.available:
        return False
    reachable = endpoint.attrs.get(CL_BRIDGED_BASIC_INFORMATION, {}).get(ATTR_BRIDGED_REACHABLE)
    if reachable is not None:
        return bool(reachable)
    return True


# ----------------------------------------------------------------------------- drafts
def external_id_for(node_id: int, endpoint_id: Optional[int] = None) -> str:
    """Hub external id for a node / endpoint."""
    return str(node_id) if endpoint_id is None else f"{node_id}:{endpoint_id}"


def split_external_id(external_id: str) -> Tuple[int, Optional[int]]:
    """``"12:3"`` -> ``(12, 3)``; ``"12"`` -> ``(12, None)``."""
    node_part, _, endpoint_part = str(external_id).partition(":")
    node_id = _int_or_none(node_part)
    if node_id is None:
        raise AdapterError(f"Invalid Matter external id '{external_id}'", "invalid_input")
    return node_id, _int_or_none(endpoint_part) if endpoint_part else None


def _draft(endpoint: EndpointInfo, node: ParsedNode, external_id: str, server_url: str, name: str,
           parent: Optional[str] = None, bridge: bool = False) -> DeviceDraft:
    identity = endpoint_identity(endpoint, node)
    config: Dict[str, Any] = {
        "node_id": node.node_id,
        "endpoint_id": endpoint.endpoint_id,
        "server_url": server_url,
        "device_types": [DEVICE_TYPE_NAMES.get(dt, str(dt)) for dt in endpoint.device_types],
        "device_type_ids": list(endpoint.device_types),
    }
    if identity["serial"]:
        config["serial"] = identity["serial"]
    if bridge:
        config["bridge"] = True
    return DeviceDraft(
        external_id=external_id,
        name=name,
        category=endpoint.category,
        protocol=PROTOCOL,
        model=identity["model"],
        manufacturer=identity["manufacturer"],
        firmware=identity["firmware"],
        capabilities=endpoint_capabilities(endpoint, node),
        state=endpoint_state(endpoint, node),
        config=config,
        parent_external_id=parent,
        online=endpoint_online(endpoint, node),
    )


def build_drafts(node: ParsedNode, server_url: str) -> List[DeviceDraft]:
    """Turn a node into hub device drafts (bridge -> gateway + children; multi-endpoint -> one per endpoint)."""
    app_endpoints = node.application_endpoints
    aggregator = node.aggregator
    if aggregator is not None:
        gateway_id = external_id_for(node.node_id)
        identity = endpoint_identity(aggregator, node)
        gateway = _draft(aggregator, node, gateway_id, server_url, identity["name"] or f"Passerelle Matter {node.node_id}", bridge=True)
        gateway.category = "gateway"
        gateway.capabilities = [cap("child_count", "int", False)]
        gateway.state = {"child_count": len(app_endpoints)}
        drafts = [gateway]
        for endpoint in app_endpoints:
            child_identity = endpoint_identity(endpoint, node)
            name = child_identity["name"] or f"{gateway.name} {endpoint.endpoint_id}"
            drafts.append(_draft(endpoint, node, external_id_for(node.node_id, endpoint.endpoint_id), server_url, name, parent=gateway_id))
        return drafts
    if not app_endpoints:
        root = node.root or EndpointInfo(endpoint_id=0, device_types=[DT_ROOT_NODE], category="generic", clusters=set(), attrs={})
        identity = endpoint_identity(root, node)
        draft = _draft(root, node, external_id_for(node.node_id), server_url, identity["name"] or f"Matter node {node.node_id}")
        draft.category = "generic"
        return [draft]
    if len(app_endpoints) == 1:
        endpoint = app_endpoints[0]
        identity = endpoint_identity(endpoint, node)
        return [_draft(endpoint, node, external_id_for(node.node_id), server_url, identity["name"] or f"Matter node {node.node_id}")]
    drafts = []
    for index, endpoint in enumerate(app_endpoints, start=1):
        identity = endpoint_identity(endpoint, node)
        base_name = identity["name"] or f"Matter node {node.node_id}"
        name = base_name if endpoint.bridged and CL_BRIDGED_BASIC_INFORMATION in endpoint.attrs else f"{base_name} {index}"
        drafts.append(_draft(endpoint, node, external_id_for(node.node_id, endpoint.endpoint_id), server_url, name))
    return drafts


def device_endpoint(node: ParsedNode, device: DeviceRef) -> Optional[EndpointInfo]:
    """Locate the endpoint a hub device maps to (``None`` for the gateway itself)."""
    _, ext_endpoint = split_external_id(device.external_id)
    endpoint_id = _int_or_none(device.cfg("endpoint_id"))
    if endpoint_id is None:
        endpoint_id = ext_endpoint
    if device.category == "gateway" or (endpoint_id is None and node.is_bridge):
        return None
    if endpoint_id is None:
        app_endpoints = node.application_endpoints
        if not app_endpoints:
            return node.root
        return app_endpoints[0]
    endpoint = node.endpoints.get(endpoint_id)
    if endpoint is None:
        raise AdapterError(f"Endpoint {endpoint_id} not found on Matter node {node.node_id}", "not_found")
    return endpoint


def device_state(node: ParsedNode, device: DeviceRef) -> DeviceState:
    """Full hub state for a device from a parsed node."""
    endpoint = device_endpoint(node, device)
    if endpoint is None:
        return DeviceState(online=node.available, state={"child_count": len(node.application_endpoints)})
    return DeviceState(online=endpoint_online(endpoint, node), state=endpoint_state(endpoint, node))


# ----------------------------------------------------------------------------- commands
@dataclass
class Operation:
    """One server call produced by :func:`build_operations`."""

    command: str  # device_command | write_attribute
    args: Dict[str, Any]


def _device_command(node_id: int, endpoint_id: int, cluster_id: int, name: str, payload: Optional[Dict[str, Any]] = None,
                    timed_ms: Optional[int] = None) -> Operation:
    args: Dict[str, Any] = {
        "node_id": node_id, "endpoint_id": endpoint_id, "cluster_id": cluster_id, "command_name": name, "payload": payload or {},
    }
    if timed_ms is not None:
        args["timed_request_timeout_ms"] = timed_ms
    return Operation("device_command", args)


def _write_attribute(node_id: int, endpoint_id: int, cluster_id: int, attribute_id: int, value: Any) -> Operation:
    return Operation("write_attribute", {"node_id": node_id, "attribute_path": f"{endpoint_id}/{cluster_id}/{attribute_id}", "value": value})


def _level_payload(level: int) -> Dict[str, Any]:
    return {"level": level, "transitionTime": 0, "optionsMask": 0, "optionsOverride": 0}


def build_operations(device: DeviceRef, code: str, value: Any) -> Tuple[List[Operation], Dict[str, Any]]:
    """Translate a canonical command into Matter operations + the partial state to merge.

    Pure function (no I/O) so payloads can be unit tested.
    """
    node_id, ext_endpoint = split_external_id(device.external_id)
    node_id = _int_or_none(device.cfg("node_id", node_id)) or node_id
    endpoint_id = _int_or_none(device.cfg("endpoint_id"))
    if endpoint_id is None:
        endpoint_id = ext_endpoint if ext_endpoint is not None else 1
    has_cap = {c.get("code") for c in (device.capabilities or [])}
    category = device.category

    if code == "switch":
        return [_device_command(node_id, endpoint_id, CL_ON_OFF, "On" if value else "Off")], {"switch": bool(value)}
    if code == "brightness":
        percent = max(0, min(100, int(round(float(value)))))
        ops = [_device_command(node_id, endpoint_id, CL_LEVEL, "MoveToLevelWithOnOff", _level_payload(percent_to_level(percent)))]
        return ops, {"brightness": percent, "switch": percent > 0}
    if code == "color_temp":
        kelvin = int(round(float(value)))
        payload = {"colorTemperatureMireds": kelvin_to_mireds(kelvin), "transitionTime": 0, "optionsMask": 0, "optionsOverride": 0}
        return [_device_command(node_id, endpoint_id, CL_COLOR, "MoveToColorTemperature", payload)], {"color_temp": kelvin, "work_mode": "white"}
    if code == "color":
        if not isinstance(value, dict):
            raise AdapterError("color expects {h, s, v}", "invalid_input")
        hue = float(value.get("h", 0)) % 360
        sat = max(0.0, min(100.0, float(value.get("s", 100))))
        bright = value.get("v")
        payload = {
            "hue": max(0, min(254, int(round(hue * 254 / 360)))),
            "saturation": max(0, min(254, int(round(sat * 254 / 100)))),
            "transitionTime": 0, "optionsMask": 0, "optionsOverride": 0,
        }
        ops = [_device_command(node_id, endpoint_id, CL_COLOR, "MoveToHueAndSaturation", payload)]
        partial: Dict[str, Any] = {"color": {"h": hue, "s": sat, "v": float(bright) if bright is not None else device.state.get("brightness", 100)},
                                   "work_mode": "colour"}
        if bright is not None and ("brightness" in has_cap or category == "light"):
            percent = max(0, min(100, int(round(float(bright)))))
            ops.append(_device_command(node_id, endpoint_id, CL_LEVEL, "MoveToLevelWithOnOff", _level_payload(percent_to_level(percent))))
            partial["brightness"] = percent
        return ops, partial
    if code == "work_mode":
        if value == "white":
            kelvin = int(device.state.get("color_temp") or 4000)
            payload = {"colorTemperatureMireds": kelvin_to_mireds(kelvin), "transitionTime": 0, "optionsMask": 0, "optionsOverride": 0}
            return [_device_command(node_id, endpoint_id, CL_COLOR, "MoveToColorTemperature", payload)], {"work_mode": "white"}
        if value == "colour":
            color = device.state.get("color") or {"h": 0, "s": 100, "v": 100}
            ops, partial = build_operations(device, "color", {"h": color.get("h", 0), "s": color.get("s", 100)})
            partial.pop("color", None)
            return ops, partial
        raise AdapterError(f"work_mode '{value}' is not supported by Matter lights", "unsupported")
    if code == "locked":
        ops = [_device_command(node_id, endpoint_id, CL_DOOR_LOCK, "LockDoor" if value else "UnlockDoor", {}, timed_ms=1000)]
        return ops, {"locked": bool(value)}
    if code == "temp_set":
        celsius = float(value)
        mode = device.state.get("mode") or "heat"
        attribute = ATTR_OCCUPIED_COOLING_SETPOINT if mode == "cool" else ATTR_OCCUPIED_HEATING_SETPOINT
        return [_write_attribute(node_id, endpoint_id, CL_THERMOSTAT, attribute, int(round(celsius * 100)))], {"temp_set": celsius}
    if code == "mode":
        if value not in HUB_TO_SYSTEM_MODE:
            raise AdapterError(f"Unknown thermostat mode '{value}'", "invalid_input")
        return [_write_attribute(node_id, endpoint_id, CL_THERMOSTAT, ATTR_SYSTEM_MODE, HUB_TO_SYSTEM_MODE[value])], {"mode": value}
    if code == "position":
        percent = max(0, min(100, int(round(float(value)))))
        payload = {"liftPercent100thsValue": (100 - percent) * 100}
        return [_device_command(node_id, endpoint_id, CL_WINDOW_COVERING, "GoToLiftPercentage", payload)], {"position": percent}
    if code == "control":
        names = {"open": "UpOrOpen", "close": "DownOrClose", "stop": "StopMotion"}
        if value not in names:
            raise AdapterError(f"Unknown cover control '{value}'", "invalid_input")
        return [_device_command(node_id, endpoint_id, CL_WINDOW_COVERING, names[value])], {"control": value}
    raise AdapterError(f"Capability '{code}' is not writable on Matter devices", "unsupported")


# ----------------------------------------------------------------------------- push subscription
class _ServerSubscription:
    """One listening connection per Matter server, with cancellable reconnect back-off."""

    def __init__(self, adapter: "MatterAdapter", url: str, devices: List[DeviceRef], ctx: AdapterContext):
        self.adapter = adapter
        self.url = url
        self.ctx = ctx
        self.devices: Dict[int, List[DeviceRef]] = {}
        for device in devices:
            node_id, _ = split_external_id(device.external_id)
            node_id = _int_or_none(device.cfg("node_id", node_id)) or node_id
            self.devices.setdefault(node_id, []).append(device)
        self.nodes: Dict[int, Dict[str, Any]] = {}
        self.last: Dict[str, Tuple[bool, Dict[str, Any]]] = {}
        self._stop = asyncio.Event()
        self._task: Optional["asyncio.Task[None]"] = None
        self.connections = 0

    def start(self) -> None:
        """Spawn the background task."""
        self._task = asyncio.create_task(self._run(), name=f"matter-subscription:{self.url}")

    async def stop(self) -> None:
        """Stop the task (cancels any back-off sleep)."""
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
            client = MatterClient(self.url, connector=self.adapter.connector, timeout=self.adapter.command_timeout, on_event=self._on_event)
            try:
                await client.connect()
                self.connections += 1
                nodes = await client.send_command("start_listening")
                for node in nodes or []:
                    if isinstance(node, dict):
                        await self._ingest(node)
                backoff = self.adapter.reconnect_min
                logger.info("Matter push subscription active on %s (%d nodes)", self.url, len(self.devices))
                await client.wait_closed()
                if not self._stop.is_set():
                    logger.warning("Matter server connection %s lost; reconnecting", self.url)
            except AdapterError as exc:
                logger.warning("Matter subscription %s failed: %s", self.url, exc.message)
            except Exception:  # pylint: disable=broad-except
                logger.exception("Matter subscription %s crashed", self.url)
            finally:
                await client.close()
            if await self._sleep(backoff):
                break
            backoff = min(backoff * 2, self.adapter.reconnect_max)

    async def _sleep(self, seconds: float) -> bool:
        """Sleep unless stopped first; returns True when stopped."""
        if self._stop.is_set():
            return True
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=seconds)
            return True
        except asyncio.TimeoutError:
            return False

    async def _on_event(self, event: str, data: Any) -> None:
        if event == "attribute_updated":
            if not isinstance(data, (list, tuple)) or len(data) != 3:
                return
            node_id = _int_or_none(data[0])
            node = self.nodes.get(node_id) if node_id is not None else None
            if node is None or node_id not in self.devices:
                return
            node.setdefault("attributes", {})[str(data[1])] = data[2]
            await self._emit(node_id)
        elif event in ("node_added", "node_updated"):
            if isinstance(data, dict):
                await self._ingest(data)
        elif event == "node_removed":
            node_id = _int_or_none(data)
            if node_id is None:
                return
            self.nodes.pop(node_id, None)
            for device in self.devices.get(node_id, []):
                self.last[device.external_id] = (False, {})
                await self.ctx.emit("state", device.external_id, {"state": {}, "online": False})

    async def _ingest(self, node: Dict[str, Any]) -> None:
        node_id = _int_or_none(node.get("node_id"))
        if node_id is None or node_id not in self.devices:
            return
        current = self.nodes.get(node_id)
        if current is not None and "attributes" not in node:
            current["available"] = node.get("available", current.get("available", True))
        else:
            self.nodes[node_id] = node
        await self._emit(node_id)

    async def _emit(self, node_id: int) -> None:
        node = self.nodes.get(node_id)
        if node is None:
            return
        try:
            parsed = parse_node(node)
        except AdapterError:
            return
        for device in self.devices.get(node_id, []):
            try:
                result = device_state(parsed, device)
            except AdapterError as exc:
                logger.debug("Cannot map state for %s: %s", device.external_id, exc.message)
                continue
            previous = self.last.get(device.external_id)
            if previous is None:
                changed = dict(result.state)
            else:
                changed = {k: v for k, v in result.state.items() if k not in previous[1] or previous[1][k] != v}
            if previous is not None and not changed and previous[0] == result.online:
                continue
            self.last[device.external_id] = (result.online, dict(result.state))
            await self.ctx.emit("state", device.external_id, {"state": changed, "online": result.online})


# ----------------------------------------------------------------------------- adapter
class MatterAdapter(BrandAdapter):
    """Matter devices through python-matter-server."""

    brand_id = BRAND_ID

    def __init__(
        self,
        connector: Optional[Connector] = None,
        command_timeout: float = COMMAND_TIMEOUT,
        commission_timeout: float = COMMISSION_TIMEOUT,
        reconnect_min: float = 2.0,
        reconnect_max: float = 60.0,
        default_server_url: Optional[str] = None,
    ):
        self.connector = connector
        self.command_timeout = command_timeout
        self.commission_timeout = commission_timeout
        self.reconnect_min = reconnect_min
        self.reconnect_max = reconnect_max
        self._default_server_url = default_server_url

    # ------------------------------------------------------------------ catalogue
    def default_server_url(self, ctx: Optional[AdapterContext] = None) -> str:
        """Server URL from settings (context first, then global settings, then the built-in default)."""
        if self._default_server_url:
            return self._default_server_url
        settings = getattr(ctx, "settings", None) if ctx is not None else None
        url = getattr(settings, "MATTER_SERVER_URL", None)
        if not url:
            try:
                from app.hub.settings import get_settings  # pylint: disable=import-outside-toplevel
                url = get_settings().MATTER_SERVER_URL
            except Exception:  # pylint: disable=broad-except
                url = None
        return url or DEFAULT_SERVER_URL

    def info(self) -> BrandInfo:
        server_url = self.default_server_url()
        network_fields = [
            FormField(name="wifi_ssid", label="Réseau Wi-Fi (SSID)", type="text", required=False,
                      help="Requis pour un appareil Wi-Fi commissionné en Bluetooth."),
            FormField(name="wifi_password", label="Mot de passe Wi-Fi", type="password", required=False),
            FormField(name="server_url", label="URL du serveur Matter", type="text", required=False, default=server_url,
                      placeholder=DEFAULT_SERVER_URL, help="WebSocket de python-matter-server."),
        ]
        return BrandInfo(
            id=BRAND_ID,
            name="Matter",
            vendor="Connectivity Standards Alliance",
            description="Appareils certifiés Matter (Wi-Fi, Thread, Ethernet) via le contrôleur open-source python-matter-server.",
            protocols=[PROTOCOL],
            categories=sorted(set(DEVICE_TYPE_CATEGORY.values()) | {"generic"}),
            methods=[
                PairingMethod(
                    id=METHOD_QR,
                    title="Scanner le code QR Matter",
                    description="Scannez le code QR Matter imprimé sur l'appareil ou son emballage.",
                    fields=[FormField(name="code", label="Scanner le code QR Matter", type="qr", placeholder="MT:...")] + network_fields,
                    requires_integration=True,
                    icon="qr_code_scanner",
                ),
                PairingMethod(
                    id=METHOD_MANUAL,
                    title="Code d'appairage manuel",
                    description="Saisissez le code à 11 ou 21 chiffres imprimé sur l'appareil.",
                    fields=[FormField(name="code", label="Code d'appairage", type="text", placeholder="3497-011-2332",
                                      help="11 ou 21 chiffres (les tirets sont ignorés).")] + network_fields,
                    requires_integration=True,
                    icon="pin",
                ),
                PairingMethod(
                    id=METHOD_ON_NETWORK,
                    title="Appareil déjà sur le réseau",
                    description="Commissionne un appareil déjà connecté au réseau local avec son code PIN de configuration.",
                    fields=[
                        FormField(name="setup_pin", label="Code PIN de configuration (8 chiffres)", type="number", placeholder="20202021"),
                        FormField(name="ip", label="Adresse IP", type="text", required=False, placeholder="192.168.1.50"),
                        network_fields[2],
                    ],
                    supports_discovery=False,
                    requires_integration=True,
                    icon="lan",
                ),
            ],
            icon="hub",
            docs_url="https://github.com/home-assistant-libs/python-matter-server",
            color="#0EA5E9",
        )

    # ------------------------------------------------------------------ helpers
    def _server_url(self, source: Dict[str, Any], ctx: AdapterContext) -> str:
        url = str(source.get("server_url") or "").strip() or self.default_server_url(ctx)
        parsed = urlparse(url)
        if parsed.scheme not in ("ws", "wss") or not parsed.netloc:
            raise AdapterError(f"URL de serveur Matter invalide: {url} (attendu ws://hote:5580/ws)", "invalid_input")
        return url

    def _device_url(self, device: DeviceRef, ctx: AdapterContext) -> str:
        return self._server_url({"server_url": device.cfg("server_url")}, ctx)

    def client(self, url: str, on_event: Optional[EventHandler] = None) -> MatterClient:
        """Build a client for a server URL (uses the injected connector)."""
        return MatterClient(url, connector=self.connector, timeout=self.command_timeout, on_event=on_event)

    @staticmethod
    def _node_id(device: DeviceRef) -> int:
        node_id, _ = split_external_id(device.external_id)
        return _int_or_none(device.cfg("node_id", node_id)) or node_id

    async def _fetch_node(self, client: MatterClient, node_id: int) -> ParsedNode:
        node = await client.send_command("get_node", node_id=node_id)
        if not isinstance(node, dict):
            raise AdapterError(f"Matter node {node_id} not found", "not_found")
        return parse_node(node)

    # ------------------------------------------------------------------ pairing
    async def pair(self, method_id: str, payload: Dict[str, Any], ctx: AdapterContext) -> PairResult:
        method = self.method(method_id)
        server_url = self._server_url(payload, ctx)
        host = urlparse(server_url).netloc
        integration = IntegrationDraft(key=f"matter:{server_url}", name=f"Matter ({host})", config={"server_url": server_url})

        code: Optional[str] = None
        parsed_code: Optional[Dict[str, Any]] = None
        setup_pin: Optional[int] = None
        if method.id in (METHOD_QR, METHOD_MANUAL):
            require(payload, "code")
            parsed_code = parse_onboarding_code(str(payload["code"]))
            if parsed_code is None:
                raise AdapterError("Code Matter invalide: attendu un code QR 'MT:...' ou un code d'appairage à 11/21 chiffres", "invalid_input")
            code = parsed_code["code"]
        else:
            require(payload, "setup_pin")
            setup_pin = _int_or_none(str(payload["setup_pin"]).replace(" ", "").replace("-", ""))
            if setup_pin is None or not is_valid_passcode(setup_pin):
                raise AdapterError("Code PIN de configuration invalide (8 chiffres, ex: 20202021)", "invalid_input")

        wifi_ssid = str(payload.get("wifi_ssid") or "").strip()
        wifi_password = str(payload.get("wifi_password") or "")
        ip_addr = str(payload.get("ip") or "").strip() or None

        client = self.client(server_url)
        try:
            server_info = await client.connect()
            if wifi_ssid:
                await client.send_command("set_wifi_credentials", ssid=wifi_ssid, credentials=wifi_password)
            if code is not None:
                # Skip the BLE phase when the server has no Bluetooth or the QR says the device is on-network only.
                network_only = bool(payload.get("network_only")) or not server_info.get("bluetooth_enabled", True)
                if parsed_code is not None and parsed_code["kind"] == "matter_qr" and not parsed_code["discovery_capabilities"]["ble"]:
                    network_only = True
                logger.info("Commissioning Matter device with code (network_only=%s)", network_only)
                result = await client.send_command("commission_with_code", timeout=self.commission_timeout, code=code, network_only=network_only)
            else:
                args: Dict[str, Any] = {"setup_pin_code": setup_pin}
                if ip_addr:
                    args["ip_addr"] = ip_addr
                result = await client.send_command("commission_on_network", timeout=self.commission_timeout, **args)
            node = await self._node_from_result(client, result)
        finally:
            await client.close()

        drafts = build_drafts(node, server_url)
        if parsed_code is not None:
            for draft in drafts:
                if parsed_code.get("vendor_id") is not None:
                    draft.config.setdefault("vendor_id", parsed_code["vendor_id"])
                if parsed_code.get("product_id") is not None:
                    draft.config.setdefault("product_id", parsed_code["product_id"])
                draft.manufacturer = draft.manufacturer or parsed_code.get("vendor_name")
        return PairResult(devices=drafts, integration=integration, message="Appareil Matter ajouté")

    async def _node_from_result(self, client: MatterClient, result: Any) -> ParsedNode:
        if isinstance(result, dict) and result.get("attributes"):
            return parse_node(result)
        node_id = _int_or_none(result.get("node_id") if isinstance(result, dict) else result)
        if node_id is None:
            raise AdapterError("Le serveur Matter n'a pas renvoyé de nœud après le commissionnement", "unreachable")
        return await self._fetch_node(client, node_id)

    # ------------------------------------------------------------------ state / commands
    async def refresh(self, device: DeviceRef, ctx: AdapterContext) -> DeviceState:
        url = self._device_url(device, ctx)
        async with self.client(url) as client:
            node = await self._fetch_node(client, self._node_id(device))
        return device_state(node, device)

    async def send_command(self, device: DeviceRef, code: str, value: Any, ctx: AdapterContext) -> Dict[str, Any]:
        operations, partial = build_operations(device, code, value)
        url = self._device_url(device, ctx)
        async with self.client(url) as client:
            for operation in operations:
                await client.send_command(operation.command, **operation.args)
        return partial

    async def subscribe(self, devices: List[DeviceRef], ctx: AdapterContext) -> Optional[Unsubscribe]:
        groups: Dict[str, List[DeviceRef]] = {}
        for device in devices:
            try:
                url = self._device_url(device, ctx)
            except AdapterError as exc:
                logger.warning("Skipping Matter device %s: %s", device.external_id, exc.message)
                continue
            groups.setdefault(url, []).append(device)
        if not groups:
            return None
        subscriptions = [_ServerSubscription(self, url, refs, ctx) for url, refs in groups.items()]
        for subscription in subscriptions:
            subscription.start()

        async def _unsubscribe() -> None:
            for subscription in subscriptions:
                await subscription.stop()

        return _unsubscribe

    async def unpair(self, device: DeviceRef, ctx: AdapterContext) -> None:
        """Remove the node from the fabric when the hub device *is* the node (single endpoint or bridge)."""
        node_id, endpoint_id = split_external_id(device.external_id)
        if endpoint_id is not None or device.parent_external_id:
            logger.info("Not removing Matter node %s: device %s is one endpoint of it", node_id, device.external_id)
            return
        url = self._device_url(device, ctx)
        async with self.client(url) as client:
            await client.send_command("remove_node", node_id=self._node_id(device))


def parse_code(code: str) -> Optional[Dict[str, Any]]:
    """Helper for ``POST /onboarding/parse-code``: ``{kind, brand, method, data}`` or ``None``."""
    parsed = parse_onboarding_code(code)
    if parsed is None:
        return None
    return {
        "kind": parsed["kind"],
        "brand": BRAND_ID,
        "method": METHOD_QR if parsed["kind"] == "matter_qr" else METHOD_MANUAL,
        "data": parsed,
    }


registry.register(MatterAdapter())
