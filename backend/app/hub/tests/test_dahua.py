"""Dahua (HTTP CGI) adapter tests: digest auth, camera/NVR pairing, streams, PTZ/coaxial commands, event stream."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Union

import httpx
import pytest

from app.hub.adapters.base import AdapterContext, AdapterError, DeviceRef
from app.hub.adapters.dahua import (
    BRAND_ID, EVENT_CODES, METHOD_IP, PROTOCOL, DahuaAdapter, EventStreamParser, HostSession, group_by_host,
    is_recorder_type, parse_camera_states, parse_channel_titles, parse_event_part, parse_kv,
)
from app.hub.adapters.registry import registry

USER, PASSWORD = "admin", "Secret123"
CAM_SERIAL = "6J0A1B2PAZC3D4E"
NVR_SERIAL = "5K03F7CPAN9A1B2"

TEXT = {"content-type": "text/plain;charset=utf-8"}
JPEG = bytes.fromhex("ffd8ffe000104a46494600010100000100010000ffd9")

CAMERA_SYSTEM_INFO = "deviceType=IPC-HDW2431T-AS-S2\nhardwareVersion=1.00\nprocessor=SSC337\nserialNumber=6J0A1B2PAZC3D4E\nupdateSerial=IPC-HDW2431T-AS-S2"
PTZ_STATUS = "status.Position[0]=0.0\nstatus.Position[1]=0.0\nstatus.Position[2]=1.0\nstatus.MoveStatus=Idle\nstatus.PresetID=0\nstatus.ZoomStatus=Idle"
COAXIAL_STATUS = "status.speaker=Off\nstatus.whiteLight=On"


def text(body: str, status: int = 200) -> httpx.Response:
    """A Dahua-style ``text/plain`` answer (CRLF line endings, trailing newline)."""
    return httpx.Response(status, headers=TEXT, content=(body.replace("\n", "\r\n") + "\r\n").encode())


def error(status: int = 400) -> httpx.Response:
    return text("Error" if status == 200 else "Bad Request", status)


Handler = Union[httpx.Response, Callable[[httpx.Request], httpx.Response]]


@dataclass
class Seen:
    """Snapshot of one request as the device saw it."""

    method: str
    path: str
    params: Dict[str, str]
    raw_query: str
    headers: Dict[str, str]
    authorized: bool


def route_key(path: str, action: Optional[str] = None, **extra: Any) -> str:
    key = path
    if action:
        key += f"?action={action}"
    for name in ("name", "channel"):
        if name in extra and extra[name] is not None:
            key += f"&{name}={extra[name]}"
    return key


class FakeDahua:
    """In-memory Dahua device: verifies HTTP Digest (or Basic) auth and routes CGI actions."""

    def __init__(self, routes: Dict[str, Handler], auth: str = "digest", password: str = PASSWORD, realm: str = "Login to 6J0A1B2PAZC3D4E"):
        self.routes = routes
        self.auth = auth
        self.password = password
        self.realm = realm
        self.nonce = "0d8f2b6a4c1e9f37"
        self.requests: List[Seen] = []

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        authorized = self.authorized(request)
        params = dict(request.url.params)
        self.requests.append(Seen(
            method=request.method, path=request.url.path, params=params, raw_query=request.url.query.decode(),
            headers={k.lower(): v for k, v in request.headers.items()}, authorized=authorized,
        ))
        if not authorized:
            challenge = (
                f'Digest realm="{self.realm}", qop="auth", nonce="{self.nonce}", opaque="5ccc069c", algorithm="MD5"'
                if self.auth == "digest" else f'Basic realm="{self.realm}"'
            )
            return httpx.Response(401, headers={"WWW-Authenticate": challenge, **TEXT}, content=b"401 Unauthorized")
        handler = None
        # Most specific route first: path?action&name / path?action&channel / path?action / path
        for key in (
            route_key(request.url.path, params.get("action"), name=params.get("name"), channel=params.get("channel")),
            route_key(request.url.path, params.get("action"), name=params.get("name")),
            route_key(request.url.path, params.get("action"), channel=params.get("channel")),
            route_key(request.url.path, params.get("action")),
            request.url.path,
        ):
            handler = self.routes.get(key)
            if handler is not None:
                break
        if handler is None:
            return error(400)
        return handler(request) if callable(handler) else handler

    def authorized(self, request: httpx.Request) -> bool:
        header = request.headers.get("Authorization", "")
        if self.auth == "basic":
            return header == "Basic " + base64.b64encode(f"{USER}:{self.password}".encode()).decode()
        if not header.lower().startswith("digest "):
            return False
        params = {k: (q or u) for k, q, u in re.findall(r'(\w+)=(?:"([^"]*)"|([^,\s]+))', header[7:])}
        ha1 = hashlib.md5(f"{params.get('username')}:{self.realm}:{self.password}".encode()).hexdigest()  # noqa: S324
        ha2 = hashlib.md5(f"{request.method}:{request.url.raw_path.decode()}".encode()).hexdigest()  # noqa: S324
        if params.get("qop"):
            expected = hashlib.md5(  # noqa: S324
                f"{ha1}:{params.get('nonce')}:{params.get('nc')}:{params.get('cnonce')}:{params.get('qop')}:{ha2}".encode()
            ).hexdigest()
        else:
            expected = hashlib.md5(f"{ha1}:{params.get('nonce')}:{ha2}".encode()).hexdigest()  # noqa: S324
        return params.get("username") == USER and params.get("uri") == request.url.raw_path.decode() and params.get("response") == expected

    def sent(self, path: str, action: Optional[str] = None) -> List[Seen]:
        """Authenticated requests that reached ``path`` (optionally a given ``action``)."""
        return [r for r in self.requests if r.path == path and r.authorized and (action is None or r.params.get("action") == action)]


def camera_routes(ptz: bool = True, coaxial: bool = True, device_type: str = "IPC-HDW2431T-AS-S2") -> Dict[str, Handler]:
    routes: Dict[str, Handler] = {
        route_key("/cgi-bin/magicBox.cgi", "getDeviceType"): text(f"type={device_type}"),
        route_key("/cgi-bin/magicBox.cgi", "getSerialNo"): text(f"sn={CAM_SERIAL}"),
        route_key("/cgi-bin/magicBox.cgi", "getSoftwareVersion"): text("version=2.800.0000000.20.R,build:2020-08-14"),
        route_key("/cgi-bin/magicBox.cgi", "getMachineName"): text("name=Entrée"),
        route_key("/cgi-bin/magicBox.cgi", "getSystemInfo"): text(CAMERA_SYSTEM_INFO),
        route_key("/cgi-bin/magicBox.cgi", "getVendor"): text("vendor=Dahua"),
        route_key("/cgi-bin/configManager.cgi", "getConfig", name="ChannelTitle"): text("table.ChannelTitle[0].Name=Entrée"),
        route_key("/cgi-bin/ptz.cgi", "start"): text("OK"),
        route_key("/cgi-bin/ptz.cgi", "stop"): text("OK"),
        route_key("/cgi-bin/coaxialControlIO.cgi", "control"): text("OK") if coaxial else error(200),
        "/cgi-bin/snapshot.cgi": httpx.Response(200, headers={"content-type": "image/jpeg"}, content=JPEG),
    }
    routes[route_key("/cgi-bin/ptz.cgi", "getStatus", channel=1)] = text(PTZ_STATUS) if ptz else error(200)
    routes[route_key("/cgi-bin/coaxialControlIO.cgi", "getStatus", channel=0)] = text(COAXIAL_STATUS) if coaxial else error(400)
    return routes


def nvr_routes(device_type: str = "NVR4108HS-4KS2") -> Dict[str, Handler]:
    states = {"states": [
        {"channel": 0, "connectionState": "Connected"},
        {"channel": 1, "connectionState": "Connected"},
        {"channel": 2, "connectionState": "Unconnect"},
    ]}
    return {
        route_key("/cgi-bin/magicBox.cgi", "getDeviceType"): text(f"type={device_type}"),
        route_key("/cgi-bin/magicBox.cgi", "getSerialNo"): text(f"sn={NVR_SERIAL}"),
        route_key("/cgi-bin/magicBox.cgi", "getSoftwareVersion"): text("version=4.001.0000000.1.R,build:2021-03-05"),
        route_key("/cgi-bin/magicBox.cgi", "getMachineName"): text("name=NVR Maison"),
        route_key("/cgi-bin/magicBox.cgi", "getVendor"): text("vendor=General"),
        route_key("/cgi-bin/configManager.cgi", "getConfig", name="ChannelTitle"): text(
            "table.ChannelTitle[0].Name=Entrée\ntable.ChannelTitle[1].Name=Garage\ntable.ChannelTitle[2].Name=Jardin"
        ),
        "/cgi-bin/api/LogicDeviceManager/getCameraState": text(json.dumps(states)),
        route_key("/cgi-bin/ptz.cgi", "getStatus", channel=2): text(PTZ_STATUS),
        route_key("/cgi-bin/ptz.cgi", "start"): text("OK"),
        route_key("/cgi-bin/ptz.cgi", "stop"): text("OK"),
        route_key("/cgi-bin/coaxialControlIO.cgi", "control"): text("OK"),
        "/cgi-bin/snapshot.cgi": httpx.Response(200, headers={"content-type": "image/jpeg"}, content=JPEG),
    }


def event_part(code: str, action: str, index: int = 0, data: Optional[str] = None, boundary: str = "myboundary") -> bytes:
    body = f"Code={code};action={action};index={index}"
    if data is not None:
        body += f";data={data}"
    return f"--{boundary}\r\nContent-Type: text/plain\r\nContent-Length:{len(body)}\r\n\r\n{body}\r\n\r\n".encode()


def heartbeat_part(boundary: str = "myboundary") -> bytes:
    return f"--{boundary}\r\nContent-Type: text/plain\r\nContent-Length:9\r\n\r\nHeartbeat\r\n\r\n".encode()


class Collector:
    """Captures ``ctx.emit`` calls."""

    def __init__(self) -> None:
        self.items: List[Any] = []

    async def __call__(self, event_type: str, external_id: str, payload: Dict[str, Any]) -> None:
        self.items.append((event_type, external_id, payload))

    def states(self) -> List[Any]:
        return [(ext, payload) for kind, ext, payload in self.items if kind == "state"]

    def events(self) -> List[Any]:
        return [(ext, payload) for kind, ext, payload in self.items if kind == "event"]


def ctx_for(server: FakeDahua, emit: Optional[Collector] = None) -> AdapterContext:
    return AdapterContext(transport=server.transport(), emit=emit)


def payload(**overrides: Any) -> Dict[str, Any]:
    data = {"host": "192.168.1.108", "port": 80, "https": False, "username": USER, "password": PASSWORD, "rtsp_port": 554}
    data.update(overrides)
    return data


HOST_CFG = {"host": "192.168.1.108", "port": 80, "https": False, "rtsp_port": 554}
CREDS = {"username": USER, "password": PASSWORD}


def camera_ref(state: Optional[Dict[str, Any]] = None, capabilities: Optional[List[Dict[str, Any]]] = None, **config: Any) -> DeviceRef:
    return DeviceRef(id="d1", external_id=CAM_SERIAL, brand=BRAND_ID, protocol=PROTOCOL, category="camera",
                     config={**HOST_CFG, "channel": 1, **config}, credentials=dict(CREDS), state=state or {},
                     capabilities=capabilities or [])


def channel_ref(channel: int) -> DeviceRef:
    # As built by DeviceService.ref_for: parent host config + credentials merged into the child
    return DeviceRef(id=f"c{channel}", external_id=f"{NVR_SERIAL}:ch{channel}", brand=BRAND_ID, protocol=PROTOCOL, category="camera",
                     config={**HOST_CFG, "channel": channel}, credentials=dict(CREDS), parent_external_id=NVR_SERIAL)


def nvr_ref() -> DeviceRef:
    return DeviceRef(id="n1", external_id=NVR_SERIAL, brand=BRAND_ID, protocol=PROTOCOL, category="nvr",
                     config={**HOST_CFG, "channel_count": 3, "channels": [1, 2, 3]}, credentials=dict(CREDS))


@pytest.fixture
def adapter() -> DahuaAdapter:
    return DahuaAdapter()


# =============================================================================== catalogue / helpers
def test_registered_and_method_fields():
    registered = registry.get(BRAND_ID)
    assert isinstance(registered, DahuaAdapter)
    assert registered.supports_push is True
    info = registered.info()
    assert info.id == BRAND_ID and info.protocols == [PROTOCOL] and set(info.categories) == {"camera", "nvr"}
    method = registered.method(METHOD_IP)
    fields = {f.name: f for f in method.fields}
    assert list(fields) == ["host", "port", "https", "username", "password", "rtsp_port", "name"]
    assert fields["port"].type == "number" and fields["port"].default == 80
    assert fields["https"].type == "toggle" and fields["https"].default is False
    assert fields["password"].type == "password"
    assert fields["rtsp_port"].type == "number" and fields["rtsp_port"].default == 554
    assert fields["name"].required is False
    with pytest.raises(AdapterError) as exc:
        registered.method("cloud")
    assert exc.value.code == "invalid_input"


def test_host_session_and_urls():
    session = HostSession.from_payload({"host": " http://cam.local/ ", "port": "8443", "https": "true", "username": "u", "password": "p", "rtsp_port": ""})
    assert session.host == "cam.local" and session.base_url == "https://cam.local:8443"
    assert session.rtsp_url(3) == "rtsp://cam.local:554/cam/realmonitor?channel=3&subtype=0"
    assert session.rtsp_url(3, sub=True) == "rtsp://cam.local:554/cam/realmonitor?channel=3&subtype=1"
    assert session.snapshot_url(1) == "https://cam.local:8443/cgi-bin/snapshot.cgi?channel=1"
    assert HostSession.from_payload({"host": "h", "https": True}).port == 443
    assert HostSession.from_payload({"host": "h"}).port == 80
    with pytest.raises(AdapterError) as exc:
        HostSession.from_device(DeviceRef(id="x", external_id="x", brand=BRAND_ID, protocol=PROTOCOL, category="camera"))
    assert exc.value.code == "invalid_input"


def test_parsers():
    assert parse_kv("type=IPC-HDW2431T\r\n") == {"type": "IPC-HDW2431T"}
    assert parse_kv("version=2.800.0000000.20.R,build:2020-08-14\r\njunk\r\n\r\n") == {"version": "2.800.0000000.20.R,build:2020-08-14"}
    titles = parse_channel_titles("table.ChannelTitle[0].Name=Entrée\r\ntable.ChannelTitle[1].Name=Garage\r\n")
    assert titles == {0: "Entrée", 1: "Garage"}
    assert parse_channel_titles("Error") == {}
    assert is_recorder_type("NVR4108HS-4KS2") and is_recorder_type("DHI-XVR5108HS-I3") and is_recorder_type("dh-hcvr7208a")
    assert not is_recorder_type("IPC-HDW2431T-AS-S2") and not is_recorder_type("")
    states = parse_camera_states('{"states":[{"channel":0,"connectionState":"Connected"},{"channel":1,"connectionState":"Unconnect"}]}')
    assert states == {1: True, 2: False}
    assert parse_camera_states("Error") == {}


# =============================================================================== pairing
async def test_pair_single_camera_with_digest(adapter: DahuaAdapter):
    server = FakeDahua(camera_routes())
    result = await adapter.pair(METHOD_IP, payload(name="Caméra entrée"), ctx_for(server))
    assert len(result.devices) == 1
    cam = result.devices[0]
    assert cam.external_id == CAM_SERIAL and cam.parent_external_id is None
    assert cam.category == "camera" and cam.protocol == PROTOCOL
    assert cam.name == "Caméra entrée"
    assert cam.model == "IPC-HDW2431T-AS-S2" and cam.manufacturer == "Dahua"
    assert cam.firmware == "2.800.0000000.20.R,build:2020-08-14"
    assert cam.config == {"host": "192.168.1.108", "port": 80, "https": False, "rtsp_port": 554, "channel": 1,
                          "device_type": "IPC-HDW2431T-AS-S2", "hardware_version": "1.00"}
    assert cam.credentials == {"username": USER, "password": PASSWORD}
    codes = {c["code"] for c in cam.capabilities}
    assert codes == {"stream_main", "stream_sub", "snapshot", "motion", "recording", "ptz", "siren", "light"}
    assert cam.state["stream_main"] == "rtsp://192.168.1.108:554/cam/realmonitor?channel=1&subtype=0"
    assert cam.state["stream_sub"] == "rtsp://192.168.1.108:554/cam/realmonitor?channel=1&subtype=1"
    assert cam.state["snapshot"] == "http://192.168.1.108:80/cgi-bin/snapshot.cgi?channel=1"
    assert cam.state["motion"] is False and cam.state["light"] is True and cam.state["siren"] is False
    assert PASSWORD not in json.dumps(cam.state) and PASSWORD not in json.dumps(cam.config)
    # First request was challenged, the retry carried a valid Digest header (verified by FakeDahua)
    first, second = server.requests[0], server.requests[1]
    assert not first.authorized and "authorization" not in first.headers
    assert second.authorized and second.headers["authorization"].startswith("Digest ")
    assert server.sent("/cgi-bin/ptz.cgi", "getStatus")[0].params["channel"] == "1"  # 1-based for PTZ
    assert server.sent("/cgi-bin/coaxialControlIO.cgi", "getStatus")[0].params["channel"] == "0"  # 0-based for coaxial
    assert "caméra" in result.message


async def test_pair_camera_without_ptz_or_coaxial_uses_device_name(adapter: DahuaAdapter):
    server = FakeDahua(camera_routes(ptz=False, coaxial=False))
    result = await adapter.pair(METHOD_IP, payload(https=True, port=443), ctx_for(server))
    cam = result.devices[0]
    assert cam.name == "Entrée"
    codes = {c["code"] for c in cam.capabilities}
    assert "ptz" not in codes and "siren" not in codes and "light" not in codes
    assert cam.state["snapshot"] == "https://192.168.1.108:443/cgi-bin/snapshot.cgi?channel=1"
    assert cam.config["https"] is True and cam.config["port"] == 443


async def test_pair_nvr_with_three_channels(adapter: DahuaAdapter):
    server = FakeDahua(nvr_routes())
    result = await adapter.pair(METHOD_IP, payload(host="192.168.1.10", port=8080), ctx_for(server))
    assert [d.category for d in result.devices] == ["nvr", "camera", "camera", "camera"]
    parent, ch1, ch2, ch3 = result.devices
    assert parent.external_id == NVR_SERIAL and parent.parent_external_id is None
    assert parent.name == "NVR Maison" and parent.model == "NVR4108HS-4KS2" and parent.manufacturer == "Dahua"
    assert parent.state == {"child_count": 3}
    assert parent.capabilities == [{"code": "child_count", "type": "int", "writable": False}]
    assert parent.credentials == CREDS
    assert parent.config["channel_count"] == 3 and parent.config["channels"] == [1, 2, 3] and parent.config["host"] == "192.168.1.10"
    # ChannelTitle[0..2] -> channels 1..3
    assert [c.external_id for c in (ch1, ch2, ch3)] == [f"{NVR_SERIAL}:ch1", f"{NVR_SERIAL}:ch2", f"{NVR_SERIAL}:ch3"]
    assert [c.name for c in (ch1, ch2, ch3)] == ["Entrée", "Garage", "Jardin"]
    assert all(c.parent_external_id == NVR_SERIAL for c in (ch1, ch2, ch3))
    assert ch1.config == {"channel": 1} and ch3.config == {"channel": 3}
    assert ch1.credentials == {} and ch2.credentials == {} and ch3.credentials == {}  # children inherit through the hub
    assert "ptz" not in {c["code"] for c in ch1.capabilities} and "ptz" in {c["code"] for c in ch2.capabilities}
    assert ch1.online is True and ch2.online is True and ch3.online is False  # getCameraState: channel 2 (0-based) Unconnect
    assert ch3.state["stream_main"] == "rtsp://192.168.1.10:554/cam/realmonitor?channel=3&subtype=0"
    assert ch3.state["stream_sub"] == "rtsp://192.168.1.10:554/cam/realmonitor?channel=3&subtype=1"
    assert ch3.state["snapshot"] == "http://192.168.1.10:8080/cgi-bin/snapshot.cgi?channel=3"
    assert "3 canaux" in result.message


async def test_pair_multi_channel_ipc_becomes_recorder_and_dhi_prefix(adapter: DahuaAdapter):
    routes = camera_routes()
    routes[route_key("/cgi-bin/configManager.cgi", "getConfig", name="ChannelTitle")] = text(
        "table.ChannelTitle[0].Name=Gauche\ntable.ChannelTitle[1].Name=Droite")
    result = await adapter.pair(METHOD_IP, payload(), ctx_for(FakeDahua(routes)))
    assert [d.category for d in result.devices] == ["nvr", "camera", "camera"]
    assert [d.external_id for d in result.devices[1:]] == [f"{CAM_SERIAL}:ch1", f"{CAM_SERIAL}:ch2"]
    # DHI- prefixed recorder with a single ChannelTitle row is still a recorder
    result = await adapter.pair(METHOD_IP, payload(), ctx_for(FakeDahua(camera_routes(device_type="DHI-XVR5104HS-I3"))))
    assert [d.category for d in result.devices] == ["nvr", "camera"]
    assert result.devices[1].name == "Entrée" and result.devices[1].config == {"channel": 1}


async def test_pair_missing_fields(adapter: DahuaAdapter):
    with pytest.raises(AdapterError) as exc:
        await adapter.pair(METHOD_IP, {"host": "1.2.3.4"}, ctx_for(FakeDahua({})))
    assert exc.value.code == "invalid_input" and "username" in exc.value.message
    with pytest.raises(AdapterError) as exc:
        await adapter.pair("qr", payload(), ctx_for(FakeDahua({})))
    assert exc.value.code == "invalid_input"


async def test_pair_auth_failed(adapter: DahuaAdapter):
    server = FakeDahua(camera_routes(), password="other-password")
    with pytest.raises(AdapterError) as exc:
        await adapter.pair(METHOD_IP, payload(), ctx_for(server))
    assert exc.value.code == "auth_failed"
    # digest challenge answered, then rejected: never falls back to Basic when a Digest challenge exists
    assert all(not r.headers.get("authorization", "").startswith("Basic") for r in server.requests)
    assert any(r.headers.get("authorization", "").startswith("Digest ") for r in server.requests)
    forbidden = FakeDahua({route_key("/cgi-bin/magicBox.cgi", "getDeviceType"): httpx.Response(403, headers=TEXT, content=b"Forbidden")})
    with pytest.raises(AdapterError) as exc:
        await adapter.pair(METHOD_IP, payload(), ctx_for(forbidden))
    assert exc.value.code == "auth_failed"


async def test_pair_unreachable(adapter: DahuaAdapter):
    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(AdapterError) as exc:
        await adapter.pair(METHOD_IP, payload(), AdapterContext(transport=httpx.MockTransport(refused)))
    assert exc.value.code == "unreachable"

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(AdapterError) as exc:
        await adapter.pair(METHOD_IP, payload(), AdapterContext(transport=httpx.MockTransport(timeout)))
    assert exc.value.code == "unreachable" and "Timeout" in exc.value.message
    gateway = FakeDahua({route_key("/cgi-bin/magicBox.cgi", "getDeviceType"): httpx.Response(503, headers=TEXT, content=b"busy")})
    with pytest.raises(AdapterError) as exc:
        await adapter.pair(METHOD_IP, payload(), ctx_for(gateway))
    assert exc.value.code == "unreachable"


async def test_pair_non_dahua_answers_are_invalid_input(adapter: DahuaAdapter):
    html = FakeDahua({route_key("/cgi-bin/magicBox.cgi", "getDeviceType"): httpx.Response(
        200, headers={"content-type": "text/html"}, content=b"<html><body>router admin</body></html>")})
    with pytest.raises(AdapterError) as exc:
        await adapter.pair(METHOD_IP, payload(), ctx_for(html))
    assert exc.value.code == "invalid_input"
    wrong_key = FakeDahua({route_key("/cgi-bin/magicBox.cgi", "getDeviceType"): text("model=Foo")})
    with pytest.raises(AdapterError) as exc:
        await adapter.pair(METHOD_IP, payload(), ctx_for(wrong_key))
    assert exc.value.code == "invalid_input"
    no_serial = FakeDahua({**camera_routes(), route_key("/cgi-bin/magicBox.cgi", "getSerialNo"): text("sn=")})
    with pytest.raises(AdapterError) as exc:
        await adapter.pair(METHOD_IP, payload(), ctx_for(no_serial))
    assert exc.value.code == "invalid_input"


async def test_basic_auth_fallback(adapter: DahuaAdapter):
    server = FakeDahua(camera_routes(), auth="basic")
    result = await adapter.pair(METHOD_IP, payload(), ctx_for(server))
    assert result.devices[0].external_id == CAM_SERIAL
    auth_headers = [r.headers.get("authorization", "") for r in server.requests]
    assert auth_headers[0] == "" and auth_headers[1].startswith("Basic ")
    assert all(h.startswith("Basic ") for h in auth_headers[1:])


# =============================================================================== media
async def test_stream_urls_main_and_sub(adapter: DahuaAdapter):
    ctx = ctx_for(FakeDahua({}))
    main = await adapter.stream(camera_ref(), "main", ctx)
    sub = await adapter.stream(camera_ref(), "sub", ctx)
    assert main.type == "rtsp" and main.url == "rtsp://192.168.1.108:554/cam/realmonitor?channel=1&subtype=0"
    assert sub.type == "rtsp" and sub.url == "rtsp://192.168.1.108:554/cam/realmonitor?channel=1&subtype=1"
    assert main.username == USER and main.password == PASSWORD
    channel = await adapter.stream(channel_ref(3), "sub", ctx)
    assert channel.url == "rtsp://192.168.1.108:554/cam/realmonitor?channel=3&subtype=1"
    assert await adapter.stream(nvr_ref(), "main", ctx) is None
    # channel derived from the external id when config lacks it
    bare = DeviceRef(id="b", external_id=f"{NVR_SERIAL}:ch2", brand=BRAND_ID, protocol=PROTOCOL, category="camera",
                     config=dict(HOST_CFG), credentials=dict(CREDS), parent_external_id=NVR_SERIAL)
    assert (await adapter.stream(bare, "main", ctx)).url.endswith("channel=2&subtype=0")


async def test_snapshot_bytes(adapter: DahuaAdapter):
    server = FakeDahua(camera_routes())
    data = await adapter.snapshot(camera_ref(), ctx_for(server))
    assert data == JPEG
    assert server.sent("/cgi-bin/snapshot.cgi")[0].params == {"channel": "1"}
    nvr = FakeDahua(nvr_routes())
    assert await adapter.snapshot(channel_ref(3), ctx_for(nvr)) == JPEG
    assert nvr.sent("/cgi-bin/snapshot.cgi")[0].params == {"channel": "3"}
    assert await adapter.snapshot(nvr_ref(), ctx_for(server)) is None
    bad = FakeDahua({"/cgi-bin/snapshot.cgi": text("Error")})
    with pytest.raises(AdapterError) as exc:
        await adapter.snapshot(camera_ref(), ctx_for(bad))
    assert exc.value.code == "invalid_input"


# =============================================================================== refresh
async def test_refresh_reachability_keeps_cached_motion(adapter: DahuaAdapter):
    server = FakeDahua(camera_routes())
    caps = [{"code": "siren", "type": "bool", "writable": True}, {"code": "light", "type": "bool", "writable": True}]
    state = await adapter.refresh(camera_ref(state={"motion": True, "recording": True}, capabilities=caps), ctx_for(server))
    assert state.online is True
    assert state.state["motion"] is True and state.state["recording"] is True  # from the push cache
    assert state.state["light"] is True and state.state["siren"] is False  # refreshed from coaxialControlIO
    assert state.state["stream_main"] == "rtsp://192.168.1.108:554/cam/realmonitor?channel=1&subtype=0"
    assert server.sent("/cgi-bin/magicBox.cgi", "getDeviceType")

    nvr = FakeDahua(nvr_routes())
    state = await adapter.refresh(channel_ref(3), ctx_for(nvr))
    assert state.online is False and state.state["motion"] is False
    assert state.state["snapshot"] == "http://192.168.1.108:80/cgi-bin/snapshot.cgi?channel=3"
    state = await adapter.refresh(nvr_ref(), ctx_for(nvr))
    assert state.online is True and state.state == {"child_count": 3}

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    with pytest.raises(AdapterError) as exc:
        await adapter.refresh(camera_ref(), AdapterContext(transport=httpx.MockTransport(down)))
    assert exc.value.code == "unreachable"
    with pytest.raises(AdapterError) as exc:
        await adapter.refresh(camera_ref(), ctx_for(FakeDahua(camera_routes(), password="changed")))
    assert exc.value.code == "auth_failed"


# =============================================================================== commands
async def test_ptz_start_and_stop_urls(adapter: DahuaAdapter):
    server = FakeDahua(camera_routes())
    ctx = ctx_for(server)
    assert await adapter.send_command(camera_ref(), "ptz", "stop", ctx) == {}  # nothing moving yet -> stop "Up"
    assert await adapter.send_command(camera_ref(), "ptz", "left", ctx) == {}
    await adapter.send_command(camera_ref(), "ptz", "stop", ctx)
    await adapter.send_command(camera_ref(), "ptz", "zoom_in", ctx)
    await adapter.send_command(camera_ref(), "ptz", "stop", ctx)
    for direction in ("up", "down", "right", "zoom_out"):
        await adapter.send_command(camera_ref(), "ptz", direction, ctx)
    seen = server.sent("/cgi-bin/ptz.cgi")
    expected = [("stop", "Up"), ("start", "Left"), ("stop", "Left"), ("start", "ZoomTele"), ("stop", "ZoomTele"),
                ("start", "Up"), ("start", "Down"), ("start", "Right"), ("start", "ZoomWide")]
    assert [(r.params["action"], r.params["code"]) for r in seen] == expected
    assert all(r.params["channel"] == "1" and r.params["arg1"] == "0" and r.params["arg2"] == "1" and r.params["arg3"] == "0" for r in seen)
    assert seen[1].raw_query == "action=start&channel=1&code=Left&arg1=0&arg2=1&arg3=0"
    with pytest.raises(AdapterError) as exc:
        await adapter.send_command(camera_ref(), "ptz", "sideways", ctx)
    assert exc.value.code == "invalid_input"
    # NVR channel 3 -> PTZ on channel 3 of the recorder (1-based)
    nvr = FakeDahua(nvr_routes())
    await adapter.send_command(channel_ref(3), "ptz", "right", ctx_for(nvr))
    assert nvr.sent("/cgi-bin/ptz.cgi", "start")[0].raw_query == "action=start&channel=3&code=Right&arg1=0&arg2=1&arg3=0"
    # a camera that answers "Error" / 400 on PTZ
    no_ptz = FakeDahua({**camera_routes(), route_key("/cgi-bin/ptz.cgi", "start"): error(400)})
    with pytest.raises(AdapterError) as exc:
        await adapter.send_command(camera_ref(), "ptz", "up", ctx_for(no_ptz))
    assert exc.value.code == "unsupported"


async def test_light_and_siren_commands_and_unsupported(adapter: DahuaAdapter):
    server = FakeDahua(camera_routes())
    ctx = ctx_for(server)
    assert await adapter.send_command(camera_ref(), "light", True, ctx) == {"light": True}
    assert await adapter.send_command(camera_ref(), "light", False, ctx) == {"light": False}
    assert await adapter.send_command(camera_ref(), "siren", "on", ctx) == {"siren": True}
    queries = [r.raw_query for r in server.sent("/cgi-bin/coaxialControlIO.cgi", "control")]
    assert queries == [
        "action=control&channel=0&info[0].Type=1&info[0].IO=1",
        "action=control&channel=0&info[0].Type=1&info[0].IO=0",
        "action=control&channel=0&info[0].Type=2&info[0].IO=1",
    ]
    # recorder channel 3 -> coaxial channel index 2 (0-based)
    nvr = FakeDahua(nvr_routes())
    await adapter.send_command(channel_ref(3), "siren", False, ctx_for(nvr))
    assert nvr.sent("/cgi-bin/coaxialControlIO.cgi", "control")[0].raw_query == "action=control&channel=2&info[0].Type=2&info[0].IO=0"
    for code in ("recording", "privacy_mode", "brightness"):
        with pytest.raises(AdapterError) as exc:
            await adapter.send_command(camera_ref(), code, True, ctx)
        assert exc.value.code == "unsupported"
    with pytest.raises(AdapterError) as exc:
        await adapter.send_command(nvr_ref(), "ptz", "up", ctx)
    assert exc.value.code == "unsupported"
    with pytest.raises(AdapterError) as exc:
        await adapter.send_command(camera_ref(), "light", True, ctx_for(FakeDahua(camera_routes(coaxial=False))))
    assert exc.value.code == "unsupported"


# =============================================================================== event stream
def test_event_stream_parser_handles_split_chunks_and_data():
    body = (
        b"\r\n" + heartbeat_part() + event_part("VideoMotion", "Start", 0)
        + event_part("CrossLineDetection", "Start", 1, data='{\r\n   "Direction" : "RightToLeft",\r\n   "Name" : "Rule1"\r\n}')
        + heartbeat_part() + event_part("VideoMotion", "Stop", 0) + b"--myboundary--\r\n"
    )
    parser = EventStreamParser()
    events: List[Any] = []
    for i in range(0, len(body), 7):
        events.extend(parser.feed(body[i:i + 7]))
    assert parser.boundary == "myboundary"
    assert [(e.code, e.action, e.index) for e in events] == [
        ("Heartbeat", "", 0), ("VideoMotion", "Start", 0), ("CrossLineDetection", "Start", 1), ("Heartbeat", "", 0), ("VideoMotion", "Stop", 0),
    ]
    assert events[0].is_heartbeat and not events[1].is_heartbeat
    assert events[1].active and events[1].channel == 1 and events[2].channel == 2 and not events[4].active
    assert json.loads(events[2].data) == {"Direction": "RightToLeft", "Name": "Rule1"}
    # other boundary names are auto-detected; garbage parts are ignored
    parser = EventStreamParser()
    events = parser.feed(event_part("AlarmLocal", "Pulse", 0, boundary="other") + b"--other\r\nContent-Type: text/plain\r\n\r\nnonsense\r\n" + b"--other")
    assert parser.boundary == "other" and [(e.code, e.action) for e in events] == [("AlarmLocal", "Pulse")]
    assert parse_event_part(b"\r\nContent-Type: text/plain\r\n\r\n\r\n") is None
    assert parse_event_part(b"--\r\n") is None
    # the last part of a burst is completed from its Content-Length without waiting for the next delimiter
    parser = EventStreamParser()
    assert parser.feed(event_part("VideoMotion", "Start", 3)[:-4]) and parser.feed(b"") == []
    # ... and, without Content-Length, from a full Code= line / balanced data JSON
    parser = EventStreamParser()
    assert parser.feed(b"--myboundary\r\nContent-Type: text/plain\r\n\r\nCode=VideoMotion;action=Stop;index=1\r\n")[0].action == "Stop"
    assert parser.feed(b'--myboundary\r\nContent-Type: text/plain\r\n\r\nCode=SmartMotionHuman;action=Start;index=0;data={\r\n "Name" : "a}b",\r\n') == []
    events = parser.feed(b' "Object" : { "Action" : "Appear" }\r\n}\r\n')
    assert len(events) == 1 and json.loads(events[0].data) == {"Name": "a}b", "Object": {"Action": "Appear"}}


async def test_event_stream_emits_motion_and_ignores_heartbeats(adapter: DahuaAdapter):
    collector = Collector()
    ctx = AdapterContext(emit=collector)
    body = (
        heartbeat_part() + heartbeat_part() + event_part("VideoMotion", "Start") + heartbeat_part()
        + event_part("VideoMotion", "Start")  # repeated Start -> emitted once
        + event_part("VideoMotion", "Stop") + heartbeat_part() + event_part("SmartMotionHuman", "Start")
        + event_part("AlarmLocal", "Pulse") + heartbeat_part()
    )

    async def chunks():
        for i in range(0, len(body), 50):
            yield body[i:i + 50]

    handled = await adapter.process_event_stream(chunks(), [camera_ref()], ctx)
    assert handled == 4
    assert collector.states() == [
        (CAM_SERIAL, {"state": {"motion": True}, "online": True}),
        (CAM_SERIAL, {"state": {"motion": False}, "online": True}),
        (CAM_SERIAL, {"state": {"motion": True}, "online": True}),
        (CAM_SERIAL, {"state": {}, "online": True}),
    ]
    assert [(ext, p["type"], p["action"], p["channel"]) for ext, p in collector.events()] == [
        (CAM_SERIAL, "VideoMotion", "Start", 1), (CAM_SERIAL, "VideoMotion", "Stop", 1),
        (CAM_SERIAL, "SmartMotionHuman", "Start", 1), (CAM_SERIAL, "AlarmLocal", "Pulse", 1),
    ]


async def test_event_stream_routes_nvr_channels_by_index(adapter: DahuaAdapter):
    collector = Collector()
    ctx = AdapterContext(emit=collector)
    body = (
        event_part("VideoMotion", "Start", 2)  # index 2 -> channel 3
        + event_part("CrossRegionDetection", "Start", 0, data='{"Name":"Zone"}')  # index 0 -> channel 1
        + event_part("VideoMotion", "Start", 7)  # unknown channel on a recorder -> ignored
        + event_part("AlarmLocal", "Start", 5)  # alarm input of the recorder itself -> parent NVR
        + event_part("VideoMotion", "Stop", 2)
    )

    async def chunks():
        yield body

    handled = await adapter.process_event_stream(chunks(), [nvr_ref(), channel_ref(1), channel_ref(2), channel_ref(3)], ctx)
    assert handled == 4
    assert collector.states() == [
        (f"{NVR_SERIAL}:ch3", {"state": {"motion": True}, "online": True}),
        (f"{NVR_SERIAL}:ch1", {"state": {"motion": True}, "online": True}),
        (NVR_SERIAL, {"state": {}, "online": True}),
        (f"{NVR_SERIAL}:ch3", {"state": {"motion": False}, "online": True}),
    ]
    events = collector.events()
    assert [ext for ext, _ in events] == [f"{NVR_SERIAL}:ch3", f"{NVR_SERIAL}:ch1", NVR_SERIAL, f"{NVR_SERIAL}:ch3"]
    assert events[1][1]["data"] == {"Name": "Zone"}


async def test_subscribe_streams_over_http_and_unsubscribe_cancels(adapter: DahuaAdapter):
    stream_opened = asyncio.Event()

    async def event_body():
        stream_opened.set()
        yield heartbeat_part() + event_part("VideoMotion", "Start")
        await asyncio.sleep(0.05)
        yield event_part("VideoMotion", "Stop")
        await asyncio.sleep(3600)  # a real stream never ends; unsubscribe must cancel it

    def attach(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/cgi-bin/eventManager.cgi"
        return httpx.Response(200, headers={"content-type": "multipart/x-mixed-replace; boundary=myboundary"}, content=event_body())

    server = FakeDahua({**camera_routes(), route_key("/cgi-bin/eventManager.cgi", "attach"): attach})
    collector = Collector()
    unsubscribe = await adapter.subscribe([camera_ref()], ctx_for(server, emit=collector))
    assert unsubscribe is not None
    await asyncio.wait_for(stream_opened.wait(), 2)
    for _ in range(200):
        if len(collector.states()) >= 2:
            break
        await asyncio.sleep(0.01)
    assert collector.states() == [
        (CAM_SERIAL, {"state": {"motion": True}, "online": True}),
        (CAM_SERIAL, {"state": {"motion": False}, "online": True}),
    ]
    attaches = server.sent("/cgi-bin/eventManager.cgi", "attach")
    assert len(attaches) == 1 and attaches[0].headers["authorization"].startswith("Digest ")
    assert attaches[0].params["codes"] == "[" + ",".join(EVENT_CODES) + "]"
    assert attaches[0].params["codes"] == "[VideoMotion,AlarmLocal,CrossLineDetection,CrossRegionDetection,SmartMotionHuman,SmartMotionVehicle]"
    assert "codes=[VideoMotion," in attaches[0].raw_query  # brackets sent literally, as Dahua expects
    assert attaches[0].params["heartbeat"] == "5"
    await unsubscribe()
    await asyncio.sleep(0.05)
    assert len(server.sent("/cgi-bin/eventManager.cgi", "attach")) == 1  # no reconnect after unsubscribe
    assert await adapter.subscribe([], ctx_for(server)) is None


async def test_subscribe_marks_host_offline_after_repeated_failures(monkeypatch: pytest.MonkeyPatch):
    attempts = 0

    async def failing_stream(session: HostSession, ctx: AdapterContext):
        nonlocal attempts
        del session, ctx
        attempts += 1
        raise AdapterError("boom", "unreachable")
        # The unreachable yield makes this an async generator like the real stream opener.
        yield b""  # pylint: disable=unreachable

    monkeypatch.setattr("app.hub.adapters.dahua.RECONNECT_MIN_DELAY", 0.001)
    monkeypatch.setattr("app.hub.adapters.dahua.RECONNECT_MAX_DELAY", 0.001)
    adapter = DahuaAdapter(stream_opener=failing_stream)
    collector = Collector()
    unsubscribe = await adapter.subscribe([nvr_ref(), channel_ref(1)], AdapterContext(emit=collector))
    for _ in range(200):
        if len(collector.states()) >= 2:
            break
        await asyncio.sleep(0.005)
    await unsubscribe()
    assert attempts >= 3
    assert collector.states() == [(NVR_SERIAL, {"state": {}, "online": False}), (f"{NVR_SERIAL}:ch1", {"state": {}, "online": False})]


def test_group_by_host_shares_one_stream_per_host():
    groups = group_by_host([nvr_ref(), channel_ref(1), channel_ref(2), camera_ref()])
    assert len(groups) == 1  # same host/port in the fixtures
    other = channel_ref(3)
    other.config["host"] = "10.0.0.5"
    groups = {g.session.host: g for g in group_by_host([nvr_ref(), channel_ref(1), other])}
    assert set(groups) == {"192.168.1.108", "10.0.0.5"}
    assert groups["192.168.1.108"].primary == NVR_SERIAL and groups["192.168.1.108"].channels == {1: f"{NVR_SERIAL}:ch1"}
    assert groups["10.0.0.5"].primary == NVR_SERIAL and groups["10.0.0.5"].is_recorder
    assert group_by_host([DeviceRef(id="x", external_id="x", brand=BRAND_ID, protocol=PROTOCOL, category="camera")]) == []
