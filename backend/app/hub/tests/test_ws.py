"""WebSocket realtime tests using Starlette's TestClient (runs the lifespan; no background services)."""
from __future__ import annotations

from typing import Any, Dict, List

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.hub import __version__
from app.hub.adapters.registry import registry
from app.hub.app import create_app
from app.hub.events import HubEvent
from app.hub.runtime import set_runtime
from app.hub.schemas import DeviceOut
from app.hub.tests.conftest import PREFIX, make_settings

WS = f"{PREFIX}/ws"


# ----------------------------------------------------------------------------- fixtures / helpers
@pytest.fixture
def tc():
    """TestClient with a fresh in-memory hub; the lifespan starts/stops the runtime."""
    app = create_app(settings=make_settings(), database_url="sqlite+aiosqlite://", start_services=False)
    with TestClient(app) as client:
        yield client
    set_runtime(None)


def register(tc: TestClient, email: str, name: str = "User") -> Dict[str, Any]:
    response = tc.post(f"{PREFIX}/auth/register", json={"email": email, "password": "secret123", "name": name})
    assert response.status_code == 201, response.text
    data = response.json()
    data["headers"] = {"Authorization": f"Bearer {data['token']}"}
    return data


def create_home(tc: TestClient, user: Dict[str, Any], name: str = "Maison") -> Dict[str, Any]:
    response = tc.post(f"{PREFIX}/homes", json={"name": name, "rooms": ["Salon"]}, headers=user["headers"])
    assert response.status_code == 201, response.text
    return response.json()


def pair_demo(tc: TestClient, home_id: str) -> Dict[str, dict]:
    """Pair the demo brand inside the app's event loop (no dependency on the onboarding route)."""
    runtime = tc.app.state.hub_runtime

    async def _pair() -> List[dict]:
        adapter = registry.get("demo")
        adapter._state.clear()  # pylint: disable=protected-access
        result = await adapter.pair("virtual", {}, runtime.ctx_for("demo"))
        async with runtime.db.session() as session:
            rows, _ = await runtime.services["devices"].materialize(session, home_id, None, "demo", result)
            return [DeviceOut.model_validate(row).model_dump(mode="json") for row in rows]

    return {device["external_id"]: device for device in tc.portal.call(_pair)}


def publish(tc: TestClient, event: HubEvent) -> None:
    """Publish on the hub bus from the test thread."""
    runtime = tc.app.state.hub_runtime
    tc.portal.call(runtime.bus.publish, event)


def switch(tc: TestClient, user: Dict[str, Any], device: dict, value: bool) -> dict:
    response = tc.post(
        f"{PREFIX}/devices/{device['id']}/commands", json={"commands": [{"code": "switch", "value": value}]}, headers=user["headers"]
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def alice(tc):
    return register(tc, "alice@safer.ci", "Alice")


@pytest.fixture
def home(tc, alice):
    return create_home(tc, alice, "Maison Cocody")


@pytest.fixture
def devices(tc, home):
    return pair_demo(tc, home["id"])


# ----------------------------------------------------------------------------- authentication
def test_ws_invalid_token_closes_4401(tc, home):
    with pytest.raises(WebSocketDisconnect) as info:
        with tc.websocket_connect(f"{WS}?token=not-a-jwt&home_id={home['id']}") as ws:
            ws.receive_json()
    assert info.value.code == 4401
    with pytest.raises(WebSocketDisconnect) as info:
        with tc.websocket_connect(WS) as ws:  # no token at all
            ws.receive_json()
    assert info.value.code == 4401


def test_ws_non_member_closes_4403(tc, home):
    bob = register(tc, "bob@safer.ci", "Bob")
    with pytest.raises(WebSocketDisconnect) as info:
        with tc.websocket_connect(f"{WS}?token={bob['token']}&home_id={home['id']}") as ws:
            ws.receive_json()
    assert info.value.code == 4403
    with pytest.raises(WebSocketDisconnect) as info:
        with tc.websocket_connect(f"{WS}?token={bob['token']}&home_id=unknown-home") as ws:
            ws.receive_json()
    assert info.value.code == 4403


def test_ws_authorization_header_is_accepted(tc, alice, home):
    with tc.websocket_connect(f"{WS}?home_id={home['id']}", headers=alice["headers"]) as ws:
        hello = ws.receive_json()
    assert hello["type"] == "hello" and hello["home_id"] == home["id"]


# ----------------------------------------------------------------------------- protocol
def test_ws_hello_and_ping_pong(tc, alice, home):
    with tc.websocket_connect(f"{WS}?token={alice['token']}&home_id={home['id']}") as ws:
        hello = ws.receive_json()
        assert hello == {"type": "hello", "home_id": home["id"], "version": __version__, "user_id": alice["user"]["id"]}
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}
        ws.send_json({"type": "ping", "ts": 1234})
        assert ws.receive_json() == {"type": "pong", "ts": 1234}


def test_ws_bad_client_frames_report_errors(tc, alice, home):
    with tc.websocket_connect(f"{WS}?token={alice['token']}&home_id={home['id']}") as ws:
        assert ws.receive_json()["type"] == "hello"
        ws.send_text("{not json")
        assert ws.receive_json() == {"type": "error", "detail": "Invalid JSON"}
        ws.send_json([1, 2, 3])
        assert ws.receive_json()["type"] == "error"
        ws.send_json({"type": "teleport"})
        error = ws.receive_json()
        assert error["type"] == "error" and "teleport" in error["detail"]
        ws.send_json({"type": "ping"})  # still alive
        assert ws.receive_json() == {"type": "pong"}
        ws.send_bytes(b'{"type": "ping", "ts": 7}')  # binary JSON frames are accepted too
        assert ws.receive_json() == {"type": "pong", "ts": 7}
        ws.send_bytes(b"\xff\xfe")  # undecodable bytes -> error frame, connection stays up
        assert ws.receive_json()["type"] == "error"


# ----------------------------------------------------------------------------- event delivery
def test_ws_receives_device_state_after_command(tc, alice, home, devices):
    plug = devices["demo-plug-1"]
    with tc.websocket_connect(f"{WS}?token={alice['token']}&home_id={home['id']}") as ws:
        assert ws.receive_json()["type"] == "hello"
        switch(tc, alice, plug, True)
        frame = ws.receive_json()
        assert frame["type"] == "device.state"
        assert frame["home_id"] == home["id"] and frame["device_id"] == plug["id"]
        assert frame["online"] is True
        assert frame["state"]["switch"] is True and frame["state"]["power"] == 42.5
        assert frame["changed"] == {"switch": True, "power": 42.5}
        switch(tc, alice, plug, False)
        assert ws.receive_json()["changed"] == {"switch": False, "power": 0.0}


def test_ws_receives_device_event_and_message_on_notable_change(tc, alice, home, devices):
    runtime = tc.app.state.hub_runtime
    pir = devices["demo-pir-1"]

    async def _trip() -> None:
        await registry.get("demo").simulate("demo-pir-1", {"motion": True}, runtime.ctx_for("demo"))

    with tc.websocket_connect(f"{WS}?token={alice['token']}&home_id={home['id']}") as ws:
        assert ws.receive_json()["type"] == "hello"
        tc.portal.call(_trip)
        frames = [ws.receive_json() for _ in range(3)]
    by_type = {frame["type"]: frame for frame in frames}
    assert set(by_type) == {"device.state", "device.event", "message.new"}
    assert by_type["device.state"]["device_id"] == pir["id"] and by_type["device.state"]["changed"] == {"motion": True}
    assert by_type["device.event"]["event"]["type"] == "motion" and by_type["device.event"]["event"]["payload"]["value"] is True
    assert by_type["message.new"]["message"]["kind"] == "alarm" and by_type["message.new"]["message"]["device_id"] == pir["id"]


def test_ws_member_of_another_home_does_not_receive_events(tc, alice, home, devices):
    bob = register(tc, "bob@safer.ci", "Bob")
    bob_home = create_home(tc, bob, "Chez Bob")
    plug = devices["demo-plug-1"]
    with tc.websocket_connect(f"{WS}?token={bob['token']}&home_id={bob_home['id']}") as bob_ws, \
            tc.websocket_connect(f"{WS}?token={alice['token']}&home_id={home['id']}") as alice_ws:
        assert bob_ws.receive_json()["type"] == "hello"
        assert alice_ws.receive_json()["type"] == "hello"
        switch(tc, alice, plug, True)
        assert alice_ws.receive_json()["type"] == "device.state"
        # Frames are delivered in order: if Bob had received the state change it would precede his pong
        bob_ws.send_json({"type": "ping"})
        assert bob_ws.receive_json() == {"type": "pong"}
        # Global events (home_id None) reach everyone
        publish(tc, HubEvent("hub.notice", payload={"text": "maintenance"}))
        assert bob_ws.receive_json() == {"type": "hub.notice", "home_id": None, "text": "maintenance"}
        assert alice_ws.receive_json() == {"type": "hub.notice", "home_id": None, "text": "maintenance"}


def test_ws_without_home_id_follows_every_home_of_the_user(tc, alice, home, devices):
    second = create_home(tc, alice, "Résidence secondaire")
    second_devices = pair_demo(tc, second["id"])
    with tc.websocket_connect(f"{WS}?token={alice['token']}") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello" and hello["home_id"] is None
        switch(tc, alice, devices["demo-plug-1"], True)
        assert ws.receive_json()["home_id"] == home["id"]
        switch(tc, alice, second_devices["demo-plug-1"], True)
        assert ws.receive_json()["home_id"] == second["id"]
        # Narrow to the second home without reconnecting
        ws.send_json({"type": "subscribe", "home_id": second["id"]})
        assert ws.receive_json() == {"type": "subscribed", "home_id": second["id"]}
        switch(tc, alice, devices["demo-plug-1"], False)
        switch(tc, alice, second_devices["demo-plug-1"], False)
        frame = ws.receive_json()
        assert frame["type"] == "device.state" and frame["home_id"] == second["id"]
        ws.send_json({"type": "subscribe", "home_id": "not-my-home"})
        assert ws.receive_json()["type"] == "error"


def test_ws_unsubscribes_on_disconnect(tc, alice, home):
    runtime = tc.app.state.hub_runtime
    before = runtime.bus.subscriber_count
    with tc.websocket_connect(f"{WS}?token={alice['token']}&home_id={home['id']}") as ws:
        assert ws.receive_json()["type"] == "hello"
        assert runtime.bus.subscriber_count == before + 1
    assert runtime.bus.subscriber_count == before
