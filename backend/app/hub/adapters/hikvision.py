"""Hikvision adapter (ISAPI): IP cameras, NVR/DVR channels and AX PRO alarm panels.

Everything goes through ISAPI over HTTP(S) with Digest authentication (Basic fallback):

* ``/ISAPI/System/deviceInfo``                     -> identity (serial, model, firmware, deviceType)
* ``/ISAPI/SecurityCP/status/*?format=json``       -> AX PRO panels (sub-systems + zones)
* ``/ISAPI/System/Video/inputs/channels`` and
  ``/ISAPI/ContentMgmt/InputProxy/channels``       -> recorder channels (analog + IP)
* ``/ISAPI/Streaming/channels/<ch>01/picture``     -> JPEG snapshot
* ``/ISAPI/PTZCtrl/channels/<ch>/continuous``      -> PTZ
* ``/ISAPI/Event/notification/alertStream``        -> push events (multipart XML stream)

External ids: ``<serial>`` for the host device (camera, NVR or panel), ``<serial>:ch<id>`` for
recorder channels and ``<serial>:zone<id>`` for panel zones. Credentials are stored on the host
device only; the hub merges them into children through ``DeviceRef``.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Tuple, Union

import httpx

from app.hub.adapters.base import (
    AdapterContext, AdapterError, BrandAdapter, BrandInfo, DeviceDraft, DeviceRef, DeviceState, FormField,
    PairResult, PairingMethod, StreamInfo, Unsubscribe, require,
)
from app.hub.adapters.registry import registry
from app.hub.capabilities import alarm_panel_caps, alarm_zone_caps, camera_caps, cap

logger = logging.getLogger("safer.hub.hikvision")

BRAND_ID = "hikvision"
PROTOCOL = "isapi"
METHOD_IP = "ip_credentials"
MANUFACTURER = "Hikvision"

# ISAPI paths -------------------------------------------------------------------
PATH_DEVICE_INFO = "/ISAPI/System/deviceInfo"
PATH_SYSTEM_CAPS = "/ISAPI/System/capabilities"
PATH_VIDEO_INPUTS = "/ISAPI/System/Video/inputs/channels"
PATH_INPUT_PROXY = "/ISAPI/ContentMgmt/InputProxy/channels"
PATH_INPUT_PROXY_STATUS = "/ISAPI/ContentMgmt/InputProxy/channels/status"
PATH_ALERT_STREAM = "/ISAPI/Event/notification/alertStream"
PATH_SUBSYSTEMS = "/ISAPI/SecurityCP/status/subSystems"
PATH_ZONES = "/ISAPI/SecurityCP/status/zones"
PATH_CP_CONTROL = "/ISAPI/SecurityCP/control"

# AX PRO arming names -> hub security modes (and back)
ARM_FROM_ISAPI = {"away": "armed_away", "stay": "armed_home", "disarm": "disarmed"}
ARM_TO_ISAPI = {"armed_away": "away", "armed_home": "stay", "armed_night": "stay"}

# alertStream event types that mean "motion" for the hub
MOTION_EVENTS = frozenset({
    "VMD", "linedetection", "fielddetection", "regionEntrance", "regionExiting", "PIR", "loitering",
    "facedetection", "peopleDetection", "attendedBaggage", "unattendedBaggage", "parking",
})
# PTZ continuous speeds per hub direction (pan, tilt, zoom)
PTZ_VECTORS: Dict[str, Tuple[int, int, int]] = {
    "left": (-60, 0, 0), "right": (60, 0, 0), "up": (0, 60, 0), "down": (0, -60, 0),
    "zoom_in": (0, 0, 60), "zoom_out": (0, 0, -60), "stop": (0, 0, 0),
}
RECORDER_TYPES = ("NVR", "DVR")
MAX_PTZ_PROBES = 64
OFFLINE_AFTER_FAILURES = 3
RECONNECT_MIN_DELAY = 5.0
RECONNECT_MAX_DELAY = 60.0
AUTH_FAILURE_DELAY = 300.0

StreamOpener = Callable[["HostSession", AdapterContext], AsyncIterator[bytes]]


# =============================================================================== helpers
def _as_int(value: Any, default: int) -> int:
    """Lenient int coercion for form payloads ("80", 80, "", None)."""
    if value in (None, ""):
        return default
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _as_bool(value: Any, default: bool = False) -> bool:
    """Lenient bool coercion for form payloads/JSON."""
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def parse_xml(data: Union[str, bytes]) -> ET.Element:
    """Parse ISAPI XML and strip namespaces from every tag. Raises AdapterError(invalid_input)."""
    raw = data.encode("utf-8") if isinstance(data, str) else data
    try:
        root = ET.fromstring(raw.strip())
    except ET.ParseError as exc:
        raise AdapterError("Device did not answer with ISAPI XML (is this a Hikvision device?)", "invalid_input") from exc
    for element in root.iter():
        if isinstance(element.tag, str) and element.tag.startswith("{"):
            element.tag = element.tag.split("}", 1)[1]
    return root


def xtext(element: Optional[ET.Element], path: str, default: str = "") -> str:
    """Text of the first child matching ``path`` (namespace-free), stripped."""
    if element is None:
        return default
    found = element.find(path)
    if found is None or found.text is None:
        return default
    return found.text.strip()


def _xint(element: Optional[ET.Element], path: str) -> Optional[int]:
    text = xtext(element, path)
    try:
        return int(text)
    except ValueError:
        return None


def _has_digest_challenge(response: httpx.Response) -> bool:
    return any(h.lower().startswith("digest") for h in response.headers.get_list("www-authenticate"))


def _response_status(response: httpx.Response) -> Tuple[Optional[int], str]:
    """Extract ``statusCode``/``statusString`` from an ISAPI ResponseStatus body (XML or JSON)."""
    body = response.content or b""
    if not body.strip():
        return None, ""
    content_type = response.headers.get("content-type", "")
    if "json" in content_type or body.lstrip().startswith(b"{"):
        try:
            data = json.loads(body)
        except ValueError:
            return None, ""
        if isinstance(data, dict) and "statusCode" in data:
            return _as_int(data.get("statusCode"), 0), str(data.get("statusString") or data.get("subStatusCode") or "")
        return None, ""
    try:
        root = parse_xml(body)
    except AdapterError:
        return None, ""
    if root.tag != "ResponseStatus":
        return None, ""
    return _xint(root, "statusCode"), xtext(root, "statusString") or xtext(root, "subStatusCode")


def _signal_percent(value: Any) -> Optional[int]:
    """AX PRO reports signal either as bars (0-4) or as a percentage; normalise to 0-100."""
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 5:
        return int(max(0.0, min(4.0, number)) * 25)
    return int(max(0.0, min(100.0, number)))


def _channel_of(device: DeviceRef) -> int:
    """Streaming channel number of a camera/NVR-channel device (default 1)."""
    channel = _as_int(device.cfg("channel"), 0)
    if channel <= 0:
        match = re.search(r":ch(\d+)$", device.external_id)
        channel = int(match.group(1)) if match else 1
    return channel


def _zone_of(device: DeviceRef) -> Optional[int]:
    zone = device.cfg("zone_id")
    if zone in (None, ""):
        match = re.search(r":zone(\d+)$", device.external_id)
        return int(match.group(1)) if match else None
    return _as_int(zone, 0)


def _host_external_id(device: DeviceRef) -> str:
    """External id of the host device (camera / NVR / panel) a ref belongs to."""
    if device.parent_external_id:
        return device.parent_external_id
    return device.external_id.split(":", 1)[0]


# =============================================================================== sessions
@dataclass
class HostSession:
    """Connection parameters of one ISAPI host."""

    host: str
    port: int = 80
    https: bool = False
    username: str = ""
    password: str = ""
    rtsp_port: int = 554

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "HostSession":
        """Build from the pairing form payload."""
        https = _as_bool(payload.get("https"), False)
        return cls(
            host=str(payload.get("host") or "").strip(),
            port=_as_int(payload.get("port"), 443 if https else 80),
            https=https,
            username=str(payload.get("username") or "").strip(),
            password=str(payload.get("password") or ""),
            rtsp_port=_as_int(payload.get("rtsp_port"), 554),
        )

    @classmethod
    def from_device(cls, device: DeviceRef) -> "HostSession":
        """Build from a stored device (children inherit host/credentials from their parent via the hub)."""
        host = str(device.cfg("host") or "").strip()
        if not host:
            raise AdapterError("Device has no host configured; pair it again", "invalid_input")
        https = _as_bool(device.cfg("https"), False)
        return cls(
            host=host,
            port=_as_int(device.cfg("port"), 443 if https else 80),
            https=https,
            username=str(device.cred("username") or ""),
            password=str(device.cred("password") or ""),
            rtsp_port=_as_int(device.cfg("rtsp_port"), 554),
        )

    @property
    def base_url(self) -> str:
        """``http(s)://host:port``."""
        return f"{'https' if self.https else 'http'}://{self.host}:{self.port}"

    def rtsp_url(self, channel: int, sub: bool = False) -> str:
        """RTSP URL of a channel (main = <ch>01, sub = <ch>02), without credentials."""
        return f"rtsp://{self.host}:{self.rtsp_port}/Streaming/Channels/{channel}{'02' if sub else '01'}"

    def snapshot_url(self, channel: int) -> str:
        """HTTP snapshot URL of a channel."""
        return f"{self.base_url}/ISAPI/Streaming/channels/{channel}01/picture"

    def config(self) -> Dict[str, Any]:
        """Non-secret config persisted on the host device."""
        return {"host": self.host, "port": self.port, "https": self.https, "rtsp_port": self.rtsp_port}

    def credentials(self) -> Dict[str, Any]:
        """Secret credentials persisted (encrypted) on the host device."""
        return {"username": self.username, "password": self.password}

    def key(self) -> Tuple[str, int, bool]:
        """Grouping key for subscriptions (one alert stream per host)."""
        return (self.host, self.port, self.https)


class IsapiClient:
    """ISAPI request helper: Digest auth with Basic fallback, transport errors mapped to AdapterError."""

    def __init__(self, client: httpx.AsyncClient, session: HostSession, log: Optional[logging.Logger] = None):
        self._client = client
        self.session = session
        self._log = log or logger
        self._auth: httpx.Auth = httpx.DigestAuth(session.username, session.password)
        self._basic_tried = False

    def _fallback_to_basic(self, response: httpx.Response) -> bool:
        """True when a 401 carried no Digest challenge and Basic auth should be tried once."""
        if response.status_code != 401 or self._basic_tried or _has_digest_challenge(response):
            return False
        self._basic_tried = True
        self._auth = httpx.BasicAuth(self.session.username, self.session.password)
        self._log.debug("%s: no Digest challenge, falling back to Basic auth", self.session.host)
        return True

    async def request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        content: Optional[bytes] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> httpx.Response:
        """Perform one request; raises AdapterError(unreachable) on transport failures."""
        url = self.session.base_url + path
        try:
            response = await self._client.request(method, url, params=params, content=content, headers=headers, auth=self._auth)
            if self._fallback_to_basic(response):
                response = await self._client.request(method, url, params=params, content=content, headers=headers, auth=self._auth)
        except httpx.TimeoutException as exc:
            raise AdapterError(f"Timeout talking to {self.session.host}:{self.session.port}", "unreachable") from exc
        except httpx.HTTPError as exc:
            raise AdapterError(f"Cannot reach {self.session.host}:{self.session.port} ({exc.__class__.__name__})", "unreachable") from exc
        except httpx.InvalidURL as exc:
            raise AdapterError(f"Invalid host: {exc}", "invalid_input") from exc
        return response

    async def stream_bytes(self, path: str, what: str) -> AsyncIterator[bytes]:
        """Stream a long-lived response body (alertStream) chunk by chunk."""
        url = self.session.base_url + path
        for _attempt in (0, 1):
            try:
                async with self._client.stream("GET", url, auth=self._auth) as response:
                    if self._fallback_to_basic(response):
                        continue
                    self.ensure_ok(response, what)
                    async for chunk in response.aiter_bytes():
                        yield chunk
                    return
            except httpx.TimeoutException as exc:
                raise AdapterError(f"Timeout talking to {self.session.host}:{self.session.port}", "unreachable") from exc
            except httpx.HTTPError as exc:
                raise AdapterError(f"Cannot reach {self.session.host}:{self.session.port} ({exc.__class__.__name__})", "unreachable") from exc

    def ensure_ok(self, response: httpx.Response, what: str) -> httpx.Response:
        """Map HTTP failures to AdapterError codes."""
        status = response.status_code
        if status == 401:
            raise AdapterError("Authentication failed: check the username and password", "auth_failed")
        if status == 403:
            raise AdapterError(f"{what}: forbidden (user lacks permission or the device is locked)", "auth_failed")
        if status == 404:
            raise AdapterError(f"{what}: not supported by this device", "unsupported")
        if status >= 500:
            raise AdapterError(f"{what}: device error HTTP {status}", "unreachable")
        if status >= 400:
            _, text = _response_status(response)
            raise AdapterError(f"{what}: rejected (HTTP {status}) {text}".strip(), "invalid_input")
        return response

    def check_control(self, response: httpx.Response, what: str) -> None:
        """For control PUTs: HTTP status + ISAPI ``statusCode`` must both be OK."""
        self.ensure_ok(response, what)
        code, text = _response_status(response)
        if code is not None and code != 1:
            raise AdapterError(f"{what}: device refused ({text or code})", "invalid_input")

    async def get_xml(self, path: str, what: str, params: Optional[Dict[str, Any]] = None) -> ET.Element:
        """GET + XML parse (errors mapped)."""
        response = self.ensure_ok(await self.request("GET", path, params=params), what)
        return parse_xml(response.content)

    async def get_json(self, path: str, what: str) -> Dict[str, Any]:
        """GET ``?format=json`` + JSON parse (errors mapped)."""
        response = self.ensure_ok(await self.request("GET", path, params={"format": "json"}), what)
        try:
            data = response.json()
        except ValueError as exc:
            raise AdapterError(f"{what}: device did not answer with JSON", "invalid_input") from exc
        if not isinstance(data, dict):
            raise AdapterError(f"{what}: unexpected JSON payload", "invalid_input")
        return data

    async def probe(self, path: str, params: Optional[Dict[str, Any]] = None) -> Optional[httpx.Response]:
        """Best-effort GET: the response on HTTP 200, None otherwise (transport errors still raise)."""
        response = await self.request("GET", path, params=params)
        if response.status_code != 200:
            return None
        return response


# =============================================================================== parsed models
@dataclass
class DeviceInfo:
    """``/ISAPI/System/deviceInfo`` essentials."""

    name: str
    model: str
    serial: str
    firmware: str
    device_type: str
    mac: str = ""

    @property
    def is_recorder(self) -> bool:
        """NVR / DVR / hybrid recorders."""
        return any(token in self.device_type.upper() for token in RECORDER_TYPES)


def parse_device_info(root: ET.Element) -> DeviceInfo:
    """Validate and extract ``DeviceInfo`` XML."""
    if root.tag != "DeviceInfo":
        raise AdapterError(f"Unexpected ISAPI answer '{root.tag}' (expected DeviceInfo)", "invalid_input")
    serial = xtext(root, "serialNumber") or xtext(root, "deviceID") or xtext(root, "macAddress").replace(":", "")
    if not serial:
        raise AdapterError("Device did not report a serial number", "invalid_input")
    return DeviceInfo(
        name=xtext(root, "deviceName"),
        model=xtext(root, "model"),
        serial=serial,
        firmware=" ".join(t for t in (xtext(root, "firmwareVersion"), xtext(root, "firmwareReleasedDate")) if t),
        device_type=xtext(root, "deviceType"),
        mac=xtext(root, "macAddress"),
    )


@dataclass
class ChannelInfo:
    """One video channel of a recorder."""

    id: int
    name: str
    ip_address: str = ""
    model: str = ""
    protocol: str = ""
    online: bool = True
    proxy: bool = False


def parse_video_inputs(root: ET.Element) -> List[ChannelInfo]:
    """``VideoInputChannelList`` -> channels (analog / built-in inputs)."""
    channels: List[ChannelInfo] = []
    for item in root.iter("VideoInputChannel"):
        cid = _xint(item, "id")
        if cid is None:
            continue
        channels.append(ChannelInfo(id=cid, name=xtext(item, "name")))
    return channels


def parse_input_proxy(root: ET.Element) -> List[ChannelInfo]:
    """``InputProxyChannelList`` -> IP channels of an NVR."""
    channels: List[ChannelInfo] = []
    for item in root.iter("InputProxyChannel"):
        cid = _xint(item, "id")
        if cid is None:
            continue
        descriptor = item.find("sourceInputPortDescriptor")
        channels.append(ChannelInfo(
            id=cid,
            name=xtext(item, "name"),
            ip_address=xtext(descriptor, "ipAddress"),
            model=xtext(descriptor, "model"),
            protocol=xtext(descriptor, "proxyProtocol"),
            proxy=True,
        ))
    return channels


def parse_input_proxy_status(root: ET.Element) -> Dict[int, bool]:
    """``InputProxyChannelStatusList`` -> {channel id: online}."""
    status: Dict[int, bool] = {}
    for item in root.iter("InputProxyChannelStatus"):
        cid = _xint(item, "id")
        if cid is not None:
            status[cid] = _as_bool(xtext(item, "online"), True)
    return status


@dataclass
class SubSystem:
    """AX PRO partition."""

    id: int
    name: str
    arming: str
    alarm: bool
    enabled: bool = True

    @property
    def arm_mode(self) -> str:
        """Hub security mode."""
        return ARM_FROM_ISAPI.get(self.arming, "disarmed")


@dataclass
class ZoneInfo:
    """AX PRO zone (detector)."""

    id: int
    name: str
    status: str
    alarm: bool
    tamper: bool
    bypassed: bool
    subsystem: int
    signal: Optional[int] = None
    battery: Optional[int] = None
    model: str = ""
    detector_type: str = ""

    @property
    def online(self) -> bool:
        """Zone reachable by the panel."""
        return self.status.lower() not in ("offline", "breakdown")

    def state(self) -> Dict[str, Any]:
        """Hub alarm_zone state."""
        data: Dict[str, Any] = {
            "open": self.status == "notReady",
            "alarm": self.alarm,
            "bypass": self.bypassed,
            "tamper": self.tamper,
        }
        if self.battery is not None:
            data["battery"] = self.battery
        if self.signal is not None:
            data["signal"] = self.signal
        return data


def parse_subsystems(data: Dict[str, Any]) -> List[SubSystem]:
    """``{"SubSysList":[{"SubSys":{...}}]}`` -> partitions (sorted by id)."""
    result: List[SubSystem] = []
    for item in data.get("SubSysList") or []:
        sub = item.get("SubSys") if isinstance(item, dict) else None
        if not isinstance(sub, dict) or sub.get("id") is None:
            continue
        result.append(SubSystem(
            id=_as_int(sub.get("id"), 1),
            name=str(sub.get("name") or ""),
            arming=str(sub.get("arming") or "disarm"),
            alarm=_as_bool(sub.get("alarm")),
            enabled=_as_bool(sub.get("enabled"), True),
        ))
    result.sort(key=lambda s: s.id)
    return result


def parse_zones(data: Dict[str, Any]) -> List[ZoneInfo]:
    """``{"ZoneList":[{"Zone":{...}}]}`` -> zones (sorted by id)."""
    result: List[ZoneInfo] = []
    for item in data.get("ZoneList") or []:
        zone = item.get("Zone") if isinstance(item, dict) else None
        if not isinstance(zone, dict) or zone.get("id") is None:
            continue
        subsystem = zone.get("subSystemNo")
        if subsystem is None:
            linked = zone.get("linkageSubSystem") or []
            subsystem = linked[0] if linked else 1
        charge = zone.get("chargeValue")
        result.append(ZoneInfo(
            id=_as_int(zone.get("id"), 0),
            name=str(zone.get("name") or ""),
            status=str(zone.get("status") or ""),
            alarm=_as_bool(zone.get("alarm")),
            tamper=_as_bool(zone.get("tamperEvident")),
            bypassed=_as_bool(zone.get("bypassed")),
            subsystem=_as_int(subsystem, 1),
            signal=_signal_percent(zone.get("signal")),
            battery=None if charge in (None, "") else max(0, min(100, _as_int(charge, 0))),
            model=str(zone.get("model") or ""),
            detector_type=str(zone.get("detectorType") or ""),
        ))
    result.sort(key=lambda z: z.id)
    return result


def panel_state(subsystems: List[SubSystem], zones: List[ZoneInfo], primary: Optional[int] = None) -> Dict[str, Any]:
    """Hub alarm_panel state from partitions + zones (arm mode of the primary partition, alarm if any)."""
    enabled = [s for s in subsystems if s.enabled] or subsystems
    chosen = next((s for s in enabled if s.id == primary), None) if primary is not None else None
    if chosen is None:
        chosen = enabled[0] if enabled else None
    triggered = next((z for z in zones if z.alarm), None)
    return {
        "arm_mode": chosen.arm_mode if chosen else "disarmed",
        "alarm": any(s.alarm for s in subsystems) or triggered is not None,
        "triggered_zone": triggered.name if triggered else "",
        "ready": all(z.status != "notReady" or z.bypassed for z in zones),
    }


# =============================================================================== alert stream
@dataclass
class AlertEvent:
    """One ``EventNotificationAlert`` document."""

    event_type: str
    state: str
    channel: Optional[int]
    description: str = ""
    cid_code: Optional[int] = None
    cid_zone: Optional[int] = None
    cid_subsystem: Optional[int] = None

    @property
    def is_heartbeat(self) -> bool:
        """``videoloss inactive`` is the keep-alive Hikvision sends every ~300 ms."""
        return self.event_type == "videoloss" and self.state == "inactive"

    @property
    def active(self) -> bool:
        """Event is starting (vs. ending)."""
        return self.state == "active"


class AlertStreamParser:
    """Incremental splitter for the ``multipart/mixed`` alertStream body.

    Rather than trusting boundaries/Content-Length (which vary across firmware), it extracts every
    complete ``<EventNotificationAlert>...</EventNotificationAlert>`` document from the byte flow.
    """

    START = b"<EventNotificationAlert"
    END = b"</EventNotificationAlert>"

    def __init__(self, max_buffer: int = 1024 * 1024):
        self._buffer = b""
        self._max_buffer = max_buffer

    def feed(self, chunk: bytes) -> List[str]:
        """Add bytes; return the XML documents completed by this chunk."""
        self._buffer += chunk
        documents: List[str] = []
        while True:
            start = self._buffer.find(self.START)
            if start < 0:
                keep = len(self.START) - 1
                self._buffer = self._buffer[-keep:] if len(self._buffer) > keep else self._buffer
                break
            end = self._buffer.find(self.END, start)
            if end < 0:
                self._buffer = self._buffer[start:]
                if len(self._buffer) > self._max_buffer:
                    logger.warning("alertStream: dropping %d unterminated bytes", len(self._buffer))
                    self._buffer = b""
                break
            end += len(self.END)
            documents.append(self._buffer[start:end].decode("utf-8", "replace"))
            self._buffer = self._buffer[end:]
        return documents


def parse_alert(document: str) -> Optional[AlertEvent]:
    """Parse one alert document; None when it is not a valid EventNotificationAlert."""
    try:
        root = parse_xml(document)
    except AdapterError:
        return None
    if root.tag != "EventNotificationAlert":
        return None
    channel = _xint(root, "channelID")
    if channel is None or channel <= 0:
        channel = _xint(root, "dynChannelID")
    event_type = xtext(root, "eventType")
    if not event_type:
        return None
    alert = AlertEvent(
        event_type=event_type,
        state=xtext(root, "eventState") or "active",
        channel=channel,
        description=xtext(root, "eventDescription"),
    )
    cid = root.find("CIDEvent")
    if cid is not None:
        alert.cid_code = _xint(cid, "code")
        alert.cid_zone = _xint(cid, "zone")
        alert.cid_subsystem = _xint(cid, "subSystem")
    return alert


@dataclass
class HostGroup:
    """Devices sharing one ISAPI host (one alert stream)."""

    session: HostSession
    primary: str = ""
    is_recorder: bool = False
    is_panel: bool = False
    channels: Dict[int, str] = field(default_factory=dict)
    zones: Dict[int, str] = field(default_factory=dict)
    external_ids: List[str] = field(default_factory=list)
    last_states: Dict[Tuple[str, str], str] = field(default_factory=dict)

    def target_for(self, alert: AlertEvent) -> Optional[str]:
        """External id an alert applies to (None when it cannot be attributed)."""
        if alert.channel is not None and alert.channel in self.channels:
            return self.channels[alert.channel]
        if len(self.channels) == 1:
            return next(iter(self.channels.values()))
        if self.is_recorder and alert.event_type in MOTION_EVENTS:
            return None
        return self.primary or None

    def changed(self, target: str, event_type: str, state: str) -> bool:
        """Debounce: True when this (device, event type) transitions to a new state."""
        key = (target, event_type)
        if self.last_states.get(key) == state:
            return False
        self.last_states[key] = state
        return True


def group_by_host(devices: List[DeviceRef]) -> List[HostGroup]:
    """Group device refs per ISAPI host for subscriptions."""
    groups: Dict[Tuple[str, int, bool], HostGroup] = {}
    for device in devices:
        try:
            session = HostSession.from_device(device)
        except AdapterError as exc:
            logger.warning("hikvision: skipping %s for push (%s)", device.external_id, exc.message)
            continue
        group = groups.get(session.key())
        if group is None:
            group = groups[session.key()] = HostGroup(session=session)
        elif not group.session.username and session.username:
            group.session = session
        group.external_ids.append(device.external_id)
        category = device.category
        if category == "nvr":
            group.primary, group.is_recorder = device.external_id, True
        elif category == "alarm_panel":
            group.primary, group.is_panel = device.external_id, True
        elif category == "alarm_zone":
            group.is_panel = True
            zone = _zone_of(device)
            if zone is not None:
                group.zones[zone] = device.external_id
            group.primary = group.primary or _host_external_id(device)
        else:  # camera / doorbell (standalone or recorder channel)
            group.channels[_channel_of(device)] = device.external_id
            if device.parent_external_id:
                group.is_recorder = True
                group.primary = group.primary or device.parent_external_id
            else:
                group.primary = group.primary or device.external_id
    return list(groups.values())


# =============================================================================== adapter
class HikvisionAdapter(BrandAdapter):
    """Hikvision ISAPI adapter (cameras, NVR/DVR, AX PRO)."""

    brand_id = BRAND_ID

    def __init__(self, stream_opener: Optional[StreamOpener] = None):
        # Tests inject an async byte iterator factory instead of the real alertStream HTTP request.
        self._stream_opener: StreamOpener = stream_opener or self._open_alert_stream

    # ------------------------------------------------------------------ catalogue
    def info(self) -> BrandInfo:
        return BrandInfo(
            id=BRAND_ID,
            name="Hikvision",
            vendor="Hangzhou Hikvision Digital Technology",
            description="Caméras IP, enregistreurs NVR/DVR et centrales AX PRO via ISAPI (réseau local).",
            protocols=[PROTOCOL],
            categories=["camera", "nvr", "alarm_panel", "alarm_zone"],
            methods=[
                PairingMethod(
                    id=METHOD_IP,
                    title="Adresse IP et identifiants",
                    description="Connexion directe à la caméra, au NVR ou à la centrale AX PRO sur le réseau local.",
                    fields=[
                        FormField(name="host", label="Adresse IP / hôte", type="text", placeholder="192.168.1.64"),
                        FormField(name="port", label="Port HTTP", type="number", default=80),
                        FormField(name="https", label="Utiliser HTTPS", type="toggle", required=False, default=False),
                        FormField(name="username", label="Utilisateur", type="text", placeholder="admin"),
                        FormField(name="password", label="Mot de passe", type="password"),
                        FormField(name="rtsp_port", label="Port RTSP", type="number", default=554,
                                  help="Port du flux vidéo (554 par défaut)."),
                        FormField(name="name", label="Nom de l'appareil", type="text", required=False,
                                  help="Optionnel, sinon le nom déclaré par l'appareil."),
                    ],
                    supports_discovery=False,
                    icon="lan",
                )
            ],
            icon="videocam",
            docs_url="https://www.hikvision.com/en/support/download/sdk/",
            color="#E4002B",
        )

    # ------------------------------------------------------------------ pairing
    async def pair(self, method_id: str, payload: Dict[str, Any], ctx: AdapterContext) -> PairResult:
        self.method(method_id)
        require(payload, "host", "username", "password")
        session = HostSession.from_payload(payload)
        custom_name = str(payload.get("name") or "").strip()
        async with ctx.http() as client:
            api = IsapiClient(client, session, ctx.logger)
            info = parse_device_info(await api.get_xml(PATH_DEVICE_INFO, "deviceInfo"))
            subsystems = await self._probe_panel(api)
            if subsystems is not None:
                devices = await self._pair_panel(api, info, subsystems, custom_name)
                kind = "centrale AX PRO"
            elif info.is_recorder:
                devices = await self._pair_recorder(api, info, custom_name)
                kind = f"enregistreur ({len(devices) - 1} canaux)"
            else:
                devices = [await self._pair_camera(api, info, custom_name)]
                kind = "caméra"
        logger.info("hikvision: paired %s %s (%s) as %s", info.device_type, info.model, info.serial, kind)
        return PairResult(devices=devices, message=f"{info.model or 'Hikvision'} — {kind} ajoutée")

    async def _probe_panel(self, api: IsapiClient) -> Optional[List[SubSystem]]:
        """AX PRO panels answer 200 on the SecurityCP sub-system status; anything else is not a panel."""
        response = await api.probe(PATH_SUBSYSTEMS, params={"format": "json"})
        if response is None:
            return None
        try:
            data = response.json()
        except ValueError:
            return None
        if not isinstance(data, dict) or "SubSysList" not in data:
            return None
        return parse_subsystems(data)

    async def _pair_camera(self, api: IsapiClient, info: DeviceInfo, custom_name: str) -> DeviceDraft:
        session = api.session
        ptz = await self._supports_ptz(api, 1)
        outputs = await self._io_outputs(api)
        config: Dict[str, Any] = {**session.config(), "channel": 1, "device_type": info.device_type, "io_outputs": outputs}
        if outputs >= 1:
            config["siren_output"] = 1
        if outputs >= 2:
            config["light_output"] = 2
        return DeviceDraft(
            external_id=info.serial,
            name=custom_name or info.name or info.model or "Caméra Hikvision",
            category="camera",
            protocol=PROTOCOL,
            model=info.model or None,
            manufacturer=MANUFACTURER,
            firmware=info.firmware or None,
            capabilities=camera_caps(ptz=ptz, siren=outputs >= 1, light=outputs >= 2),
            state={"motion": False, **self._stream_state(session, 1)},
            config=config,
            credentials=session.credentials(),
            icon="videocam",
        )

    async def _pair_recorder(self, api: IsapiClient, info: DeviceInfo, custom_name: str) -> List[DeviceDraft]:
        session = api.session
        channels = await self._recorder_channels(api)
        parent = DeviceDraft(
            external_id=info.serial,
            name=custom_name or info.name or info.model or "Enregistreur Hikvision",
            category="nvr",
            protocol=PROTOCOL,
            model=info.model or None,
            manufacturer=MANUFACTURER,
            firmware=info.firmware or None,
            capabilities=[cap("child_count", "int", False)],
            state={"child_count": len(channels)},
            config={**session.config(), "device_type": info.device_type, "channel_count": len(channels),
                    "channels": [c.id for c in channels]},
            credentials=session.credentials(),
            icon="dns",
        )
        drafts = [parent]
        for index, channel in enumerate(channels):
            ptz = await self._supports_ptz(api, channel.id) if index < MAX_PTZ_PROBES else False
            config: Dict[str, Any] = {"channel": channel.id}
            if channel.ip_address:
                config["ip_address"] = channel.ip_address
            drafts.append(DeviceDraft(
                external_id=f"{info.serial}:ch{channel.id}",
                name=channel.name or f"Canal {channel.id}",
                category="camera",
                protocol=PROTOCOL,
                model=channel.model or None,
                manufacturer=MANUFACTURER if channel.protocol.upper() in ("", "HIKVISION") else channel.protocol.title(),
                capabilities=camera_caps(ptz=ptz),
                state={"motion": False, **self._stream_state(session, channel.id)},
                config=config,
                parent_external_id=info.serial,
                icon="videocam",
                online=channel.online,
            ))
        return drafts

    async def _recorder_channels(self, api: IsapiClient) -> List[ChannelInfo]:
        """Analog/built-in inputs + IP (proxy) channels, merged by id (proxy entries win)."""
        merged: Dict[int, ChannelInfo] = {}
        response = await api.probe(PATH_VIDEO_INPUTS)
        if response is not None:
            try:
                for channel in parse_video_inputs(parse_xml(response.content)):
                    merged[channel.id] = channel
            except AdapterError:
                logger.debug("hikvision: unparsable VideoInputChannelList from %s", api.session.host)
        response = await api.probe(PATH_INPUT_PROXY)
        if response is not None:
            try:
                for channel in parse_input_proxy(parse_xml(response.content)):
                    merged[channel.id] = channel
            except AdapterError:
                logger.debug("hikvision: unparsable InputProxyChannelList from %s", api.session.host)
        if any(c.proxy for c in merged.values()):
            response = await api.probe(PATH_INPUT_PROXY_STATUS)
            if response is not None:
                try:
                    for cid, online in parse_input_proxy_status(parse_xml(response.content)).items():
                        if cid in merged:
                            merged[cid].online = online
                except AdapterError:
                    logger.debug("hikvision: unparsable InputProxy status from %s", api.session.host)
        return [merged[cid] for cid in sorted(merged)]

    async def _supports_ptz(self, api: IsapiClient, channel: int) -> bool:
        """True when the PTZ capabilities endpoint answers 200 for the channel."""
        try:
            response = await api.probe(f"/ISAPI/PTZCtrl/channels/{channel}/capabilities")
        except AdapterError:
            return False
        if response is None:
            return False
        try:
            return parse_xml(response.content).tag != "ResponseStatus"
        except AdapterError:
            return False

    async def _io_outputs(self, api: IsapiClient) -> int:
        """Number of alarm outputs declared in ``/ISAPI/System/capabilities`` (best effort, 0 when unknown)."""
        try:
            response = await api.probe(PATH_SYSTEM_CAPS)
            if response is None:
                return 0
            root = parse_xml(response.content)
        except AdapterError:
            return 0
        found = root.find(".//IOOutputPortNums")
        return _as_int(found.text if found is not None else None, 0)

    async def _pair_panel(self, api: IsapiClient, info: DeviceInfo, subsystems: List[SubSystem], custom_name: str) -> List[DeviceDraft]:
        session = api.session
        zones = parse_zones(await api.get_json(PATH_ZONES, "zones"))
        subsystem_ids = [s.id for s in subsystems if s.enabled] or [s.id for s in subsystems] or [1]
        panel = DeviceDraft(
            external_id=info.serial,
            name=custom_name or info.name or info.model or "Centrale AX PRO",
            category="alarm_panel",
            protocol=PROTOCOL,
            model=info.model or None,
            manufacturer=MANUFACTURER,
            firmware=info.firmware or None,
            capabilities=alarm_panel_caps(),
            state=panel_state(subsystems, zones, subsystem_ids[0]),
            config={**session.config(), "device_type": info.device_type, "subsystem": subsystem_ids[0],
                    "subsystems": subsystem_ids, "zone_count": len(zones)},
            credentials=session.credentials(),
            icon="shield",
        )
        drafts = [panel]
        for zone in zones:
            drafts.append(DeviceDraft(
                external_id=f"{info.serial}:zone{zone.id}",
                name=zone.name or f"Zone {zone.id}",
                category="alarm_zone",
                protocol=PROTOCOL,
                model=zone.model or None,
                manufacturer=MANUFACTURER,
                capabilities=alarm_zone_caps(),
                state=zone.state(),
                config={"zone_id": zone.id, "subsystem": zone.subsystem, "detector_type": zone.detector_type},
                parent_external_id=info.serial,
                icon="radar",
                online=zone.online,
            ))
        return drafts

    @staticmethod
    def _stream_state(session: HostSession, channel: int) -> Dict[str, Any]:
        return {
            "stream_main": session.rtsp_url(channel, sub=False),
            "stream_sub": session.rtsp_url(channel, sub=True),
            "snapshot": session.snapshot_url(channel),
        }

    # ------------------------------------------------------------------ refresh
    async def refresh(self, device: DeviceRef, ctx: AdapterContext) -> DeviceState:
        session = HostSession.from_device(device)
        async with ctx.http() as client:
            api = IsapiClient(client, session, ctx.logger)
            if device.category == "alarm_panel":
                return await self._refresh_panel(api, device)
            if device.category == "alarm_zone":
                return await self._refresh_zone(api, device)
            if device.category == "nvr":
                parse_device_info(await api.get_xml(PATH_DEVICE_INFO, "deviceInfo"))
                count = _as_int(device.cfg("channel_count"), len(device.cfg("channels") or []))
                return DeviceState(online=True, state={"child_count": count})
            return await self._refresh_camera(api, device)

    async def _refresh_camera(self, api: IsapiClient, device: DeviceRef) -> DeviceState:
        parse_device_info(await api.get_xml(PATH_DEVICE_INFO, "deviceInfo"))
        channel = _channel_of(device)
        online: Optional[bool] = None
        if device.parent_external_id:
            response = await api.probe(f"{PATH_INPUT_PROXY}/{channel}/status")
            if response is not None:
                try:
                    online = _as_bool(xtext(parse_xml(response.content), "online"), True)
                except AdapterError:
                    online = None
        if online is None:
            response = await api.request("GET", f"/ISAPI/Streaming/channels/{channel}01")
            if response.status_code in (401, 403):
                api.ensure_ok(response, "streaming channel")
            online = response.status_code == 200
        state: Dict[str, Any] = {"motion": bool(device.state.get("motion", False)), **self._stream_state(api.session, channel)}
        if "recording" in device.state:
            state["recording"] = device.state["recording"]
        return DeviceState(online=online, state=state)

    async def _panel_status(self, api: IsapiClient) -> Tuple[List[SubSystem], List[ZoneInfo]]:
        subsystems = parse_subsystems(await api.get_json(PATH_SUBSYSTEMS, "subSystems"))
        zones = parse_zones(await api.get_json(PATH_ZONES, "zones"))
        return subsystems, zones

    async def _refresh_panel(self, api: IsapiClient, device: DeviceRef) -> DeviceState:
        subsystems, zones = await self._panel_status(api)
        primary = _as_int(device.cfg("subsystem"), 0) or None
        return DeviceState(online=True, state=panel_state(subsystems, zones, primary))

    async def _refresh_zone(self, api: IsapiClient, device: DeviceRef) -> DeviceState:
        zone_id = _zone_of(device)
        zones = parse_zones(await api.get_json(PATH_ZONES, "zones"))
        zone = next((z for z in zones if z.id == zone_id), None)
        if zone is None:
            raise AdapterError(f"Zone {zone_id} no longer exists on the panel", "not_found")
        return DeviceState(online=zone.online, state=zone.state())

    # ------------------------------------------------------------------ commands
    async def send_command(self, device: DeviceRef, code: str, value: Any, ctx: AdapterContext) -> Dict[str, Any]:
        session = HostSession.from_device(device)
        async with ctx.http() as client:
            api = IsapiClient(client, session, ctx.logger)
            if device.category == "alarm_panel":
                return await self._panel_command(api, device, code, value)
            if device.category == "alarm_zone":
                return await self._zone_command(api, device, code, value)
            if code == "ptz":
                return await self._ptz(api, device, str(value))
            if code in ("siren", "light"):
                return await self._io_output(api, device, code, _as_bool(value))
        raise AdapterError(f"Command '{code}' is not supported by this Hikvision device", "unsupported")

    async def _ptz(self, api: IsapiClient, device: DeviceRef, direction: str) -> Dict[str, Any]:
        vector = PTZ_VECTORS.get(direction)
        if vector is None:
            raise AdapterError(f"Unknown PTZ direction '{direction}'", "invalid_input")
        pan, tilt, zoom = vector
        body = f"<PTZData><pan>{pan}</pan><tilt>{tilt}</tilt><zoom>{zoom}</zoom></PTZData>".encode()
        response = await api.request(
            "PUT", f"/ISAPI/PTZCtrl/channels/{_channel_of(device)}/continuous", content=body,
            headers={"Content-Type": "application/xml"},
        )
        if response.status_code in (400, 403, 404):
            raise AdapterError("This channel does not support PTZ", "unsupported")
        api.check_control(response, "PTZ")
        return {}

    async def _io_output(self, api: IsapiClient, device: DeviceRef, code: str, on: bool) -> Dict[str, Any]:
        output = _as_int(device.cfg(f"{code}_output"), 0)
        if output <= 0:
            raise AdapterError(f"This camera has no alarm output for '{code}'", "unsupported")
        body = f"<IOPortData><outputState>{'high' if on else 'low'}</outputState></IOPortData>".encode()
        response = await api.request(
            "PUT", f"/ISAPI/System/IO/outputs/{output}/trigger", content=body, headers={"Content-Type": "application/xml"},
        )
        if response.status_code in (400, 403, 404):
            raise AdapterError(f"Alarm output {output} is not available on this device", "unsupported")
        api.check_control(response, f"{code} output")
        return {code: on}

    async def _panel_command(self, api: IsapiClient, device: DeviceRef, code: str, value: Any) -> Dict[str, Any]:
        subsystems = [_as_int(s, 0) for s in (device.cfg("subsystems") or [])]
        subsystems = [s for s in subsystems if s > 0] or [_as_int(device.cfg("subsystem"), 1) or 1]
        if code == "arm_mode":
            mode = str(value)
            if mode == "disarmed":
                for sub in subsystems:
                    api.check_control(await api.request("PUT", f"{PATH_CP_CONTROL}/disarm/{sub}"), "disarm")
                return {"arm_mode": "disarmed", "alarm": False, "triggered_zone": ""}
            ways = ARM_TO_ISAPI.get(mode)
            if ways is None:
                raise AdapterError(f"Unknown arm mode '{mode}'", "invalid_input")
            for sub in subsystems:
                api.check_control(await api.request("PUT", f"{PATH_CP_CONTROL}/arm/{sub}", params={"ways": ways}), "arm")
            return {"arm_mode": mode}
        if code == "clear_alarm" or (code == "alarm" and not _as_bool(value)):
            for sub in subsystems:
                api.check_control(await api.request("PUT", f"{PATH_CP_CONTROL}/clearAlarm/{sub}"), "clearAlarm")
            return {"alarm": False, "triggered_zone": ""}
        raise AdapterError(f"Command '{code}' is not supported by AX PRO panels", "unsupported")

    async def _zone_command(self, api: IsapiClient, device: DeviceRef, code: str, value: Any) -> Dict[str, Any]:
        if code != "bypass":
            raise AdapterError(f"Command '{code}' is not supported by AX PRO zones", "unsupported")
        zone_id = _zone_of(device)
        if zone_id is None:
            raise AdapterError("Zone id missing from device config", "invalid_input")
        bypass = bool(_as_bool(value))
        # Body-less control endpoints: ``bypass/{zone}`` sets the bypass, ``Recoverbypass/{zone}`` clears it.
        action = "bypass" if bypass else "Recoverbypass"
        response = await api.request("PUT", f"{PATH_CP_CONTROL}/{action}/{zone_id}", params={"format": "json"})
        api.check_control(response, "bypass" if bypass else "recover bypass")
        return {"bypass": bypass}

    # ------------------------------------------------------------------ media
    async def stream(self, device: DeviceRef, quality: str, ctx: AdapterContext) -> Optional[StreamInfo]:
        if device.category not in ("camera", "doorbell"):
            return None
        session = HostSession.from_device(device)
        url = session.rtsp_url(_channel_of(device), sub=(quality == "sub"))
        return StreamInfo(url=url, type="rtsp", username=session.username or None, password=session.password or None)

    async def snapshot(self, device: DeviceRef, ctx: AdapterContext) -> Optional[bytes]:
        if device.category not in ("camera", "doorbell"):
            return None
        session = HostSession.from_device(device)
        channel = _channel_of(device)
        async with ctx.http() as client:
            api = IsapiClient(client, session, ctx.logger)
            response = api.ensure_ok(await api.request("GET", f"/ISAPI/Streaming/channels/{channel}01/picture"), "snapshot")
        content = response.content or b""
        if not content.startswith(b"\xff\xd8") and "image" not in response.headers.get("content-type", ""):
            raise AdapterError("Device did not return a JPEG snapshot", "invalid_input")
        return content

    # ------------------------------------------------------------------ push (alertStream)
    async def subscribe(self, devices: List[DeviceRef], ctx: AdapterContext) -> Optional[Unsubscribe]:
        groups = group_by_host(devices)
        if not groups:
            return None
        tasks = [asyncio.create_task(self._alert_loop(group, ctx), name=f"hikvision-alerts-{group.session.host}") for group in groups]

        async def _unsubscribe() -> None:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        return _unsubscribe

    async def _open_alert_stream(self, session: HostSession, ctx: AdapterContext) -> AsyncIterator[bytes]:
        """Default stream opener: long-lived GET on the alertStream (no read timeout)."""
        timeout = httpx.Timeout(ctx.timeout, read=None)
        async with ctx.http(timeout=timeout) as client:
            api = IsapiClient(client, session, ctx.logger)
            async for chunk in api.stream_bytes(PATH_ALERT_STREAM, "alertStream"):
                yield chunk

    async def _alert_loop(self, group: HostGroup, ctx: AdapterContext) -> None:
        """Keep one alertStream open per host, reconnecting with backoff."""
        delay = RECONNECT_MIN_DELAY
        failures = 0
        while True:
            connected = False
            try:
                parser = AlertStreamParser()
                async for chunk in self._stream_opener(group.session, ctx):
                    if not connected:
                        connected = True
                        if failures >= OFFLINE_AFTER_FAILURES:
                            await self._emit_online(group, ctx, True)
                        failures, delay = 0, RECONNECT_MIN_DELAY
                    for document in parser.feed(chunk):
                        await self._handle_alert(document, group, ctx)
                logger.info("hikvision: alertStream from %s ended, reconnecting", group.session.host)
            except asyncio.CancelledError:
                raise
            except AdapterError as exc:
                logger.warning("hikvision: alertStream %s: %s (%s)", group.session.host, exc.message, exc.code)
                if exc.code == "auth_failed":
                    delay = AUTH_FAILURE_DELAY
            except Exception:  # pylint: disable=broad-except
                logger.exception("hikvision: alertStream %s crashed", group.session.host)
            failures += 1
            if failures == OFFLINE_AFTER_FAILURES:
                await self._emit_online(group, ctx, False)
            await asyncio.sleep(delay)
            delay = min(delay * 2, RECONNECT_MAX_DELAY)

    async def _emit_online(self, group: HostGroup, ctx: AdapterContext, online: bool) -> None:
        for external_id in group.external_ids:
            await ctx.emit("state", external_id, {"state": {}, "online": online})

    async def process_alert_stream(self, chunks: AsyncIterator[bytes], devices: List[DeviceRef], ctx: AdapterContext) -> int:
        """Feed an alertStream byte iterator for ``devices`` (testing hook / one-shot consumer). Returns handled alerts."""
        groups = group_by_host(devices)
        if not groups:
            return 0
        group = groups[0]
        parser = AlertStreamParser()
        handled = 0
        async for chunk in chunks:
            for document in parser.feed(chunk):
                handled += 1 if await self._handle_alert(document, group, ctx) else 0
        return handled

    async def _handle_alert(self, document: str, group: HostGroup, ctx: AdapterContext) -> bool:
        """Translate one alert into hub emits. Returns False for ignored/heartbeat alerts."""
        alert = parse_alert(document)
        if alert is None or alert.is_heartbeat:
            return False
        if alert.cid_code is not None and group.is_panel:
            return await self._handle_cid(alert, group, ctx)
        target = group.target_for(alert)
        if target is None:
            logger.debug("hikvision: %s event on unknown channel %s of %s", alert.event_type, alert.channel, group.session.host)
            return False
        if not group.changed(target, alert.event_type, alert.state):
            return False
        if alert.event_type in MOTION_EVENTS:
            await ctx.emit("state", target, {"state": {"motion": alert.active}, "online": True})
        elif alert.event_type == "videoloss":
            await ctx.emit("state", target, {"state": {}, "online": False})
        else:
            await ctx.emit("state", target, {"state": {}, "online": True})
        await ctx.emit("event", target, {
            "type": alert.event_type, "state": alert.state, "channel": alert.channel, "description": alert.description,
        })
        return True

    async def _handle_cid(self, alert: AlertEvent, group: HostGroup, ctx: AdapterContext) -> bool:
        """Best-effort Contact-ID mapping for AX PRO alert streams (arm/disarm, alarms, bypass)."""
        code = alert.cid_code or 0
        panel = group.primary
        zone_target = group.zones.get(alert.cid_zone) if alert.cid_zone is not None else None
        qualifier, event = divmod(code, 1000)
        if event in (401, 407, 408) and qualifier == 3:
            await ctx.emit("state", panel, {"state": {"arm_mode": "armed_away"}, "online": True})
        elif event in (441, 456) and qualifier == 3:
            await ctx.emit("state", panel, {"state": {"arm_mode": "armed_home"}, "online": True})
        elif event in (401, 407, 408, 441, 456) and qualifier == 1:
            await ctx.emit("state", panel, {"state": {"arm_mode": "disarmed", "alarm": False, "triggered_zone": ""}, "online": True})
        elif 100 <= event < 200:
            active = qualifier == 1
            if zone_target:
                await ctx.emit("state", zone_target, {"state": {"alarm": active}, "online": True})
            await ctx.emit("state", panel, {"state": {"alarm": active} if active else {"alarm": False, "triggered_zone": ""}, "online": True})
        elif event == 570 and zone_target:
            await ctx.emit("state", zone_target, {"state": {"bypass": qualifier == 1}, "online": True})
        await ctx.emit("event", zone_target or panel, {
            "type": "cid", "code": code, "zone": alert.cid_zone, "subsystem": alert.cid_subsystem, "description": alert.description,
        })
        return True


registry.register(HikvisionAdapter())
