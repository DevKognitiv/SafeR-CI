"""Camera credentials never reach phones: ``StreamOut`` stripping, the opt-in flag and the generic device schema."""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

import httpx
import pytest

from app.hub.adapters.base import (
    AdapterContext, BrandAdapter, BrandInfo, DeviceDraft, DeviceRef, DeviceState, PairResult, PairingMethod, StreamInfo,
)
from app.hub.adapters.registry import registry
from app.hub.app import create_app
from app.hub.capabilities import camera_caps
from app.hub.runtime import set_runtime
from app.hub.schemas import DeviceOut, StreamOut, split_userinfo
from app.hub.tests.conftest import PREFIX, make_settings, register_user

SECRET = "s3cret@lan"
STREAM = StreamInfo(
    url="rtsp://admin:s3cret%40lan@192.168.1.64:554/Streaming/Channels/101", type="rtsp", username="admin", password=SECRET,
    headers={"Authorization": "Basic YWRtaW46czNjcmV0", "X-Trace": "1"},
)


class FakeCameraAdapter(BrandAdapter):
    """A camera brand whose stream needs the admin credentials, inline in the URL and as fields."""

    brand_id = "fakecam"

    def __init__(self) -> None:
        super().__init__()
        self.stream_info: Optional[StreamInfo] = STREAM

    def info(self) -> BrandInfo:
        return BrandInfo(id=self.brand_id, name="Fake camera", protocols=["fake"], categories=["camera"],
                         methods=[PairingMethod(id="manual", title="Manual")])

    async def pair(self, method_id: str, payload: Dict[str, Any], ctx: AdapterContext) -> PairResult:
        return PairResult(devices=[DeviceDraft(
            external_id="cam-1", name="Caméra entrée", category="camera", protocol="fake", capabilities=camera_caps(),
            state={"stream_main": "rtsp://192.168.1.64:554/Streaming/Channels/101"}, config={"host": "192.168.1.64"},
            credentials={"username": "admin", "password": SECRET},
        )])

    async def refresh(self, device: DeviceRef, ctx: AdapterContext) -> DeviceState:
        return DeviceState(online=True, state={})

    async def stream(self, device: DeviceRef, quality: str, ctx: AdapterContext) -> Optional[StreamInfo]:
        assert device.cred("password") == SECRET  # the adapter still gets the real credentials
        return self.stream_info


@pytest.fixture
def fake_camera():
    """Register the fake camera brand for one test (the registry is process-wide)."""
    adapter = FakeCameraAdapter()
    registry.register(adapter)
    try:
        yield adapter
    finally:
        registry._adapters.pop(adapter.brand_id, None)  # pylint: disable=protected-access


async def paired_camera(http: httpx.AsyncClient, headers: Dict[str, str]) -> dict:
    """Create a home and pair the fake camera into it through the API; returns the DeviceOut dict."""
    home = await http.post(f"{PREFIX}/homes", json={"name": "Maison"}, headers=headers)
    assert home.status_code == 201, home.text
    paired = await http.post(f"{PREFIX}/onboarding/fakecam/pair", json={"home_id": home.json()["id"], "method": "manual", "payload": {}}, headers=headers)
    assert paired.status_code == 201, paired.text
    assert SECRET not in paired.text  # pairing answers with DeviceOut: no credentials
    return paired.json()["devices"][0]


# ----------------------------------------------------------------------------- unit
def test_split_userinfo():
    assert split_userinfo("rtsp://admin:s3cret%40lan@192.168.1.64:554/a?b=1#f") == ("rtsp://192.168.1.64:554/a?b=1#f", "admin", "s3cret@lan")
    assert split_userinfo("rtsp://admin@[fe80::1]:554/a") == ("rtsp://[fe80::1]:554/a", "admin", None)
    assert split_userinfo("rtsp://admin:@cam/a") == ("rtsp://cam/a", "admin", "")
    assert split_userinfo("http://cam/path@with/at") == ("http://cam/path@with/at", None, None)
    assert split_userinfo("not a url") == ("not a url", None, None)


def test_stream_out_strips_everything_by_default():
    out = StreamOut.from_info(STREAM)
    assert out.model_dump() == {
        "url": "rtsp://192.168.1.64:554/Streaming/Channels/101", "type": "rtsp", "headers": {"X-Trace": "1"},
        "auth_required": True, "credentials_included": False, "username": None, "password": None,
    }
    # userinfo only in the URL still counts as credentials
    out = StreamOut.from_info(StreamInfo(url="rtsp://user:pw@cam/x"))
    assert out.url == "rtsp://cam/x" and out.auth_required is True and out.username is None and out.password is None
    # an open stream
    out = StreamOut.from_info(StreamInfo(url="rtsp://demo.safer.local:554/demo", headers={"X-Trace": "1"}))
    assert out.auth_required is False and out.credentials_included is False and out.headers == {"X-Trace": "1"}


def test_stream_out_includes_credentials_only_when_asked():
    out = StreamOut.from_info(STREAM, include_credentials=True)
    assert out.url == "rtsp://192.168.1.64:554/Streaming/Channels/101"  # never inline, the app re-adds them
    assert out.username == "admin" and out.password == SECRET
    assert out.auth_required is True and out.credentials_included is True
    assert out.headers == {"Authorization": "Basic YWRtaW46czNjcmV0", "X-Trace": "1"}
    # credentials that live only in the URL are surfaced as fields
    out = StreamOut.from_info(StreamInfo(url="rtsp://user:p%2Fw@cam/x"), include_credentials=True)
    assert (out.url, out.username, out.password, out.credentials_included) == ("rtsp://cam/x", "user", "p/w", True)
    # nothing to include on an open stream
    out = StreamOut.from_info(StreamInfo(url="rtsp://cam/x"), include_credentials=True)
    assert out.credentials_included is False and out.auth_required is False


def test_device_out_never_carries_credentials():
    """The generic device schema has no credential fields at all, so StreamOut can never leak through it."""
    for name in ("credentials_enc", "credentials", "webhook_secret", "username", "password"):
        assert name not in DeviceOut.model_fields, name


# ----------------------------------------------------------------------------- routes
async def test_stream_route_strips_credentials(client, auth, fake_camera):
    camera = await paired_camera(client, auth["headers"])
    response = await client.get(f"{PREFIX}/devices/{camera['id']}/stream", headers=auth["headers"])
    assert response.status_code == 200, response.text
    assert response.json() == {
        "url": "rtsp://192.168.1.64:554/Streaming/Channels/101", "type": "rtsp", "headers": {"X-Trace": "1"},
        "auth_required": True, "credentials_included": False, "username": None, "password": None,
    }
    for leak in (SECRET, "s3cret", "admin", "Basic "):
        assert leak not in response.text
    # the generic device representations never carry them either
    for url in (f"{PREFIX}/devices/{camera['id']}", f"{PREFIX}/homes/{camera['home_id']}/devices"):
        body = await client.get(url, headers=auth["headers"])
        assert body.status_code == 200 and SECRET not in body.text and "credentials" not in json.dumps(body.json())


async def test_stream_route_includes_credentials_when_owner_opted_in(fake_camera, caplog):
    app = create_app(settings=make_settings(HUB_STREAM_CREDENTIALS_TO_CLIENTS=True), database_url="sqlite+aiosqlite://", start_services=False)
    runtime = app.state.hub_runtime
    with caplog.at_level("WARNING", logger="safer.hub.runtime"):
        await runtime.start()
    assert any("HUB_STREAM_CREDENTIALS_TO_CLIENTS" in record.getMessage() for record in caplog.records)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://hub") as http:
            alice = await register_user(http)
            headers = {"Authorization": f"Bearer {alice['token']}"}
            camera = await paired_camera(http, headers)
            response = await http.get(f"{PREFIX}/devices/{camera['id']}/stream", headers=headers)
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["username"] == "admin" and body["password"] == SECRET
            assert body["auth_required"] is True and body["credentials_included"] is True
            assert body["url"] == "rtsp://192.168.1.64:554/Streaming/Channels/101"
            assert body["headers"] == {"Authorization": "Basic YWRtaW46czNjcmV0", "X-Trace": "1"}
            # an open stream stays open
            fake_camera.stream_info = StreamInfo(url="rtsp://192.168.1.64:554/open")
            body = (await http.get(f"{PREFIX}/devices/{camera['id']}/stream", headers=headers)).json()
            assert body["credentials_included"] is False and body["auth_required"] is False and body["username"] is None
    finally:
        await runtime.stop()
        set_runtime(None)


async def test_stream_route_404_without_stream(client, auth, fake_camera):
    camera = await paired_camera(client, auth["headers"])
    fake_camera.stream_info = None
    assert (await client.get(f"{PREFIX}/devices/{camera['id']}/stream", headers=auth["headers"])).status_code == 404


def test_fake_camera_pairs_with_credentials_in_vault_only(fake_camera):
    """The paired device keeps credentials encrypted, out of ``config``/``state`` (what the app can read)."""
    draft = DeviceDraft(external_id="x", name="x", category="camera", protocol="fake", config={"host": "h"}, credentials={"password": SECRET})
    assert SECRET not in json.dumps(draft.config) and SECRET not in json.dumps(draft.state)
    assert isinstance(fake_camera.stream_info, StreamInfo)
    assert [m.id for m in fake_camera.info().methods] == ["manual"]
