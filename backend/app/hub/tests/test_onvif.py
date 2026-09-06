"""ONVIF adapter tests: WS-Security digest, SOAP parsing, pairing, PTZ, faults, streams, snapshots."""
from __future__ import annotations

import base64
import hashlib
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx
import pytest

from app.hub.adapters.base import AdapterContext, AdapterError, DeviceRef
from app.hub.adapters.onvif import (
    BRAND_ID, METHOD_IP, NS_MEDIA, NS_PTZ, PROTOCOL, OnvifAdapter, build_security_header, fault_to_error,
    format_created, parse_host, parse_soap, password_digest, rebase_url, with_credentials,
)
from app.hub.adapters.registry import registry

USER, PASSWORD = "admin", "Sec ret/123"
HOST, PORT = "192.168.1.20", 8000
SERIAL = "RLC-810A-00112233445566"
SOAP_HEADERS = {"content-type": "application/soap+xml; charset=utf-8"}

SOAP_ENV = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope" '
    'xmlns:tds="http://www.onvif.org/ver10/device/wsdl" xmlns:trt="http://www.onvif.org/ver10/media/wsdl" '
    'xmlns:tptz="http://www.onvif.org/ver20/ptz/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema" '
    'xmlns:ter="http://www.onvif.org/ver10/error">'
    "<SOAP-ENV:Body>{body}</SOAP-ENV:Body></SOAP-ENV:Envelope>"
)


def soap(body: str, status: int = 200) -> httpx.Response:
    return httpx.Response(status, content=SOAP_ENV.format(body=body).encode("utf-8"), headers=SOAP_HEADERS)


def fault(subcode: str, reason: str, status: int = 400) -> httpx.Response:
    body = (
        "<SOAP-ENV:Fault>"
        "<SOAP-ENV:Code><SOAP-ENV:Value>SOAP-ENV:Sender</SOAP-ENV:Value>"
        f"<SOAP-ENV:Subcode><SOAP-ENV:Value>{subcode}</SOAP-ENV:Value></SOAP-ENV:Subcode></SOAP-ENV:Code>"
        f'<SOAP-ENV:Reason><SOAP-ENV:Text xml:lang="en">{reason}</SOAP-ENV:Text></SOAP-ENV:Reason>'
        "</SOAP-ENV:Fault>"
    )
    return soap(body, status)


def strip_ns(root: ET.Element) -> ET.Element:
    for element in root.iter():
        if isinstance(element.tag, str) and element.tag.startswith("{"):
            element.tag = element.tag.split("}", 1)[1]
    return root


def text(element: Optional[ET.Element], path: str) -> str:
    found = element.find(path) if element is not None else None
    return (found.text or "").strip() if found is not None else ""


def md5(value: str) -> str:
    return hashlib.md5(value.encode("utf-8")).hexdigest()


class FakeOnvifCamera:
    """A Reolink-like ONVIF camera behind ``httpx.MockTransport``.

    Verifies the WS-Security PasswordDigest and the ``Created`` timestamp (5 minute window, like real
    cameras) and serves a JPEG snapshot behind HTTP Digest (or Basic) authentication.
    """

    def __init__(
        self,
        username: str = USER,
        password: str = PASSWORD,
        ptz: bool = True,
        profiles: int = 2,
        drift_seconds: float = 0.0,
        capabilities_supported: bool = True,
        snapshot_auth: str = "digest",
        advertised_host: str = HOST,
    ):
        self.username = username
        self.password = password
        self.ptz = ptz
        self.profile_count = profiles
        self.drift = drift_seconds
        self.capabilities_supported = capabilities_supported
        self.snapshot_auth = snapshot_auth
        self.advertised_host = advertised_host
        self.requests: List[Tuple[str, str, str]] = []  # (path, operation, raw body)
        self.snapshot_auth_headers: List[str] = []  # Authorization header of each snapshot request, as sent
        self.nonce = "dcd98b7102dd2f0e8b11d0f600bfb0c093"

    # ------------------------------------------------------------------ helpers
    def now(self) -> datetime:
        return datetime.now(timezone.utc) + timedelta(seconds=self.drift)

    def base(self) -> str:
        return f"http://{self.advertised_host}:{PORT}"

    def operations(self, name: str) -> List[str]:
        return [body for _, op, body in self.requests if op == name]

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)

    def _check_security(self, root: ET.Element) -> Optional[httpx.Response]:
        token = root.find(".//UsernameToken")
        if token is None:
            return fault("ter:NotAuthorized", "Sender not Authorized")
        username = text(token, "Username")
        digest = text(token, "Password")
        nonce = base64.b64decode(text(token, "Nonce"))
        created = text(token, "Created")
        expected = base64.b64encode(hashlib.sha1(nonce + created.encode() + self.password.encode()).digest()).decode()
        if username != self.username or digest != expected:
            return fault("ter:NotAuthorized", "Sender not Authorized")
        created_at = datetime.strptime(created, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
        if abs((created_at - self.now()).total_seconds()) > 300:
            return fault("ter:NotAuthorized", "Sender not Authorized (time out of sync)")
        return None

    # ------------------------------------------------------------------ SOAP responses
    def _date_time(self) -> httpx.Response:
        now = self.now()
        return soap(
            "<tds:GetSystemDateAndTimeResponse><tds:SystemDateAndTime>"
            "<tt:DateTimeType>NTP</tt:DateTimeType><tt:DaylightSavings>false</tt:DaylightSavings>"
            "<tt:TimeZone><tt:TZ>GMT0</tt:TZ></tt:TimeZone>"
            "<tt:UTCDateTime>"
            f"<tt:Time><tt:Hour>{now.hour}</tt:Hour><tt:Minute>{now.minute}</tt:Minute><tt:Second>{now.second}</tt:Second></tt:Time>"
            f"<tt:Date><tt:Year>{now.year}</tt:Year><tt:Month>{now.month}</tt:Month><tt:Day>{now.day}</tt:Day></tt:Date>"
            "</tt:UTCDateTime>"
            "</tds:SystemDateAndTime></tds:GetSystemDateAndTimeResponse>"
        )

    def _device_information(self) -> httpx.Response:
        return soap(
            "<tds:GetDeviceInformationResponse>"
            "<tds:Manufacturer>Reolink</tds:Manufacturer><tds:Model>RLC-810A</tds:Model>"
            "<tds:FirmwareVersion>v3.1.0.2368_23062700</tds:FirmwareVersion>"
            f"<tds:SerialNumber>{SERIAL}</tds:SerialNumber><tds:HardwareId>IPC_560B168MP</tds:HardwareId>"
            "</tds:GetDeviceInformationResponse>"
        )

    def _capabilities(self) -> httpx.Response:
        ptz = f"<tt:PTZ><tt:XAddr>{self.base()}/onvif/ptz_service</tt:XAddr></tt:PTZ>" if self.ptz else ""
        return soap(
            "<tds:GetCapabilitiesResponse><tds:Capabilities>"
            f"<tt:Device><tt:XAddr>{self.base()}/onvif/device_service</tt:XAddr></tt:Device>"
            f"<tt:Events><tt:XAddr>{self.base()}/onvif/event_service</tt:XAddr></tt:Events>"
            f"<tt:Media><tt:XAddr>{self.base()}/onvif/media_service</tt:XAddr>"
            "<tt:StreamingCapabilities><tt:RTPMulticast>false</tt:RTPMulticast><tt:RTP_TCP>true</tt:RTP_TCP>"
            "<tt:RTP_RTSP_TCP>true</tt:RTP_RTSP_TCP></tt:StreamingCapabilities></tt:Media>"
            f"{ptz}"
            "</tds:Capabilities></tds:GetCapabilitiesResponse>"
        )

    def _services(self) -> httpx.Response:
        services = [
            ("http://www.onvif.org/ver10/device/wsdl", f"{self.base()}/onvif/device_service"),
            ("http://www.onvif.org/ver10/media/wsdl", f"{self.base()}/onvif/media_service"),
            ("http://www.onvif.org/ver20/media/wsdl", f"{self.base()}/onvif/media2_service"),
        ]
        if self.ptz:
            services.append(("http://www.onvif.org/ver20/ptz/wsdl", f"{self.base()}/onvif/ptz_service"))
        items = "".join(
            f"<tds:Service><tds:Namespace>{ns}</tds:Namespace><tds:XAddr>{xaddr}</tds:XAddr>"
            "<tds:Version><tt:Major>2</tt:Major><tt:Minor>6</tt:Minor></tds:Version></tds:Service>"
            for ns, xaddr in services
        )
        return soap(f"<tds:GetServicesResponse>{items}</tds:GetServicesResponse>")

    def _profiles(self) -> httpx.Response:
        specs = [("000", "mainStream", 3840, 2160, "H265"), ("001", "subStream", 640, 360, "H264")][: self.profile_count]
        items = "".join(
            f'<trt:Profiles token="{token}" fixed="true"><tt:Name>{name}</tt:Name>'
            f'<tt:VideoSourceConfiguration token="000"><tt:Name>VideoSourceConfig</tt:Name>'
            "<tt:SourceToken>000</tt:SourceToken></tt:VideoSourceConfiguration>"
            f'<tt:VideoEncoderConfiguration token="{token}"><tt:Name>{name}Encoder</tt:Name>'
            f"<tt:Encoding>{encoding}</tt:Encoding><tt:Resolution><tt:Width>{width}</tt:Width>"
            f"<tt:Height>{height}</tt:Height></tt:Resolution><tt:Quality>4</tt:Quality>"
            "</tt:VideoEncoderConfiguration></trt:Profiles>"
            for token, name, width, height, encoding in specs
        )
        return soap(f"<trt:GetProfilesResponse>{items}</trt:GetProfilesResponse>")

    def _stream_uri(self, body: ET.Element) -> httpx.Response:
        token = text(body, ".//ProfileToken")
        if token not in ("000", "001"):
            return fault("ter:InvalidArgVal/ter:NoProfile", "The requested profile token does not exist")
        path = "h265Preview_01_main" if token == "000" else "h264Preview_01_sub"
        return soap(
            "<trt:GetStreamUriResponse><trt:MediaUri>"
            f"<tt:Uri>rtsp://{self.advertised_host}:554/{path}</tt:Uri>"
            "<tt:InvalidAfterConnect>false</tt:InvalidAfterConnect><tt:InvalidAfterReboot>false</tt:InvalidAfterReboot>"
            "<tt:Timeout>PT0S</tt:Timeout></trt:MediaUri></trt:GetStreamUriResponse>"
        )

    def _snapshot_uri(self) -> httpx.Response:
        return soap(
            "<trt:GetSnapshotUriResponse><trt:MediaUri>"
            f"<tt:Uri>{self.base()}/cgi-bin/api.cgi?cmd=Snap&amp;channel=0</tt:Uri>"
            "<tt:InvalidAfterConnect>false</tt:InvalidAfterConnect><tt:InvalidAfterReboot>false</tt:InvalidAfterReboot>"
            "<tt:Timeout>PT0S</tt:Timeout></trt:MediaUri></trt:GetSnapshotUriResponse>"
        )

    # ------------------------------------------------------------------ snapshot auth
    def _snapshot(self, request: httpx.Request) -> httpx.Response:
        authorization = request.headers.get("authorization", "")
        self.snapshot_auth_headers.append(authorization)
        if self.snapshot_auth == "basic":
            expected = "Basic " + base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
            if authorization == expected:
                return httpx.Response(200, content=b"\xff\xd8\xff\xe0JPEG-BASIC", headers={"content-type": "image/jpeg"})
            return httpx.Response(401, headers={"www-authenticate": 'Basic realm="IPCam"'})
        if authorization.startswith("Digest ") and self._digest_ok(request, authorization):
            return httpx.Response(200, content=b"\xff\xd8\xff\xe0JPEG-DIGEST", headers={"content-type": "image/jpeg"})
        return httpx.Response(
            401, headers={"www-authenticate": f'Digest realm="IPCam", nonce="{self.nonce}", qop="auth", algorithm=MD5'}
        )

    def _digest_ok(self, request: httpx.Request, header: str) -> bool:
        fields = {key: quoted or bare for key, quoted, bare in re.findall(r'(\w+)=(?:"([^"]*)"|([^,\s]*))', header)}
        if fields.get("username") != self.username or fields.get("realm") != "IPCam":
            return False
        ha1 = md5(f"{self.username}:IPCam:{self.password}")
        ha2 = md5(f"{request.method}:{fields.get('uri')}")
        expected = md5(f"{ha1}:{self.nonce}:{fields.get('nc')}:{fields.get('cnonce')}:auth:{ha2}")
        return fields.get("response") == expected

    # ------------------------------------------------------------------ dispatcher
    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/cgi-bin/api.cgi":
            return self._snapshot(request)
        if request.headers.get("content-type", "").split(";")[0] != "application/soap+xml":
            return httpx.Response(415, content=b"unsupported media type")
        root = strip_ns(ET.fromstring(request.content))
        body = root.find("Body")
        operation = body[0].tag if body is not None and len(body) else ""
        self.requests.append((path, operation, request.content.decode("utf-8")))
        if operation == "GetSystemDateAndTime":
            return self._date_time()
        error = self._check_security(root)
        if error is not None:
            return error
        if path == "/onvif/device_service":
            if operation == "GetDeviceInformation":
                return self._device_information()
            if operation == "GetCapabilities":
                if not self.capabilities_supported:
                    return fault("ter:ActionNotSupported", "Optional Action Not Implemented", status=500)
                return self._capabilities()
            if operation == "GetServices":
                return self._services()
        elif path == "/onvif/media_service":
            if operation == "GetProfiles":
                return self._profiles()
            if operation == "GetStreamUri":
                return self._stream_uri(body)
            if operation == "GetSnapshotUri":
                return self._snapshot_uri()
        elif path == "/onvif/ptz_service" and self.ptz:
            if operation == "ContinuousMove":
                return soap("<tptz:ContinuousMoveResponse/>")
            if operation == "Stop":
                return soap("<tptz:StopResponse/>")
        return fault("ter:ActionNotSupported", f"{operation} not implemented", status=500)


def ctx_for(camera: FakeOnvifCamera) -> AdapterContext:
    return AdapterContext(transport=camera.transport())


def payload(**overrides: Any) -> Dict[str, Any]:
    data = {"host": HOST, "port": PORT, "username": USER, "password": PASSWORD, "name": "Caméra entrée"}
    data.update(overrides)
    return data


def device_ref(draft: Any) -> DeviceRef:
    return DeviceRef(
        id="dev-1", external_id=draft.external_id, brand=BRAND_ID, protocol=PROTOCOL, category=draft.category,
        config=dict(draft.config), credentials=dict(draft.credentials), state=dict(draft.state),
        capabilities=list(draft.capabilities), name=draft.name,
    )


# =============================================================================== unit tests
def test_registered_and_info():
    adapter = registry.get(BRAND_ID)
    assert isinstance(adapter, OnvifAdapter)
    info = adapter.info()
    assert info.protocols == [PROTOCOL]
    method = adapter.method(METHOD_IP)
    names = [f.name for f in method.fields]
    assert names == ["host", "port", "username", "password", "name"]
    assert next(f for f in method.fields if f.name == "port").default == 80
    assert next(f for f in method.fields if f.name == "password").type == "password"
    assert next(f for f in method.fields if f.name == "name").required is False


def test_password_digest_matches_independent_computation():
    nonce = b"\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f\x10"
    created = "2026-09-06T10:22:05.123Z"
    expected = base64.b64encode(hashlib.sha1(nonce + created.encode() + PASSWORD.encode()).digest()).decode()
    assert password_digest(nonce, created, PASSWORD) == expected

    header = build_security_header("ad<min>", PASSWORD, nonce=nonce, created=created)
    root = strip_ns(ET.fromstring(header))
    token = root.find("UsernameToken")
    assert text(token, "Username") == "ad<min>"
    assert text(token, "Password") == expected
    assert token.find("Password").get("Type").endswith("#PasswordDigest")
    assert base64.b64decode(text(token, "Nonce")) == nonce
    assert token.find("Nonce").get("EncodingType").endswith("#Base64Binary")
    assert text(token, "Created") == created

    # Fresh headers use a random nonce and an ISO-8601 UTC timestamp
    fresh = strip_ns(ET.fromstring(build_security_header(USER, PASSWORD)))
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", text(fresh, "UsernameToken/Created"))
    assert len(base64.b64decode(text(fresh, "UsernameToken/Nonce"))) == 16
    assert format_created(datetime(2026, 9, 6, 10, 22, 5, 123456, tzinfo=timezone.utc)) == "2026-09-06T10:22:05.123Z"


def test_soap_fault_mapping_and_non_soap_answers():
    unauthorized = fault("ter:NotAuthorized", "Sender not Authorized")
    with pytest.raises(AdapterError) as excinfo:
        parse_soap(unauthorized.content)
    assert excinfo.value.code == "auth_failed"

    unsupported = strip_ns(ET.fromstring(fault("ter:ActionNotSupported", "Optional Action Not Implemented").content))
    assert fault_to_error(unsupported.find(".//Fault")).code == "unsupported"
    missing = strip_ns(ET.fromstring(fault("ter:InvalidArgVal/ter:NoProfile", "Profile does not exist").content))
    assert fault_to_error(missing.find(".//Fault")).code == "not_found"

    with pytest.raises(AdapterError) as excinfo:
        parse_soap(b"<html><body>Login</body></html>")
    assert excinfo.value.code == "invalid_input"
    with pytest.raises(AdapterError) as excinfo:
        parse_soap(b"garbage")
    assert excinfo.value.code == "invalid_input"


def test_url_helpers():
    assert parse_host("192.168.1.20") == ("192.168.1.20", 80)
    assert parse_host("cam.local:8899", 80) == ("cam.local", 8899)
    assert parse_host("http://cam.local:8000/onvif/device_service") == ("cam.local", 8000)
    assert parse_host("cam.local", 2020) == ("cam.local", 2020)
    with pytest.raises(AdapterError):
        parse_host("")
    assert with_credentials("rtsp://10.0.0.5:554/main", "ad min", "p@ss:word") == "rtsp://ad%20min:p%40ss%3Aword@10.0.0.5:554/main"
    assert with_credentials("rtsp://old:x@10.0.0.5/main", "u", "p") == "rtsp://u:p@10.0.0.5/main"
    assert rebase_url("http://10.0.0.5/onvif/media_service", "cam.local", 8000) == "http://cam.local:8000/onvif/media_service"
    assert rebase_url("rtsp://10.0.0.5:554/main", "cam.local") == "rtsp://cam.local:554/main"
    assert rebase_url("rtsp://cam.local:554/main", "cam.local", 8000) == "rtsp://cam.local:554/main"


# =============================================================================== pairing
async def test_pair_parses_device_info_profiles_and_uris():
    camera = FakeOnvifCamera()
    adapter = OnvifAdapter()
    result = await adapter.pair(METHOD_IP, payload(), ctx_for(camera))

    assert len(result.devices) == 1
    draft = result.devices[0]
    assert draft.external_id == SERIAL
    assert draft.name == "Caméra entrée"
    assert draft.category == "camera" and draft.protocol == PROTOCOL
    assert (draft.manufacturer, draft.model, draft.firmware) == ("Reolink", "RLC-810A", "v3.1.0.2368_23062700")
    assert draft.config["host"] == HOST and draft.config["port"] == PORT
    assert draft.config["profile_main"] == "000" and draft.config["profile_sub"] == "001"
    assert draft.config["media_xaddr"] == f"http://{HOST}:{PORT}/onvif/media_service"
    assert draft.config["ptz_xaddr"] == f"http://{HOST}:{PORT}/onvif/ptz_service"
    assert draft.config["resolution_main"] == "3840x2160" and draft.config["resolution_sub"] == "640x360"
    assert draft.credentials == {"username": USER, "password": PASSWORD}
    assert draft.state["stream_main"] == f"rtsp://{HOST}:554/h265Preview_01_main"
    assert draft.state["stream_sub"] == f"rtsp://{HOST}:554/h264Preview_01_sub"
    assert draft.state["snapshot"] == f"http://{HOST}:{PORT}/cgi-bin/api.cgi?cmd=Snap&channel=0"
    codes = {c["code"] for c in draft.capabilities}
    assert {"stream_main", "stream_sub", "snapshot", "ptz"} <= codes
    assert result.integration is None

    # The request went to the conventional device service with a SOAP 1.2 action header
    operations = [op for _, op, _ in camera.requests]
    assert operations[:3] == ["GetSystemDateAndTime", "GetDeviceInformation", "GetCapabilities"]
    assert "GetServices" not in operations
    body = camera.operations("GetStreamUri")[0]
    assert "RTP-Unicast" in body and "<tt:Protocol>RTSP</tt:Protocol>" in body


async def test_pair_falls_back_to_get_services_and_default_name_without_ptz():
    camera = FakeOnvifCamera(ptz=False, profiles=1, capabilities_supported=False)
    adapter = OnvifAdapter()
    result = await adapter.pair(METHOD_IP, payload(name=""), ctx_for(camera))
    draft = result.devices[0]
    assert draft.name == "Reolink RLC-810A"
    assert "GetServices" in [op for _, op, _ in camera.requests]
    assert draft.config["ptz_xaddr"] is None
    assert "ptz" not in {c["code"] for c in draft.capabilities}
    # single profile: sub stream falls back to the main stream
    assert draft.config["profile_sub"] == "000"
    assert draft.state["stream_sub"] == draft.state["stream_main"]


async def test_pair_rebases_urls_when_camera_advertises_another_address():
    camera = FakeOnvifCamera(advertised_host="10.10.10.10")
    result = await OnvifAdapter().pair(METHOD_IP, payload(), ctx_for(camera))
    draft = result.devices[0]
    assert draft.config["media_xaddr"] == f"http://{HOST}:{PORT}/onvif/media_service"
    assert draft.state["stream_main"] == f"rtsp://{HOST}:554/h265Preview_01_main"
    assert draft.state["snapshot"].startswith(f"http://{HOST}:{PORT}/cgi-bin/")


async def test_pair_compensates_camera_clock_drift():
    camera = FakeOnvifCamera(drift_seconds=15 * 60)  # camera clock 15 minutes ahead
    adapter = OnvifAdapter()
    result = await adapter.pair(METHOD_IP, payload(), ctx_for(camera))
    assert result.devices[0].external_id == SERIAL
    created = re.search(r"<wsu:Created>([^<]+)</wsu:Created>", camera.operations("GetDeviceInformation")[0]).group(1)
    created_at = datetime.strptime(created, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    assert abs((created_at - camera.now()).total_seconds()) < 30


async def test_pair_wrong_password_is_auth_failed():
    camera = FakeOnvifCamera()
    with pytest.raises(AdapterError) as excinfo:
        await OnvifAdapter().pair(METHOD_IP, payload(password="nope"), ctx_for(camera))
    assert excinfo.value.code == "auth_failed"


async def test_pair_http_401_is_auth_failed():
    def handler(request: httpx.Request) -> httpx.Response:
        if b"GetSystemDateAndTime" in request.content:
            return FakeOnvifCamera()._date_time()  # pylint: disable=protected-access
        return httpx.Response(401, headers={"www-authenticate": 'Digest realm="ONVIF"'})

    with pytest.raises(AdapterError) as excinfo:
        await OnvifAdapter().pair(METHOD_IP, payload(), AdapterContext(transport=httpx.MockTransport(handler)))
    assert excinfo.value.code == "auth_failed"


async def test_pair_unreachable_and_non_soap():
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=request)

    with pytest.raises(AdapterError) as excinfo:
        await OnvifAdapter().pair(METHOD_IP, payload(), AdapterContext(transport=httpx.MockTransport(refuse)))
    assert excinfo.value.code == "unreachable"

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(AdapterError) as excinfo:
        await OnvifAdapter().pair(METHOD_IP, payload(), AdapterContext(transport=httpx.MockTransport(timeout)))
    assert excinfo.value.code == "unreachable"

    def web_ui(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<!DOCTYPE html><html><body>Camera login</body></html>", headers={"content-type": "text/html"})

    with pytest.raises(AdapterError) as excinfo:
        await OnvifAdapter().pair(METHOD_IP, payload(), AdapterContext(transport=httpx.MockTransport(web_ui)))
    assert excinfo.value.code == "invalid_input"

    def not_found(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, content=b"Not Found")

    with pytest.raises(AdapterError) as excinfo:
        await OnvifAdapter().pair(METHOD_IP, payload(), AdapterContext(transport=httpx.MockTransport(not_found)))
    assert excinfo.value.code == "invalid_input"


async def test_pair_requires_fields():
    with pytest.raises(AdapterError) as excinfo:
        await OnvifAdapter().pair(METHOD_IP, {"host": HOST}, AdapterContext())
    assert excinfo.value.code == "invalid_input"
    with pytest.raises(AdapterError):
        await OnvifAdapter().pair("bogus", payload(), AdapterContext())


# =============================================================================== runtime
async def test_ptz_bodies_and_auto_stop():
    camera = FakeOnvifCamera()
    adapter = OnvifAdapter(ptz_speed=0.5, ptz_step_seconds=0.01)
    ctx = ctx_for(camera)
    ref = device_ref((await adapter.pair(METHOD_IP, payload(), ctx)).devices[0])
    camera.requests.clear()

    assert await adapter.send_command(ref, "ptz", "left", ctx) == {}
    ptz_calls = [(path, op) for path, op, _ in camera.requests if path == "/onvif/ptz_service"]
    assert ptz_calls == [("/onvif/ptz_service", "ContinuousMove"), ("/onvif/ptz_service", "Stop")]
    move = strip_ns(ET.fromstring(camera.operations("ContinuousMove")[0]))
    assert text(move, ".//ContinuousMove/ProfileToken") == "000"
    pan_tilt = move.find(".//Velocity/PanTilt")
    assert (pan_tilt.get("x"), pan_tilt.get("y")) == ("-0.5", "0")
    assert move.find(".//Velocity/Zoom").get("x") == "0"
    assert text(move, ".//ContinuousMove/Timeout") == "PT1S"
    raw = camera.operations("ContinuousMove")[0]
    assert f'action="{NS_PTZ}/ContinuousMove"' not in raw  # action lives in the Content-Type header, not the body
    assert "<wsse:Security" in raw and "<wsu:Created>" in raw
    stop = strip_ns(ET.fromstring(camera.operations("Stop")[0]))
    assert text(stop, ".//Stop/PanTilt") == "true" and text(stop, ".//Stop/Zoom") == "true"

    camera.requests.clear()
    await adapter.send_command(ref, "ptz", "zoom_in", ctx)
    move = strip_ns(ET.fromstring(camera.operations("ContinuousMove")[0]))
    assert move.find(".//Velocity/Zoom").get("x") == "0.5"
    assert move.find(".//Velocity/PanTilt").get("x") == "0"

    camera.requests.clear()
    await adapter.send_command(ref, "ptz", "stop", ctx)
    assert [op for _, op, _ in camera.requests if op in ("ContinuousMove", "Stop")] == ["Stop"]

    with pytest.raises(AdapterError) as excinfo:
        await adapter.send_command(ref, "ptz", "sideways", ctx)
    assert excinfo.value.code == "invalid_input"
    with pytest.raises(AdapterError) as excinfo:
        await adapter.send_command(ref, "siren", True, ctx)
    assert excinfo.value.code == "unsupported"


async def test_ptz_unsupported_without_ptz_service():
    camera = FakeOnvifCamera(ptz=False)
    adapter = OnvifAdapter(ptz_step_seconds=0)
    ctx = ctx_for(camera)
    ref = device_ref((await adapter.pair(METHOD_IP, payload(), ctx)).devices[0])
    with pytest.raises(AdapterError) as excinfo:
        await adapter.send_command(ref, "ptz", "left", ctx)
    assert excinfo.value.code == "unsupported"


async def test_stream_injects_credentials():
    camera = FakeOnvifCamera()
    adapter = OnvifAdapter()
    ctx = ctx_for(camera)
    ref = device_ref((await adapter.pair(METHOD_IP, payload(), ctx)).devices[0])

    main = await adapter.stream(ref, "main", ctx)
    assert main.type == "rtsp"
    assert main.url == f"rtsp://admin:Sec%20ret%2F123@{HOST}:554/h265Preview_01_main"
    assert (main.username, main.password) == (USER, PASSWORD)
    sub = await adapter.stream(ref, "sub", ctx)
    assert sub.url == f"rtsp://admin:Sec%20ret%2F123@{HOST}:554/h264Preview_01_sub"

    # No cached URL: the adapter asks the camera again (GetStreamUri) instead of failing
    ref.state = {}
    camera.requests.clear()
    fetched = await adapter.stream(ref, "sub", ctx)
    assert fetched.url.endswith("/h264Preview_01_sub")
    assert "GetStreamUri" in [op for _, op, _ in camera.requests]


async def test_refresh_reports_reachability():
    camera = FakeOnvifCamera()
    adapter = OnvifAdapter()
    ref = device_ref((await adapter.pair(METHOD_IP, payload(), ctx_for(camera))).devices[0])
    camera.requests.clear()

    state = await adapter.refresh(ref, ctx_for(camera))
    assert state.online is True
    assert [op for _, op, _ in camera.requests] == ["GetSystemDateAndTime"]
    # GetSystemDateAndTime is sent without WS-Security (cameras answer it unauthenticated)
    assert "UsernameToken" not in camera.requests[0][2]

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("No route to host", request=request)

    offline = await adapter.refresh(ref, AdapterContext(transport=httpx.MockTransport(refuse)))
    assert offline.online is False

    def web_ui(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>not onvif</html>", headers={"content-type": "text/html"})

    with pytest.raises(AdapterError) as excinfo:
        await adapter.refresh(ref, AdapterContext(transport=httpx.MockTransport(web_ui)))
    assert excinfo.value.code == "invalid_input"


async def test_snapshot_digest_then_basic_fallback():
    camera = FakeOnvifCamera(snapshot_auth="digest")
    adapter = OnvifAdapter()
    ctx = ctx_for(camera)
    ref = device_ref((await adapter.pair(METHOD_IP, payload(), ctx)).devices[0])

    image = await adapter.snapshot(ref, ctx)
    assert image == b"\xff\xd8\xff\xe0JPEG-DIGEST"
    assert [bool(header) for header in camera.snapshot_auth_headers] == [False, True]
    assert camera.snapshot_auth_headers[-1].startswith("Digest ")

    basic_camera = FakeOnvifCamera(snapshot_auth="basic")
    image = await adapter.snapshot(ref, ctx_for(basic_camera))
    assert image == b"\xff\xd8\xff\xe0JPEG-BASIC"
    assert basic_camera.snapshot_auth_headers[-1].startswith("Basic ")

    wrong = FakeOnvifCamera(password="other")
    with pytest.raises(AdapterError) as excinfo:
        await adapter.snapshot(ref, ctx_for(wrong))
    assert excinfo.value.code == "auth_failed"

    # Without a cached snapshot URI the adapter asks the media service first
    ref.state = {}
    fresh = FakeOnvifCamera()
    image = await adapter.snapshot(ref, ctx_for(fresh))
    assert image.startswith(b"\xff\xd8")
    assert "GetSnapshotUri" in [op for _, op, _ in fresh.requests]


async def test_media_action_headers_use_soap12_content_type():
    camera = FakeOnvifCamera()
    seen: List[str] = []

    def spy(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("content-type", ""))
        return camera.handler(request)

    await OnvifAdapter().pair(METHOD_IP, payload(), AdapterContext(transport=httpx.MockTransport(spy)))
    assert all(value.startswith("application/soap+xml; charset=utf-8; action=") for value in seen)
    assert any(f'action="{NS_MEDIA}/GetProfiles"' in value for value in seen)
