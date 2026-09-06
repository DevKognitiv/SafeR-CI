"""Hikvision (ISAPI) adapter tests: digest/basic auth, camera/NVR/AX PRO pairing, commands, streams, alertStream."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import httpx
import pytest

from app.hub.adapters.base import AdapterContext, AdapterError, DeviceRef
from app.hub.adapters.hikvision import (
    BRAND_ID, METHOD_IP, PROTOCOL, AlertStreamParser, HikvisionAdapter, HostSession, group_by_host, parse_alert,
)
from app.hub.adapters.registry import registry

USER, PASSWORD = "admin", "Secret123"
CAM_SERIAL = "DS-2CD2143G0-I20200101AAWRD12345678"
NVR_SERIAL = "DS-7608NI-K220200202BBWRE87654321"
PANEL_SERIAL = "DS-PWA96-M-WE20210303CCWRF11112222"

XML = {"content-type": "application/xml; charset=\"UTF-8\""}
JSON_H = {"content-type": "application/json"}

CAMERA_INFO = f"""<?xml version="1.0" encoding="UTF-8"?>
<DeviceInfo version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
<deviceName>Entrée</deviceName>
<deviceID>b5c3a4e0-1111-2222-3333-444455556666</deviceID>
<model>DS-2CD2143G0-I</model>
<serialNumber>{CAM_SERIAL}</serialNumber>
<macAddress>c0:56:e3:aa:bb:cc</macAddress>
<firmwareVersion>V5.6.3</firmwareVersion>
<firmwareReleasedDate>build 200103</firmwareReleasedDate>
<deviceType>IPCamera</deviceType>
<telecontrolID>88</telecontrolID>
</DeviceInfo>"""

NVR_INFO = f"""<?xml version="1.0" encoding="UTF-8"?>
<DeviceInfo version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
<deviceName>NVR Maison</deviceName>
<model>DS-7608NI-K2</model>
<serialNumber>{NVR_SERIAL}</serialNumber>
<macAddress>c0:56:e3:dd:ee:ff</macAddress>
<firmwareVersion>V4.61.010</firmwareVersion>
<deviceType>NVR</deviceType>
</DeviceInfo>"""

PANEL_INFO = f"""<?xml version="1.0" encoding="UTF-8"?>
<DeviceInfo version="2.0" xmlns="http://www.isapi.org/ver20/XMLSchema">
<deviceName>AX PRO</deviceName>
<model>DS-PWA96-M-WE</model>
<serialNumber>{PANEL_SERIAL}</serialNumber>
<firmwareVersion>V1.2.8</firmwareVersion>
<deviceType>AXPro</deviceType>
</DeviceInfo>"""

PTZ_CAPS = """<?xml version="1.0" encoding="UTF-8"?>
<PTZChanelCap version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
<AbsolutePanTiltPositionSpace><XRange><Min>0</Min><Max>3600</Max></XRange></AbsolutePanTiltPositionSpace>
<ContinuousPanTiltSpace><XRange><Min>-100</Min><Max>100</Max></XRange></ContinuousPanTiltSpace>
</PTZChanelCap>"""

SYSTEM_CAPS = """<?xml version="1.0" encoding="UTF-8"?>
<DeviceCap version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
<SysCap><isSupportDst>true</isSupportDst></SysCap>
<IOCap><IOInputPortNums>1</IOInputPortNums><IOOutputPortNums>1</IOOutputPortNums></IOCap>
</DeviceCap>"""

VIDEO_INPUTS = """<?xml version="1.0" encoding="UTF-8"?>
<VideoInputChannelList version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
<VideoInputChannel version="2.0"><id>1</id><inputPort>1</inputPort><name>Camera 01</name><videoFormat>PAL</videoFormat></VideoInputChannel>
</VideoInputChannelList>"""

INPUT_PROXY = """<?xml version="1.0" encoding="UTF-8"?>
<InputProxyChannelList version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
<InputProxyChannel version="2.0">
<id>1</id><name>Jardin</name>
<sourceInputPortDescriptor><proxyProtocol>HIKVISION</proxyProtocol><addressingFormatType>ipaddress</addressingFormatType>
<ipAddress>192.168.1.64</ipAddress><managePortNo>8000</managePortNo><srcInputPort>1</srcInputPort><userName>admin</userName>
<streamType>auto</streamType><model>DS-2DE4225IW-DE</model></sourceInputPortDescriptor>
</InputProxyChannel>
<InputProxyChannel version="2.0">
<id>2</id><name>Garage</name>
<sourceInputPortDescriptor><proxyProtocol>ONVIF</proxyProtocol><addressingFormatType>ipaddress</addressingFormatType>
<ipAddress>192.168.1.65</ipAddress><managePortNo>80</managePortNo><srcInputPort>1</srcInputPort></sourceInputPortDescriptor>
</InputProxyChannel>
</InputProxyChannelList>"""

INPUT_PROXY_STATUS = """<?xml version="1.0" encoding="UTF-8"?>
<InputProxyChannelStatusList version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
<InputProxyChannelStatus><id>1</id><online>true</online></InputProxyChannelStatus>
<InputProxyChannelStatus><id>2</id><online>false</online></InputProxyChannelStatus>
</InputProxyChannelStatusList>"""

RESPONSE_OK = """<?xml version="1.0" encoding="UTF-8"?>
<ResponseStatus version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
<requestURL>/ISAPI/x</requestURL><statusCode>1</statusCode><statusString>OK</statusString><subStatusCode>ok</subStatusCode>
</ResponseStatus>"""

RESPONSE_INVALID_OP = """<?xml version="1.0" encoding="UTF-8"?>
<ResponseStatus version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
<statusCode>4</statusCode><statusString>Invalid Operation</statusString><subStatusCode>notSupport</subStatusCode>
</ResponseStatus>"""

RESPONSE_NOT_FOUND = """<?xml version="1.0" encoding="UTF-8"?>
<ResponseStatus version="2.0"><statusCode>4</statusCode><statusString>Invalid Operation</statusString></ResponseStatus>"""

JPEG = bytes.fromhex("ffd8ffe000104a46494600010100000100010000ffd9")


def subsystems_json(arming: str = "away", alarm: bool = False) -> Dict[str, Any]:
    return {"SubSysList": [{"SubSys": {"id": 1, "arming": arming, "alarm": alarm, "enabled": True, "name": "Maison", "delayTime": 0}}]}


def zones_json(zone1_alarm: bool = False) -> Dict[str, Any]:
    return {"ZoneList": [
        {"Zone": {"id": 1, "name": "Porte d'entrée", "status": "online", "tamperEvident": False, "shielded": False,
                  "bypassed": False, "armed": True, "isArming": False, "alarm": zone1_alarm, "subSystemNo": 1,
                  "linkageSubSystem": [1], "detectorType": "magneticContact", "zoneType": "Instant",
                  "zoneAttrib": "wireless", "deviceNo": 1, "chargeValue": 100, "signal": 4, "model": "DS-PDMC-EG2-WE"}},
        {"Zone": {"id": 2, "name": "PIR salon", "status": "notReady", "tamperEvident": True, "bypassed": True,
                  "armed": True, "alarm": False, "subSystemNo": 1, "detectorType": "passiveInfraredDetector",
                  "chargeValue": 62, "signal": 2, "model": "DS-PDP15P-EG2-WE"}},
    ]}


def alert_xml(event_type: str, state: str, channel: int = 1, dyn_channel: Optional[int] = None, extra: str = "") -> str:
    dyn = f"<dynChannelID>{dyn_channel}</dynChannelID>" if dyn_channel is not None else ""
    return (
        '<EventNotificationAlert version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">'
        "<ipAddress>192.168.1.64</ipAddress><portNo>80</portNo><protocol>HTTP</protocol>"
        f"<macAddress>c0:56:e3:aa:bb:cc</macAddress><channelID>{channel}</channelID>{dyn}"
        "<dateTime>2026-09-06T10:00:00+00:00</dateTime><activePostCount>1</activePostCount>"
        f"<eventType>{event_type}</eventType><eventState>{state}</eventState>"
        f"<eventDescription>{event_type} alarm</eventDescription>{extra}</EventNotificationAlert>"
    )


def multipart(*documents: str, boundary: str = "boundary") -> bytes:
    parts = []
    for document in documents:
        body = document.encode()
        parts.append(
            f'--{boundary}\r\nContent-Type: application/xml; charset="UTF-8"\r\nContent-Length: {len(body)}\r\n\r\n'.encode()
            + body + b"\r\n"
        )
    return b"".join(parts)


def _md5(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()  # noqa: S324 - RFC 2617 digest


Handler = Union[httpx.Response, Callable[[httpx.Request], httpx.Response]]


class FakeIsapi:
    """In-memory ISAPI device: verifies HTTP Digest (or Basic) auth like a real Hikvision unit."""

    def __init__(self, routes: Dict[Tuple[str, str], Handler], auth: str = "digest", password: str = PASSWORD, realm: str = "IP Camera(12345)"):
        self.routes = routes
        self.auth = auth
        self.password = password
        self.realm = realm
        self.nonce = "5f3e9c1b2a7d4e6f"
        self.requests: List[httpx.Request] = []

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if not self.authorized(request):
            challenge = (
                f'Digest realm="{self.realm}", qop="auth", nonce="{self.nonce}", opaque="8b1a9953", algorithm="MD5"'
                if self.auth == "digest" else f'Basic realm="{self.realm}"'
            )
            return httpx.Response(401, headers={"WWW-Authenticate": challenge, **XML}, content=b"<html>Unauthorized</html>")
        handler = self.routes.get((request.method, request.url.path))
        if handler is None:
            return httpx.Response(404, headers=XML, content=RESPONSE_NOT_FOUND)
        return handler(request) if callable(handler) else handler

    def authorized(self, request: httpx.Request) -> bool:
        header = request.headers.get("Authorization", "")
        if self.auth == "basic":
            return header == "Basic " + base64.b64encode(f"{USER}:{self.password}".encode()).decode()
        if not header.lower().startswith("digest "):
            return False
        params = {k: (q or u) for k, q, u in re.findall(r'(\w+)=(?:"([^"]*)"|([^,\s]+))', header[7:])}
        ha1 = _md5(f"{params.get('username')}:{self.realm}:{self.password}")
        ha2 = _md5(f"{request.method}:{request.url.raw_path.decode()}")
        if params.get("qop"):
            expected = _md5(f"{ha1}:{params.get('nonce')}:{params.get('nc')}:{params.get('cnonce')}:{params.get('qop')}:{ha2}")
        else:
            expected = _md5(f"{ha1}:{params.get('nonce')}:{ha2}")
        return params.get("username") == USER and params.get("uri") == request.url.raw_path.decode() and params.get("response") == expected

    def sent(self, method: str, path: str) -> List[httpx.Request]:
        return [r for r in self.requests if r.method == method and r.url.path == path and "Authorization" in r.headers]


def camera_routes(ptz: bool = True) -> Dict[Tuple[str, str], Handler]:
    routes: Dict[Tuple[str, str], Handler] = {
        ("GET", "/ISAPI/System/deviceInfo"): httpx.Response(200, headers=XML, content=CAMERA_INFO),
        ("GET", "/ISAPI/System/capabilities"): httpx.Response(200, headers=XML, content=SYSTEM_CAPS),
        ("GET", "/ISAPI/SecurityCP/status/subSystems"): httpx.Response(403, headers=XML, content=RESPONSE_INVALID_OP),
        ("GET", "/ISAPI/Streaming/channels/101"): httpx.Response(200, headers=XML, content="<StreamingChannel><id>101</id></StreamingChannel>"),
        ("GET", "/ISAPI/Streaming/channels/101/picture"): httpx.Response(200, headers={"content-type": "image/jpeg"}, content=JPEG),
        ("PUT", "/ISAPI/PTZCtrl/channels/1/continuous"): httpx.Response(200, headers=XML, content=RESPONSE_OK),
        ("PUT", "/ISAPI/System/IO/outputs/1/trigger"): httpx.Response(200, headers=XML, content=RESPONSE_OK),
    }
    if ptz:
        routes[("GET", "/ISAPI/PTZCtrl/channels/1/capabilities")] = httpx.Response(200, headers=XML, content=PTZ_CAPS)
    return routes


def nvr_routes() -> Dict[Tuple[str, str], Handler]:
    return {
        ("GET", "/ISAPI/System/deviceInfo"): httpx.Response(200, headers=XML, content=NVR_INFO),
        ("GET", "/ISAPI/SecurityCP/status/subSystems"): httpx.Response(404, headers=XML, content=RESPONSE_NOT_FOUND),
        ("GET", "/ISAPI/System/Video/inputs/channels"): httpx.Response(200, headers=XML, content=VIDEO_INPUTS),
        ("GET", "/ISAPI/ContentMgmt/InputProxy/channels"): httpx.Response(200, headers=XML, content=INPUT_PROXY),
        ("GET", "/ISAPI/ContentMgmt/InputProxy/channels/status"): httpx.Response(200, headers=XML, content=INPUT_PROXY_STATUS),
        ("GET", "/ISAPI/PTZCtrl/channels/1/capabilities"): httpx.Response(200, headers=XML, content=PTZ_CAPS),
        ("GET", "/ISAPI/PTZCtrl/channels/2/capabilities"): httpx.Response(403, headers=XML, content=RESPONSE_INVALID_OP),
    }


def panel_routes(arming: str = "away", alarm: bool = False, zone1_alarm: bool = False) -> Dict[Tuple[str, str], Handler]:
    def control(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, headers=JSON_H, content=json.dumps({"statusCode": 1, "statusString": "OK"}))

    return {
        ("GET", "/ISAPI/System/deviceInfo"): httpx.Response(200, headers=XML, content=PANEL_INFO),
        ("GET", "/ISAPI/SecurityCP/status/subSystems"): httpx.Response(200, headers=JSON_H, content=json.dumps(subsystems_json(arming, alarm))),
        ("GET", "/ISAPI/SecurityCP/status/zones"): httpx.Response(200, headers=JSON_H, content=json.dumps(zones_json(zone1_alarm))),
        ("PUT", "/ISAPI/SecurityCP/control/arm/1"): control,
        ("PUT", "/ISAPI/SecurityCP/control/disarm/1"): control,
        ("PUT", "/ISAPI/SecurityCP/control/clearAlarm/1"): control,
        ("PUT", "/ISAPI/SecurityCP/control/bypass/2"): control,
    }


class Collector:
    """Captures ``ctx.emit`` calls."""

    def __init__(self) -> None:
        self.items: List[Tuple[str, str, Dict[str, Any]]] = []

    async def __call__(self, event_type: str, external_id: str, payload: Dict[str, Any]) -> None:
        self.items.append((event_type, external_id, payload))

    def states(self) -> List[Tuple[str, Dict[str, Any]]]:
        return [(ext, payload) for kind, ext, payload in self.items if kind == "state"]

    def events(self) -> List[Tuple[str, Dict[str, Any]]]:
        return [(ext, payload) for kind, ext, payload in self.items if kind == "event"]


def ctx_for(server: FakeIsapi, emit: Optional[Collector] = None) -> AdapterContext:
    return AdapterContext(transport=server.transport(), emit=emit)


def payload(**overrides: Any) -> Dict[str, Any]:
    data = {"host": "192.168.1.64", "port": 80, "https": False, "username": USER, "password": PASSWORD, "rtsp_port": 554}
    data.update(overrides)
    return data


HOST_CFG = {"host": "192.168.1.64", "port": 80, "https": False, "rtsp_port": 554}
CREDS = {"username": USER, "password": PASSWORD}


def camera_ref(state: Optional[Dict[str, Any]] = None, **config: Any) -> DeviceRef:
    return DeviceRef(id="d1", external_id=CAM_SERIAL, brand=BRAND_ID, protocol=PROTOCOL, category="camera",
                     config={**HOST_CFG, "channel": 1, "io_outputs": 1, "siren_output": 1, **config}, credentials=dict(CREDS), state=state or {})


def channel_ref(channel: int) -> DeviceRef:
    # As built by DeviceService.ref_for: parent host config + credentials merged into the child
    return DeviceRef(id=f"c{channel}", external_id=f"{NVR_SERIAL}:ch{channel}", brand=BRAND_ID, protocol=PROTOCOL, category="camera",
                     config={**HOST_CFG, "channel": channel}, credentials=dict(CREDS), parent_external_id=NVR_SERIAL)


def nvr_ref() -> DeviceRef:
    return DeviceRef(id="n1", external_id=NVR_SERIAL, brand=BRAND_ID, protocol=PROTOCOL, category="nvr",
                     config={**HOST_CFG, "channel_count": 2, "channels": [1, 2]}, credentials=dict(CREDS))


def panel_ref() -> DeviceRef:
    return DeviceRef(id="p1", external_id=PANEL_SERIAL, brand=BRAND_ID, protocol=PROTOCOL, category="alarm_panel",
                     config={**HOST_CFG, "subsystem": 1, "subsystems": [1]}, credentials=dict(CREDS))


def zone_ref(zone_id: int) -> DeviceRef:
    return DeviceRef(id=f"z{zone_id}", external_id=f"{PANEL_SERIAL}:zone{zone_id}", brand=BRAND_ID, protocol=PROTOCOL, category="alarm_zone",
                     config={**HOST_CFG, "zone_id": zone_id, "subsystem": 1}, credentials=dict(CREDS), parent_external_id=PANEL_SERIAL)


@pytest.fixture
def adapter() -> HikvisionAdapter:
    return HikvisionAdapter()


# =============================================================================== catalogue
def test_registered_and_method_fields():
    registered = registry.get(BRAND_ID)
    assert isinstance(registered, HikvisionAdapter)
    assert registered.supports_push is True
    info = registered.info()
    assert info.protocols == [PROTOCOL]
    method = registered.method(METHOD_IP)
    assert method.supports_discovery is False
    fields = {f.name: f for f in method.fields}
    assert set(fields) == {"host", "port", "https", "username", "password", "rtsp_port", "name"}
    assert fields["port"].type == "number" and fields["port"].default == 80
    assert fields["https"].type == "toggle" and fields["https"].default is False
    assert fields["password"].type == "password"
    assert fields["rtsp_port"].default == 554
    assert fields["name"].required is False
    with pytest.raises(AdapterError) as exc:
        registered.method("qr")
    assert exc.value.code == "invalid_input"


def test_host_session_coercion():
    session = HostSession.from_payload({"host": " cam.local ", "port": "8443", "https": "true", "username": "u", "password": "p", "rtsp_port": ""})
    assert session.base_url == "https://cam.local:8443"
    assert session.rtsp_url(3) == "rtsp://cam.local:554/Streaming/Channels/301"
    assert session.rtsp_url(3, sub=True) == "rtsp://cam.local:554/Streaming/Channels/302"
    assert session.snapshot_url(1) == "https://cam.local:8443/ISAPI/Streaming/channels/101/picture"
    assert HostSession.from_payload({"host": "h", "https": True}).port == 443
    with pytest.raises(AdapterError) as exc:
        HostSession.from_device(DeviceRef(id="x", external_id="x", brand=BRAND_ID, protocol=PROTOCOL, category="camera"))
    assert exc.value.code == "invalid_input"


# =============================================================================== pairing
async def test_pair_ip_camera_with_digest(adapter: HikvisionAdapter):
    server = FakeIsapi(camera_routes())
    result = await adapter.pair(METHOD_IP, payload(name="Caméra entrée"), ctx_for(server))
    assert len(result.devices) == 1
    cam = result.devices[0]
    assert cam.external_id == CAM_SERIAL
    assert cam.category == "camera" and cam.protocol == PROTOCOL
    assert cam.name == "Caméra entrée"
    assert cam.model == "DS-2CD2143G0-I" and cam.manufacturer == "Hikvision" and cam.firmware.startswith("V5.6.3")
    assert cam.config["host"] == "192.168.1.64" and cam.config["port"] == 80 and cam.config["https"] is False
    assert cam.config["rtsp_port"] == 554 and cam.config["channel"] == 1
    assert cam.credentials == {"username": USER, "password": PASSWORD}
    codes = {c["code"] for c in cam.capabilities}
    assert {"stream_main", "stream_sub", "snapshot", "motion", "ptz", "siren"} <= codes
    assert "light" not in codes  # one IO output only -> siren, no light
    assert cam.state["stream_main"] == f"rtsp://192.168.1.64:554/Streaming/Channels/101"
    assert cam.state["stream_sub"] == f"rtsp://192.168.1.64:554/Streaming/Channels/102"
    assert cam.state["snapshot"] == "http://192.168.1.64:80/ISAPI/Streaming/channels/101/picture"
    assert PASSWORD not in json.dumps(cam.state)
    # First request was challenged, the retry carried a valid Digest header
    first, second = server.requests[0], server.requests[1]
    assert "Authorization" not in first.headers and second.headers["Authorization"].startswith("Digest ")
    assert result.message


async def test_pair_camera_without_ptz_uses_device_name(adapter: HikvisionAdapter):
    server = FakeIsapi(camera_routes(ptz=False))
    result = await adapter.pair(METHOD_IP, payload(), ctx_for(server))
    cam = result.devices[0]
    assert cam.name == "Entrée"
    assert "ptz" not in {c["code"] for c in cam.capabilities}


async def test_pair_nvr_with_two_ip_channels(adapter: HikvisionAdapter):
    server = FakeIsapi(nvr_routes())
    result = await adapter.pair(METHOD_IP, payload(host="192.168.1.10", port=8080), ctx_for(server))
    assert [d.category for d in result.devices] == ["nvr", "camera", "camera"]
    parent, ch1, ch2 = result.devices
    assert parent.external_id == NVR_SERIAL and parent.parent_external_id is None
    assert parent.state == {"child_count": 2}
    assert parent.capabilities == [{"code": "child_count", "type": "int", "writable": False}]
    assert parent.credentials == CREDS and parent.config["channel_count"] == 2
    assert ch1.external_id == f"{NVR_SERIAL}:ch1" and ch1.parent_external_id == NVR_SERIAL
    assert ch2.external_id == f"{NVR_SERIAL}:ch2" and ch2.parent_external_id == NVR_SERIAL
    assert ch1.config == {"channel": 1, "ip_address": "192.168.1.64"} and ch2.config["channel"] == 2
    assert ch1.credentials == {} and ch2.credentials == {}  # children inherit through the hub
    assert ch1.name == "Jardin" and ch1.model == "DS-2DE4225IW-DE" and ch1.manufacturer == "Hikvision"
    assert ch2.name == "Garage" and ch2.manufacturer == "Onvif"
    assert "ptz" in {c["code"] for c in ch1.capabilities} and "ptz" not in {c["code"] for c in ch2.capabilities}
    assert ch1.online is True and ch2.online is False
    assert ch2.state["stream_main"] == "rtsp://192.168.1.10:554/Streaming/Channels/201"
    assert ch2.state["snapshot"] == "http://192.168.1.10:8080/ISAPI/Streaming/channels/201/picture"


async def test_pair_ax_pro_panel_and_zones(adapter: HikvisionAdapter):
    server = FakeIsapi(panel_routes(arming="away"))
    result = await adapter.pair(METHOD_IP, payload(host="192.168.1.20"), ctx_for(server))
    assert [d.category for d in result.devices] == ["alarm_panel", "alarm_zone", "alarm_zone"]
    panel, zone1, zone2 = result.devices
    assert panel.external_id == PANEL_SERIAL and panel.credentials == CREDS
    assert panel.state == {"arm_mode": "armed_away", "alarm": False, "triggered_zone": "", "ready": True}
    assert panel.config["subsystems"] == [1] and panel.config["subsystem"] == 1
    assert {c["code"] for c in panel.capabilities} == {"arm_mode", "alarm", "triggered_zone", "ready"}
    assert zone1.external_id == f"{PANEL_SERIAL}:zone1" and zone1.parent_external_id == PANEL_SERIAL
    assert zone1.config == {"zone_id": 1, "subsystem": 1, "detector_type": "magneticContact"}
    assert zone1.state == {"open": False, "alarm": False, "bypass": False, "tamper": False, "battery": 100, "signal": 100}
    assert zone2.external_id == f"{PANEL_SERIAL}:zone2" and zone2.name == "PIR salon"
    assert zone2.state == {"open": True, "alarm": False, "bypass": True, "tamper": True, "battery": 62, "signal": 50}
    assert zone2.credentials == {}
    assert server.sent("GET", "/ISAPI/SecurityCP/status/subSystems")[0].url.params["format"] == "json"


@pytest.mark.parametrize("arming,expected", [("away", "armed_away"), ("stay", "armed_home"), ("disarm", "disarmed")])
async def test_ax_pro_arm_mode_mapping(adapter: HikvisionAdapter, arming: str, expected: str):
    server = FakeIsapi(panel_routes(arming=arming))
    result = await adapter.pair(METHOD_IP, payload(), ctx_for(server))
    assert result.devices[0].state["arm_mode"] == expected


async def test_ax_pro_alarm_from_subsystem_and_zone(adapter: HikvisionAdapter):
    server = FakeIsapi(panel_routes(arming="stay", alarm=True, zone1_alarm=True))
    result = await adapter.pair(METHOD_IP, payload(), ctx_for(server))
    panel, zone1, _ = result.devices
    assert panel.state["alarm"] is True and panel.state["triggered_zone"] == "Porte d'entrée"
    assert zone1.state["alarm"] is True


async def test_pair_missing_fields(adapter: HikvisionAdapter):
    with pytest.raises(AdapterError) as exc:
        await adapter.pair(METHOD_IP, {"host": "1.2.3.4"}, ctx_for(FakeIsapi({})))
    assert exc.value.code == "invalid_input" and "username" in exc.value.message


async def test_pair_auth_failed(adapter: HikvisionAdapter):
    server = FakeIsapi(camera_routes(), password="other-password")
    with pytest.raises(AdapterError) as exc:
        await adapter.pair(METHOD_IP, payload(), ctx_for(server))
    assert exc.value.code == "auth_failed"
    # digest challenge answered once, then rejected: never falls back to Basic when a Digest challenge exists
    assert all(not r.headers.get("Authorization", "").startswith("Basic") for r in server.requests)


async def test_pair_unreachable(adapter: HikvisionAdapter):
    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(AdapterError) as exc:
        await adapter.pair(METHOD_IP, payload(), AdapterContext(transport=httpx.MockTransport(refused)))
    assert exc.value.code == "unreachable"

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(AdapterError) as exc:
        await adapter.pair(METHOD_IP, payload(), AdapterContext(transport=httpx.MockTransport(timeout)))
    assert exc.value.code == "unreachable"


async def test_pair_non_isapi_answers_are_invalid_input(adapter: HikvisionAdapter):
    html = FakeIsapi({("GET", "/ISAPI/System/deviceInfo"): httpx.Response(200, headers={"content-type": "text/html"}, content="<html><body>router</body>")})
    with pytest.raises(AdapterError) as exc:
        await adapter.pair(METHOD_IP, payload(), ctx_for(html))
    assert exc.value.code == "invalid_input"
    other = FakeIsapi({("GET", "/ISAPI/System/deviceInfo"): httpx.Response(200, headers=XML, content="<Foo><bar>1</bar></Foo>")})
    with pytest.raises(AdapterError) as exc:
        await adapter.pair(METHOD_IP, payload(), ctx_for(other))
    assert exc.value.code == "invalid_input"


async def test_basic_auth_fallback(adapter: HikvisionAdapter):
    server = FakeIsapi(camera_routes(), auth="basic")
    result = await adapter.pair(METHOD_IP, payload(), ctx_for(server))
    assert result.devices[0].external_id == CAM_SERIAL
    auth_headers = [r.headers.get("Authorization", "") for r in server.requests]
    assert auth_headers[0] == "" and auth_headers[1].startswith("Basic ")
    assert all(h.startswith("Basic ") for h in auth_headers[1:])  # sticks to Basic for the rest of the session


# =============================================================================== media
async def test_stream_urls_main_and_sub(adapter: HikvisionAdapter):
    ctx = ctx_for(FakeIsapi({}))
    main = await adapter.stream(camera_ref(), "main", ctx)
    sub = await adapter.stream(camera_ref(), "sub", ctx)
    assert main.type == "rtsp" and main.url == "rtsp://192.168.1.64:554/Streaming/Channels/101"
    assert sub.url == "rtsp://192.168.1.64:554/Streaming/Channels/102"
    assert main.username == USER and main.password == PASSWORD
    channel = await adapter.stream(channel_ref(2), "sub", ctx)
    assert channel.url == "rtsp://192.168.1.64:554/Streaming/Channels/202"
    assert await adapter.stream(nvr_ref(), "main", ctx) is None
    assert await adapter.stream(panel_ref(), "main", ctx) is None


async def test_snapshot_bytes(adapter: HikvisionAdapter):
    server = FakeIsapi(camera_routes())
    data = await adapter.snapshot(camera_ref(), ctx_for(server))
    assert data == JPEG
    assert server.sent("GET", "/ISAPI/Streaming/channels/101/picture")
    assert await adapter.snapshot(panel_ref(), ctx_for(server)) is None
    bad = FakeIsapi({("GET", "/ISAPI/Streaming/channels/101/picture"): httpx.Response(200, headers=XML, content=RESPONSE_INVALID_OP)})
    with pytest.raises(AdapterError) as exc:
        await adapter.snapshot(camera_ref(), ctx_for(bad))
    assert exc.value.code == "invalid_input"


# =============================================================================== refresh
async def test_refresh_camera_channel_and_nvr(adapter: HikvisionAdapter):
    server = FakeIsapi(camera_routes())
    state = await adapter.refresh(camera_ref(state={"motion": True}), ctx_for(server))
    assert state.online is True
    assert state.state["motion"] is True  # from the push cache
    assert state.state["stream_main"] == "rtsp://192.168.1.64:554/Streaming/Channels/101"
    assert server.sent("GET", "/ISAPI/System/deviceInfo") and server.sent("GET", "/ISAPI/Streaming/channels/101")

    nvr = FakeIsapi({**nvr_routes(),
                     ("GET", "/ISAPI/ContentMgmt/InputProxy/channels/2/status"): httpx.Response(
                         200, headers=XML, content="<InputProxyChannelStatus><id>2</id><online>false</online></InputProxyChannelStatus>")})
    state = await adapter.refresh(channel_ref(2), ctx_for(nvr))
    assert state.online is False and state.state["snapshot"].endswith("/ISAPI/Streaming/channels/201/picture")
    state = await adapter.refresh(nvr_ref(), ctx_for(nvr))
    assert state.online is True and state.state == {"child_count": 2}

    gone = FakeIsapi({("GET", "/ISAPI/System/deviceInfo"): httpx.Response(200, headers=XML, content=CAMERA_INFO)})
    state = await adapter.refresh(camera_ref(), ctx_for(gone))
    assert state.online is False


async def test_refresh_panel_and_zone(adapter: HikvisionAdapter):
    server = FakeIsapi(panel_routes(arming="stay", alarm=True))
    state = await adapter.refresh(panel_ref(), ctx_for(server))
    assert state.state["arm_mode"] == "armed_home" and state.state["alarm"] is True and state.state["ready"] is True
    zone = await adapter.refresh(zone_ref(2), ctx_for(server))
    assert zone.online is True and zone.state["open"] is True and zone.state["bypass"] is True
    with pytest.raises(AdapterError) as exc:
        await adapter.refresh(zone_ref(9), ctx_for(server))
    assert exc.value.code == "not_found"


# =============================================================================== commands
async def test_ptz_command_body(adapter: HikvisionAdapter):
    server = FakeIsapi(camera_routes())
    ctx = ctx_for(server)
    assert await adapter.send_command(camera_ref(), "ptz", "left", ctx) == {}
    await adapter.send_command(camera_ref(), "ptz", "up", ctx)
    await adapter.send_command(camera_ref(), "ptz", "zoom_in", ctx)
    await adapter.send_command(camera_ref(), "ptz", "stop", ctx)
    bodies = [r.content.decode() for r in server.sent("PUT", "/ISAPI/PTZCtrl/channels/1/continuous")]
    assert bodies == [
        "<PTZData><pan>-60</pan><tilt>0</tilt><zoom>0</zoom></PTZData>",
        "<PTZData><pan>0</pan><tilt>60</tilt><zoom>0</zoom></PTZData>",
        "<PTZData><pan>0</pan><tilt>0</tilt><zoom>60</zoom></PTZData>",
        "<PTZData><pan>0</pan><tilt>0</tilt><zoom>0</zoom></PTZData>",
    ]
    with pytest.raises(AdapterError) as exc:
        await adapter.send_command(camera_ref(), "ptz", "sideways", ctx)
    assert exc.value.code == "invalid_input"
    # NVR channel 2 -> PTZ on channel 2 of the recorder
    nvr = FakeIsapi({("PUT", "/ISAPI/PTZCtrl/channels/2/continuous"): httpx.Response(200, headers=XML, content=RESPONSE_OK)})
    await adapter.send_command(channel_ref(2), "ptz", "right", ctx_for(nvr))
    assert nvr.sent("PUT", "/ISAPI/PTZCtrl/channels/2/continuous")[0].content == b"<PTZData><pan>60</pan><tilt>0</tilt><zoom>0</zoom></PTZData>"


async def test_arm_disarm_bypass_and_clear_commands(adapter: HikvisionAdapter):
    server = FakeIsapi(panel_routes())
    ctx = ctx_for(server)
    assert await adapter.send_command(panel_ref(), "arm_mode", "armed_away", ctx) == {"arm_mode": "armed_away"}
    assert await adapter.send_command(panel_ref(), "arm_mode", "armed_home", ctx) == {"arm_mode": "armed_home"}
    assert await adapter.send_command(panel_ref(), "arm_mode", "armed_night", ctx) == {"arm_mode": "armed_night"}
    arms = server.sent("PUT", "/ISAPI/SecurityCP/control/arm/1")
    assert [r.url.params["ways"] for r in arms] == ["away", "stay", "stay"]
    result = await adapter.send_command(panel_ref(), "arm_mode", "disarmed", ctx)
    assert result["arm_mode"] == "disarmed" and result["alarm"] is False
    assert len(server.sent("PUT", "/ISAPI/SecurityCP/control/disarm/1")) == 1
    assert await adapter.send_command(zone_ref(2), "bypass", True, ctx) == {"bypass": True}
    bypass = server.sent("PUT", "/ISAPI/SecurityCP/control/bypass/2")[0]
    assert json.loads(bypass.content) == {"BypassCtrl": {"bypass": True}}
    assert bypass.url.params["format"] == "json" and bypass.headers["content-type"] == "application/json"
    assert (await adapter.send_command(panel_ref(), "alarm", False, ctx))["alarm"] is False
    assert len(server.sent("PUT", "/ISAPI/SecurityCP/control/clearAlarm/1")) == 1
    with pytest.raises(AdapterError) as exc:
        await adapter.send_command(panel_ref(), "arm_mode", "vacation", ctx)
    assert exc.value.code == "invalid_input"
    with pytest.raises(AdapterError) as exc:
        await adapter.send_command(zone_ref(2), "open", True, ctx)
    assert exc.value.code == "unsupported"


async def test_panel_command_rejected_by_device(adapter: HikvisionAdapter):
    routes = panel_routes()
    routes[("PUT", "/ISAPI/SecurityCP/control/arm/1")] = httpx.Response(
        200, headers=JSON_H, content=json.dumps({"statusCode": 4, "statusString": "Invalid Operation", "subStatusCode": "zoneNotReady"}))
    with pytest.raises(AdapterError) as exc:
        await adapter.send_command(panel_ref(), "arm_mode", "armed_away", ctx_for(FakeIsapi(routes)))
    assert exc.value.code == "invalid_input" and "Invalid Operation" in exc.value.message


async def test_siren_output_and_unsupported_light(adapter: HikvisionAdapter):
    server = FakeIsapi(camera_routes())
    ctx = ctx_for(server)
    assert await adapter.send_command(camera_ref(), "siren", True, ctx) == {"siren": True}
    assert await adapter.send_command(camera_ref(), "siren", False, ctx) == {"siren": False}
    bodies = [r.content for r in server.sent("PUT", "/ISAPI/System/IO/outputs/1/trigger")]
    assert bodies == [b"<IOPortData><outputState>high</outputState></IOPortData>", b"<IOPortData><outputState>low</outputState></IOPortData>"]
    with pytest.raises(AdapterError) as exc:
        await adapter.send_command(camera_ref(), "light", True, ctx)  # no light_output configured
    assert exc.value.code == "unsupported"
    with pytest.raises(AdapterError) as exc:
        await adapter.send_command(camera_ref(light_output=2), "light", True, ctx)  # device answers 404
    assert exc.value.code == "unsupported"
    with pytest.raises(AdapterError) as exc:
        await adapter.send_command(camera_ref(), "brightness", 50, ctx)
    assert exc.value.code == "unsupported"


# =============================================================================== alertStream
def test_alert_stream_parser_handles_split_chunks():
    body = multipart(alert_xml("VMD", "active"), alert_xml("videoloss", "inactive"))
    parser = AlertStreamParser()
    documents: List[str] = []
    for i in range(0, len(body), 7):
        documents.extend(parser.feed(body[i:i + 7]))
    assert len(documents) == 2
    first = parse_alert(documents[0])
    assert first.event_type == "VMD" and first.state == "active" and first.channel == 1 and not first.is_heartbeat
    assert parse_alert(documents[1]).is_heartbeat
    assert parse_alert("<html>nope</html>") is None
    dyn = parse_alert(alert_xml("linedetection", "active", channel=0, dyn_channel=2))
    assert dyn.channel == 2


async def test_alert_stream_emits_motion_and_ignores_heartbeats(adapter: HikvisionAdapter):
    collector = Collector()
    ctx = AdapterContext(emit=collector)
    heartbeat = alert_xml("videoloss", "inactive")
    body = multipart(
        heartbeat, heartbeat, alert_xml("VMD", "active"), heartbeat, alert_xml("VMD", "active"),  # repeated active -> once
        heartbeat, alert_xml("VMD", "inactive"), heartbeat, alert_xml("linedetection", "active"), heartbeat,
    )

    async def chunks():
        for i in range(0, len(body), 100):
            yield body[i:i + 100]

    handled = await adapter.process_alert_stream(chunks(), [camera_ref()], ctx)
    assert handled == 3
    assert collector.states() == [
        (CAM_SERIAL, {"state": {"motion": True}, "online": True}),
        (CAM_SERIAL, {"state": {"motion": False}, "online": True}),
        (CAM_SERIAL, {"state": {"motion": True}, "online": True}),
    ]
    events = collector.events()
    assert [(ext, p["type"], p["state"]) for ext, p in events] == [
        (CAM_SERIAL, "VMD", "active"), (CAM_SERIAL, "VMD", "inactive"), (CAM_SERIAL, "linedetection", "active"),
    ]


async def test_alert_stream_routes_nvr_channels(adapter: HikvisionAdapter):
    collector = Collector()
    ctx = AdapterContext(emit=collector)
    body = multipart(
        alert_xml("VMD", "active", channel=2), alert_xml("videoloss", "active", channel=1),
        alert_xml("VMD", "active", channel=7),  # unknown channel on a recorder -> ignored
        alert_xml("IO", "active", channel=0, dyn_channel=0),  # recorder-level event -> parent NVR
    )

    async def chunks():
        yield body

    handled = await adapter.process_alert_stream(chunks(), [nvr_ref(), channel_ref(1), channel_ref(2)], ctx)
    assert handled == 3
    assert collector.states() == [
        (f"{NVR_SERIAL}:ch2", {"state": {"motion": True}, "online": True}),
        (f"{NVR_SERIAL}:ch1", {"state": {}, "online": False}),
        (NVR_SERIAL, {"state": {}, "online": True}),
    ]
    assert [ext for ext, _ in collector.events()] == [f"{NVR_SERIAL}:ch2", f"{NVR_SERIAL}:ch1", NVR_SERIAL]


async def test_alert_stream_cid_events_for_panels(adapter: HikvisionAdapter):
    collector = Collector()
    ctx = AdapterContext(emit=collector)
    cid = "<CIDEvent><code>{code}</code><type>x</type><zone>1</zone><subSystem>1</subSystem></CIDEvent>"
    body = multipart(
        alert_xml("CIDEvent", "active", extra=cid.format(code=3401)),
        alert_xml("CIDEvent", "active", extra=cid.format(code=1130)),
        alert_xml("CIDEvent", "active", extra=cid.format(code=1401)),
    )

    async def chunks():
        yield body

    await adapter.process_alert_stream(chunks(), [panel_ref(), zone_ref(1), zone_ref(2)], ctx)
    states = collector.states()
    assert (PANEL_SERIAL, {"state": {"arm_mode": "armed_away"}, "online": True}) in states
    assert (f"{PANEL_SERIAL}:zone1", {"state": {"alarm": True}, "online": True}) in states
    assert (PANEL_SERIAL, {"state": {"alarm": True}, "online": True}) in states
    assert states[-1] == (PANEL_SERIAL, {"state": {"arm_mode": "disarmed", "alarm": False, "triggered_zone": ""}, "online": True})
    assert all(p["type"] == "cid" for _, p in collector.events())


async def test_subscribe_streams_over_http_and_unsubscribe_cancels(adapter: HikvisionAdapter):
    stream_opened = asyncio.Event()

    async def alert_body():
        stream_opened.set()
        yield multipart(alert_xml("videoloss", "inactive"), alert_xml("VMD", "active"))
        await asyncio.sleep(0.05)
        yield multipart(alert_xml("VMD", "inactive"))
        await asyncio.sleep(3600)  # a real stream never ends; unsubscribe must cancel it

    def alert_stream(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ISAPI/Event/notification/alertStream"
        return httpx.Response(200, headers={"content-type": "multipart/mixed; boundary=boundary"}, content=alert_body())

    server = FakeIsapi({**camera_routes(), ("GET", "/ISAPI/Event/notification/alertStream"): alert_stream})
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
    stream_requests = server.sent("GET", "/ISAPI/Event/notification/alertStream")
    assert len(stream_requests) == 1 and stream_requests[0].headers["Authorization"].startswith("Digest ")
    await unsubscribe()
    await asyncio.sleep(0.05)
    assert len(server.sent("GET", "/ISAPI/Event/notification/alertStream")) == 1  # no reconnect after unsubscribe
    assert await adapter.subscribe([], ctx_for(server)) is None


async def test_subscribe_marks_host_offline_after_repeated_failures(monkeypatch: pytest.MonkeyPatch):
    attempts = 0

    async def failing_stream(session: HostSession, ctx: AdapterContext):
        nonlocal attempts
        del session, ctx
        attempts += 1
        raise AdapterError("boom", "unreachable")
        yield b""  # pylint: disable=unreachable  (makes this an async generator)

    monkeypatch.setattr("app.hub.adapters.hikvision.RECONNECT_MIN_DELAY", 0.001)
    monkeypatch.setattr("app.hub.adapters.hikvision.RECONNECT_MAX_DELAY", 0.001)
    adapter = HikvisionAdapter(stream_opener=failing_stream)
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
    groups = group_by_host([nvr_ref(), channel_ref(1), channel_ref(2), panel_ref(), zone_ref(1)])
    assert len(groups) == 1  # same host/port in the fixtures
    other = channel_ref(3)
    other.config["host"] = "10.0.0.5"
    groups = {g.session.host: g for g in group_by_host([nvr_ref(), channel_ref(1), other])}
    assert set(groups) == {"192.168.1.64", "10.0.0.5"}
    assert groups["192.168.1.64"].primary == NVR_SERIAL and groups["192.168.1.64"].channels == {1: f"{NVR_SERIAL}:ch1"}
    assert groups["10.0.0.5"].primary == NVR_SERIAL and groups["10.0.0.5"].is_recorder
