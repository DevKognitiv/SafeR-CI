"""Home Assistant bridge tests: discovery/pair mapping, refresh, service calls, errors, WebSocket push."""
from __future__ import annotations

import asyncio
import copy
import json
from typing import Any, Dict, List, Optional, Tuple

import httpx
import pytest

from app.hub.adapters.base import AdapterContext, AdapterError, DeviceRef
from app.hub.adapters.home_assistant import (
    BRAND_ID, METHOD_TOKEN, PROTOCOL, HomeAssistantAdapter, describe_entity, normalize_url, websocket_url,
)
from app.hub.adapters.registry import registry

URL = "http://ha.local:8123"
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.longlived.token"
JSON_H = {"content-type": "application/json"}

SAMPLE_STATES: List[Dict[str, Any]] = [
    {
        "entity_id": "light.salon",
        "state": "on",
        "attributes": {
            "min_color_temp_kelvin": 2000, "max_color_temp_kelvin": 6535, "min_mireds": 153, "max_mireds": 500,
            "supported_color_modes": ["color_temp", "hs"], "color_mode": "hs", "brightness": 128,
            "color_temp_kelvin": 4000, "color_temp": 250, "hs_color": [30.0, 40.0], "rgb_color": [255, 204, 153],
            "friendly_name": "Lampe salon", "supported_features": 44,
        },
        "last_changed": "2026-09-06T08:00:00.000000+00:00", "last_updated": "2026-09-06T08:00:00.000000+00:00",
        "context": {"id": "01J", "parent_id": None, "user_id": None},
    },
    {
        "entity_id": "binary_sensor.porte_entree",
        "state": "on",
        "attributes": {"device_class": "door", "battery_level": 87, "friendly_name": "Porte d'entrée"},
    },
    {
        "entity_id": "binary_sensor.couloir_motion",
        "state": "unavailable",
        "attributes": {"device_class": "motion", "friendly_name": "Mouvement couloir"},
    },
    {
        "entity_id": "sensor.salon_temperature",
        "state": "23.4",
        "attributes": {"state_class": "measurement", "unit_of_measurement": "°C", "device_class": "temperature", "friendly_name": "Température salon"},
    },
    {
        "entity_id": "sensor.salon_humidity",
        "state": "56",
        "attributes": {"unit_of_measurement": "%", "device_class": "humidity", "friendly_name": "Humidité salon"},
    },
    {
        "entity_id": "sensor.prise_tv_power",
        "state": "42.5",
        "attributes": {"unit_of_measurement": "W", "device_class": "power", "friendly_name": "Prise TV puissance"},
    },
    {
        "entity_id": "sensor.random_text",
        "state": "12",
        "attributes": {"friendly_name": "Sans classe"},
    },
    {
        "entity_id": "alarm_control_panel.maison",
        "state": "armed_home",
        "attributes": {"code_format": "number", "changed_by": None, "code_arm_required": False, "friendly_name": "Alarme maison", "supported_features": 15},
    },
    {
        "entity_id": "camera.entree",
        "state": "streaming",
        "attributes": {"access_token": "abc123", "frontend_stream_type": "hls", "entity_picture": "/api/camera_proxy/camera.entree?token=abc123", "friendly_name": "Caméra entrée", "supported_features": 2},
    },
    {
        "entity_id": "climate.chambre",
        "state": "heat",
        "attributes": {
            "hvac_modes": ["off", "heat", "cool", "heat_cool"], "min_temp": 7, "max_temp": 35, "target_temp_step": 0.5,
            "current_temperature": 21.5, "temperature": 22.0, "current_humidity": 48, "hvac_action": "heating",
            "friendly_name": "Thermostat chambre", "supported_features": 1,
        },
    },
    {"entity_id": "lock.porte", "state": "locked", "attributes": {"friendly_name": "Serrure porte", "supported_features": 1}},
    {
        "entity_id": "cover.volet_salon",
        "state": "open",
        "attributes": {"current_position": 70, "device_class": "shutter", "friendly_name": "Volet salon", "supported_features": 15},
    },
    {"entity_id": "switch.prise_tv", "state": "off", "attributes": {"device_class": "outlet", "friendly_name": "Prise TV"}},
    {"entity_id": "switch.portail", "state": "on", "attributes": {"friendly_name": "Portail"}},
    {"entity_id": "fan.ventilateur", "state": "on", "attributes": {"percentage": 66, "friendly_name": "Ventilateur"}},
    {"entity_id": "siren.exterieur", "state": "off", "attributes": {"available_tones": ["alarm"], "friendly_name": "Sirène extérieure"}},
    {"entity_id": "automation.nuit", "state": "on", "attributes": {"friendly_name": "Mode nuit"}},
    {"entity_id": "person.alice", "state": "home", "attributes": {"friendly_name": "Alice"}},
    {"entity_id": "sun.sun", "state": "above_horizon", "attributes": {}},
]


class FakeHomeAssistant:
    """Home Assistant REST API behind ``httpx.MockTransport``."""

    def __init__(self, token: str = TOKEN, states: Optional[List[Dict[str, Any]]] = None):
        self.token = token
        self.states: Dict[str, Dict[str, Any]] = {e["entity_id"]: copy.deepcopy(e) for e in (states or SAMPLE_STATES)}
        self.calls: List[Tuple[str, str, Dict[str, Any]]] = []
        self.requests: List[httpx.Request] = []

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.headers.get("authorization") != f"Bearer {self.token}":
            return httpx.Response(401, content=b"401: Unauthorized")
        path = request.url.path
        if request.method == "GET" and path == "/api/":
            return httpx.Response(200, json={"message": "API running."})
        if request.method == "GET" and path == "/api/states":
            return httpx.Response(200, json=list(self.states.values()))
        if request.method == "GET" and path.startswith("/api/states/"):
            entity = self.states.get(path[len("/api/states/"):])
            if entity is None:
                return httpx.Response(404, json={"message": "Entity not found."})
            return httpx.Response(200, json=entity)
        if request.method == "POST" and path.startswith("/api/services/"):
            _, _, _, domain, service = path.split("/", 4)
            body = json.loads(request.content or b"{}")
            self.calls.append((domain, service, body))
            entity = self.states.get(str(body.get("entity_id")))
            return httpx.Response(200, json=[entity] if entity else [])
        if request.method == "GET" and path.startswith("/api/camera_proxy/"):
            entity_id = path[len("/api/camera_proxy/"):]
            if entity_id not in self.states:
                return httpx.Response(404, json={"message": "Entity not found."})
            return httpx.Response(200, content=b"\xff\xd8\xff\xe0JPEG-HA", headers={"content-type": "image/jpeg"})
        return httpx.Response(404, json={"message": "Not found"})


class FakeHaSocket:
    """Scripted Home Assistant WebSocket server side (auth flow + subscribe_events + events)."""

    def __init__(self, token: str = TOKEN, events: Optional[List[Dict[str, Any]]] = None, close_after_events: bool = False):
        self.token = token
        self.events = list(events or [])
        self.close_after_events = close_after_events
        self.sent: List[Dict[str, Any]] = []
        self.closed = False
        self.inbox: "asyncio.Queue[Optional[str]]" = asyncio.Queue()
        self.inbox.put_nowait(json.dumps({"type": "auth_required", "ha_version": "2025.8.1"}))

    async def send(self, text: str) -> None:
        message = json.loads(text)
        self.sent.append(message)
        if message["type"] == "auth":
            if message.get("access_token") == self.token:
                self.inbox.put_nowait(json.dumps({"type": "auth_ok", "ha_version": "2025.8.1"}))
            else:
                self.inbox.put_nowait(json.dumps({"type": "auth_invalid", "message": "Invalid access token or password"}))
                self.inbox.put_nowait(None)
        elif message["type"] == "subscribe_events":
            self.inbox.put_nowait(json.dumps({"id": message["id"], "type": "result", "success": True, "result": None}))
            for event in self.events:
                self.inbox.put_nowait(json.dumps({"id": message["id"], "type": "event", "event": event}))
            if self.close_after_events:
                self.inbox.put_nowait(None)

    async def recv(self) -> str:
        item = await self.inbox.get()
        if item is None:
            raise ConnectionError("connection closed")
        return item

    async def close(self) -> None:
        self.closed = True
        self.inbox.put_nowait(None)


def state_changed(entity_id: str, new_state: Optional[Dict[str, Any]], old_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "event_type": "state_changed",
        "data": {"entity_id": entity_id, "old_state": old_state, "new_state": new_state},
        "origin": "LOCAL",
        "time_fired": "2026-09-06T09:00:00.000000+00:00",
        "context": {"id": "01J8", "parent_id": None, "user_id": None},
    }


def ctx_for(server: FakeHomeAssistant, emit: Any = None) -> AdapterContext:
    return AdapterContext(transport=server.transport(), emit=emit)


def payload(**overrides: Any) -> Dict[str, Any]:
    data: Dict[str, Any] = {"url": URL, "token": TOKEN}
    data.update(overrides)
    return data


def ref_for(draft: Any, url: str = URL, token: str = TOKEN) -> DeviceRef:
    return DeviceRef(
        id=f"dev-{draft.external_id}", external_id=draft.external_id, brand=BRAND_ID, protocol=PROTOCOL,
        category=draft.category, config=dict(draft.config), credentials={}, integration_config={"url": url},
        integration_credentials={"token": token}, state=dict(draft.state), capabilities=list(draft.capabilities),
        name=draft.name,
    )


async def paired(server: FakeHomeAssistant, *entity_ids: str) -> Dict[str, DeviceRef]:
    adapter = HomeAssistantAdapter()
    result = await adapter.pair(METHOD_TOKEN, payload(selected_external_ids=list(entity_ids) or None), ctx_for(server))
    return {draft.external_id: ref_for(draft) for draft in result.devices}


# =============================================================================== catalogue / helpers
def test_registered_and_method():
    adapter = registry.get(BRAND_ID)
    assert isinstance(adapter, HomeAssistantAdapter)
    assert adapter.supports_push is True
    method = adapter.method(METHOD_TOKEN)
    assert method.requires_integration is True and method.supports_discovery is True
    assert [f.name for f in method.fields] == ["url", "token"]
    assert next(f for f in method.fields if f.name == "token").type == "password"
    assert "Long-lived access token" in (next(f for f in method.fields if f.name == "token").help or "")


def test_url_helpers():
    assert normalize_url("ha.local:8123/") == "http://ha.local:8123"
    assert normalize_url("https://ha.example.com/api/") == "https://ha.example.com"
    assert normalize_url(" http://192.168.1.2:8123 ") == "http://192.168.1.2:8123"
    assert websocket_url("http://ha.local:8123") == "ws://ha.local:8123/api/websocket"
    assert websocket_url("https://ha.example.com") == "wss://ha.example.com/api/websocket"
    with pytest.raises(AdapterError):
        normalize_url("")
    with pytest.raises(AdapterError):
        normalize_url("ftp://x")


# =============================================================================== discovery / pairing
async def test_discover_maps_entities():
    server = FakeHomeAssistant()
    found = await HomeAssistantAdapter().discover(METHOD_TOKEN, payload(), ctx_for(server))
    by_id = {item.external_id: item for item in found}

    assert by_id["light.salon"].category == "light" and by_id["light.salon"].name == "Lampe salon"
    assert by_id["light.salon"].extra == {"domain": "light", "device_class": None, "state": "on", "online": True}
    assert by_id["binary_sensor.porte_entree"].category == "sensor_contact"
    assert by_id["binary_sensor.porte_entree"].extra["device_class"] == "door"
    assert by_id["binary_sensor.couloir_motion"].category == "sensor_motion"
    assert by_id["binary_sensor.couloir_motion"].extra["online"] is False
    assert by_id["sensor.salon_temperature"].category == "sensor_temperature"
    assert by_id["sensor.salon_humidity"].category == "sensor_humidity"
    assert by_id["sensor.prise_tv_power"].category == "generic"
    assert by_id["alarm_control_panel.maison"].category == "alarm_panel"
    assert by_id["camera.entree"].category == "camera"
    assert by_id["climate.chambre"].category == "thermostat"
    assert by_id["lock.porte"].category == "lock"
    assert by_id["cover.volet_salon"].category == "cover"
    assert by_id["switch.prise_tv"].category == "plug"
    assert by_id["switch.portail"].category == "switch"
    assert by_id["fan.ventilateur"].category == "switch"
    assert by_id["siren.exterieur"].category == "siren"
    # Unsupported domains / classless sensors are left out
    for excluded in ("sensor.random_text", "automation.nuit", "person.alice", "sun.sun"):
        assert excluded not in by_id
    assert all(item.address == URL for item in found)
    assert server.requests[0].headers["authorization"] == f"Bearer {TOKEN}"
    assert server.requests[0].url.path == "/api/states"


async def test_pair_selected_entities_builds_drafts_and_integration():
    server = FakeHomeAssistant()
    selected = ["light.salon", "binary_sensor.porte_entree", "sensor.salon_temperature", "alarm_control_panel.maison", "camera.entree", "climate.chambre"]
    result = await HomeAssistantAdapter().pair(METHOD_TOKEN, payload(selected_external_ids=selected), ctx_for(server))

    assert [d.external_id for d in result.devices] == selected
    assert result.integration is not None
    assert result.integration.key == f"ha:{URL}"
    assert result.integration.config == {"url": URL}
    assert result.integration.credentials == {"token": TOKEN}
    assert "6" in result.message
    drafts = {d.external_id: d for d in result.devices}

    light = drafts["light.salon"]
    assert light.protocol == PROTOCOL and light.category == "light"
    assert light.config["entity_id"] == "light.salon" and light.config["domain"] == "light"
    assert light.credentials == {}  # token lives on the integration only
    codes = {c["code"]: c for c in light.capabilities}
    assert {"switch", "brightness", "color_temp", "color", "work_mode"} <= set(codes)
    assert codes["color_temp"]["min"] == 2000 and codes["color_temp"]["max"] == 6535
    assert light.state == {"switch": True, "brightness": 50, "color_temp": 4000, "color": {"h": 30.0, "s": 40.0, "v": 50}, "work_mode": "colour"}

    door = drafts["binary_sensor.porte_entree"]
    assert door.state == {"contact": True, "battery": 87}
    assert {c["code"] for c in door.capabilities} == {"contact", "battery"}
    assert door.config["device_class"] == "door"

    temperature = drafts["sensor.salon_temperature"]
    assert temperature.state == {"temperature": 23.4}
    assert temperature.capabilities[0]["unit"] == "°C"

    panel = drafts["alarm_control_panel.maison"]
    assert panel.state == {"arm_mode": "armed_home", "alarm": False, "ready": True}
    assert any(c["code"] == "arm_mode" and c["writable"] for c in panel.capabilities)

    camera = drafts["camera.entree"]
    assert camera.state["stream_main"] == f"{URL}/api/camera_proxy_stream/camera.entree"
    assert camera.state["snapshot"] == f"{URL}/api/camera_proxy/camera.entree"

    climate = drafts["climate.chambre"]
    assert climate.state == {"temp_current": 21.5, "temp_set": 22.0, "mode": "heat", "humidity_current": 48.0}
    assert climate.config["hvac_modes"] == ["off", "heat", "cool", "heat_cool"]
    temp_set = next(c for c in climate.capabilities if c["code"] == "temp_set")
    assert (temp_set["min"], temp_set["max"], temp_set["step"]) == (7.0, 35.0, 0.5)


async def test_pair_without_selection_imports_everything_supported():
    server = FakeHomeAssistant()
    adapter = HomeAssistantAdapter()
    found = await adapter.discover(METHOD_TOKEN, payload(), ctx_for(server))
    result = await adapter.pair(METHOD_TOKEN, payload(url="ha.local:8123/"), ctx_for(server))
    assert {d.external_id for d in result.devices} == {f.external_id for f in found}
    assert result.integration.key == "ha:http://ha.local:8123"
    offline = next(d for d in result.devices if d.external_id == "binary_sensor.couloir_motion")
    assert offline.online is False
    cover = next(d for d in result.devices if d.external_id == "cover.volet_salon")
    assert cover.state == {"position": 70}
    lock = next(d for d in result.devices if d.external_id == "lock.porte")
    assert lock.state == {"locked": True}
    plug = next(d for d in result.devices if d.external_id == "switch.prise_tv")
    assert plug.state == {"switch": False}


async def test_pair_unknown_selection_is_not_found():
    server = FakeHomeAssistant()
    with pytest.raises(AdapterError) as excinfo:
        await HomeAssistantAdapter().pair(METHOD_TOKEN, payload(selected_external_ids=["light.nope"]), ctx_for(server))
    assert excinfo.value.code == "not_found"
    with pytest.raises(AdapterError) as excinfo:
        await HomeAssistantAdapter().pair(METHOD_TOKEN, {"url": URL}, ctx_for(server))
    assert excinfo.value.code == "invalid_input"


# =============================================================================== refresh
async def test_refresh_light_mapping():
    server = FakeHomeAssistant()
    refs = await paired(server, "light.salon")
    light = refs["light.salon"]
    server.states["light.salon"]["state"] = "on"
    server.states["light.salon"]["attributes"].update({"brightness": 255, "color_mode": "color_temp", "color_temp_kelvin": 3000, "hs_color": [27.0, 19.0]})

    state = await HomeAssistantAdapter().refresh(light, ctx_for(server))
    assert state.online is True
    assert state.state == {"switch": True, "brightness": 100, "color_temp": 3000, "color": {"h": 27.0, "s": 19.0, "v": 100}, "work_mode": "white"}
    assert server.requests[-1].url.path == "/api/states/light.salon"

    server.states["light.salon"]["state"] = "off"
    server.states["light.salon"]["attributes"].update({"brightness": None, "color_mode": None, "color_temp_kelvin": None, "color_temp": None, "hs_color": None})
    state = await HomeAssistantAdapter().refresh(light, ctx_for(server))
    assert state.state == {"switch": False}


async def test_refresh_alarm_states():
    server = FakeHomeAssistant()
    refs = await paired(server, "alarm_control_panel.maison")
    panel = refs["alarm_control_panel.maison"]
    adapter = HomeAssistantAdapter()

    server.states["alarm_control_panel.maison"]["state"] = "triggered"
    state = await adapter.refresh(panel, ctx_for(server))
    assert state.state["alarm"] is True and "arm_mode" not in state.state

    server.states["alarm_control_panel.maison"]["state"] = "armed_away"
    state = await adapter.refresh(panel, ctx_for(server))
    assert state.state == {"arm_mode": "armed_away", "alarm": False, "ready": True}

    server.states["alarm_control_panel.maison"]["state"] = "armed_vacation"
    assert (await adapter.refresh(panel, ctx_for(server))).state["arm_mode"] == "armed_away"


async def test_refresh_unavailable_and_missing():
    server = FakeHomeAssistant()
    refs = await paired(server, "sensor.salon_temperature", "binary_sensor.couloir_motion")
    adapter = HomeAssistantAdapter()
    state = await adapter.refresh(refs["binary_sensor.couloir_motion"], ctx_for(server))
    assert state.online is False and state.state == {"motion": False}

    server.states["sensor.salon_temperature"]["state"] = "unknown"
    state = await adapter.refresh(refs["sensor.salon_temperature"], ctx_for(server))
    assert state.online is False and state.state == {}

    del server.states["sensor.salon_temperature"]
    with pytest.raises(AdapterError) as excinfo:
        await adapter.refresh(refs["sensor.salon_temperature"], ctx_for(server))
    assert excinfo.value.code == "not_found"


def test_describe_entity_edge_cases():
    fahrenheit = describe_entity({"entity_id": "sensor.garage", "state": "68", "attributes": {"device_class": "temperature", "unit_of_measurement": "°F"}}, URL)
    assert fahrenheit.state == {"temperature": 20.0}
    mireds = describe_entity({"entity_id": "light.old", "state": "on", "attributes": {"color_temp": 250, "supported_color_modes": ["color_temp"]}}, URL)
    assert mireds.state["color_temp"] == 4000
    assert {c["code"] for c in mireds.capabilities} == {"switch", "brightness", "color_temp"}
    onoff = describe_entity({"entity_id": "light.simple", "state": "off", "attributes": {"supported_color_modes": ["onoff"]}}, URL)
    assert [c["code"] for c in onoff.capabilities] == ["switch"]
    unknown_binary = describe_entity({"entity_id": "binary_sensor.plug", "state": "on", "attributes": {"device_class": "plug"}}, URL)
    assert unknown_binary.category == "generic" and unknown_binary.state == {"raw_plug": True}
    co = describe_entity({"entity_id": "binary_sensor.co", "state": "off", "attributes": {"device_class": "carbon_monoxide"}}, URL)
    assert co.category == "sensor_gas" and co.state == {"co": False}
    assert describe_entity({"entity_id": "sensor.text", "state": "abc", "attributes": {}}, URL) is None
    forced = describe_entity({"entity_id": "sensor.text", "state": "abc", "attributes": {}}, URL, force=True)
    assert forced.category == "generic" and forced.state == {}
    closing = describe_entity({"entity_id": "cover.garage", "state": "closing", "attributes": {}}, URL)
    assert closing.state == {"control": "close"}


# =============================================================================== commands
async def test_command_light_services():
    server = FakeHomeAssistant()
    light = (await paired(server, "light.salon"))["light.salon"]
    adapter = HomeAssistantAdapter()
    ctx = ctx_for(server)

    assert await adapter.send_command(light, "brightness", 40, ctx) == {"brightness": 40, "switch": True}
    assert server.calls[-1] == ("light", "turn_on", {"entity_id": "light.salon", "brightness_pct": 40})
    assert server.requests[-1].url.path == "/api/services/light/turn_on"
    assert server.requests[-1].headers["content-type"] == "application/json"

    assert await adapter.send_command(light, "switch", False, ctx) == {"switch": False}
    assert server.calls[-1] == ("light", "turn_off", {"entity_id": "light.salon"})

    await adapter.send_command(light, "color_temp", 3500, ctx)
    assert server.calls[-1] == ("light", "turn_on", {"entity_id": "light.salon", "color_temp_kelvin": 3500})

    partial = await adapter.send_command(light, "color", {"h": 120.0, "s": 80.0, "v": 60.0}, ctx)
    assert server.calls[-1] == ("light", "turn_on", {"entity_id": "light.salon", "hs_color": [120.0, 80.0], "brightness_pct": 60})
    assert partial["brightness"] == 60 and partial["work_mode"] == "colour"

    assert await adapter.send_command(light, "brightness", 0, ctx) == {"brightness": 0, "switch": False}
    assert server.calls[-1] == ("light", "turn_off", {"entity_id": "light.salon"})

    await adapter.send_command(light, "work_mode", "white", ctx)
    assert server.calls[-1] == ("light", "turn_on", {"entity_id": "light.salon", "color_temp_kelvin": 4000})
    with pytest.raises(AdapterError) as excinfo:
        await adapter.send_command(light, "work_mode", "scene", ctx)
    assert excinfo.value.code == "unsupported"


async def test_command_alarm_lock_cover_climate_switch_siren():
    server = FakeHomeAssistant()
    refs = await paired(server, "alarm_control_panel.maison", "lock.porte", "cover.volet_salon", "climate.chambre", "fan.ventilateur", "siren.exterieur", "switch.prise_tv")
    adapter = HomeAssistantAdapter()
    ctx = ctx_for(server)

    assert await adapter.send_command(refs["alarm_control_panel.maison"], "arm_mode", "armed_away", ctx) == {"arm_mode": "armed_away"}
    assert server.calls[-1] == ("alarm_control_panel", "alarm_arm_away", {"entity_id": "alarm_control_panel.maison"})
    assert await adapter.send_command(refs["alarm_control_panel.maison"], "arm_mode", "disarmed", ctx) == {"arm_mode": "disarmed", "alarm": False}
    assert server.calls[-1] == ("alarm_control_panel", "alarm_disarm", {"entity_id": "alarm_control_panel.maison"})
    await adapter.send_command(refs["alarm_control_panel.maison"], "arm_mode", "armed_home", ctx)
    assert server.calls[-1][1] == "alarm_arm_home"
    await adapter.send_command(refs["alarm_control_panel.maison"], "arm_mode", "armed_night", ctx)
    assert server.calls[-1][1] == "alarm_arm_night"
    coded = refs["alarm_control_panel.maison"]
    coded.credentials = {"alarm_code": "1234"}
    await adapter.send_command(coded, "arm_mode", "armed_away", ctx)
    assert server.calls[-1][2] == {"entity_id": "alarm_control_panel.maison", "code": "1234"}

    await adapter.send_command(refs["lock.porte"], "locked", False, ctx)
    assert server.calls[-1] == ("lock", "unlock", {"entity_id": "lock.porte"})
    await adapter.send_command(refs["lock.porte"], "locked", True, ctx)
    assert server.calls[-1] == ("lock", "lock", {"entity_id": "lock.porte"})

    await adapter.send_command(refs["cover.volet_salon"], "position", 35, ctx)
    assert server.calls[-1] == ("cover", "set_cover_position", {"entity_id": "cover.volet_salon", "position": 35})
    await adapter.send_command(refs["cover.volet_salon"], "control", "open", ctx)
    assert server.calls[-1] == ("cover", "open_cover", {"entity_id": "cover.volet_salon"})
    await adapter.send_command(refs["cover.volet_salon"], "control", "stop", ctx)
    assert server.calls[-1][1] == "stop_cover"

    await adapter.send_command(refs["climate.chambre"], "temp_set", 21.5, ctx)
    assert server.calls[-1] == ("climate", "set_temperature", {"entity_id": "climate.chambre", "temperature": 21.5})
    await adapter.send_command(refs["climate.chambre"], "mode", "auto", ctx)
    assert server.calls[-1] == ("climate", "set_hvac_mode", {"entity_id": "climate.chambre", "hvac_mode": "heat_cool"})
    await adapter.send_command(refs["climate.chambre"], "mode", "off", ctx)
    assert server.calls[-1][2]["hvac_mode"] == "off"

    await adapter.send_command(refs["fan.ventilateur"], "switch", False, ctx)
    assert server.calls[-1] == ("fan", "turn_off", {"entity_id": "fan.ventilateur"})
    await adapter.send_command(refs["switch.prise_tv"], "switch", True, ctx)
    assert server.calls[-1] == ("switch", "turn_on", {"entity_id": "switch.prise_tv"})
    await adapter.send_command(refs["siren.exterieur"], "siren", True, ctx)
    assert server.calls[-1] == ("siren", "turn_on", {"entity_id": "siren.exterieur"})

    with pytest.raises(AdapterError) as excinfo:
        await adapter.send_command(refs["lock.porte"], "ptz", "left", ctx)
    assert excinfo.value.code == "unsupported"
    with pytest.raises(AdapterError) as excinfo:
        await adapter.send_command(refs["cover.volet_salon"], "control", "sideways", ctx)
    assert excinfo.value.code == "invalid_input"


async def test_command_errors_from_home_assistant():
    server = FakeHomeAssistant()
    light = (await paired(server, "light.salon"))["light.salon"]

    def bad_request(_: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"message": "extra keys not allowed @ data['bogus']"})

    with pytest.raises(AdapterError) as excinfo:
        await HomeAssistantAdapter().send_command(light, "brightness", 10, AdapterContext(transport=httpx.MockTransport(bad_request)))
    assert excinfo.value.code == "invalid_input" and "extra keys" in excinfo.value.message

    missing = DeviceRef(id="x", external_id="light.salon", brand=BRAND_ID, protocol=PROTOCOL, category="light")
    with pytest.raises(AdapterError) as excinfo:
        await HomeAssistantAdapter().send_command(missing, "switch", True, ctx_for(server))
    assert excinfo.value.code == "invalid_input"


# =============================================================================== errors
async def test_auth_failed_unreachable_and_non_json():
    server = FakeHomeAssistant()
    adapter = HomeAssistantAdapter()
    with pytest.raises(AdapterError) as excinfo:
        await adapter.discover(METHOD_TOKEN, payload(token="wrong"), ctx_for(server))
    assert excinfo.value.code == "auth_failed"

    light = (await paired(server, "light.salon"))["light.salon"]
    with pytest.raises(AdapterError) as excinfo:
        await adapter.refresh(ref_for(light, token="expired"), ctx_for(server))
    assert excinfo.value.code == "auth_failed"

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=request)

    with pytest.raises(AdapterError) as excinfo:
        await adapter.refresh(light, AdapterContext(transport=httpx.MockTransport(refuse)))
    assert excinfo.value.code == "unreachable"

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    with pytest.raises(AdapterError) as excinfo:
        await adapter.pair(METHOD_TOKEN, payload(), AdapterContext(transport=httpx.MockTransport(timeout)))
    assert excinfo.value.code == "unreachable"

    def html(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html><body>Not HA</body></html>", headers={"content-type": "text/html"})

    with pytest.raises(AdapterError) as excinfo:
        await adapter.discover(METHOD_TOKEN, payload(), AdapterContext(transport=httpx.MockTransport(html)))
    assert excinfo.value.code == "invalid_input"

    def gateway(_: httpx.Request) -> httpx.Response:
        return httpx.Response(502, content=b"Bad Gateway")

    with pytest.raises(AdapterError) as excinfo:
        await adapter.discover(METHOD_TOKEN, payload(), AdapterContext(transport=httpx.MockTransport(gateway)))
    assert excinfo.value.code == "unreachable"


# =============================================================================== stream / snapshot
async def test_stream_and_snapshot():
    server = FakeHomeAssistant()
    refs = await paired(server, "camera.entree", "light.salon")
    adapter = HomeAssistantAdapter()
    ctx = ctx_for(server)

    stream = await adapter.stream(refs["camera.entree"], "main", ctx)
    # The per-camera rotating token HA exposes on the entity is used; the long-lived (admin) token never leaves the hub
    assert stream.url == f"{URL}/api/camera_proxy_stream/camera.entree?token=abc123"
    assert stream.type == "mjpeg" and stream.headers == {} and stream.username is None and stream.password is None
    assert TOKEN not in stream.model_dump_json()
    assert await adapter.stream(refs["light.salon"], "main", ctx) is None
    # A camera without an access_token attribute has no stream the app can open without the admin token
    server.states["camera.entree"]["attributes"].pop("access_token")
    assert await adapter.stream(refs["camera.entree"], "main", ctx) is None

    image = await adapter.snapshot(refs["camera.entree"], ctx)
    assert image == b"\xff\xd8\xff\xe0JPEG-HA"
    assert server.requests[-1].url.path == "/api/camera_proxy/camera.entree"
    assert server.requests[-1].headers["authorization"] == f"Bearer {TOKEN}"
    assert await adapter.snapshot(refs["light.salon"], ctx) is None


# =============================================================================== websocket push
async def test_websocket_state_changed_is_emitted():
    server = FakeHomeAssistant()
    refs = await paired(server, "light.salon", "binary_sensor.porte_entree")
    new_light = copy.deepcopy(server.states["light.salon"])
    new_light["state"] = "off"
    new_light["attributes"].update({"brightness": None, "color_mode": None, "hs_color": None, "color_temp_kelvin": None, "color_temp": None})
    new_door = copy.deepcopy(server.states["binary_sensor.porte_entree"])
    new_door["state"] = "off"
    events = [
        state_changed("light.salon", new_light, server.states["light.salon"]),
        state_changed("sensor.salon_temperature", {"entity_id": "sensor.salon_temperature", "state": "25", "attributes": {"device_class": "temperature"}}),
        state_changed("binary_sensor.porte_entree", new_door),
        state_changed("binary_sensor.porte_entree", None),  # entity removed
    ]
    sockets: List[FakeHaSocket] = []
    urls: List[str] = []

    async def connector(url: str) -> FakeHaSocket:
        urls.append(url)
        sockets.append(FakeHaSocket(events=events))
        return sockets[-1]

    emitted: List[Tuple[str, str, Dict[str, Any]]] = []
    got_all = asyncio.Event()

    async def emit(event_type: str, external_id: str, data: Dict[str, Any]) -> None:
        emitted.append((event_type, external_id, data))
        if len(emitted) >= 3:
            got_all.set()

    adapter = HomeAssistantAdapter(connector=connector, reconnect_min=0.01, reconnect_max=0.05)
    unsubscribe = await adapter.subscribe(list(refs.values()), AdapterContext(transport=server.transport(), emit=emit))
    assert unsubscribe is not None
    await asyncio.wait_for(got_all.wait(), timeout=2)
    await unsubscribe()

    assert urls == ["ws://ha.local:8123/api/websocket"]
    assert sockets[0].sent[0] == {"type": "auth", "access_token": TOKEN}
    assert sockets[0].sent[1] == {"id": 1, "type": "subscribe_events", "event_type": "state_changed"}
    assert sockets[0].closed is True
    assert emitted[0] == ("state", "light.salon", {"state": {"switch": False}, "online": True})
    assert emitted[1] == ("state", "binary_sensor.porte_entree", {"state": {"contact": False, "battery": 87}, "online": True})
    assert emitted[2] == ("state", "binary_sensor.porte_entree", {"state": {}, "online": False})
    # the temperature sensor was not paired, so its event is ignored
    assert all(item[1] != "sensor.salon_temperature" for item in emitted)


async def test_websocket_reconnects_after_close():
    server = FakeHomeAssistant()
    refs = await paired(server, "light.salon")
    sockets: List[FakeHaSocket] = []

    async def connector(_: str) -> FakeHaSocket:
        sockets.append(FakeHaSocket(close_after_events=True))
        return sockets[-1]

    adapter = HomeAssistantAdapter(connector=connector, reconnect_min=0.01, reconnect_max=0.02)
    unsubscribe = await adapter.subscribe(list(refs.values()), AdapterContext(transport=server.transport()))
    for _ in range(100):
        if len(sockets) >= 2:
            break
        await asyncio.sleep(0.01)
    await unsubscribe()
    assert len(sockets) >= 2
    assert all(sock.closed for sock in sockets)
    assert all(sock.sent[0]["type"] == "auth" for sock in sockets)


async def test_websocket_auth_invalid_backs_off():
    server = FakeHomeAssistant()
    refs = await paired(server, "light.salon")
    sockets: List[FakeHaSocket] = []

    async def connector(_: str) -> FakeHaSocket:
        sockets.append(FakeHaSocket(token="another-token"))
        return sockets[-1]

    adapter = HomeAssistantAdapter(connector=connector, reconnect_min=0.01, auth_failure_delay=60)
    unsubscribe = await adapter.subscribe(list(refs.values()), AdapterContext(transport=server.transport()))
    await asyncio.sleep(0.15)
    await unsubscribe()
    assert len(sockets) == 1  # waited for the auth back-off instead of hammering the server
    assert sockets[0].sent == [{"type": "auth", "access_token": TOKEN}]


async def test_websocket_unreachable_retries_and_stops_cleanly():
    server = FakeHomeAssistant()
    refs = await paired(server, "light.salon")
    attempts: List[str] = []

    async def connector(url: str) -> Any:
        attempts.append(url)
        raise AdapterError("connection refused", "unreachable")

    adapter = HomeAssistantAdapter(connector=connector, reconnect_min=0.01, reconnect_max=0.02)
    unsubscribe = await adapter.subscribe(list(refs.values()), AdapterContext(transport=server.transport()))
    await asyncio.sleep(0.1)
    await unsubscribe()
    assert len(attempts) >= 2

    # devices without an integration are skipped; nothing to subscribe to -> None
    orphan = DeviceRef(id="x", external_id="light.x", brand=BRAND_ID, protocol=PROTOCOL, category="light")
    assert await adapter.subscribe([orphan], AdapterContext()) is None


# =============================================================================== API (member access)
async def test_member_stream_never_exposes_the_long_lived_token():
    """GET /devices/{id}/stream is open to every member: the integration token must not be in the answer."""
    from app.hub.app import create_app  # pylint: disable=import-outside-toplevel
    from app.hub.runtime import set_runtime  # pylint: disable=import-outside-toplevel
    from app.hub.tests.conftest import PREFIX, make_settings, register_user  # pylint: disable=import-outside-toplevel

    server = FakeHomeAssistant()
    app = create_app(settings=make_settings(), database_url="sqlite+aiosqlite://", transport=server.transport(), start_services=False)
    runtime = app.state.hub_runtime
    await runtime.start()
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://hub") as http:
            owner = await register_user(http)
            owner_h = {"Authorization": f"Bearer {owner['token']}"}
            home = (await http.post(f"{PREFIX}/homes", json={"name": "Maison"}, headers=owner_h)).json()
            member = await register_user(http, email="bob@safer.ci", name="Bob")
            member_h = {"Authorization": f"Bearer {member['token']}"}
            assert (await http.post(f"{PREFIX}/homes/{home['id']}/members", json={"email": "bob@safer.ci", "role": "member"}, headers=owner_h)).status_code == 201
            paired_ = await http.post(
                f"{PREFIX}/onboarding/{BRAND_ID}/pair",
                json={"home_id": home["id"], "method": METHOD_TOKEN, "payload": payload(), "selected_external_ids": ["camera.entree"]},
                headers=owner_h,
            )
            assert paired_.status_code == 201, paired_.text
            assert TOKEN not in paired_.text
            camera = paired_.json()["devices"][0]
            response = await http.get(f"{PREFIX}/devices/{camera['id']}/stream", headers=member_h)
            assert response.status_code == 200, response.text
            assert TOKEN not in response.text
            assert response.json()["url"] == f"{URL}/api/camera_proxy_stream/camera.entree?token=abc123"
            assert TOKEN not in (await http.get(f"{PREFIX}/devices/{camera['id']}", headers=member_h)).text
    finally:
        await runtime.stop()
        set_runtime(None)
