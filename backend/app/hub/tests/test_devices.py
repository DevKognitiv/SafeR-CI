"""Device routes, poller and subscription manager tests (demo brand + in-module fake adapters, no network)."""
from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, List, Optional

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import select

from app.hub import events as ev
from app.hub.adapters.base import (
    AdapterContext, AdapterError, BrandAdapter, BrandInfo, DeviceDraft, DeviceRef, DeviceState, PairResult,
    PairingMethod,
)
from app.hub.adapters.registry import registry
from app.hub.capabilities import switch_caps
from app.hub.models import Device, DeviceEvent, Message
from app.hub.schemas import DeviceOut
from app.hub.services.poller import Poller
from app.hub.services.subscriptions import SubscriptionManager
from app.hub.tests.conftest import PREFIX, register_user

DEMO_DEVICE_COUNT = 13


# ----------------------------------------------------------------------------- fake adapters
class FakePollAdapter(BrandAdapter):
    """Brand without push: the poller must refresh it; ``fail_with`` makes ``refresh`` raise."""

    brand_id = "fakepoll"

    def __init__(self) -> None:
        self.refreshes = 0
        self.fail_with: Optional[str] = None
        self.state: Dict[str, Any] = {"switch": True}

    def info(self) -> BrandInfo:
        return BrandInfo(id=self.brand_id, name="Fake polled brand", protocols=["fake"], categories=["plug"],
                         methods=[PairingMethod(id="manual", title="Manual")])

    async def pair(self, method_id: str, payload: Dict[str, Any], ctx: AdapterContext) -> PairResult:
        return PairResult(devices=[draft("fp-1")])

    async def refresh(self, device: DeviceRef, ctx: AdapterContext) -> DeviceState:
        self.refreshes += 1
        if self.fail_with:
            raise AdapterError(f"simulated {self.fail_with}", self.fail_with)
        return DeviceState(online=True, state=dict(self.state))


class FakePushAdapter(FakePollAdapter):
    """Brand with push: the subscription manager must call ``subscribe`` and keep the unsubscribe."""

    brand_id = "fakepush"

    def __init__(self) -> None:
        super().__init__()
        self.subscriptions: List[List[DeviceRef]] = []
        self.unsubscribed = 0

    async def subscribe(self, devices: List[DeviceRef], ctx: AdapterContext):
        self.subscriptions.append(list(devices))

        async def _unsubscribe() -> None:
            self.unsubscribed += 1

        return _unsubscribe


def draft(external_id: str, **extra: Any) -> DeviceDraft:
    """A one-gang plug draft for the fake brands."""
    values = dict(external_id=external_id, name=f"Fake {external_id}", category="plug", protocol="fake",
                  capabilities=switch_caps(), state={"switch": False})
    values.update(extra)
    return DeviceDraft(**values)


@pytest.fixture
def fake_adapters():
    """Register the fake brands for one test and remove them afterwards (the registry is process-wide)."""
    poll, push = FakePollAdapter(), FakePushAdapter()
    registry.register(poll)
    registry.register(push)
    try:
        yield poll, push
    finally:
        registry._adapters.pop(poll.brand_id, None)  # pylint: disable=protected-access
        registry._adapters.pop(push.brand_id, None)  # pylint: disable=protected-access


# ----------------------------------------------------------------------------- helpers / fixtures
async def materialize(hub_app: FastAPI, home_id: str, brand: str, result: PairResult, room_id: Optional[str] = None) -> List[dict]:
    runtime = hub_app.state.hub_runtime
    async with runtime.db.session() as session:
        rows, _ = await runtime.services["devices"].materialize(session, home_id, room_id, brand, result)
        return [DeviceOut.model_validate(row).model_dump(mode="json") for row in rows]


async def pair_demo(hub_app: FastAPI, home_id: str) -> Dict[str, dict]:
    """Pair the demo brand directly through the device service; devices keyed by external id."""
    runtime = hub_app.state.hub_runtime
    adapter = registry.get("demo")
    # Process-wide singleton: start every test from the blueprint state
    adapter._state.clear()  # pylint: disable=protected-access
    result = await adapter.pair("virtual", {}, runtime.ctx_for("demo"))
    return {device["external_id"]: device for device in await materialize(hub_app, home_id, "demo", result)}


@pytest_asyncio.fixture
async def devices(hub_app: FastAPI, home: Dict) -> Dict[str, dict]:
    """Demo devices paired into ``home``, keyed by external id."""
    return await pair_demo(hub_app, home["id"])


@pytest_asyncio.fixture
async def member(client: httpx.AsyncClient, auth: Dict, home: Dict) -> Dict:
    """A plain member of ``home`` (Bob)."""
    data = await register_user(client, email="bob@safer.ci", name="Bob")
    data["headers"] = {"Authorization": f"Bearer {data['token']}"}
    response = await client.post(f"{PREFIX}/homes/{home['id']}/members", json={"email": "bob@safer.ci", "role": "member"}, headers=auth["headers"])
    assert response.status_code == 201, response.text
    return data


def demo_ref(device: dict) -> DeviceRef:
    return DeviceRef(id=device["id"], external_id=device["external_id"], brand="demo", protocol="demo",
                     category=device["category"], state=dict(device["state"]))


def collect_events(hub_app: FastAPI, *types: str) -> List[ev.HubEvent]:
    """Subscribe to the bus and return the list that receives matching events."""
    seen: List[ev.HubEvent] = []

    async def _listener(event: ev.HubEvent) -> None:
        if not types or event.type in types:
            seen.append(event)

    hub_app.state.hub_runtime.bus.subscribe(_listener)
    return seen


async def wait_until(predicate: Callable[[], bool], timeout: float = 2.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.01)


# ----------------------------------------------------------------------------- listing / get
async def test_list_devices_ordered_and_serialised(client, auth, home, devices):
    response = await client.get(f"{PREFIX}/homes/{home['id']}/devices", headers=auth["headers"])
    assert response.status_code == 200, response.text
    items = response.json()
    assert len(items) == len(devices) == DEMO_DEVICE_COUNT
    assert [item["created_at"] for item in items] == sorted(item["created_at"] for item in items)
    assert {item["external_id"] for item in items} == set(devices)
    light = next(item for item in items if item["external_id"] == "demo-light-1")
    assert light["brand"] == "demo" and light["protocol"] == "demo" and light["category"] == "light"
    assert light["state"]["brightness"] == 80 and light["online"] is True
    assert {cap["code"] for cap in light["capabilities"]} >= {"switch", "brightness", "color_temp", "color", "work_mode"}
    assert light["config"] == {"virtual": True}
    assert "credentials" not in light and "credentials_enc" not in light
    zone = next(item for item in items if item["external_id"] == "demo-zone-1")
    assert zone["parent_id"] == devices["demo-panel-1"]["id"]


async def test_list_devices_filters(client, auth, home, devices):
    salon = home["rooms"][0]["id"]
    light = devices["demo-light-1"]
    moved = await client.patch(f"{PREFIX}/devices/{light['id']}", json={"room_id": salon}, headers=auth["headers"])
    assert moved.status_code == 200 and moved.json()["room_id"] == salon

    async def listed(**params: str) -> List[str]:
        response = await client.get(f"{PREFIX}/homes/{home['id']}/devices", params=params, headers=auth["headers"])
        assert response.status_code == 200, response.text
        return [item["external_id"] for item in response.json()]

    assert await listed(room_id=salon) == ["demo-light-1"]
    assert await listed(room_id=home["rooms"][1]["id"]) == []
    assert await listed(category="sensor_contact") == ["demo-door-1"]
    assert len(await listed(brand="demo")) == DEMO_DEVICE_COUNT
    assert await listed(brand="tuya") == []
    assert await listed(category="light", room_id=salon) == ["demo-light-1"]
    assert await listed(category="plug", room_id=salon) == []
    # Room counts follow the assignment
    rooms = await client.get(f"{PREFIX}/homes/{home['id']}/rooms", headers=auth["headers"])
    assert next(room for room in rooms.json() if room["id"] == salon)["device_count"] == 1


async def test_get_device_and_membership(client, auth, home, devices):
    plug = devices["demo-plug-1"]
    response = await client.get(f"{PREFIX}/devices/{plug['id']}", headers=auth["headers"])
    assert response.status_code == 200
    assert response.json()["id"] == plug["id"] and response.json()["home_id"] == home["id"]
    assert (await client.get(f"{PREFIX}/devices/does-not-exist", headers=auth["headers"])).status_code == 404
    assert (await client.get(f"{PREFIX}/devices/{plug['id']}")).status_code == 401

    stranger = await register_user(client, email="eve@safer.ci", name="Eve")
    headers = {"Authorization": f"Bearer {stranger['token']}"}
    assert (await client.get(f"{PREFIX}/devices/{plug['id']}", headers=headers)).status_code == 404
    assert (await client.get(f"{PREFIX}/homes/{home['id']}/devices", headers=headers)).status_code == 404


# ----------------------------------------------------------------------------- patch
async def test_patch_device(client, auth, home, devices):
    light = devices["demo-light-1"]
    url = f"{PREFIX}/devices/{light['id']}"
    response = await client.patch(url, json={"name": "  Plafonnier  ", "icon": "light"}, headers=auth["headers"])
    assert response.status_code == 200, response.text
    assert response.json()["name"] == "Plafonnier" and response.json()["icon"] == "light"
    assert (await client.patch(url, json={"name": "   "}, headers=auth["headers"])).status_code == 400
    assert (await client.patch(url, json={"name": ""}, headers=auth["headers"])).status_code == 422

    chambre = home["rooms"][1]["id"]
    response = await client.patch(url, json={"room_id": chambre}, headers=auth["headers"])
    assert response.status_code == 200 and response.json()["room_id"] == chambre
    response = await client.patch(url, json={"clear_room": True}, headers=auth["headers"])
    assert response.status_code == 200 and response.json()["room_id"] is None
    response = await client.patch(url, json={"room_id": chambre}, headers=auth["headers"])
    assert response.json()["room_id"] == chambre
    response = await client.patch(url, json={"room_id": None}, headers=auth["headers"])
    assert response.status_code == 200 and response.json()["room_id"] is None
    # Unrelated fields survive an empty patch
    response = await client.patch(url, json={}, headers=auth["headers"])
    assert response.status_code == 200 and response.json()["name"] == "Plafonnier"


async def test_patch_device_room_from_another_home_is_400(client, auth, home, devices):
    other = await client.post(f"{PREFIX}/homes", json={"name": "Bureau", "rooms": ["Open space"]}, headers=auth["headers"])
    assert other.status_code == 201
    foreign_room = other.json()["rooms"][0]["id"]
    light = devices["demo-light-1"]
    response = await client.patch(f"{PREFIX}/devices/{light['id']}", json={"room_id": foreign_room}, headers=auth["headers"])
    assert response.status_code == 400
    assert "home" in response.json()["detail"].lower()
    response = await client.patch(f"{PREFIX}/devices/{light['id']}", json={"room_id": "missing-room"}, headers=auth["headers"])
    assert response.status_code == 400
    unchanged = await client.get(f"{PREFIX}/devices/{light['id']}", headers=auth["headers"])
    assert unchanged.json()["room_id"] is None


async def test_member_cannot_manage_but_can_control(client, home, devices, member):
    light = devices["demo-light-1"]
    assert (await client.patch(f"{PREFIX}/devices/{light['id']}", json={"name": "X"}, headers=member["headers"])).status_code == 403
    assert (await client.delete(f"{PREFIX}/devices/{light['id']}", headers=member["headers"])).status_code == 403
    response = await client.post(
        f"{PREFIX}/devices/{light['id']}/commands", json={"commands": [{"code": "switch", "value": False}]}, headers=member["headers"]
    )
    assert response.status_code == 200, response.text
    assert response.json()["state"]["switch"] is False
    assert (await client.post(f"{PREFIX}/devices/{light['id']}/refresh", headers=member["headers"])).status_code == 200


# ----------------------------------------------------------------------------- delete
async def test_delete_device_removes_children(client, auth, home, devices, hub_app):
    panel, zone = devices["demo-panel-1"], devices["demo-zone-1"]
    removed = collect_events(hub_app, ev.DEVICE_REMOVED)
    response = await client.delete(f"{PREFIX}/devices/{panel['id']}", headers=auth["headers"])
    assert response.status_code == 204
    assert (await client.get(f"{PREFIX}/devices/{panel['id']}", headers=auth["headers"])).status_code == 404
    assert (await client.get(f"{PREFIX}/devices/{zone['id']}", headers=auth["headers"])).status_code == 404
    listed = await client.get(f"{PREFIX}/homes/{home['id']}/devices", headers=auth["headers"])
    assert len(listed.json()) == DEMO_DEVICE_COUNT - 2
    assert [event.device_id for event in removed] == [panel["id"]]
    assert removed[0].home_id == home["id"]
    assert (await client.delete(f"{PREFIX}/devices/{panel['id']}", headers=auth["headers"])).status_code == 404


# ----------------------------------------------------------------------------- refresh
async def test_refresh_updates_state_from_adapter(client, auth, devices, hub_app):
    runtime = hub_app.state.hub_runtime
    light = devices["demo-light-1"]
    adapter = registry.get("demo")
    # The virtual device changes behind the hub's back (e.g. a physical button)
    await adapter.send_command(demo_ref(light), "brightness", 33, runtime.ctx_for("demo"))
    states = collect_events(hub_app, ev.DEVICE_STATE)
    response = await client.post(f"{PREFIX}/devices/{light['id']}/refresh", headers=auth["headers"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"]["brightness"] == 33 and body["online"] is True
    assert body["last_seen_at"] is not None and body["last_seen_at"] >= light["last_seen_at"]
    assert len(states) == 1 and states[0].device_id == light["id"]
    assert states[0].payload["changed"] == {"brightness": 33}


async def test_refresh_unreachable_marks_offline(client, auth, home, hub_app, fake_adapters):
    poll, _ = fake_adapters
    (device,) = await materialize(hub_app, home["id"], "fakepoll", PairResult(devices=[draft("fp-1")]))
    poll.fail_with = "unreachable"
    response = await client.post(f"{PREFIX}/devices/{device['id']}/refresh", headers=auth["headers"])
    assert response.status_code == 502
    assert response.json()["code"] == "unreachable"
    current = await client.get(f"{PREFIX}/devices/{device['id']}", headers=auth["headers"])
    assert current.json()["online"] is False
    events = await client.get(f"{PREFIX}/devices/{device['id']}/events", headers=auth["headers"])
    assert [(e["type"], e["payload"]["value"]) for e in events.json()] == [("online", False)]

    poll.fail_with = "auth_failed"
    assert (await client.post(f"{PREFIX}/devices/{device['id']}/refresh", headers=auth["headers"])).status_code == 401
    poll.fail_with = None
    response = await client.post(f"{PREFIX}/devices/{device['id']}/refresh", headers=auth["headers"])
    assert response.status_code == 200 and response.json()["online"] is True and response.json()["state"]["switch"] is True


async def test_unreachable_refresh_keeps_last_seen_at(client, auth, home, hub_app, fake_adapters):
    """``last_seen_at`` is the last real contact: a failed poll must not bump it (the app shows "Last seen")."""
    poll, _ = fake_adapters
    (device,) = await materialize(hub_app, home["id"], "fakepoll", PairResult(devices=[draft("fp-1")]))
    ok = await client.post(f"{PREFIX}/devices/{device['id']}/refresh", headers=auth["headers"])
    assert ok.status_code == 200
    last_seen = ok.json()["last_seen_at"]
    assert last_seen is not None
    poll.fail_with = "unreachable"
    for _ in range(2):  # the poller repeats this every cycle
        assert (await client.post(f"{PREFIX}/devices/{device['id']}/refresh", headers=auth["headers"])).status_code == 502
    current = (await client.get(f"{PREFIX}/devices/{device['id']}", headers=auth["headers"])).json()
    assert current["online"] is False and current["last_seen_at"] == last_seen
    poll.fail_with = None
    back = (await client.post(f"{PREFIX}/devices/{device['id']}/refresh", headers=auth["headers"])).json()
    assert back["online"] is True and back["last_seen_at"] > last_seen


# ----------------------------------------------------------------------------- commands
async def test_command_validation(client, auth, devices):
    light, plug = devices["demo-light-1"], devices["demo-plug-1"]
    headers = auth["headers"]

    async def send(device: dict, *commands: Dict[str, Any]) -> httpx.Response:
        return await client.post(f"{PREFIX}/devices/{device['id']}/commands", json={"commands": list(commands)}, headers=headers)

    unknown = await send(light, {"code": "teleport", "value": True})
    assert unknown.status_code == 400 and "teleport" in unknown.json()["detail"]
    read_only = await send(plug, {"code": "power", "value": 10})
    assert read_only.status_code == 400 and "read-only" in read_only.json()["detail"]
    bad_enum = await send(light, {"code": "work_mode", "value": "disco"})
    assert bad_enum.status_code == 400 and "work_mode" in bad_enum.json()["detail"]
    out_of_range = await send(light, {"code": "brightness", "value": 150})
    assert out_of_range.status_code == 400
    not_a_number = await send(light, {"code": "brightness", "value": "bright"})
    assert not_a_number.status_code == 400
    assert (await send(light)).status_code == 422  # commands must not be empty
    # A bad second command rejects the whole batch: the first one is not applied
    before = (await client.get(f"{PREFIX}/devices/{light['id']}", headers=headers)).json()["state"]["brightness"]
    batch = await send(light, {"code": "brightness", "value": 5}, {"code": "nope", "value": 1})
    assert batch.status_code == 400
    assert (await client.get(f"{PREFIX}/devices/{light['id']}", headers=headers)).json()["state"]["brightness"] == before

    coerced = await send(plug, {"code": "switch", "value": "on"})
    assert coerced.status_code == 200, coerced.text
    assert coerced.json()["state"]["switch"] is True
    assert coerced.json()["state"]["power"] == 42.5  # partial state returned by the adapter is merged
    coerced = await send(plug, {"code": "switch", "value": "off"})
    assert coerced.json()["state"]["switch"] is False and coerced.json()["state"]["power"] == 0.0


async def test_commands_run_sequentially_and_emit_state(client, auth, devices, hub_app):
    light = devices["demo-light-1"]
    states = collect_events(hub_app, ev.DEVICE_STATE)
    response = await client.post(
        f"{PREFIX}/devices/{light['id']}/commands",
        json={"commands": [
            {"code": "switch", "value": True},
            {"code": "brightness", "value": "25"},
            {"code": "color", "value": {"h": 370, "s": 120, "v": 50}},
            {"code": "work_mode", "value": "colour"},
        ]},
        headers=auth["headers"],
    )
    assert response.status_code == 200, response.text
    state = response.json()["state"]
    assert state["switch"] is True and state["brightness"] == 25 and state["work_mode"] == "colour"
    assert state["color"] == {"h": 10.0, "s": 100.0, "v": 50.0}
    assert [event.payload["changed"] for event in states][1:] == [{"brightness": 25}, {"color": {"h": 10.0, "s": 100.0, "v": 50.0}}, {"work_mode": "colour"}]
    # The adapter saw every command, in order
    runtime = hub_app.state.hub_runtime
    fresh = await registry.get("demo").refresh(demo_ref(light), runtime.ctx_for("demo"))
    assert fresh.state["brightness"] == 25 and fresh.state["work_mode"] == "colour"


async def test_command_on_notable_code_records_event(client, auth, devices, hub_app):
    lock = devices["demo-lock-1"]
    device_events = collect_events(hub_app, ev.DEVICE_EVENT)
    response = await client.post(
        f"{PREFIX}/devices/{lock['id']}/commands", json={"commands": [{"code": "locked", "value": False}]}, headers=auth["headers"]
    )
    assert response.status_code == 200 and response.json()["state"]["locked"] is False
    events = await client.get(f"{PREFIX}/devices/{lock['id']}/events", headers=auth["headers"])
    assert events.status_code == 200
    assert [(e["type"], e["payload"]) for e in events.json()] == [("locked", {"value": False, "source": "command"})]
    assert events.json()[0]["device_id"] == lock["id"] and events.json()[0]["home_id"] == lock["home_id"]
    assert len(device_events) == 1 and device_events[0].payload["event"]["type"] == "locked"
    # Same value again is not a transition
    await client.post(f"{PREFIX}/devices/{lock['id']}/commands", json={"commands": [{"code": "locked", "value": False}]}, headers=auth["headers"])
    assert len((await client.get(f"{PREFIX}/devices/{lock['id']}/events", headers=auth["headers"])).json()) == 1


async def test_simulated_push_creates_event_and_message(client, auth, home, devices, hub_app):
    runtime = hub_app.state.hub_runtime
    pir = devices["demo-pir-1"]
    adapter = registry.get("demo")
    await adapter.simulate("demo-pir-1", {"motion": True}, runtime.ctx_for("demo"))
    current = await client.get(f"{PREFIX}/devices/{pir['id']}", headers=auth["headers"])
    assert current.json()["state"]["motion"] is True
    events = await client.get(f"{PREFIX}/devices/{pir['id']}/events", headers=auth["headers"])
    assert [(e["type"], e["payload"]["value"]) for e in events.json()] == [("motion", True)]
    async with runtime.db.session() as session:
        messages = (await session.execute(select(Message).where(Message.device_id == pir["id"]))).scalars().all()
    assert len(messages) == 1 and messages[0].kind == "alarm" and "Mouvement" in messages[0].title
    # Motion clearing is not notable
    await adapter.simulate("demo-pir-1", {"motion": False}, runtime.ctx_for("demo"))
    assert len((await client.get(f"{PREFIX}/devices/{pir['id']}/events", headers=auth["headers"])).json()) == 1


# ----------------------------------------------------------------------------- media
async def test_stream_and_snapshot(client, auth, devices):
    camera, plug = devices["demo-cam-1"], devices["demo-plug-1"]
    headers = auth["headers"]
    main = await client.get(f"{PREFIX}/devices/{camera['id']}/stream", headers=headers)
    assert main.status_code == 200, main.text
    assert main.json() == {"url": "rtsp://demo.safer.local:554/cam1/main", "type": "rtsp", "headers": {}, "username": None, "password": None}
    sub = await client.get(f"{PREFIX}/devices/{camera['id']}/stream", params={"quality": "sub"}, headers=headers)
    assert sub.json()["url"].endswith("/cam1/sub")
    assert (await client.get(f"{PREFIX}/devices/{camera['id']}/stream", params={"quality": "4k"}, headers=headers)).status_code == 422
    assert (await client.get(f"{PREFIX}/devices/{plug['id']}/stream", headers=headers)).status_code == 404

    snapshot = await client.get(f"{PREFIX}/devices/{camera['id']}/snapshot", headers=headers)
    assert snapshot.status_code == 200
    assert snapshot.headers["content-type"] == "image/jpeg"
    assert snapshot.content.startswith(b"\xff\xd8") and snapshot.content.endswith(b"\xff\xd9")
    assert (await client.get(f"{PREFIX}/devices/{plug['id']}/snapshot", headers=headers)).status_code == 404


# ----------------------------------------------------------------------------- hierarchy / history
async def test_children_of_panel(client, auth, devices):
    panel, zone, plug = devices["demo-panel-1"], devices["demo-zone-1"], devices["demo-plug-1"]
    response = await client.get(f"{PREFIX}/devices/{panel['id']}/children", headers=auth["headers"])
    assert response.status_code == 200
    assert [child["id"] for child in response.json()] == [zone["id"]]
    assert response.json()[0]["parent_id"] == panel["id"] and response.json()[0]["category"] == "alarm_zone"
    assert (await client.get(f"{PREFIX}/devices/{plug['id']}/children", headers=auth["headers"])).json() == []


async def test_events_limit_and_order(client, auth, devices, hub_app):
    runtime = hub_app.state.hub_runtime
    door = devices["demo-door-1"]
    adapter = registry.get("demo")
    for _ in range(3):
        await adapter.simulate("demo-door-1", {"contact": True}, runtime.ctx_for("demo"))
        await adapter.simulate("demo-door-1", {"contact": False}, runtime.ctx_for("demo"))
    headers = auth["headers"]
    everything = await client.get(f"{PREFIX}/devices/{door['id']}/events", headers=headers)
    assert everything.status_code == 200 and len(everything.json()) == 3
    stamps = [event["created_at"] for event in everything.json()]
    assert stamps == sorted(stamps, reverse=True)
    limited = await client.get(f"{PREFIX}/devices/{door['id']}/events", params={"limit": 2}, headers=headers)
    assert [event["id"] for event in limited.json()] == [event["id"] for event in everything.json()[:2]]
    assert (await client.get(f"{PREFIX}/devices/{door['id']}/events", params={"limit": 500}, headers=headers)).status_code == 422
    assert (await client.get(f"{PREFIX}/devices/{door['id']}/events", params={"limit": 0}, headers=headers)).status_code == 422
    filtered = await client.get(f"{PREFIX}/devices/{door['id']}/events", params={"type": "online"}, headers=headers)
    assert filtered.json() == []
    async with runtime.db.session() as session:
        stored = (await session.execute(select(DeviceEvent).where(DeviceEvent.device_id == door["id"]))).scalars().all()
    assert len(stored) == 3


# ----------------------------------------------------------------------------- poller
async def test_poller_poll_once_refreshes_demo_devices(hub_app, home, devices):
    runtime = hub_app.state.hub_runtime
    adapter = registry.get("demo")
    light, thermo = devices["demo-light-1"], devices["demo-thermo-1"]
    await adapter.send_command(demo_ref(light), "brightness", 15, runtime.ctx_for("demo"))
    await adapter.send_command(demo_ref(thermo), "temp_set", 21.5, runtime.ctx_for("demo"))
    states = collect_events(hub_app, ev.DEVICE_STATE)

    poller = Poller(runtime)
    assert "demo" in poller.polled_brands()
    assert poller.interval == runtime.settings.HUB_POLL_INTERVAL and 1 <= poller.concurrency <= 5
    assert await poller.poll_once() == DEMO_DEVICE_COUNT
    assert poller.runs == 1 and poller.last_run_at is not None and poller.last_refreshed == DEMO_DEVICE_COUNT
    async with runtime.db.session() as session:
        assert (await session.get(Device, light["id"])).state["brightness"] == 15
        assert (await session.get(Device, thermo["id"])).state["temp_set"] == 21.5
    assert len(states) == DEMO_DEVICE_COUNT
    changed = {event.device_id: event.payload["changed"] for event in states}
    assert changed[light["id"]] == {"brightness": 15} and changed[thermo["id"]] == {"temp_set": 21.5}


async def test_poller_skips_push_brands_marks_unreachable_offline_and_runs_in_background(hub_app, home, fake_adapters):
    runtime = hub_app.state.hub_runtime
    poll, push = fake_adapters
    (polled,) = await materialize(hub_app, home["id"], "fakepoll", PairResult(devices=[draft("fp-1")]))
    await materialize(hub_app, home["id"], "fakepush", PairResult(devices=[draft("push-1")]))

    poller = Poller(runtime, interval=0.05, concurrency=5)
    assert "fakepoll" in poller.polled_brands() and "fakepush" not in poller.polled_brands()

    poll.fail_with = "unreachable"
    await poller.poll_once()  # the error is logged, the device goes offline, the cycle survives
    async with runtime.db.session() as session:
        assert (await session.get(Device, polled["id"])).online is False
        notices = (await session.execute(select(Message).where(Message.device_id == polled["id"]))).scalars().all()
    assert len(notices) == 1 and "hors ligne" in notices[0].title
    assert push.refreshes == 0

    poll.fail_with = None
    poll.state = {"switch": True}
    await poller.poll_once()
    async with runtime.db.session() as session:
        row = await session.get(Device, polled["id"])
        assert row.online is True and row.state["switch"] is True

    before = poll.refreshes
    await poller.start()
    assert poller.running
    await poller.start()  # idempotent
    await wait_until(lambda: poll.refreshes >= before + 2)
    await poller.stop()
    assert not poller.running
    settled = poll.refreshes
    await asyncio.sleep(0.12)
    assert poll.refreshes == settled
    assert push.refreshes == 0

    disabled = Poller(runtime, interval=0)
    await disabled.start()
    assert not disabled.running


# ----------------------------------------------------------------------------- subscriptions
async def test_subscription_manager_lifecycle(client, auth, home, hub_app, fake_adapters):
    runtime = hub_app.state.hub_runtime
    _, push = fake_adapters
    (first,) = await materialize(
        hub_app, home["id"], "fakepush",
        PairResult(devices=[draft("push-a", credentials={"token": "s3cret"}, config={"host": "10.0.0.5"})]),
    )
    manager = SubscriptionManager(runtime, debounce=0.05)
    await manager.start()
    assert manager.subscribed_brands == ["fakepush"]
    assert len(push.subscriptions) == 1
    (ref,) = push.subscriptions[0]
    assert ref.id == first["id"] and ref.external_id == "push-a"
    assert ref.credentials == {"token": "s3cret"} and ref.cfg("host") == "10.0.0.5"  # decrypted via ref_for

    # Nothing changed: resync leaves the subscription alone
    assert await manager.resync() == 0
    assert len(push.subscriptions) == 1 and push.unsubscribed == 0

    # A new device of the brand -> device.added -> debounced resubscribe with both devices
    await materialize(hub_app, home["id"], "fakepush", PairResult(devices=[draft("push-b")]))
    await wait_until(lambda: len(push.subscriptions) == 2)
    await wait_until(lambda: not manager.resync_pending)  # let the resync finish iterating the other brands
    assert push.unsubscribed == 1
    assert sorted(ref.external_id for ref in push.subscriptions[1]) == ["push-a", "push-b"]

    # Devices of a polled brand do not disturb push subscriptions
    resyncs = manager.resyncs
    await pair_demo(hub_app, home["id"])
    await asyncio.sleep(0.12)
    assert manager.resyncs == resyncs and len(push.subscriptions) == 2

    # Removing a device -> device.removed -> resubscribe with the remaining one
    assert (await client.delete(f"{PREFIX}/devices/{first['id']}", headers=auth["headers"])).status_code == 204
    await wait_until(lambda: len(push.subscriptions) == 3)
    await wait_until(lambda: not manager.resync_pending)
    assert push.unsubscribed == 2
    assert [ref.external_id for ref in push.subscriptions[2]] == ["push-b"]

    await manager.stop()
    assert push.unsubscribed == 3 and manager.subscribed_brands == []
    # Stopped: bus events no longer trigger anything
    await materialize(hub_app, home["id"], "fakepush", PairResult(devices=[draft("push-c")]))
    await asyncio.sleep(0.12)
    assert len(push.subscriptions) == 3


async def test_subscription_manager_without_devices_and_with_failing_adapter(hub_app, home, fake_adapters):
    runtime = hub_app.state.hub_runtime
    _, push = fake_adapters
    manager = SubscriptionManager(runtime, debounce=0)
    await manager.start()
    assert manager.subscribed_brands == [] and push.subscriptions == []  # nothing to subscribe yet

    async def _boom(devices: List[DeviceRef], ctx: AdapterContext):
        raise AdapterError("cloud down", "unreachable")

    push.subscribe = _boom  # type: ignore[method-assign]
    await materialize(hub_app, home["id"], "fakepush", PairResult(devices=[draft("push-a")]))
    await wait_until(lambda: manager.resyncs >= 2)
    assert manager.subscribed_brands == []  # failure logged, manager still alive
    del push.subscribe
    assert await manager.resync() == 1
    assert manager.subscription("fakepush").device_ids and len(push.subscriptions) == 1
    await manager.stop()
    assert push.unsubscribed == 1


async def test_subscription_manager_resubscribes_when_a_device_is_repaired(hub_app, home, fake_adapters):
    """Re-pairing with a new password/host keeps the device id: the live subscription must still be renewed."""
    runtime = hub_app.state.hub_runtime
    _, push = fake_adapters
    (first,) = await materialize(
        hub_app, home["id"], "fakepush",
        PairResult(devices=[draft("push-a", credentials={"token": "old"}, config={"host": "10.0.0.5"})]),
    )
    manager = SubscriptionManager(runtime, debounce=0.05)
    await manager.start()
    assert len(push.subscriptions) == 1 and push.subscriptions[0][0].credentials == {"token": "old"}
    (again,) = await materialize(
        hub_app, home["id"], "fakepush",
        PairResult(devices=[draft("push-a", credentials={"token": "new"}, config={"host": "10.0.0.99"})]),
    )
    assert again["id"] == first["id"]  # upsert, same row
    await wait_until(lambda: len(push.subscriptions) == 2)
    await wait_until(lambda: not manager.resync_pending)
    (ref,) = push.subscriptions[1]
    assert push.unsubscribed == 1 and ref.credentials == {"token": "new"} and ref.cfg("host") == "10.0.0.99"
    assert ref.home_id == home["id"]
    # identical data: nothing to renew
    await materialize(hub_app, home["id"], "fakepush", PairResult(devices=[draft("push-a", credentials={"token": "new"}, config={"host": "10.0.0.99"})]))
    await asyncio.sleep(0.12)
    await wait_until(lambda: not manager.resync_pending)
    assert len(push.subscriptions) == 2 and await manager.resync() == 0
    await manager.stop()


async def test_subscriptions_are_opened_per_home(client, hub_app, home, auth, fake_adapters):
    """Refs of two homes go to the adapter separately with home-bound contexts, so pushes cannot cross homes."""
    runtime = hub_app.state.hub_runtime
    _, push = fake_adapters
    other = (await client.post(f"{PREFIX}/homes", json={"name": "Bureau"}, headers=auth["headers"])).json()
    (mine,) = await materialize(hub_app, home["id"], "fakepush", PairResult(devices=[draft("shared-id")]))
    (theirs,) = await materialize(hub_app, other["id"], "fakepush", PairResult(devices=[draft("shared-id")]))
    manager = SubscriptionManager(runtime, debounce=0)
    await manager.start()
    assert manager.subscribed_brands == ["fakepush"] and len(push.subscriptions) == 2
    assert sorted(refs[0].home_id for refs in push.subscriptions) == sorted([home["id"], other["id"]])
    # emitting through the home-bound context of ``other`` only touches that home's device
    await runtime.ctx_for("fakepush", other["id"]).emit("state", "shared-id", {"state": {"switch": True}, "online": True})
    assert (await client.get(f"{PREFIX}/devices/{theirs['id']}", headers=auth["headers"])).json()["state"]["switch"] is True
    assert (await client.get(f"{PREFIX}/devices/{mine['id']}", headers=auth["headers"])).json()["state"]["switch"] is False
    await manager.stop()
    assert push.unsubscribed == 2
