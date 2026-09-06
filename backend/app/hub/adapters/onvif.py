"""ONVIF adapter: generic IP cameras (Profile S/T) over hand-written SOAP 1.2 with WS-Security.

Works with any ONVIF-compliant camera (Reolink, Uniview, TP-Link Tapo/VIGI, Axis, Amcrest, Foscam,
Hikvision/Dahua as a fallback when their native adapters are not applicable...). No ``zeep``/``onvif``
dependency: the handful of operations the hub needs are written by hand and parsed with ElementTree,
ignoring XML namespaces.

* Device service ``http://host:port/onvif/device_service``
  - ``GetSystemDateAndTime`` (no auth) -> reachability check + clock offset for WS-Security ``Created``
  - ``GetDeviceInformation``           -> manufacturer, model, firmware, serial number
  - ``GetCapabilities`` / ``GetServices`` -> Media and PTZ service addresses (XAddr)
* Media service: ``GetProfiles``, ``GetStreamUri`` (RTP-Unicast over RTSP), ``GetSnapshotUri``
* PTZ service:   ``ContinuousMove`` + ``Stop``

One ``camera`` device per host; external id = serial number (or the host when the camera hides it).
Credentials live on the device; ``stream()`` injects them into the RTSP URL for the player.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
import time
import xml.etree.ElementTree as ET
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple, Union
from urllib.parse import quote, urlsplit, urlunsplit
from xml.sax.saxutils import escape

import httpx

from app.hub.adapters.base import (
    AdapterContext, AdapterError, BrandAdapter, BrandInfo, DeviceDraft, DeviceRef, DeviceState, FormField,
    PairResult, PairingMethod, StreamInfo, require,
)
from app.hub.adapters.registry import registry
from app.hub.capabilities import camera_caps

logger = logging.getLogger("safer.hub.onvif")

BRAND_ID = "onvif"
PROTOCOL = "onvif"
METHOD_IP = "ip_credentials"

DEVICE_SERVICE_PATH = "/onvif/device_service"
DEFAULT_MEDIA_PATH = "/onvif/media_service"

# Namespaces ---------------------------------------------------------------------
NS_SOAP = "http://www.w3.org/2003/05/soap-envelope"
NS_WSSE = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
NS_WSU = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
NS_DEVICE = "http://www.onvif.org/ver10/device/wsdl"
NS_MEDIA = "http://www.onvif.org/ver10/media/wsdl"
NS_MEDIA2 = "http://www.onvif.org/ver20/media/wsdl"
NS_PTZ = "http://www.onvif.org/ver20/ptz/wsdl"
NS_SCHEMA = "http://www.onvif.org/ver10/schema"
PASSWORD_DIGEST_TYPE = (
    "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest"
)
NONCE_ENCODING = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary"
PANTILT_VELOCITY_SPACE = "http://www.onvif.org/ver10/tptz/PanTiltSpaces/VelocityGenericSpace"
ZOOM_VELOCITY_SPACE = "http://www.onvif.org/ver10/tptz/ZoomSpaces/VelocityGenericSpace"

# Unit PTZ vectors per hub direction: (pan, tilt, zoom); scaled by ``OnvifAdapter.ptz_speed``
PTZ_VECTORS: Dict[str, Tuple[float, float, float]] = {
    "left": (-1.0, 0.0, 0.0), "right": (1.0, 0.0, 0.0), "up": (0.0, 1.0, 0.0), "down": (0.0, -1.0, 0.0),
    "zoom_in": (0.0, 0.0, 1.0), "zoom_out": (0.0, 0.0, -1.0), "stop": (0.0, 0.0, 0.0),
}
PTZ_MOVE_TIMEOUT = "PT1S"  # camera-side safety stop when the hub never sends Stop

AUTH_HINTS = (
    "notauthorized", "not authorized", "failedauthentication", "invalidsecurity", "unauthorized",
    "authentication failed", "invalid username", "wrong password", "invalid password", "authorization",
)
UNSUPPORTED_HINTS = ("actionnotsupported", "action not supported", "notsupported", "not supported", "notimplemented")
NOT_FOUND_HINTS = ("noprofile", "no profile", "nosuch", "not found", "notfound", "noconfig")


# =============================================================================== helpers
def _as_int(value: Any, default: int) -> int:
    """Lenient int coercion for form payloads ("80", 80, "", None)."""
    if value in (None, ""):
        return default
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _int_or_none(value: str) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _num(value: float) -> str:
    """Compact float formatting for SOAP attributes (``-0.5``, ``0``, ``1``)."""
    return "%g" % float(value)


def _hostport(host: str, port: Optional[int]) -> str:
    """``host:port`` with IPv6 brackets."""
    text = f"[{host}]" if ":" in host and not host.startswith("[") else host
    return f"{text}:{port}" if port else text


def _looks_like_xml(content: bytes) -> bool:
    return content.lstrip()[:1] == b"<"


def parse_host(value: str, port: int = 0) -> Tuple[str, int]:
    """Split ``host``, ``host:port`` or ``http://host:port/...`` into (host, port).

    A port embedded in the host string wins over ``port`` (the user typed it explicitly).
    """
    text = (value or "").strip()
    parts = urlsplit(text if "://" in text else "//" + text)
    host = parts.hostname
    if not host:
        raise AdapterError(f"Invalid camera address '{value}'", "invalid_input")
    try:
        embedded = parts.port
    except ValueError as exc:
        raise AdapterError(f"Invalid port in '{value}'", "invalid_input") from exc
    return host, embedded or port or 80


def rebase_url(url: str, host: str, port: Optional[int] = None) -> str:
    """Point ``url`` at ``host`` when the camera advertised another address (NAT, docker, wrong NIC).

    ``port`` replaces the URL port only when the host is rewritten (``None`` keeps the original port,
    which is what we want for RTSP URLs whose port mapping we do not know).
    """
    try:
        parts = urlsplit(url)
        current = parts.hostname
        current_port = parts.port
    except ValueError:
        return url
    if not current or current == host:
        return url
    new_port = port if port is not None else current_port
    netloc = _hostport(host, new_port)
    if parts.username:
        userinfo = quote(parts.username, safe="")
        if parts.password is not None:
            userinfo += ":" + quote(parts.password, safe="")
        netloc = f"{userinfo}@{netloc}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def with_credentials(url: str, username: str, password: str) -> str:
    """Insert ``user:pass@`` into a URL (RTSP players expect inline credentials)."""
    if not username:
        return url
    try:
        parts = urlsplit(url)
        hostname = parts.hostname
        port = parts.port
    except ValueError:
        return url
    if not hostname:
        return url
    userinfo = quote(username, safe="")
    if password:
        userinfo += ":" + quote(password, safe="")
    netloc = f"{userinfo}@{_hostport(hostname, port)}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


# =============================================================================== WS-Security
def password_digest(nonce: bytes, created: str, password: str) -> str:
    """``Base64(SHA1(nonce + created + password))`` as mandated by the WS-Security UsernameToken profile."""
    digest = hashlib.sha1(nonce + created.encode("utf-8") + password.encode("utf-8")).digest()
    return base64.b64encode(digest).decode("ascii")


def format_created(moment: datetime) -> str:
    """``Created`` timestamp: UTC ISO-8601 with milliseconds and a ``Z`` suffix."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    moment = moment.astimezone(timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%S") + f".{moment.microsecond // 1000:03d}Z"


def build_security_header(username: str, password: str, nonce: Optional[bytes] = None, created: Optional[str] = None) -> str:
    """WS-Security ``UsernameToken`` header with PasswordDigest (fresh nonce/timestamp unless given)."""
    nonce_bytes = nonce if nonce is not None else os.urandom(16)
    created_text = created or format_created(datetime.now(timezone.utc))
    digest = password_digest(nonce_bytes, created_text, password)
    return (
        f'<wsse:Security xmlns:wsse="{NS_WSSE}" xmlns:wsu="{NS_WSU}">'
        "<wsse:UsernameToken>"
        f"<wsse:Username>{escape(username)}</wsse:Username>"
        f'<wsse:Password Type="{PASSWORD_DIGEST_TYPE}">{digest}</wsse:Password>'
        f'<wsse:Nonce EncodingType="{NONCE_ENCODING}">{base64.b64encode(nonce_bytes).decode("ascii")}</wsse:Nonce>'
        f"<wsu:Created>{created_text}</wsu:Created>"
        "</wsse:UsernameToken>"
        "</wsse:Security>"
    )


def build_envelope(body_xml: str, security_header: Optional[str] = None) -> str:
    """SOAP 1.2 envelope with the ONVIF prefixes the request bodies use."""
    header = f"<s:Header>{security_header}</s:Header>" if security_header else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<s:Envelope xmlns:s="{NS_SOAP}" xmlns:tds="{NS_DEVICE}" xmlns:trt="{NS_MEDIA}" '
        f'xmlns:tptz="{NS_PTZ}" xmlns:tt="{NS_SCHEMA}">'
        f"{header}<s:Body>{body_xml}</s:Body></s:Envelope>"
    )


# =============================================================================== XML parsing
def strip_namespaces(root: ET.Element) -> ET.Element:
    """Rewrite ``{ns}tag`` into ``tag`` for the whole tree (ONVIF prefixes vary per vendor)."""
    for element in root.iter():
        if isinstance(element.tag, str) and element.tag.startswith("{"):
            element.tag = element.tag.split("}", 1)[1]
    return root


def parse_xml(data: Union[str, bytes]) -> ET.Element:
    """Parse XML and strip namespaces. Raises ``AdapterError(invalid_input)`` on garbage."""
    raw = data.encode("utf-8") if isinstance(data, str) else data
    try:
        root = ET.fromstring(raw.strip())
    except ET.ParseError as exc:
        raise AdapterError("The device did not answer with SOAP/XML (is this an ONVIF camera?)", "invalid_input") from exc
    return strip_namespaces(root)


def xtext(element: Optional[ET.Element], path: str, default: str = "") -> str:
    """Stripped text of the first descendant matching ``path`` (namespace-free)."""
    if element is None:
        return default
    found = element.find(path)
    if found is None or found.text is None:
        return default
    return found.text.strip()


def fault_to_error(fault: ET.Element) -> AdapterError:
    """Map a SOAP fault to an ``AdapterError`` (``ter:NotAuthorized`` -> auth_failed, ...)."""
    code = xtext(fault, "Code/Value") or xtext(fault, "faultcode")
    subcode = xtext(fault, "Code/Subcode/Value")
    sub_subcode = xtext(fault, "Code/Subcode/Subcode/Value")
    reason = xtext(fault, "Reason/Text") or xtext(fault, "faultstring")
    detail = xtext(fault, "Detail/Text") or xtext(fault, "detail")
    tokens = " ".join(part for part in (code, subcode, sub_subcode, reason, detail) if part).lower()
    description = reason or sub_subcode or subcode or code or "unknown fault"
    if any(hint in tokens for hint in AUTH_HINTS):
        return AdapterError(f"The camera rejected the credentials ({description})", "auth_failed")
    if any(hint in tokens for hint in UNSUPPORTED_HINTS):
        return AdapterError(f"The camera does not support this operation ({description})", "unsupported")
    if any(hint in tokens for hint in NOT_FOUND_HINTS):
        return AdapterError(f"ONVIF fault: {description}", "not_found")
    return AdapterError(f"ONVIF fault: {description}", "invalid_input")


def parse_soap(data: Union[str, bytes]) -> ET.Element:
    """Parse a SOAP envelope and return its ``Body``; SOAP faults raise the mapped ``AdapterError``."""
    root = parse_xml(data)
    if root.tag != "Envelope":
        raise AdapterError("The device answered with XML that is not a SOAP envelope", "invalid_input")
    body = root.find("Body")
    if body is None:
        raise AdapterError("SOAP envelope without Body", "invalid_input")
    fault = body.find("Fault")
    if fault is not None:
        raise fault_to_error(fault)
    return body


def parse_system_datetime(body: ET.Element) -> Optional[datetime]:
    """UTC time from a ``GetSystemDateAndTimeResponse`` body (None when the camera omits it)."""
    utc = body.find(".//UTCDateTime")
    if utc is None:
        return None
    try:
        return datetime(
            int(xtext(utc, "Date/Year")), int(xtext(utc, "Date/Month")), int(xtext(utc, "Date/Day")),
            int(xtext(utc, "Time/Hour")), int(xtext(utc, "Time/Minute")), int(xtext(utc, "Time/Second")),
            tzinfo=timezone.utc,
        )
    except (TypeError, ValueError):
        return None


# =============================================================================== session + client
@dataclass
class OnvifSession:
    """Connection parameters for one camera (built from the pairing form or a ``DeviceRef``)."""

    host: str
    port: int = 80
    username: str = ""
    password: str = ""
    clock_offset: float = 0.0  # seconds to add to our clock so ``Created`` matches the camera's clock
    media_xaddr: Optional[str] = None
    ptz_xaddr: Optional[str] = None

    @property
    def key(self) -> str:
        """Cache key for per-camera data."""
        return _hostport(self.host, self.port)

    @property
    def base_url(self) -> str:
        """``http://host:port``."""
        return f"http://{_hostport(self.host, self.port)}"

    @property
    def device_url(self) -> str:
        """Device service endpoint."""
        return self.base_url + DEVICE_SERVICE_PATH

    @property
    def media_url(self) -> str:
        """Media service endpoint (advertised XAddr or the conventional path)."""
        return self.media_xaddr or self.base_url + DEFAULT_MEDIA_PATH

    def security_header(self) -> Optional[str]:
        """Fresh WS-Security header (None when no username is configured)."""
        if not self.username:
            return None
        created = format_created(datetime.now(timezone.utc) + timedelta(seconds=self.clock_offset))
        return build_security_header(self.username, self.password, created=created)

    def rebase(self, url: str, http: bool = False) -> str:
        """Point an advertised URL at the configured host (HTTP URLs also take the configured port)."""
        return rebase_url(url, self.host, self.port if http else None)


class OnvifClient:
    """Hand-written ONVIF operations on top of an ``httpx.AsyncClient``."""

    def __init__(self, session: OnvifSession, http: httpx.AsyncClient):
        self.session = session
        self.http = http

    # ------------------------------------------------------------------ transport
    async def call(self, url: str, body_xml: str, action: str, auth: bool = True) -> ET.Element:
        """POST one SOAP operation and return the response ``Body`` (faults/HTTP errors mapped)."""
        envelope = build_envelope(body_xml, self.session.security_header() if auth else None)
        headers = {"Content-Type": f'application/soap+xml; charset=utf-8; action="{action}"'}
        try:
            response = await self.http.post(url, content=envelope.encode("utf-8"), headers=headers)
        except httpx.TimeoutException as exc:
            raise AdapterError(f"Camera {self.session.host} did not answer in time", "unreachable") from exc
        except httpx.HTTPError as exc:
            raise AdapterError(f"Cannot reach camera {self.session.host}: {exc}", "unreachable") from exc
        return self._parse_response(response, url)

    def _parse_response(self, response: httpx.Response, url: str) -> ET.Element:
        status = response.status_code
        if status == 401:
            raise AdapterError("The camera rejected the credentials (HTTP 401)", "auth_failed")
        content = response.content or b""
        if not _looks_like_xml(content):
            if status == 404:
                raise AdapterError(f"No ONVIF service at {url} (HTTP 404)", "invalid_input")
            if status >= 500:
                raise AdapterError(f"Camera error HTTP {status} on {url}", "unreachable")
            raise AdapterError(
                f"The device did not answer with SOAP (HTTP {status}) - is this an ONVIF camera?", "invalid_input"
            )
        body = parse_soap(content)
        if status >= 400:
            raise AdapterError(f"ONVIF request failed (HTTP {status})", "invalid_input")
        return body

    # ------------------------------------------------------------------ device service
    async def get_system_date_and_time(self) -> Optional[datetime]:
        """``GetSystemDateAndTime`` (unauthenticated on virtually every camera)."""
        body = await self.call(
            self.session.device_url, "<tds:GetSystemDateAndTime/>", f"{NS_DEVICE}/GetSystemDateAndTime", auth=False
        )
        return parse_system_datetime(body)

    async def sync_clock(self) -> float:
        """Measure the camera clock offset and store it on the session (WS-Security tolerates ~5 min)."""
        camera_time = await self.get_system_date_and_time()
        offset = 0.0 if camera_time is None else (camera_time - datetime.now(timezone.utc)).total_seconds()
        self.session.clock_offset = offset
        return offset

    async def get_device_information(self) -> Dict[str, str]:
        """Manufacturer / model / firmware / serial / hardware id."""
        body = await self.call(self.session.device_url, "<tds:GetDeviceInformation/>", f"{NS_DEVICE}/GetDeviceInformation")
        response = body.find("GetDeviceInformationResponse")
        scope = response if response is not None else body
        return {
            "manufacturer": xtext(scope, "Manufacturer"),
            "model": xtext(scope, "Model"),
            "firmware": xtext(scope, "FirmwareVersion"),
            "serial": xtext(scope, "SerialNumber"),
            "hardware_id": xtext(scope, "HardwareId"),
        }

    async def get_service_addresses(self) -> Tuple[Optional[str], Optional[str]]:
        """(media XAddr, PTZ XAddr) via ``GetCapabilities``, falling back to ``GetServices``."""
        media: Optional[str] = None
        ptz: Optional[str] = None
        try:
            body = await self.call(
                self.session.device_url,
                "<tds:GetCapabilities><tds:Category>All</tds:Category></tds:GetCapabilities>",
                f"{NS_DEVICE}/GetCapabilities",
            )
            capabilities = body.find(".//Capabilities")
            media = xtext(capabilities, "Media/XAddr") or None
            ptz = xtext(capabilities, "PTZ/XAddr") or None
        except AdapterError as exc:
            if exc.code in ("unreachable", "auth_failed"):
                raise
            logger.debug("GetCapabilities failed on %s (%s); trying GetServices", self.session.host, exc.message)
        if media is None:
            try:
                body = await self.call(
                    self.session.device_url,
                    "<tds:GetServices><tds:IncludeCapability>false</tds:IncludeCapability></tds:GetServices>",
                    f"{NS_DEVICE}/GetServices",
                )
                for service in body.iter("Service"):
                    namespace = xtext(service, "Namespace")
                    xaddr = xtext(service, "XAddr")
                    if not xaddr:
                        continue
                    if namespace == NS_MEDIA and media is None:
                        media = xaddr
                    elif namespace == NS_PTZ and ptz is None:
                        ptz = xaddr
            except AdapterError as exc:
                if exc.code in ("unreachable", "auth_failed"):
                    raise
                logger.debug("GetServices failed on %s (%s); using default paths", self.session.host, exc.message)
        return (
            self.session.rebase(media, http=True) if media else None,
            self.session.rebase(ptz, http=True) if ptz else None,
        )

    # ------------------------------------------------------------------ media service
    async def get_profiles(self) -> List[Dict[str, Any]]:
        """Media profiles: ``[{token, name, width, height, encoding}]`` in camera order."""
        body = await self.call(self.session.media_url, "<trt:GetProfiles/>", f"{NS_MEDIA}/GetProfiles")
        profiles: List[Dict[str, Any]] = []
        for element in body.iter("Profiles"):
            token = element.get("token") or xtext(element, "token")
            if not token:
                continue
            encoder = element.find("VideoEncoderConfiguration")
            profiles.append({
                "token": token,
                "name": xtext(element, "Name") or token,
                "width": _int_or_none(xtext(encoder, "Resolution/Width")),
                "height": _int_or_none(xtext(encoder, "Resolution/Height")),
                "encoding": xtext(encoder, "Encoding") or None,
            })
        return profiles

    async def get_stream_uri(self, profile_token: str) -> str:
        """RTSP URI (RTP-Unicast) for a profile."""
        body = await self.call(
            self.session.media_url,
            "<trt:GetStreamUri>"
            "<trt:StreamSetup><tt:Stream>RTP-Unicast</tt:Stream>"
            "<tt:Transport><tt:Protocol>RTSP</tt:Protocol></tt:Transport></trt:StreamSetup>"
            f"<trt:ProfileToken>{escape(profile_token)}</trt:ProfileToken>"
            "</trt:GetStreamUri>",
            f"{NS_MEDIA}/GetStreamUri",
        )
        uri = xtext(body, ".//MediaUri/Uri")
        if not uri:
            raise AdapterError(f"The camera returned no stream URI for profile '{profile_token}'", "not_found")
        return uri

    async def get_snapshot_uri(self, profile_token: str) -> Optional[str]:
        """JPEG snapshot URI for a profile (None when the camera returns an empty one)."""
        body = await self.call(
            self.session.media_url,
            f"<trt:GetSnapshotUri><trt:ProfileToken>{escape(profile_token)}</trt:ProfileToken></trt:GetSnapshotUri>",
            f"{NS_MEDIA}/GetSnapshotUri",
        )
        return xtext(body, ".//MediaUri/Uri") or None

    # ------------------------------------------------------------------ PTZ service
    async def continuous_move(self, profile_token: str, pan: float, tilt: float, zoom: float, timeout: str = PTZ_MOVE_TIMEOUT) -> None:
        """``ContinuousMove`` with normalised velocities (-1..1)."""
        if not self.session.ptz_xaddr:
            raise AdapterError("This camera has no PTZ service", "unsupported")
        await self.call(
            self.session.ptz_xaddr,
            "<tptz:ContinuousMove>"
            f"<tptz:ProfileToken>{escape(profile_token)}</tptz:ProfileToken>"
            "<tptz:Velocity>"
            f'<tt:PanTilt x="{_num(pan)}" y="{_num(tilt)}" space="{PANTILT_VELOCITY_SPACE}"/>'
            f'<tt:Zoom x="{_num(zoom)}" space="{ZOOM_VELOCITY_SPACE}"/>'
            "</tptz:Velocity>"
            f"<tptz:Timeout>{timeout}</tptz:Timeout>"
            "</tptz:ContinuousMove>",
            f"{NS_PTZ}/ContinuousMove",
        )

    async def stop(self, profile_token: str) -> None:
        """``Stop`` pan/tilt and zoom."""
        if not self.session.ptz_xaddr:
            raise AdapterError("This camera has no PTZ service", "unsupported")
        await self.call(
            self.session.ptz_xaddr,
            "<tptz:Stop>"
            f"<tptz:ProfileToken>{escape(profile_token)}</tptz:ProfileToken>"
            "<tptz:PanTilt>true</tptz:PanTilt><tptz:Zoom>true</tptz:Zoom>"
            "</tptz:Stop>",
            f"{NS_PTZ}/Stop",
        )


# =============================================================================== adapter
class OnvifAdapter(BrandAdapter):
    """Generic ONVIF camera adapter (one camera device per host)."""

    brand_id = BRAND_ID

    def __init__(self, ptz_speed: float = 0.5, ptz_step_seconds: float = 0.6, clock_cache_ttl: float = 3600.0):
        self.ptz_speed = ptz_speed
        self.ptz_step_seconds = ptz_step_seconds  # how long a PTZ nudge moves before the hub sends Stop
        self.clock_cache_ttl = clock_cache_ttl
        self._clock_offsets: Dict[str, Tuple[float, float]] = {}  # host:port -> (offset seconds, measured at)

    def info(self) -> BrandInfo:
        return BrandInfo(
            id=BRAND_ID,
            name="Caméra ONVIF",
            vendor="ONVIF",
            description="Caméras IP compatibles ONVIF (Reolink, Uniview, TP-Link Tapo/VIGI, Axis, Hikvision, Dahua...).",
            protocols=[PROTOCOL],
            categories=["camera"],
            methods=[
                PairingMethod(
                    id=METHOD_IP,
                    title="Adresse IP et identifiants",
                    description="Connecte une caméra ONVIF par son adresse IP (Profile S) et le compte ONVIF de la caméra.",
                    fields=[
                        FormField(name="host", label="Adresse IP / hôte", type="text", placeholder="192.168.1.20"),
                        FormField(name="port", label="Port ONVIF", type="number", required=False, default=80,
                                  help="80 sur la plupart des caméras (8000 Reolink, 2020 Tapo, 8899 sur certains modèles)."),
                        FormField(name="username", label="Utilisateur", type="text", placeholder="admin"),
                        FormField(name="password", label="Mot de passe", type="password"),
                        FormField(name="name", label="Nom", type="text", required=False, placeholder="Caméra entrée"),
                    ],
                    icon="videocam",
                )
            ],
            icon="videocam",
            docs_url="https://www.onvif.org/",
            color="#0EA5E9",
        )

    # ------------------------------------------------------------------ sessions
    @staticmethod
    def session_from_payload(payload: Dict[str, Any]) -> OnvifSession:
        """Session from the pairing form."""
        require(payload, "host", "username", "password")
        host, port = parse_host(str(payload["host"]), _as_int(payload.get("port"), 0))
        return OnvifSession(host=host, port=port, username=str(payload["username"]).strip(), password=str(payload["password"]))

    @staticmethod
    def session_from_device(device: DeviceRef) -> OnvifSession:
        """Session from a paired device (config + decrypted credentials)."""
        host = device.cfg("host")
        if not host:
            raise AdapterError("This camera has no host configured", "invalid_input")
        return OnvifSession(
            host=str(host),
            port=_as_int(device.cfg("port"), 80),
            username=str(device.cred("username") or ""),
            password=str(device.cred("password") or ""),
            media_xaddr=device.cfg("media_xaddr") or None,
            ptz_xaddr=device.cfg("ptz_xaddr") or None,
        )

    @asynccontextmanager
    async def client(self, session: OnvifSession, ctx: AdapterContext, sync_clock: bool = True) -> AsyncIterator[OnvifClient]:
        """Open an HTTP client for ``session`` (clock offset measured once per camera and cached)."""
        async with ctx.http() as http:
            onvif = OnvifClient(session, http)
            if sync_clock and session.username:
                session.clock_offset = await self._clock_offset(onvif)
            yield onvif

    async def _clock_offset(self, onvif: OnvifClient) -> float:
        key = onvif.session.key
        now = time.monotonic()
        cached = self._clock_offsets.get(key)
        if cached is not None and now - cached[1] < self.clock_cache_ttl:
            return cached[0]
        try:
            offset = await onvif.sync_clock()
        except AdapterError as exc:
            if exc.code in ("unreachable", "invalid_input"):
                raise
            logger.debug("GetSystemDateAndTime refused on %s (%s); assuming clocks are in sync", key, exc.message)
            offset = 0.0
        if abs(offset) > 30:
            logger.info("Camera %s clock is %.0fs off ours; compensating in WS-Security timestamps", key, offset)
        self._clock_offsets[key] = (offset, now)
        return offset

    # ------------------------------------------------------------------ pairing
    async def pair(self, method_id: str, payload: Dict[str, Any], ctx: AdapterContext) -> PairResult:
        self.method(method_id)
        session = self.session_from_payload(payload)
        async with self.client(session, ctx) as onvif:
            info = await onvif.get_device_information()
            media_xaddr, ptz_xaddr = await onvif.get_service_addresses()
            session.media_xaddr = media_xaddr
            session.ptz_xaddr = ptz_xaddr
            profiles = await onvif.get_profiles()
            if not profiles:
                raise AdapterError("The camera exposes no media profile", "not_found")
            main = profiles[0]
            sub = profiles[1] if len(profiles) > 1 else None
            stream_main = session.rebase(await onvif.get_stream_uri(main["token"]))
            stream_sub = session.rebase(await onvif.get_stream_uri(sub["token"])) if sub else stream_main
            snapshot: Optional[str] = None
            try:
                snapshot = await onvif.get_snapshot_uri(main["token"])
            except AdapterError as exc:
                if exc.code in ("unreachable", "auth_failed"):
                    raise
                logger.info("Camera %s has no snapshot URI: %s", session.host, exc.message)
            if snapshot:
                snapshot = session.rebase(snapshot, http=True)

        serial = info.get("serial") or ""
        external_id = serial or session.host
        vendor_name = " ".join(part for part in (info.get("manufacturer"), info.get("model")) if part)
        name = (payload.get("name") or "").strip() or vendor_name or f"Caméra {session.host}"
        state: Dict[str, Any] = {"stream_main": stream_main, "stream_sub": stream_sub}
        if snapshot:
            state["snapshot"] = snapshot
        config: Dict[str, Any] = {
            "host": session.host,
            "port": session.port,
            "profile_main": main["token"],
            "profile_sub": (sub or main)["token"],
            "media_xaddr": session.media_url,
            "ptz_xaddr": ptz_xaddr,
        }
        if main.get("width") and main.get("height"):
            config["resolution_main"] = f"{main['width']}x{main['height']}"
        if sub and sub.get("width") and sub.get("height"):
            config["resolution_sub"] = f"{sub['width']}x{sub['height']}"
        if info.get("hardware_id"):
            config["hardware_id"] = info["hardware_id"]
        draft = DeviceDraft(
            external_id=external_id,
            name=name,
            category="camera",
            protocol=PROTOCOL,
            model=info.get("model") or None,
            manufacturer=info.get("manufacturer") or None,
            firmware=info.get("firmware") or None,
            capabilities=camera_caps(ptz=bool(ptz_xaddr)),
            state=state,
            config=config,
            credentials={"username": session.username, "password": session.password},
            icon="videocam",
        )
        return PairResult(devices=[draft], message=f"Caméra {name} ajoutée")

    # ------------------------------------------------------------------ runtime
    async def refresh(self, device: DeviceRef, ctx: AdapterContext) -> DeviceState:
        session = self.session_from_device(device)
        async with ctx.http() as http:
            onvif = OnvifClient(session, http)
            try:
                camera_time = await onvif.get_system_date_and_time()
            except AdapterError as exc:
                if exc.code == "unreachable":
                    logger.info("ONVIF camera %s unreachable: %s", session.key, exc.message)
                    return DeviceState(online=False, state={})
                raise
        if camera_time is not None:
            offset = (camera_time - datetime.now(timezone.utc)).total_seconds()
            self._clock_offsets[session.key] = (offset, time.monotonic())
        return DeviceState(online=True, state={})

    async def send_command(self, device: DeviceRef, code: str, value: Any, ctx: AdapterContext) -> Dict[str, Any]:
        if code != "ptz":
            raise AdapterError(f"ONVIF cameras do not accept '{code}' commands", "unsupported")
        session = self.session_from_device(device)
        if not session.ptz_xaddr:
            raise AdapterError("This camera has no PTZ service", "unsupported")
        direction = str(value)
        if direction not in PTZ_VECTORS:
            raise AdapterError(f"Unknown PTZ direction '{value}'", "invalid_input")
        token = str(device.cfg("profile_main") or "")
        pan, tilt, zoom = PTZ_VECTORS[direction]
        async with self.client(session, ctx) as onvif:
            if direction == "stop":
                await onvif.stop(token)
            else:
                await onvif.continuous_move(token, pan * self.ptz_speed, tilt * self.ptz_speed, zoom * self.ptz_speed)
                if self.ptz_step_seconds > 0:
                    await asyncio.sleep(self.ptz_step_seconds)
                    await onvif.stop(token)
        return {}

    async def stream(self, device: DeviceRef, quality: str, ctx: AdapterContext) -> Optional[StreamInfo]:
        session = self.session_from_device(device)
        key = "stream_sub" if quality == "sub" else "stream_main"
        url = device.state.get(key) or device.state.get("stream_main")
        if not url:
            token = device.cfg("profile_sub" if quality == "sub" else "profile_main") or device.cfg("profile_main")
            if not token:
                return None
            async with self.client(session, ctx) as onvif:
                url = await onvif.get_stream_uri(str(token))
        url = session.rebase(str(url))
        return StreamInfo(
            url=with_credentials(url, session.username, session.password),
            type="rtsp",
            username=session.username or None,
            password=session.password or None,
        )

    async def snapshot(self, device: DeviceRef, ctx: AdapterContext) -> Optional[bytes]:
        session = self.session_from_device(device)
        uri = device.state.get("snapshot") or device.cfg("snapshot_uri")
        async with ctx.http() as http:
            if not uri:
                token = device.cfg("profile_main")
                if not token:
                    return None
                onvif = OnvifClient(session, http)
                session.clock_offset = await self._clock_offset(onvif)
                uri = await onvif.get_snapshot_uri(str(token))
                if not uri:
                    return None
            uri = session.rebase(str(uri), http=True)
            return await self._fetch_image(http, uri, session)

    @staticmethod
    async def _fetch_image(http: httpx.AsyncClient, uri: str, session: OnvifSession) -> bytes:
        """GET a JPEG with Digest auth, falling back to Basic when the camera only offers that."""
        try:
            if session.username:
                response = await http.get(uri, auth=httpx.DigestAuth(session.username, session.password))
                if response.status_code == 401:
                    response = await http.get(uri, auth=httpx.BasicAuth(session.username, session.password))
            else:
                response = await http.get(uri)
        except httpx.TimeoutException as exc:
            raise AdapterError(f"Camera {session.host} did not answer in time", "unreachable") from exc
        except httpx.HTTPError as exc:
            raise AdapterError(f"Cannot reach camera {session.host}: {exc}", "unreachable") from exc
        status = response.status_code
        if status == 401:
            raise AdapterError("The camera rejected the credentials for the snapshot", "auth_failed")
        if status == 404:
            raise AdapterError("Snapshot URI not found on the camera", "not_found")
        if status >= 500:
            raise AdapterError(f"Snapshot failed (HTTP {status})", "unreachable")
        if status >= 400:
            raise AdapterError(f"Snapshot failed (HTTP {status})", "invalid_input")
        if not response.content:
            raise AdapterError("The camera returned an empty snapshot", "invalid_input")
        content_type = response.headers.get("content-type", "")
        if content_type and not content_type.startswith("image/") and not response.content.startswith(b"\xff\xd8"):
            raise AdapterError(f"The snapshot URI did not return an image ({content_type})", "invalid_input")
        return response.content


registry.register(OnvifAdapter())
