"""Ajax adapter tests: Enterprise API login, hub/device mapping, commands, session refresh, webhooks, SIA pairing."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional, Tuple

import httpx
import pytest

from app.hub.adapters.ajax import (
    BRAND_ID, DEFAULT_BASE_URL, METHOD_CLOUD, METHOD_SIA, PROTOCOL_CLOUD, PROTOCOL_SIA, AjaxAdapter, arm_mode_from_ajax,
    category_for, map_device_state, signal_percent, webhook_event_items,
)
from app.hub.adapters.base import AdapterContext, AdapterError, DeviceRef
from app.hub.adapters.registry import registry
from app.hub.tests.conftest import make_settings

API_KEY = "ent-api-key-0123456789"
LOGIN = "alice@safer.ci"
PASSWORD = "S3cret!pass"
USER_ID = "8f1c2a9d-user"
HUB_ID = "000BE22C"

HUB_SUMMARY = {"hubId": HUB_ID, "hubBinding": "OWNER"}
HUB_DETAIL = {
    "hubId": HUB_ID, "name": "Maison Cocody", "state": "ARMED", "online": True, "hubSubtype": "HUB_2",
    "firmware": {"version": "OS Malevich 2.14.1"}, "battery": {"chargeLevelPercentage": 100, "state": "OK"},
    "tampered": False, "gsm": {"signalLevel": "STRONG", "networkStatus": "OK"},
    "ethernet": {"connectionStatus": "CONNECTED"}, "groupsEnabled": False,
}
MOTION = {"id": "0004A1B2", "deviceName": "Couloir", "deviceType": "MotionProtect", "online": True,
          "batteryChargeLevelPercentage": 87, "tampered": False, "signalLevel": "STRONG", "temperature": 24,
          "motionDetected": False, "roomName": "Couloir", "firmwareVersion": "3.55.0"}
DOOR = {"id": "0004A1B3", "deviceName": "Porte d'entrée", "deviceType": "DoorProtect", "online": True,
        "batteryChargeLevelPercentage": 100, "tampered": False, "signalLevel": "NORMAL", "reedClosed": False,
        "externalContactClosed": True}
FIRE = {"id": "0004A1B4", "deviceName": "Cuisine", "deviceType": "FireProtectPlus", "online": True,
        "batteryChargeLevelPercentage": 95, "tampered": False, "signalLevel": "STRONG", "temperature": 27.5,
        "smokeDetected": False, "coDetected": True}
SOCKET = {"id": "0004A1B5", "deviceName": "Prise TV", "deviceType": "Socket", "online": True, "signalLevel": "WEAK",
          "switchState": "ON", "power": 42.5, "energy": 12.3}
SIREN = {"id": "0004A1B6", "deviceName": "Sirène salon", "deviceType": "HomeSiren", "online": False,
         "batteryChargeLevelPercentage": 60, "tampered": True, "signalLevel": "NORMAL", "sirenActive": False}
UNKNOWN = {"id": "0004A1B7", "deviceName": "Zone filaire", "deviceType": "MultiTransmitter", "online": True,
           "tampered": False, "signalLevel": "STRONG"}
DEVICES = [MOTION, DOOR, FIRE, SOCKET, SIREN, UNKNOWN]


class FakeAjaxCloud:
    """In-memory Ajax Enterprise API served through ``httpx.MockTransport``."""

    def __init__(self) -> None:
        self.requests: List[httpx.Request] = []
        self.valid_tokens = {"sess-1"}
        self.refresh_tokens = {"refr-1"}
        self.counter = 1
        self.arming: List[Tuple[str, Dict[str, Any]]] = []
        self.commands: List[Tuple[str, Dict[str, Any]]] = []
        self.login_status = 200
        self.hubs: List[Dict[str, Any]] = [HUB_SUMMARY]
        self.groups_status = 404
        self.devices = {d["id"]: d for d in DEVICES}

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def _issue(self) -> Dict[str, Any]:
        self.counter += 1
        session, refresh = f"sess-{self.counter}", f"refr-{self.counter}"
        self.valid_tokens.add(session)
        self.refresh_tokens.add(refresh)
        return {"sessionToken": session, "refreshToken": refresh, "userId": USER_ID}

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        body = json.loads(request.content) if request.content else {}
        assert str(request.url).startswith(DEFAULT_BASE_URL)
        if request.headers.get("X-Api-Key") != API_KEY:
            return httpx.Response(403, json={"message": "invalid api key"})
        if path == "/api/login":
            if self.login_status != 200:
                return httpx.Response(self.login_status, json={"message": "bad credentials"})
            assert body == {"login": LOGIN, "passwordHash": hashlib.sha256(PASSWORD.encode()).hexdigest(), "userRole": "USER"}
            return httpx.Response(200, json=self._issue())
        if path == "/api/refresh":
            if body.get("refreshToken") not in self.refresh_tokens or body.get("userId") != USER_ID:
                return httpx.Response(401, json={"message": "refresh token expired"})
            self.refresh_tokens.discard(body["refreshToken"])
            return httpx.Response(200, json=self._issue())
        if request.headers.get("X-Session-Token") not in self.valid_tokens:
            return httpx.Response(401, json={"message": "session expired"})
        prefix = f"/api/user/{USER_ID}/hubs"
        if path == prefix:
            return httpx.Response(200, json=self.hubs)
        if path == f"{prefix}/{HUB_ID}":
            return httpx.Response(200, json=HUB_DETAIL)
        if path == f"{prefix}/{HUB_ID}/groups":
            return httpx.Response(self.groups_status, json=[{"id": "g1", "groupName": "Rez-de-chaussée"}])
        if path == f"{prefix}/{HUB_ID}/devices":
            return httpx.Response(200, json=list(self.devices.values()))
        if path == f"{prefix}/{HUB_ID}/commands/arming" and request.method == "PUT":
            self.arming.append((HUB_ID, body))
            return httpx.Response(200)
        if path.startswith(f"{prefix}/{HUB_ID}/groups/") and path.endswith("/commands/arming") and request.method == "PUT":
            group_id = path.split("/groups/")[1].split("/")[0]
            if group_id == "missing":
                return httpx.Response(404, json={"message": "group not found"})
            self.arming.append((group_id, body))
            return httpx.Response(200)
        if path.startswith(f"{prefix}/{HUB_ID}/devices/"):
            device_id = path[len(f"{prefix}/{HUB_ID}/devices/"):].split("/")[0]
            device = self.devices.get(device_id)
            if device is None:
                return httpx.Response(404, json={"message": "device not found"})
            if path.endswith("/command") and request.method == "POST":
                self.commands.append((device_id, body))
                return httpx.Response(200, content=b"")
            return httpx.Response(200, json=device)
        return httpx.Response(404, json={"message": f"no route {path}"})


@pytest.fixture
def cloud() -> FakeAjaxCloud:
    return FakeAjaxCloud()


@pytest.fixture
def ctx(cloud: FakeAjaxCloud) -> AdapterContext:
    return AdapterContext(settings=make_settings(HUB_SIA_PORT=9500), transport=cloud.transport())


@pytest.fixture
def adapter() -> AjaxAdapter:
    return AjaxAdapter()


def cloud_payload(**extra: Any) -> Dict[str, Any]:
    payload = {"api_key": API_KEY, "login": LOGIN, "password": PASSWORD}
    payload.update(extra)
    return payload


def integration_creds(session_token: str = "sess-1", refresh_token: str = "refr-1", password_hash: Optional[str] = None) -> Dict[str, Any]:
    creds = {"api_key": API_KEY, "login": LOGIN, "session_token": session_token, "refresh_token": refresh_token}
    if password_hash is not None:
        creds["password_hash"] = password_hash
    return creds


def panel_ref(state: Optional[Dict[str, Any]] = None, **cred_overrides: Any) -> DeviceRef:
    return DeviceRef(
        id="panel", external_id=HUB_ID, brand=BRAND_ID, protocol=PROTOCOL_CLOUD, category="alarm_panel",
        config={"hub_id": HUB_ID, "groups": [], "group_mode": False},
        integration_config={"base_url": DEFAULT_BASE_URL, "user_id": USER_ID},
        integration_credentials=integration_creds(**cred_overrides),
        state=state or {"arm_mode": "disarmed"},
    )


def child_ref(device: Dict[str, Any], category: str) -> DeviceRef:
    return DeviceRef(
        id=device["id"], external_id=device["id"], brand=BRAND_ID, protocol=PROTOCOL_CLOUD, category=category,
        config={"hub_id": HUB_ID, "device_type": device["deviceType"]},
        integration_config={"base_url": DEFAULT_BASE_URL, "user_id": USER_ID},
        integration_credentials=integration_creds(),
        parent_external_id=HUB_ID,
    )


# ----------------------------------------------------------------------------- catalogue
def test_registered_brand_info():
    adapter = registry.get(BRAND_ID)
    assert isinstance(adapter, AjaxAdapter)
    info = adapter.info()
    assert info.protocols == [PROTOCOL_CLOUD, PROTOCOL_SIA]
    cloud_method = adapter.method(METHOD_CLOUD)
    assert cloud_method.requires_integration and cloud_method.supports_discovery
    fields = {f.name: f for f in cloud_method.fields}
    assert fields["api_key"].type == "password" and "Enterprise API key" in (fields["api_key"].help or "")
    assert fields["password"].type == "password" and fields["login"].type == "text"
    assert fields["base_url"].required is False and fields["base_url"].default == DEFAULT_BASE_URL
    sia_method = adapter.method(METHOD_SIA)
    assert [f.name for f in sia_method.fields] == ["account", "name"]
    assert "SIA DC-09" in (sia_method.fields[0].help or "") and "HUB_SIA_PORT" in (sia_method.fields[0].help or "")
    with pytest.raises(AdapterError):
        adapter.method("nope")


def test_static_mappings():
    assert category_for("MotionProtect Plus") == "sensor_motion"
    assert category_for("CombiProtect") == "sensor_motion"
    assert category_for("DoorProtectPlus") == "sensor_contact"
    assert category_for("GlassProtect") == "sensor_multi"
    assert category_for("FireProtect 2") == "sensor_smoke"
    assert category_for("LeaksProtect") == "sensor_water"
    assert category_for("StreetSirenDoubleDeck") == "siren"
    assert category_for("Socket") == "plug"
    assert category_for("WallSwitch") == "switch" and category_for("Relay") == "switch"
    assert category_for("SpaceControl") == "remote" and category_for("Button") == "remote"
    assert category_for("ReX 2") == "gateway"
    assert category_for("MultiTransmitter") == "alarm_zone" and category_for("") == "alarm_zone"
    assert arm_mode_from_ajax("ARMED") == "armed_away"
    assert arm_mode_from_ajax("NIGHT_MODE") == "armed_night"
    assert arm_mode_from_ajax("PARTIALLY_ARMED") == "armed_home"
    assert arm_mode_from_ajax("DISARMED") == "disarmed"
    assert arm_mode_from_ajax("night-mode-off") == "disarmed"
    assert arm_mode_from_ajax(None) is None
    assert signal_percent("STRONG") == 100 and signal_percent("WEAK") == 33 and signal_percent({"signalLevel": "NO_SIGNAL"}) == 0
    assert signal_percent(250) == 100 and signal_percent("UNKNOWN") is None


# ----------------------------------------------------------------------------- pairing
async def test_login_and_pair_maps_hub_and_devices(adapter: AjaxAdapter, cloud: FakeAjaxCloud, ctx: AdapterContext):
    result = await adapter.pair(METHOD_CLOUD, cloud_payload(), ctx)

    login = cloud.requests[0]
    assert login.method == "POST" and login.url.path == "/api/login"
    assert login.headers["X-Api-Key"] == API_KEY and "X-Session-Token" not in login.headers
    assert json.loads(login.content)["passwordHash"] == hashlib.sha256(PASSWORD.encode()).hexdigest()
    hubs_call = cloud.requests[1]
    assert hubs_call.url.path == f"/api/user/{USER_ID}/hubs" and hubs_call.headers["X-Session-Token"] == "sess-2"
    assert [r.url.path.rsplit("/", 1)[-1] for r in cloud.requests[2:5]] == [HUB_ID, "groups", "devices"]

    integration = result.integration
    assert integration is not None
    assert integration.key == f"ajax_cloud:{LOGIN}"
    assert integration.config == {"base_url": DEFAULT_BASE_URL, "user_id": USER_ID}
    for key in ("api_key", "login", "session_token", "refresh_token"):
        assert integration.credentials[key]
    assert integration.credentials["session_token"] == "sess-2" and integration.credentials["refresh_token"] == "refr-2"
    assert "importés" in result.message

    by_id = {d.external_id: d for d in result.devices}
    assert len(result.devices) == 1 + len(DEVICES)
    panel = by_id[HUB_ID]
    assert panel.category == "alarm_panel" and panel.protocol == PROTOCOL_CLOUD and panel.parent_external_id is None
    assert panel.name == "Maison Cocody" and panel.model == "HUB_2" and panel.firmware == "OS Malevich 2.14.1"
    assert panel.config["hub_id"] == HUB_ID and panel.config["groups"] == []
    assert panel.state["arm_mode"] == "armed_away" and panel.state["alarm"] is False and panel.state["ready"] is True
    assert panel.state["battery"] == 100 and panel.state["tamper"] is False and panel.state["signal"] == 100
    codes = {c["code"]: c for c in panel.capabilities}
    assert codes["arm_mode"]["writable"] and codes["arm_mode"]["values"] == ["disarmed", "armed_home", "armed_away", "armed_night"]
    assert {"alarm", "triggered_zone", "ready", "battery", "tamper", "signal"} <= set(codes)

    motion = by_id[MOTION["id"]]
    assert motion.category == "sensor_motion" and motion.parent_external_id == HUB_ID
    assert motion.config == {"hub_id": HUB_ID, "device_type": "MotionProtect", "room": "Couloir"}
    assert motion.model == "MotionProtect" and motion.firmware == "3.55.0" and motion.manufacturer == "Ajax Systems"
    assert motion.state == {"battery": 87, "tamper": False, "signal": 100, "temperature": 24.0, "motion": False}
    assert {c["code"] for c in motion.capabilities} == {"motion", "temperature", "battery", "tamper", "signal"}

    door = by_id[DOOR["id"]]
    assert door.category == "sensor_contact"
    assert door.state["contact"] is True and door.state["signal"] == 66 and door.state["battery"] == 100

    fire = by_id[FIRE["id"]]
    assert fire.category == "sensor_smoke"
    assert fire.state["smoke"] is False and fire.state["co"] is True and fire.state["temperature"] == 27.5
    assert {c["code"] for c in fire.capabilities} >= {"smoke", "co", "temperature", "battery", "tamper", "signal"}

    socket = by_id[SOCKET["id"]]
    assert socket.category == "plug"
    assert socket.state == {"signal": 33, "switch": True, "power": 42.5, "energy": 12.3}
    switch_cap = next(c for c in socket.capabilities if c["code"] == "switch")
    assert switch_cap["writable"] is True
    assert {c["code"] for c in socket.capabilities} >= {"switch", "power", "energy"}

    siren = by_id[SIREN["id"]]
    assert siren.category == "siren" and siren.online is False and siren.state["tamper"] is True and siren.state["siren"] is False

    zone = by_id[UNKNOWN["id"]]
    assert zone.category == "alarm_zone" and zone.config["device_type"] == "MultiTransmitter"
    assert {c["code"] for c in zone.capabilities} == {"open", "alarm", "bypass", "tamper", "battery", "signal"}
    assert zone.state["alarm"] is False and zone.state["bypass"] is False


async def test_pair_with_groups_and_discover(adapter: AjaxAdapter, cloud: FakeAjaxCloud, ctx: AdapterContext):
    cloud.groups_status = 200
    result = await adapter.pair(METHOD_CLOUD, cloud_payload(base_url=DEFAULT_BASE_URL + "/"), ctx)
    panel = next(d for d in result.devices if d.category == "alarm_panel")
    assert panel.config["groups"] == [{"id": "g1", "name": "Rez-de-chaussée"}]
    found = await adapter.discover(METHOD_CLOUD, cloud_payload(), ctx)
    assert [d.external_id for d in found][:2] == [HUB_ID, MOTION["id"]]
    assert found[1].extra["parent_external_id"] == HUB_ID and found[1].category == "sensor_motion"
    assert await adapter.discover(METHOD_SIA, {}, ctx) == []


async def test_pair_auth_failed_and_missing_fields(adapter: AjaxAdapter, cloud: FakeAjaxCloud, ctx: AdapterContext):
    cloud.login_status = 401
    with pytest.raises(AdapterError) as exc:
        await adapter.pair(METHOD_CLOUD, cloud_payload(), ctx)
    assert exc.value.code == "auth_failed" and "bad credentials" in exc.value.message
    with pytest.raises(AdapterError) as exc:
        await adapter.pair(METHOD_CLOUD, cloud_payload(api_key="wrong-key"), ctx)
    assert exc.value.code == "auth_failed"
    with pytest.raises(AdapterError) as exc:
        await adapter.pair(METHOD_CLOUD, {"api_key": API_KEY, "login": LOGIN}, ctx)
    assert exc.value.code == "invalid_input" and "password" in exc.value.message


async def test_pair_no_hub_and_unreachable(adapter: AjaxAdapter, cloud: FakeAjaxCloud, ctx: AdapterContext):
    cloud.hubs = []
    with pytest.raises(AdapterError) as exc:
        await adapter.pair(METHOD_CLOUD, cloud_payload(), ctx)
    assert exc.value.code == "not_found"

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(AdapterError) as exc:
        await adapter.pair(METHOD_CLOUD, cloud_payload(), AdapterContext(transport=httpx.MockTransport(boom)))
    assert exc.value.code == "unreachable"


# ----------------------------------------------------------------------------- commands
async def test_arm_command_bodies(adapter: AjaxAdapter, cloud: FakeAjaxCloud, ctx: AdapterContext):
    ref = panel_ref()
    assert await adapter.send_command(ref, "arm_mode", "armed_away", ctx) == {"arm_mode": "armed_away"}
    assert await adapter.send_command(ref, "arm_mode", "armed_night", ctx) == {"arm_mode": "armed_night"}
    assert await adapter.send_command(ref, "arm_mode", "armed_home", ctx) == {"arm_mode": "armed_home"}
    assert await adapter.send_command(ref, "arm_mode", "disarmed", ctx) == {"arm_mode": "disarmed", "alarm": False}
    assert [body["command"] for _, body in cloud.arming] == ["ARM", "NIGHT_MODE_ON", "ARM", "DISARM"]
    assert all(body["ignoreProblems"] is True for _, body in cloud.arming)
    put = next(r for r in cloud.requests if r.method == "PUT")
    assert put.url.path == f"/api/user/{USER_ID}/hubs/{HUB_ID}/commands/arming"
    assert put.headers["X-Api-Key"] == API_KEY and put.headers["X-Session-Token"] == "sess-1"
    with pytest.raises(AdapterError) as exc:
        await adapter.send_command(ref, "arm_mode", "armed_sideways", ctx)
    assert exc.value.code == "invalid_input"
    with pytest.raises(AdapterError) as exc:
        await adapter.send_command(ref, "ready", True, ctx)
    assert exc.value.code == "unsupported"


async def test_arm_home_uses_groups_in_group_mode(adapter: AjaxAdapter, cloud: FakeAjaxCloud, ctx: AdapterContext):
    ref = panel_ref()
    ref.config["groups"] = [{"id": "g1", "name": "RDC"}, {"id": "g2", "name": "Étage"}]
    ref.config["group_mode"] = True
    assert await adapter.send_command(ref, "arm_mode", "armed_home", ctx) == {"arm_mode": "armed_home"}
    paths = [r.url.path for r in cloud.requests if r.method == "PUT"]
    assert paths == [f"/api/user/{USER_ID}/hubs/{HUB_ID}/groups/g1/commands/arming", f"/api/user/{USER_ID}/hubs/{HUB_ID}/groups/g2/commands/arming"]
    assert cloud.arming == [("g1", {"command": "ARM", "ignoreProblems": True}), ("g2", {"command": "ARM", "ignoreProblems": True})]
    # When the group endpoint is unavailable the whole hub is armed instead (best effort)
    cloud.groups_status = 404
    ref.config["groups"] = [{"id": "missing", "name": "?"}]
    cloud.arming.clear()
    assert await adapter.send_command(ref, "arm_mode", "armed_home", ctx) == {"arm_mode": "armed_home"}
    assert cloud.arming == [(HUB_ID, {"command": "ARM", "ignoreProblems": True})]


async def test_switch_command(adapter: AjaxAdapter, cloud: FakeAjaxCloud, ctx: AdapterContext):
    ref = child_ref(SOCKET, "plug")
    assert await adapter.send_command(ref, "switch", True, ctx) == {"switch": True}
    assert await adapter.send_command(ref, "switch", "off", ctx) == {"switch": False}
    assert cloud.commands == [(SOCKET["id"], {"command": "SWITCH_ON"}), (SOCKET["id"], {"command": "SWITCH_OFF"})]
    post = next(r for r in cloud.requests if r.method == "POST" and r.url.path.endswith("/command"))
    assert post.url.path == f"/api/user/{USER_ID}/hubs/{HUB_ID}/devices/{SOCKET['id']}/command"
    with pytest.raises(AdapterError) as exc:
        await adapter.send_command(child_ref(SIREN, "siren"), "siren", True, ctx)
    assert exc.value.code == "unsupported"


# ----------------------------------------------------------------------------- refresh / sessions
async def test_refresh_panel_and_child(adapter: AjaxAdapter, cloud: FakeAjaxCloud, ctx: AdapterContext):
    panel = await adapter.refresh(panel_ref(), ctx)
    assert panel.online is True and panel.state["arm_mode"] == "armed_away" and panel.state["battery"] == 100
    assert cloud.requests[-1].url.path == f"/api/user/{USER_ID}/hubs/{HUB_ID}"
    cloud.devices[DOOR["id"]] = {**DOOR, "reedClosed": True, "online": False, "batteryChargeLevelPercentage": 15}
    door = await adapter.refresh(child_ref(DOOR, "sensor_contact"), ctx)
    assert door.online is False and door.state["contact"] is False and door.state["battery"] == 15
    assert cloud.requests[-1].url.path == f"/api/user/{USER_ID}/hubs/{HUB_ID}/devices/{DOOR['id']}"
    with pytest.raises(AdapterError) as exc:
        await adapter.refresh(child_ref({**MOTION, "id": "deadbeef"}, "sensor_motion"), ctx)
    assert exc.value.code == "not_found"


async def test_session_refresh_on_401(adapter: AjaxAdapter, cloud: FakeAjaxCloud, ctx: AdapterContext):
    cloud.valid_tokens.discard("sess-1")  # persisted token expired
    state = await adapter.refresh(panel_ref(), ctx)
    assert state.state["arm_mode"] == "armed_away"
    paths = [(r.method, r.url.path) for r in cloud.requests]
    assert paths == [
        ("GET", f"/api/user/{USER_ID}/hubs/{HUB_ID}"),
        ("POST", "/api/refresh"),
        ("GET", f"/api/user/{USER_ID}/hubs/{HUB_ID}"),
    ]
    assert json.loads(cloud.requests[1].content) == {"userId": USER_ID, "refreshToken": "refr-1"}
    assert cloud.requests[0].headers["X-Session-Token"] == "sess-1"
    assert cloud.requests[2].headers["X-Session-Token"] == "sess-2"
    # The rotated token is reused by later calls (no second refresh)
    await adapter.send_command(panel_ref(), "arm_mode", "disarmed", ctx)
    assert cloud.requests[-1].headers["X-Session-Token"] == "sess-2" and cloud.requests[-1].method == "PUT"
    assert len(cloud.requests) == 4


async def test_session_refresh_falls_back_to_login_then_auth_failed(adapter: AjaxAdapter, cloud: FakeAjaxCloud, ctx: AdapterContext):
    cloud.valid_tokens.discard("sess-1")
    cloud.refresh_tokens.discard("refr-1")
    ref = panel_ref(password_hash=hashlib.sha256(PASSWORD.encode()).hexdigest())
    state = await adapter.refresh(ref, ctx)
    assert state.state["arm_mode"] == "armed_away"
    assert [r.url.path for r in cloud.requests][:3] == [f"/api/user/{USER_ID}/hubs/{HUB_ID}", "/api/refresh", "/api/login"]
    # Without a password hash the failure surfaces as auth_failed and the cached session is dropped
    other = AjaxAdapter()
    cloud.requests.clear()
    with pytest.raises(AdapterError) as exc:
        await other.refresh(panel_ref(session_token="dead", refresh_token="dead"), ctx)
    assert exc.value.code == "auth_failed"
    assert [r.url.path for r in cloud.requests] == [f"/api/user/{USER_ID}/hubs/{HUB_ID}", "/api/refresh"]


# ----------------------------------------------------------------------------- webhooks
async def test_webhook_parsing(adapter: AjaxAdapter, ctx: AdapterContext):
    payload = [
        {"hubId": HUB_ID, "eventCode": "HUB_ARMED", "state": "ARMED"},
        {"hubId": HUB_ID, "deviceId": MOTION["id"], "deviceType": "MotionProtect", "deviceName": "Couloir",
         "eventCode": "MOTION_DETECTED_ALARM"},
        {"hubId": HUB_ID, "deviceId": DOOR["id"], "deviceType": "DoorProtect", "type": "DOOR_OPENED"},
        {"hubId": HUB_ID, "deviceId": FIRE["id"], "deviceType": "FireProtectPlus", "deviceName": "Cuisine", "eventCode": "SMOKE_DETECTED"},
        {"hubId": HUB_ID, "deviceId": MOTION["id"], "deviceType": "MotionProtect", "deviceName": "Couloir", "eventCode": "BA"},
        {"hubId": HUB_ID, "eventCode": "ALARM_RESTORED"},
        {"hubId": HUB_ID, "deviceId": SOCKET["id"], "deviceType": "Socket", "eventCode": "SWITCH_OFF"},
        {"hubId": HUB_ID, "eventCode": "HUB_OFFLINE"},
        {"hubId": HUB_ID, "deviceId": DOOR["id"], "deviceType": "DoorProtect", "state": {"reedClosed": True, "batteryChargeLevelPercentage": 42}},
        {"hubId": HUB_ID, "eventCode": "PANIC_BUTTON", "deviceName": "SpaceControl"},
        {"hubId": HUB_ID, "eventCode": "FIRMWARE_UPDATED", "version": "2.15"},
        {"noise": True},
    ]
    items = await adapter.handle_webhook({"base_url": DEFAULT_BASE_URL, "user_id": USER_ID}, {}, payload, ctx)
    states = [(i["external_id"], i["payload"]) for i in items if i["type"] == "state"]
    events = [(i["external_id"], i["payload"]["type"]) for i in items if i["type"] == "event"]

    assert (HUB_ID, {"state": {"arm_mode": "armed_away"}}) == states[0]
    assert (HUB_ID, {"state": {"alarm": True, "triggered_zone": "Couloir"}}) in states
    assert (MOTION["id"], {"state": {"motion": True}}) in states
    assert (DOOR["id"], {"state": {"contact": True}}) in states
    assert (FIRE["id"], {"state": {"smoke": True}}) in states
    assert (HUB_ID, {"state": {"alarm": True, "triggered_zone": "Cuisine"}}) in states
    assert (HUB_ID, {"state": {"alarm": False}}) in states
    assert (SOCKET["id"], {"state": {"switch": False}}) in states
    assert (HUB_ID, {"state": {}, "online": False}) in states
    assert (DOOR["id"], {"state": {"battery": 42, "contact": False}}) in states
    assert (HUB_ID, {"state": {"alarm": True, "triggered_zone": "SpaceControl"}}) in states
    assert (HUB_ID, "alarm") in events and (HUB_ID, "fire") in events and (HUB_ID, "burglary") in events
    assert (HUB_ID, "panic") in events and (HUB_ID, "firmware_updated") in events
    assert all(i["external_id"] for i in items)

    # Single object, JSON string body, wrapped list, junk
    single = await adapter.handle_webhook({}, {}, json.dumps({"hubId": HUB_ID, "state": "NIGHT_MODE"}), ctx)
    assert single == [{"external_id": HUB_ID, "type": "state", "payload": {"state": {"arm_mode": "armed_night"}}}]
    wrapped = await adapter.handle_webhook({"hub_id": HUB_ID}, {}, {"events": [{"eventCode": "DISARMED"}]}, ctx)
    assert wrapped == [{"external_id": HUB_ID, "type": "state", "payload": {"state": {"arm_mode": "disarmed", "alarm": False}}}]
    assert await adapter.handle_webhook({}, {}, "", ctx) == []
    with pytest.raises(AdapterError) as exc:
        await adapter.handle_webhook({}, {}, "not json", ctx)
    assert exc.value.code == "invalid_input"
    assert webhook_event_items({"hubId": HUB_ID, "deviceId": "X", "deviceType": "MotionProtect", "eventCode": "TAMPER_ALARM"})[1]["payload"] == {"state": {"tamper": True}}


# ----------------------------------------------------------------------------- SIA method
async def test_sia_pair_draft_refresh_and_command(adapter: AjaxAdapter, ctx: AdapterContext):
    result = await adapter.pair(METHOD_SIA, {"account": "12ab", "name": "Centrale Ajax"}, ctx)
    assert result.integration is None and len(result.devices) == 1
    draft = result.devices[0]
    assert draft.external_id == "sia:12AB" and draft.protocol == PROTOCOL_SIA and draft.category == "alarm_panel"
    assert draft.name == "Centrale Ajax" and draft.config == {"account": "12AB", "port": 9500}
    assert draft.state == {"arm_mode": "disarmed", "alarm": False, "triggered_zone": "", "ready": True, "tamper": False}
    assert {c["code"] for c in draft.capabilities} == {"arm_mode", "alarm", "triggered_zone", "ready", "tamper"}
    assert "9500" in result.message and "12AB" in result.message and "SIA DC-09" in result.message

    ref = DeviceRef(id="sia", external_id="sia:12AB", brand=BRAND_ID, protocol=PROTOCOL_SIA, category="alarm_panel",
                    config=draft.config, state={"arm_mode": "armed_away", "alarm": True})
    state = await adapter.refresh(ref, AdapterContext())
    assert state.online is True and state.state == {"arm_mode": "armed_away", "alarm": True}
    with pytest.raises(AdapterError) as exc:
        await adapter.send_command(ref, "arm_mode", "disarmed", AdapterContext())
    assert exc.value.code == "unsupported" and "one-way" in exc.value.message

    for bad in ("12", "xyz1", "0123456789abcdef0"):
        with pytest.raises(AdapterError) as exc:
            await adapter.pair(METHOD_SIA, {"account": bad}, ctx)
        assert exc.value.code == "invalid_input"
    default_name = await adapter.pair(METHOD_SIA, {"account": "abc"}, AdapterContext())
    assert default_name.devices[0].name == "Centrale SIA ABC" and default_name.devices[0].config["port"] == 0


def test_map_device_state_variants():
    _, state = map_device_state({"reedClosed": True, "signalLevel": "GOOD"}, "sensor_contact")
    assert state == {"signal": 75, "contact": False}
    _, state = map_device_state({"openDoor": True}, "sensor_contact")
    assert state["contact"] is True
    online, state = map_device_state({"online": False, "leakDetected": True, "batteryChargeLevelPercentage": "12"}, "sensor_water")
    assert online is False and state == {"battery": 12, "water_leak": True}
    _, state = map_device_state({"state": "OFF", "power": "0"}, "switch")
    assert state == {"switch": False, "power": 0.0}
    _, state = map_device_state({"devicesCount": 3, "signalLevel": 80}, "gateway")
    assert state == {"signal": 80, "child_count": 3}
