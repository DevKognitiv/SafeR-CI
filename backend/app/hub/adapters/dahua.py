"""Dahua adapter (HTTP CGI API): IP cameras and NVR/DVR/XVR recorders from Dahua, IMOU, Amcrest, Lorex...

Everything goes through the Dahua CGI API over HTTP(S) with Digest authentication (Basic fallback):

* ``/cgi-bin/magicBox.cgi?action=getDeviceType|getSerialNo|getSoftwareVersion|getMachineName|getSystemInfo``
  -> identity (``key=value`` text lines)
* ``/cgi-bin/configManager.cgi?action=getConfig&name=ChannelTitle`` -> channels (``table.ChannelTitle[i].Name=``)
* ``/cgi-bin/ptz.cgi?action=getStatus|start|stop``   -> PTZ detection and moves
* ``/cgi-bin/coaxialControlIO.cgi``                   -> white light (Type=1) / siren (Type=2)
* ``/cgi-bin/snapshot.cgi?channel=<n>``               -> JPEG snapshot
* ``/cgi-bin/eventManager.cgi?action=attach``         -> push events (``multipart/x-mixed-replace`` text parts)

Channel numbering: Dahua channels are **1-based** for RTSP, PTZ and snapshots but **0-based** in the
``ChannelTitle`` table, in ``coaxialControlIO`` and in the ``index`` of event notifications. The hub
always stores the 1-based channel in ``config["channel"]`` and converts at the wire.

External ids: ``<serial>`` for the host device (camera or recorder) and ``<serial>:ch<n>`` for recorder
channels. Credentials are stored on the host device only; the hub merges them into children.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Tuple
from urllib.parse import quote

import httpx

from app.hub.adapters.base import (
    AdapterContext, AdapterError, BrandAdapter, BrandInfo, DeviceDraft, DeviceRef, DeviceState, FormField,
    PairResult, PairingMethod, StreamInfo, Unsubscribe, require,
)
from app.hub.adapters.registry import registry
from app.hub.capabilities import camera_caps, cap

logger = logging.getLogger("safer.hub.dahua")

BRAND_ID = "dahua"
PROTOCOL = "dahua_http"
METHOD_IP = "ip_credentials"
MANUFACTURER = "Dahua"

# CGI paths ---------------------------------------------------------------------
PATH_MAGICBOX = "/cgi-bin/magicBox.cgi"
PATH_CONFIG = "/cgi-bin/configManager.cgi"
PATH_PTZ = "/cgi-bin/ptz.cgi"
PATH_SNAPSHOT = "/cgi-bin/snapshot.cgi"
PATH_COAXIAL = "/cgi-bin/coaxialControlIO.cgi"
PATH_EVENTS = "/cgi-bin/eventManager.cgi"
PATH_CAMERA_STATE = "/cgi-bin/api/LogicDeviceManager/getCameraState"

# Event codes subscribed on the eventManager stream; the motion ones drive the ``motion`` capability.
EVENT_CODES: List[str] = [
    "VideoMotion", "AlarmLocal", "CrossLineDetection", "CrossRegionDetection", "SmartMotionHuman", "SmartMotionVehicle",
]
MOTION_CODES = frozenset({"VideoMotion", "CrossLineDetection", "CrossRegionDetection", "SmartMotionHuman", "SmartMotionVehicle"})
HEARTBEAT_SECONDS = 5
DEFAULT_BOUNDARY = "myboundary"

# Hub PTZ directions -> Dahua PTZ action codes
PTZ_CODES: Dict[str, str] = {
    "up": "Up", "down": "Down", "left": "Left", "right": "Right", "zoom_in": "ZoomTele", "zoom_out": "ZoomWide",
}
# Hub capability -> coaxialControlIO ``info[0].Type``
COAXIAL_TYPES: Dict[str, int] = {"light": 1, "siren": 2}
COAXIAL_STATUS_KEYS: Dict[str, str] = {"status.whiteLight": "light", "status.speaker": "siren"}

RECORDER_PREFIXES = ("NVR", "DVR", "XVR", "HCVR")
VENDOR_PREFIXES = ("DHI-", "DH-")
GENERIC_VENDORS = ("", "general", "private", "unknown")
MAX_PTZ_PROBES = 64
OFFLINE_AFTER_FAILURES = 3
RECONNECT_MIN_DELAY = 5.0
RECONNECT_MAX_DELAY = 60.0
AUTH_FAILURE_DELAY = 300.0
MAX_EVENT_DATA = 4000

StreamOpener = Callable[["HostSession", AdapterContext], AsyncIterator[bytes]]

EVENT_RE = re.compile(
    r"Code=(?P<code>[^;\r\n]+);\s*action=(?P<action>[^;\r\n]+)(?:;\s*index=(?P<index>-?\d+))?(?:;\s*data=(?P<data>.*))?",
    re.S,
)
CHANNEL_TITLE_RE = re.compile(r"^\s*table\.ChannelTitle\[(\d+)\]\.Name=(.*?)\s*$", re.M)
BOUNDARY_RE = re.compile(rb"^--([A-Za-z0-9'()+_,\-./:=?]+)")
HEADER_END_RE = re.compile(rb"\r?\n\r?\n")
CONTENT_LENGTH_RE = re.compile(rb"content-length\s*:\s*(\d+)", re.I)


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


def _clean_host(value: Any) -> str:
    """Accept ``192.168.1.108``, ``cam.local`` or a pasted ``http://host/`` and keep only the host."""
    host = str(value or "").strip()
    if "://" in host:
        host = host.split("://", 1)[1]
    return host.split("/", 1)[0].strip()


def parse_kv(text: str) -> Dict[str, str]:
    """Parse Dahua ``key=value`` text lines (``\\r\\n`` separated) into a dict. Non ``k=v`` lines are ignored."""
    data: Dict[str, str] = {}
    for line in (text or "").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key:
            data[key] = value.strip()
    return data


def parse_channel_titles(text: str) -> Dict[int, str]:
    """``table.ChannelTitle[i].Name=...`` lines -> {0-based index: name}."""
    return {int(index): name.strip() for index, name in CHANNEL_TITLE_RE.findall(text or "")}


def is_error_body(text: str) -> bool:
    """Dahua answers ``Error`` (HTTP 200) or ``Bad Request`` (HTTP 400) for unsupported actions."""
    head = (text or "").lstrip()[:16].lower()
    return head.startswith("error") or head.startswith("bad request")


def normalize_device_type(device_type: str) -> str:
    """Strip vendor prefixes (``DHI-NVR4108`` -> ``NVR4108``) and upper-case the model."""
    model = (device_type or "").strip().upper()
    for prefix in VENDOR_PREFIXES:
        if model.startswith(prefix):
            model = model[len(prefix):]
    return model


def is_recorder_type(device_type: str) -> bool:
    """True for NVR / DVR / XVR / HCVR recorders."""
    return normalize_device_type(device_type).startswith(RECORDER_PREFIXES)


def _channel_of(device: DeviceRef) -> int:
    """1-based channel of a camera / recorder-channel device (default 1)."""
    channel = _as_int(device.cfg("channel"), 0)
    if channel <= 0:
        match = re.search(r":ch(\d+)$", device.external_id)
        channel = int(match.group(1)) if match else 1
    return channel


def _host_external_id(device: DeviceRef) -> str:
    """External id of the host device (camera / recorder) a ref belongs to."""
    if device.parent_external_id:
        return device.parent_external_id
    return device.external_id.split(":", 1)[0]


def _has_digest_challenge(response: httpx.Response) -> bool:
    return any(h.lower().startswith("digest") for h in response.headers.get_list("www-authenticate"))


def build_query(params: Dict[str, Any]) -> str:
    """Encode CGI parameters keeping ``[ ] , :`` literal, as Dahua firmwares expect (``codes=[VideoMotion]``)."""
    return "&".join(f"{key}={quote(str(value), safe='[],:/@')}" for key, value in params.items())


# =============================================================================== sessions
@dataclass
class HostSession:
    """Connection parameters of one Dahua host."""

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
            host=_clean_host(payload.get("host")),
            port=_as_int(payload.get("port"), 443 if https else 80),
            https=https,
            username=str(payload.get("username") or "").strip(),
            password=str(payload.get("password") or ""),
            rtsp_port=_as_int(payload.get("rtsp_port"), 554),
        )

    @classmethod
    def from_device(cls, device: DeviceRef) -> "HostSession":
        """Build from a stored device (children inherit host/credentials from their parent via the hub)."""
        host = _clean_host(device.cfg("host"))
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
        """RTSP URL of a channel (subtype 0 = main stream, 1 = sub stream), without credentials."""
        return f"rtsp://{self.host}:{self.rtsp_port}/cam/realmonitor?channel={channel}&subtype={1 if sub else 0}"

    def snapshot_url(self, channel: int) -> str:
        """HTTP snapshot URL of a channel."""
        return f"{self.base_url}{PATH_SNAPSHOT}?channel={channel}"

    def config(self) -> Dict[str, Any]:
        """Non-secret config persisted on the host device."""
        return {"host": self.host, "port": self.port, "https": self.https, "rtsp_port": self.rtsp_port}

    def credentials(self) -> Dict[str, Any]:
        """Secret credentials persisted (encrypted) on the host device."""
        return {"username": self.username, "password": self.password}

    def key(self) -> Tuple[str, int, bool]:
        """Grouping key for subscriptions (one event stream per host)."""
        return (self.host, self.port, self.https)


class DahuaClient:
    """CGI request helper: Digest auth with Basic fallback, transport errors mapped to AdapterError."""

    def __init__(self, client: httpx.AsyncClient, session: HostSession, log: Optional[logging.Logger] = None):
        self._client = client
        self.session = session
        self._log = log or logger
        self._auth: httpx.Auth = httpx.DigestAuth(session.username, session.password)
        self._basic_tried = False

    def url(self, path: str, params: Optional[Dict[str, Any]] = None) -> str:
        """Absolute URL with a literal (non percent-encoded) CGI query string."""
        url = self.session.base_url + path
        if params:
            url += "?" + build_query(params)
        return url

    def _fallback_to_basic(self, response: httpx.Response) -> bool:
        """True when a 401 carried no Digest challenge and Basic auth should be tried once."""
        if response.status_code != 401 or self._basic_tried or _has_digest_challenge(response):
            return False
        self._basic_tried = True
        self._auth = httpx.BasicAuth(self.session.username, self.session.password)
        self._log.debug("%s: no Digest challenge, falling back to Basic auth", self.session.host)
        return True

    def _transport_error(self, exc: Exception) -> AdapterError:
        where = f"{self.session.host}:{self.session.port}"
        if isinstance(exc, httpx.TimeoutException):
            return AdapterError(f"Timeout talking to {where}", "unreachable")
        return AdapterError(f"Cannot reach {where} ({exc.__class__.__name__})", "unreachable")

    async def request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None) -> httpx.Response:
        """Perform one request; raises AdapterError(unreachable) on transport failures."""
        url = self.url(path, params)
        try:
            response = await self._client.request(method, url, auth=self._auth)
            if self._fallback_to_basic(response):
                response = await self._client.request(method, url, auth=self._auth)
        except httpx.InvalidURL as exc:
            raise AdapterError(f"Invalid host: {exc}", "invalid_input") from exc
        except httpx.HTTPError as exc:
            raise self._transport_error(exc) from exc
        return response

    async def stream_bytes(self, path: str, params: Dict[str, Any], what: str) -> AsyncIterator[bytes]:
        """Stream a long-lived response body (event stream) chunk by chunk."""
        url = self.url(path, params)
        for _attempt in (0, 1):
            try:
                async with self._client.stream("GET", url, auth=self._auth) as response:
                    if self._fallback_to_basic(response):
                        continue
                    self.ensure_ok(response, what)
                    async for chunk in response.aiter_bytes():
                        yield chunk
                    return
            except httpx.HTTPError as exc:
                raise self._transport_error(exc) from exc

    def ensure_ok(self, response: httpx.Response, what: str) -> httpx.Response:
        """Map HTTP failures to AdapterError codes."""
        status = response.status_code
        if status == 401:
            raise AdapterError("Authentication failed: check the username and password", "auth_failed")
        if status == 403:
            raise AdapterError(f"{what}: forbidden (user lacks permission or the account is locked)", "auth_failed")
        if status == 404:
            raise AdapterError(f"{what}: not supported by this device", "unsupported")
        if status >= 500:
            raise AdapterError(f"{what}: device error HTTP {status}", "unreachable")
        if status >= 400:
            raise AdapterError(f"{what}: rejected by the device (HTTP {status})", "invalid_input")
        return response

    def check_command(self, response: httpx.Response, what: str) -> None:
        """For control GETs: HTTP status must be OK and the body must not be ``Error``."""
        self.ensure_ok(response, what)
        if is_error_body(response.text):
            raise AdapterError(f"{what}: device refused the command", "invalid_input")

    async def get_kv(self, path: str, params: Dict[str, Any], what: str, required: Optional[str] = None) -> Dict[str, str]:
        """GET + ``key=value`` parse (errors mapped; ``required`` key must be present)."""
        response = self.ensure_ok(await self.request("GET", path, params), what)
        text = response.text
        if is_error_body(text):
            raise AdapterError(f"{what}: device answered 'Error' (action not supported)", "unsupported")
        data = parse_kv(text)
        if required is not None and not data.get(required):
            raise AdapterError(f"{what}: unexpected answer (is this a Dahua device?)", "invalid_input")
        return data

    async def probe(self, path: str, params: Dict[str, Any]) -> Optional[str]:
        """Best-effort GET: the body on HTTP 200 (and not ``Error``), None otherwise (transport errors still raise)."""
        response = await self.request("GET", path, params)
        if response.status_code != 200:
            return None
        text = response.text
        if is_error_body(text):
            return None
        return text


# =============================================================================== parsed models
@dataclass
class DeviceInfo:
    """Identity gathered from ``magicBox.cgi``."""

    device_type: str
    serial: str
    firmware: str = ""
    name: str = ""
    vendor: str = ""
    hardware_version: str = ""

    @property
    def is_recorder(self) -> bool:
        """NVR / DVR / XVR / HCVR recorders."""
        return is_recorder_type(self.device_type)

    @property
    def manufacturer(self) -> str:
        """Vendor name reported by ``getVendor`` (Dahua, Amcrest, IMOU...) or Dahua."""
        vendor = self.vendor.strip()
        return vendor if vendor.lower() not in GENERIC_VENDORS else MANUFACTURER


@dataclass
class ChannelInfo:
    """One video channel (1-based)."""

    channel: int
    name: str = ""
    online: bool = True


def parse_camera_states(text: str) -> Dict[int, bool]:
    """``getCameraState`` JSON -> {1-based channel: connected}. Empty when the answer is not the expected JSON."""
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return {}
    states: Dict[int, bool] = {}
    items = data.get("states") if isinstance(data, dict) else None
    for item in items or []:
        if not isinstance(item, dict) or item.get("channel") is None:
            continue
        states[_as_int(item.get("channel"), -1) + 1] = str(item.get("connectionState") or "").lower() == "connected"
    return states


# =============================================================================== event stream
@dataclass
class DahuaEvent:
    """One ``Code=...;action=...;index=...`` notification from the eventManager stream."""

    code: str
    action: str
    index: int = 0
    data: str = ""

    @property
    def is_heartbeat(self) -> bool:
        """Keep-alive part (sent every ``heartbeat`` seconds)."""
        return self.code.lower() == "heartbeat"

    @property
    def channel(self) -> int:
        """1-based channel (``index`` is 0-based on the wire)."""
        return self.index + 1

    @property
    def active(self) -> bool:
        """Event is starting (vs. ending)."""
        return self.action == "Start"


def parse_event_part(part: bytes) -> Optional[DahuaEvent]:
    """Parse one multipart part (MIME headers + text body); None for empty / closing / unknown parts."""
    text = part.decode("utf-8", "replace")
    if re.search(r"^\s*Heartbeat\s*$", text, re.M):
        return DahuaEvent(code="Heartbeat", action="")
    match = re.search(r"^\s*(Code=.*)", text, re.M | re.S)
    if match is None:
        return None
    fields = EVENT_RE.match(match.group(1).strip())
    if fields is None:
        return None
    data = (fields.group("data") or "").strip()
    return DahuaEvent(
        code=fields.group("code").strip(),
        action=fields.group("action").strip(),
        index=_as_int(fields.group("index"), 0),
        data=data[:MAX_EVENT_DATA],
    )


def _text_body_end(buffer: bytes, body_start: int) -> int:
    """End of a part body without ``Content-Length``: a full ``Heartbeat``/``Code=`` line, or balanced ``data=`` JSON."""
    body = buffer[body_start:]
    stripped = body.lstrip(b"\r\n\t ")
    offset = body_start + (len(body) - len(stripped))
    newline = stripped.find(b"\n")
    if newline < 0:
        return -1
    first_line = stripped[:newline]
    if b"data=" not in first_line or not (first_line.startswith(b"Code=") or first_line.startswith(b"Heartbeat")):
        return offset + newline + 1
    opening = stripped.find(b"{", first_line.find(b"data="))
    if opening < 0:
        return offset + newline + 1
    depth, in_string, escaped = 0, False, False
    for position in range(opening, len(stripped)):
        char = stripped[position:position + 1]
        if in_string:
            if escaped:
                escaped = False
            elif char == b"\\":
                escaped = True
            elif char == b'"':
                in_string = False
        elif char == b'"':
            in_string = True
        elif char == b"{":
            depth += 1
        elif char == b"}":
            depth -= 1
            if depth == 0:
                return offset + position + 1
    return -1


class EventStreamParser:
    """Incremental splitter for the ``multipart/x-mixed-replace`` eventManager body.

    Parts are delimited by ``--<boundary>`` lines (``myboundary`` on every known firmware; the boundary is
    still auto-detected from the first delimiter in case a device uses another one).
    """

    def __init__(self, boundary: Optional[str] = None, max_buffer: int = 1024 * 1024):
        self._marker: Optional[bytes] = f"--{boundary}".encode() if boundary else None
        self._buffer = b""
        self._max_buffer = max_buffer

    @property
    def boundary(self) -> Optional[str]:
        """Boundary in use (None until detected)."""
        return self._marker[2:].decode() if self._marker else None

    def _detect_marker(self) -> bool:
        """Learn the boundary from the first ``--<boundary>`` line; assume the default when the stream has none."""
        head = self._buffer.lstrip(b"\r\n")
        if not head or head == b"-":
            return False  # nothing (or the start of a delimiter) received yet
        if head.startswith(b"--"):
            if b"\n" not in head:
                return False  # delimiter line not complete yet
            match = BOUNDARY_RE.match(head)
            if match is not None:
                self._marker = b"--" + match.group(1).rstrip(b"-")
                return True
        self._marker = f"--{DEFAULT_BOUNDARY}".encode()
        return True

    def feed(self, chunk: bytes) -> List[DahuaEvent]:
        """Add bytes; return the events completed by this chunk (heartbeats included, callers skip them).

        A part is complete when the next delimiter shows up, or — since the device sends nothing more until
        the next event — as soon as its declared ``Content-Length`` bytes (or a full ``Code=`` line) are in.
        """
        self._buffer += chunk
        events: List[DahuaEvent] = []
        if self._marker is None and not self._detect_marker():
            return events
        marker = self._marker or b""
        while True:
            start = self._buffer.find(marker)
            if start < 0:
                keep = len(marker) - 1
                self._buffer = self._buffer[-keep:] if len(self._buffer) > keep else self._buffer
                break
            if start > 0:
                self._buffer = self._buffer[start:]  # drop preamble / trailing CRLFs of the previous part
            part_start = len(marker)
            end = self._buffer.find(marker, part_start)
            if end < 0:
                end = self._self_delimited_end(part_start)
            if end < 0:
                if len(self._buffer) > self._max_buffer:
                    logger.warning("eventManager: dropping %d unterminated bytes", len(self._buffer))
                    self._buffer = b""
                break
            part = self._buffer[part_start:end]
            self._buffer = self._buffer[end:]
            event = parse_event_part(part)
            if event is not None:
                events.append(event)
        return events

    def _self_delimited_end(self, part_start: int) -> int:
        """End offset of the part starting at ``part_start`` when it can be completed without the next delimiter, else -1."""
        if self._buffer[part_start:part_start + 2] == b"--":  # closing delimiter ``--boundary--``
            newline = self._buffer.find(b"\n", part_start)
            return newline + 1 if newline >= 0 else len(self._buffer)
        headers = HEADER_END_RE.search(self._buffer, part_start)
        if headers is None:
            return -1
        body_start = headers.end()
        length = CONTENT_LENGTH_RE.search(self._buffer, part_start, body_start)
        if length is not None:
            end = body_start + int(length.group(1))
            return end if len(self._buffer) >= end else -1
        return _text_body_end(self._buffer, body_start)


@dataclass
class HostGroup:
    """Devices sharing one Dahua host (one event stream)."""

    session: HostSession
    primary: str = ""
    is_recorder: bool = False
    channels: Dict[int, str] = field(default_factory=dict)
    external_ids: List[str] = field(default_factory=list)
    last_states: Dict[Tuple[str, str], str] = field(default_factory=dict)

    def target_for(self, event: DahuaEvent) -> Optional[str]:
        """External id an event applies to (None when it cannot be attributed)."""
        if event.channel in self.channels:
            return self.channels[event.channel]
        if len(self.channels) == 1:
            return next(iter(self.channels.values()))
        if self.is_recorder and event.code in MOTION_CODES:
            return None
        return self.primary or None

    def changed(self, target: str, code: str, action: str) -> bool:
        """Debounce: True when this (device, event code) transitions to a new Start/Stop state."""
        key = (target, code)
        if self.last_states.get(key) == action:
            return False
        self.last_states[key] = action
        return True


def group_by_host(devices: List[DeviceRef]) -> List[HostGroup]:
    """Group device refs per Dahua host for subscriptions."""
    groups: Dict[Tuple[str, int, bool], HostGroup] = {}
    for device in devices:
        try:
            session = HostSession.from_device(device)
        except AdapterError as exc:
            logger.warning("dahua: skipping %s for push (%s)", device.external_id, exc.message)
            continue
        group = groups.get(session.key())
        if group is None:
            group = groups[session.key()] = HostGroup(session=session)
        elif not group.session.username and session.username:
            group.session = session
        group.external_ids.append(device.external_id)
        if device.category == "nvr":
            group.primary, group.is_recorder = device.external_id, True
        else:  # camera / doorbell (standalone or recorder channel)
            group.channels[_channel_of(device)] = device.external_id
            if device.parent_external_id:
                group.is_recorder = True
                group.primary = group.primary or device.parent_external_id
            else:
                group.primary = group.primary or _host_external_id(device)
    return list(groups.values())


# =============================================================================== adapter
class DahuaAdapter(BrandAdapter):
    """Dahua HTTP CGI adapter (cameras, NVR/DVR/XVR recorders)."""

    brand_id = BRAND_ID

    def __init__(self, stream_opener: Optional[StreamOpener] = None):
        # Tests inject an async byte iterator factory instead of the real eventManager HTTP request.
        self._stream_opener: StreamOpener = stream_opener or self._open_event_stream
        # Last PTZ move per device: Dahua's ``stop`` must repeat the code of the move being stopped.
        self._last_ptz: Dict[str, str] = {}

    # ------------------------------------------------------------------ catalogue
    def info(self) -> BrandInfo:
        return BrandInfo(
            id=BRAND_ID,
            name="Dahua / IMOU / Amcrest",
            vendor="Zhejiang Dahua Technology",
            description="Caméras IP et enregistreurs NVR/DVR/XVR Dahua (et marques dérivées IMOU, Amcrest, Lorex) via l'API HTTP locale.",
            protocols=[PROTOCOL],
            categories=["camera", "nvr"],
            methods=[
                PairingMethod(
                    id=METHOD_IP,
                    title="Adresse IP et identifiants",
                    description="Connexion directe à la caméra ou à l'enregistreur sur le réseau local.",
                    fields=[
                        FormField(name="host", label="Adresse IP / hôte", type="text", placeholder="192.168.1.108"),
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
            docs_url="https://www.dahuasecurity.com/support/downloadCenter",
            color="#D3202F",
        )

    # ------------------------------------------------------------------ pairing
    async def pair(self, method_id: str, payload: Dict[str, Any], ctx: AdapterContext) -> PairResult:
        self.method(method_id)
        require(payload, "host", "username", "password")
        session = HostSession.from_payload(payload)
        custom_name = str(payload.get("name") or "").strip()
        async with ctx.http() as client:
            api = DahuaClient(client, session, ctx.logger)
            info = await self._device_info(api)
            channels = await self._channels(api)
            if info.is_recorder or len(channels) > 1:
                devices = await self._pair_recorder(api, info, channels, custom_name)
                kind = f"enregistreur ({len(devices) - 1} canaux)"
            else:
                devices = [await self._pair_camera(api, info, channels[0], custom_name)]
                kind = "caméra"
        logger.info("dahua: paired %s (%s) as %s", info.device_type, info.serial, kind)
        return PairResult(devices=devices, message=f"{info.device_type or 'Dahua'} — {kind} ajoutée")

    async def _device_info(self, api: DahuaClient) -> DeviceInfo:
        """Identity from ``magicBox.cgi`` (device type + serial are mandatory, the rest is best effort)."""
        device_type = (await api.get_kv(PATH_MAGICBOX, {"action": "getDeviceType"}, "getDeviceType", "type"))["type"]
        serial = (await api.get_kv(PATH_MAGICBOX, {"action": "getSerialNo"}, "getSerialNo", "sn"))["sn"]
        info = DeviceInfo(device_type=device_type, serial=serial)
        for action, key, attr in (
            ("getSoftwareVersion", "version", "firmware"),
            ("getMachineName", "name", "name"),
            ("getVendor", "vendor", "vendor"),
        ):
            text = await api.probe(PATH_MAGICBOX, {"action": action})
            if text:
                setattr(info, attr, parse_kv(text).get(key, ""))
        text = await api.probe(PATH_MAGICBOX, {"action": "getSystemInfo"})
        if text:
            system = parse_kv(text)
            info.hardware_version = system.get("hardwareVersion", "")
            if not info.device_type:
                info.device_type = system.get("deviceType", "")
        return info

    async def _channels(self, api: DahuaClient) -> List[ChannelInfo]:
        """Channels from the ``ChannelTitle`` table (0-based on the wire -> 1-based here); at least one."""
        titles: Dict[int, str] = {}
        text = await api.probe(PATH_CONFIG, {"action": "getConfig", "name": "ChannelTitle"})
        if text:
            titles = parse_channel_titles(text)
        if not titles:
            titles = {0: ""}
        return [ChannelInfo(channel=index + 1, name=name) for index, name in sorted(titles.items())]

    async def _camera_states(self, api: DahuaClient) -> Dict[int, bool]:
        """Recorder channel connection states (best effort, empty when unsupported)."""
        try:
            text = await api.probe(PATH_CAMERA_STATE, {"uniqueChannels[0]": -1})
        except AdapterError:
            return {}
        return parse_camera_states(text) if text else {}

    async def _supports_ptz(self, api: DahuaClient, channel: int) -> bool:
        """True when ``ptz.cgi?action=getStatus`` answers 200 with ``status.`` lines for the channel."""
        try:
            text = await api.probe(PATH_PTZ, {"action": "getStatus", "channel": channel})
        except AdapterError:
            return False
        return bool(text) and "status." in text

    async def _coaxial_status(self, api: DahuaClient, channel: int) -> Dict[str, bool]:
        """White light / speaker states from ``coaxialControlIO.cgi?action=getStatus`` (empty when unsupported)."""
        try:
            text = await api.probe(PATH_COAXIAL, {"action": "getStatus", "channel": channel - 1})
        except AdapterError:
            return {}
        if not text:
            return {}
        status: Dict[str, bool] = {}
        for key, value in parse_kv(text).items():
            code = COAXIAL_STATUS_KEYS.get(key)
            if code is not None:
                status[code] = value.strip().lower() == "on"
        return status

    async def _pair_camera(self, api: DahuaClient, info: DeviceInfo, channel: ChannelInfo, custom_name: str) -> DeviceDraft:
        session = api.session
        ptz = await self._supports_ptz(api, channel.channel)
        coaxial = await self._coaxial_status(api, channel.channel)
        config: Dict[str, Any] = {**session.config(), "channel": channel.channel, "device_type": info.device_type}
        if info.hardware_version:
            config["hardware_version"] = info.hardware_version
        return DeviceDraft(
            external_id=info.serial,
            name=custom_name or info.name or channel.name or info.device_type or "Caméra Dahua",
            category="camera",
            protocol=PROTOCOL,
            model=info.device_type or None,
            manufacturer=info.manufacturer,
            firmware=info.firmware or None,
            capabilities=camera_caps(ptz=ptz, siren="siren" in coaxial, light="light" in coaxial),
            state={"motion": False, **coaxial, **self._stream_state(session, channel.channel)},
            config=config,
            credentials=session.credentials(),
            icon="videocam",
        )

    async def _pair_recorder(self, api: DahuaClient, info: DeviceInfo, channels: List[ChannelInfo], custom_name: str) -> List[DeviceDraft]:
        session = api.session
        states = await self._camera_states(api)
        parent = DeviceDraft(
            external_id=info.serial,
            name=custom_name or info.name or info.device_type or "Enregistreur Dahua",
            category="nvr",
            protocol=PROTOCOL,
            model=info.device_type or None,
            manufacturer=info.manufacturer,
            firmware=info.firmware or None,
            capabilities=[cap("child_count", "int", False)],
            state={"child_count": len(channels)},
            config={**session.config(), "device_type": info.device_type, "channel_count": len(channels),
                    "channels": [c.channel for c in channels]},
            credentials=session.credentials(),
            icon="dns",
        )
        drafts = [parent]
        for index, channel in enumerate(channels):
            ptz = await self._supports_ptz(api, channel.channel) if index < MAX_PTZ_PROBES else False
            coaxial = await self._coaxial_status(api, channel.channel) if index < MAX_PTZ_PROBES else {}
            drafts.append(DeviceDraft(
                external_id=f"{info.serial}:ch{channel.channel}",
                name=channel.name or f"Canal {channel.channel}",
                category="camera",
                protocol=PROTOCOL,
                manufacturer=info.manufacturer,
                capabilities=camera_caps(ptz=ptz, siren="siren" in coaxial, light="light" in coaxial),
                state={"motion": False, **coaxial, **self._stream_state(session, channel.channel)},
                config={"channel": channel.channel},
                parent_external_id=info.serial,
                icon="videocam",
                online=states.get(channel.channel, channel.online),
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
            api = DahuaClient(client, session, ctx.logger)
            # Reachability + authentication check; raises unreachable/auth_failed when the host is down.
            await api.get_kv(PATH_MAGICBOX, {"action": "getDeviceType"}, "getDeviceType", "type")
            if device.category == "nvr":
                count = _as_int(device.cfg("channel_count"), len(device.cfg("channels") or []))
                return DeviceState(online=True, state={"child_count": count})
            channel = _channel_of(device)
            online = True
            if device.parent_external_id:
                online = (await self._camera_states(api)).get(channel, True)
            state: Dict[str, Any] = {"motion": bool(device.state.get("motion", False)), **self._stream_state(session, channel)}
            for code in ("recording", "siren", "light"):
                if code in device.state:
                    state[code] = device.state[code]
            codes = {c.get("code") for c in device.capabilities or []}
            if codes & {"siren", "light"}:
                state.update(await self._coaxial_status(api, channel))
        return DeviceState(online=online, state=state)

    # ------------------------------------------------------------------ commands
    async def send_command(self, device: DeviceRef, code: str, value: Any, ctx: AdapterContext) -> Dict[str, Any]:
        if device.category == "nvr":
            raise AdapterError("Recorders do not accept commands; control the channel devices instead", "unsupported")
        if code not in ("ptz", "siren", "light"):
            raise AdapterError(f"Command '{code}' is not supported by this Dahua device", "unsupported")
        session = HostSession.from_device(device)
        async with ctx.http() as client:
            api = DahuaClient(client, session, ctx.logger)
            if code == "ptz":
                return await self._ptz(api, device, str(value))
            return await self._coaxial(api, device, code, _as_bool(value))

    async def _ptz(self, api: DahuaClient, device: DeviceRef, direction: str) -> Dict[str, Any]:
        channel = _channel_of(device)
        if direction == "stop":
            action, ptz_code = "stop", self._last_ptz.get(device.external_id, "Up")
        else:
            ptz_code = PTZ_CODES.get(direction, "")
            if not ptz_code:
                raise AdapterError(f"Unknown PTZ direction '{direction}'", "invalid_input")
            action = "start"
        params = {"action": action, "channel": channel, "code": ptz_code, "arg1": 0, "arg2": 1, "arg3": 0}
        response = await api.request("GET", PATH_PTZ, params)
        if response.status_code in (400, 404):
            raise AdapterError("This channel does not support PTZ", "unsupported")
        api.check_command(response, "PTZ")
        if action == "start":
            self._last_ptz[device.external_id] = ptz_code
        else:
            self._last_ptz.pop(device.external_id, None)
        return {}

    async def _coaxial(self, api: DahuaClient, device: DeviceRef, code: str, on: bool) -> Dict[str, Any]:
        channel = _channel_of(device)
        params = {
            "action": "control", "channel": channel - 1,
            "info[0].Type": COAXIAL_TYPES[code], "info[0].IO": 1 if on else 0,
        }
        response = await api.request("GET", PATH_COAXIAL, params)
        if response.status_code in (400, 404) or (response.status_code == 200 and is_error_body(response.text)):
            raise AdapterError(f"This device has no controllable {code}", "unsupported")
        api.check_command(response, f"{code} control")
        return {code: on}

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
            api = DahuaClient(client, session, ctx.logger)
            response = api.ensure_ok(await api.request("GET", PATH_SNAPSHOT, {"channel": channel}), "snapshot")
        content = response.content or b""
        if not content.startswith(b"\xff\xd8") and "image" not in response.headers.get("content-type", ""):
            raise AdapterError("Device did not return a JPEG snapshot", "invalid_input")
        return content

    # ------------------------------------------------------------------ push (eventManager attach)
    async def subscribe(self, devices: List[DeviceRef], ctx: AdapterContext) -> Optional[Unsubscribe]:
        groups = group_by_host(devices)
        if not groups:
            return None
        tasks = [asyncio.create_task(self._event_loop(group, ctx), name=f"dahua-events-{group.session.host}") for group in groups]

        async def _unsubscribe() -> None:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        return _unsubscribe

    @staticmethod
    def event_params() -> Dict[str, Any]:
        """Query parameters of the eventManager attach request."""
        return {"action": "attach", "codes": "[" + ",".join(EVENT_CODES) + "]", "heartbeat": HEARTBEAT_SECONDS}

    async def _open_event_stream(self, session: HostSession, ctx: AdapterContext) -> AsyncIterator[bytes]:
        """Default stream opener: long-lived GET on eventManager (read timeout bounded by the heartbeat)."""
        timeout = httpx.Timeout(ctx.timeout, read=HEARTBEAT_SECONDS * 6)
        async with ctx.http(timeout=timeout) as client:
            api = DahuaClient(client, session, ctx.logger)
            async for chunk in api.stream_bytes(PATH_EVENTS, self.event_params(), "eventManager"):
                yield chunk

    async def _event_loop(self, group: HostGroup, ctx: AdapterContext) -> None:
        """Keep one event stream open per host, reconnecting with backoff."""
        delay = RECONNECT_MIN_DELAY
        failures = 0
        while True:
            connected = False
            try:
                parser = EventStreamParser()
                async for chunk in self._stream_opener(group.session, ctx):
                    if not connected:
                        connected = True
                        if failures >= OFFLINE_AFTER_FAILURES:
                            await self._emit_online(group, ctx, True)
                        failures, delay = 0, RECONNECT_MIN_DELAY
                    for event in parser.feed(chunk):
                        await self._handle_event(event, group, ctx)
                logger.info("dahua: event stream from %s ended, reconnecting", group.session.host)
            except asyncio.CancelledError:
                raise
            except AdapterError as exc:
                logger.warning("dahua: event stream %s: %s (%s)", group.session.host, exc.message, exc.code)
                if exc.code == "auth_failed":
                    delay = AUTH_FAILURE_DELAY
            except Exception:  # pylint: disable=broad-except
                logger.exception("dahua: event stream %s crashed", group.session.host)
            failures += 1
            if failures == OFFLINE_AFTER_FAILURES:
                await self._emit_online(group, ctx, False)
            await asyncio.sleep(delay)
            delay = min(delay * 2, RECONNECT_MAX_DELAY)

    async def _emit_online(self, group: HostGroup, ctx: AdapterContext, online: bool) -> None:
        for external_id in group.external_ids:
            await ctx.emit("state", external_id, {"state": {}, "online": online})

    async def process_event_stream(self, chunks: AsyncIterator[bytes], devices: List[DeviceRef], ctx: AdapterContext) -> int:
        """Feed an event stream byte iterator for ``devices`` (testing hook / one-shot consumer). Returns handled events."""
        groups = group_by_host(devices)
        if not groups:
            return 0
        group = groups[0]
        parser = EventStreamParser()
        handled = 0
        async for chunk in chunks:
            for event in parser.feed(chunk):
                handled += 1 if await self._handle_event(event, group, ctx) else 0
        return handled

    async def _handle_event(self, event: DahuaEvent, group: HostGroup, ctx: AdapterContext) -> bool:
        """Translate one event into hub emits. Returns False for ignored/heartbeat events."""
        if event.is_heartbeat:
            return False
        target = group.target_for(event)
        if target is None:
            logger.debug("dahua: %s event on unknown channel %s of %s", event.code, event.channel, group.session.host)
            return False
        if event.action in ("Start", "Stop") and not group.changed(target, event.code, event.action):
            return False
        if event.code in MOTION_CODES and event.action in ("Start", "Stop"):
            await ctx.emit("state", target, {"state": {"motion": event.active}, "online": True})
        else:
            await ctx.emit("state", target, {"state": {}, "online": True})
        payload: Dict[str, Any] = {"type": event.code, "action": event.action, "channel": event.channel}
        if event.data:
            try:
                payload["data"] = json.loads(event.data)
            except ValueError:
                payload["data"] = event.data
        await ctx.emit("event", target, payload)
        return True


registry.register(DahuaAdapter())
