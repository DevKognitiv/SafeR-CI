"""Matter adapter tests: onboarding payload codec, node classification, command payloads and the
python-matter-server WebSocket protocol against an in-memory fake server (no network)."""
from __future__ import annotations

import asyncio
import copy
import json
import random
from typing import Any, Callable, Dict, List, Optional, Tuple

import pytest

from app.hub.adapters import matter
from app.hub.adapters.base import AdapterContext, AdapterError, DeviceRef
from app.hub.adapters.matter import (
    MatterAdapter, MatterClient, build_drafts, build_operations, device_state, map_server_error, parse_code, parse_node,
)
from app.hub.adapters.matter_payload import (
    INVALID_PASSCODES, PayloadError, base38_decode, base38_encode, encode_manual_code, encode_qr, format_manual_code,
    parse_manual_code, parse_onboarding_code, parse_qr, verhoeff_checksum, verhoeff_validate,
)
from app.hub.adapters.registry import registry

QR_VECTOR = "MT:Y.K9042C00KA0648G00"
MANUAL_VECTOR = "34970112332"
SERVER_URL = "ws://matter.test:5580/ws"

# ----------------------------------------------------------------------------- sample nodes
ROOT = {
    "0/29/0": [{"deviceType": 22, "revision": 1}],
    "0/29/1": [29, 31, 40, 48, 49, 51, 60, 62, 63],
}


def node(node_id: int, attributes: Dict[str, Any], available: bool = True, vendor: str = "Nanoleaf", product: str = "Essentials A19",
         label: Optional[str] = "Lampe bureau", include_root: bool = True) -> Dict[str, Any]:
    attrs: Dict[str, Any] = dict(ROOT) if include_root else {}
    if include_root:
        attrs.update({"0/40/1": vendor, "0/40/2": 4937, "0/40/3": product, "0/40/4": 1, "0/40/10": "3.5.2", "0/40/15": f"SN{node_id:04d}"})
        if label:
            attrs["0/40/5"] = label
    attrs.update(attributes)
    return {"node_id": node_id, "available": available, "attributes": attrs}


LIGHT = node(7, {
    "1/29/0": [{"deviceType": 257, "revision": 2}],
    "1/29/1": [3, 4, 6, 8, 29],
    "1/6/0": True,
    "1/8/0": 203,
})
COLOR_LIGHT = node(17, {
    "1/29/0": [{"deviceType": 269, "revision": 2}],
    "1/6/0": True, "1/8/0": 254,
    "1/768/0": 127, "1/768/1": 254, "1/768/7": 250, "1/768/8": 0, "1/768/16394": 0x11,
}, product="Shapes", label="Panneaux")
CONTACT = node(8, {
    "1/29/0": [{"deviceType": 21, "revision": 1}],
    "1/69/0": True,
    "0/47/12": 180,
}, vendor="Aqara", product="Door and Window Sensor P2", label=None)
THERMOSTAT = node(9, {
    "1/29/0": [{"deviceType": 769, "revision": 2}],
    "1/513/0": 2150, "1/513/17": 2600, "1/513/18": 2050, "1/513/28": 4,
    "1/1029/0": 4520,
}, vendor="Eve Systems", product="Eve Thermo", label="Radiateur salon")
BRIDGE = node(10, {
    "1/29/0": [{"deviceType": 14, "revision": 1}],
    "2/29/0": [{"deviceType": 256, "revision": 2}, {"deviceType": 19, "revision": 1}],
    "2/57/1": "Signify", "2/57/3": "Hue white", "2/57/5": "Plafonnier", "2/57/17": True,
    "2/6/0": False,
    "3/29/0": [{"deviceType": 263, "revision": 2}, {"deviceType": 19, "revision": 1}],
    "3/57/1": "Signify", "3/57/3": "Hue motion", "3/57/5": "Détecteur couloir", "3/57/17": False,
    "3/1030/0": 1, "3/47/12": 120,
}, vendor="Signify", product="Hue Bridge", label="Pont Hue")
LOCK = node(11, {"1/29/0": [{"deviceType": 10}], "1/257/0": 1, "1/257/3": 1, "0/47/12": 130}, vendor="Aqara", product="U100", label="Porte")
LIGHT_SENSOR = node(12, {"1/29/0": [{"deviceType": 262}], "1/1024/0": 30001}, product="Lux", label=None)
TEMP_SENSOR = node(13, {"1/29/0": [{"deviceType": 770}], "1/1026/0": 2345, "0/47/12": 200}, product="Thermo", label=None)
COVER = node(14, {"1/29/0": [{"deviceType": 514}], "1/258/14": 2500, "1/258/10": 0}, product="Blinds", label="Volet")
SMOKE = node(15, {"1/29/0": [{"deviceType": 118}], "1/92/1": 0, "1/92/2": 2, "0/47/12": 190}, product="Smoke CO", label=None)
MULTI_GANG = node(16, {
    "1/29/0": [{"deviceType": 266}], "1/6/0": True,
    "2/29/0": [{"deviceType": 266}], "2/6/0": False,
}, product="Double prise", label=None)
ALL_NODES = [LIGHT, COLOR_LIGHT, CONTACT, THERMOSTAT, BRIDGE, LOCK, LIGHT_SENSOR, TEMP_SENSOR, COVER, SMOKE, MULTI_GANG]

SERVER_INFO = {
    "fabric_id": 1, "compressed_fabric_id": 3245688245, "schema_version": 11, "min_supported_schema_version": 1,
    "sdk_version": "2024.11.4", "wifi_credentials_set": False, "thread_credentials_set": False, "bluetooth_enabled": True,
}


# ----------------------------------------------------------------------------- fake server
class FakeConnection:
    """One WebSocket connection to the fake server (send/recv/close like ``websockets``)."""

    def __init__(self, server: "FakeMatterServer"):
        self.server = server
        self.inbox: "asyncio.Queue[Optional[str]]" = asyncio.Queue()
        self.closed = False
        self.sent: List[Dict[str, Any]] = []

    async def send(self, text: str) -> None:
        if self.closed:
            raise ConnectionError("connection closed")
        message = json.loads(text)
        self.sent.append(message)
        reply = await self.server.handle(message)
        if reply is not None:
            await self.inbox.put(json.dumps(reply))

    async def recv(self) -> str:
        item = await self.inbox.get()
        if item is None:
            raise ConnectionError("connection closed by server")
        return item

    async def push(self, message: Dict[str, Any]) -> None:
        await self.inbox.put(json.dumps(message))

    async def close(self) -> None:
        self.closed = True
        await self.inbox.put(None)


class FakeMatterServer:
    """python-matter-server stand-in: banner on connect, command dispatch, event push, error injection."""

    def __init__(self, nodes: List[Dict[str, Any]], bluetooth: bool = True):
        self.nodes: Dict[int, Dict[str, Any]] = {n["node_id"]: copy.deepcopy(n) for n in nodes}
        self.bluetooth = bluetooth
        self.calls: List[Tuple[str, Dict[str, Any]]] = []
        self.errors: Dict[str, Tuple[int, str]] = {}
        self.connections: List[FakeConnection] = []
        self.wifi: Optional[Tuple[str, str]] = None
        self.commission_result: Any = None
        self.fail_connect: Optional[Exception] = None

    async def connect(self, url: str) -> FakeConnection:
        assert url == SERVER_URL, url
        if self.fail_connect is not None:
            raise self.fail_connect
        conn = FakeConnection(self)
        await conn.push({**SERVER_INFO, "bluetooth_enabled": self.bluetooth})
        self.connections.append(conn)
        return conn

    def calls_for(self, command: str) -> List[Dict[str, Any]]:
        return [args for name, args in self.calls if name == command]

    async def handle(self, message: Dict[str, Any]) -> Dict[str, Any]:
        command, args, mid = message["command"], message.get("args") or {}, message["message_id"]
        self.calls.append((command, args))
        if command in self.errors:
            code, details = self.errors[command]
            return {"message_id": mid, "error_code": code, "details": details}
        result: Any = None
        if command == "server_info":
            result = SERVER_INFO
        elif command in ("start_listening", "get_nodes"):
            result = list(self.nodes.values())
        elif command == "get_node":
            result = self.nodes.get(args["node_id"])
            if result is None:
                return {"message_id": mid, "error_code": 8, "details": f"Node {args['node_id']} does not exist"}
        elif command == "set_wifi_credentials":
            self.wifi = (args["ssid"], args["credentials"])
        elif command in ("commission_with_code", "commission_on_network"):
            result = self.commission_result if self.commission_result is not None else next(iter(self.nodes.values()))
        elif command == "read_attribute":
            result = self.nodes[args["node_id"]]["attributes"].get(args["attribute_path"])
        elif command in ("device_command", "write_attribute", "remove_node"):
            if command == "remove_node":
                self.nodes.pop(args["node_id"], None)
        else:
            return {"message_id": mid, "error_code": 4, "details": f"Invalid command {command}"}
        return {"message_id": mid, "result": result}

    async def push_event(self, event: str, data: Any) -> None:
        for conn in self.connections:
            if not conn.closed:
                await conn.push({"event": event, "data": data})

    async def drop_connections(self) -> None:
        for conn in self.connections:
            if not conn.closed:
                await conn.close()


async def wait_until(predicate: Callable[[], bool], timeout: float = 2.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() > deadline:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.01)


def make_adapter(server: FakeMatterServer) -> MatterAdapter:
    return MatterAdapter(connector=server.connect, command_timeout=2.0, commission_timeout=2.0, reconnect_min=0.02, reconnect_max=0.05,
                         default_server_url=SERVER_URL)


def ref(external_id: str, category: str, endpoint_id: Optional[int] = None, state: Optional[Dict[str, Any]] = None,
        capabilities: Optional[List[Dict[str, Any]]] = None, parent: Optional[str] = None) -> DeviceRef:
    node_id = int(external_id.split(":")[0])
    config: Dict[str, Any] = {"node_id": node_id, "server_url": SERVER_URL}
    if endpoint_id is not None:
        config["endpoint_id"] = endpoint_id
    return DeviceRef(id=f"dev-{external_id}", external_id=external_id, brand="matter", protocol="matter", category=category,
                     config=config, state=state or {}, capabilities=capabilities or [], parent_external_id=parent)


def caps(draft_or_ref: Any) -> List[str]:
    return [c["code"] for c in draft_or_ref.capabilities]


# ----------------------------------------------------------------------------- QR payload
def test_qr_known_vector():
    parsed = parse_qr(QR_VECTOR)
    assert parsed["vendor_id"] == 0xFFF1 == 65521
    assert parsed["discriminator"] == 3840
    assert parsed["short_discriminator"] == 15
    assert parsed["passcode"] == 20202021
    assert parsed["version"] == 0
    assert parsed["commissioning_flow"] == 0
    # The published test payload encodes product 0x8000 with the BLE discovery bit: re-encoding those
    # fields must reproduce the vector byte for byte, which pins the bit packing.
    assert parsed["product_id"] == 0x8000
    assert parsed["discovery_capabilities"] == 2
    assert encode_qr(0xFFF1, 0x8000, 3840, 20202021, 0, 2) == QR_VECTOR
    assert parse_qr(QR_VECTOR.lower()) == parsed  # alphabet is case-insensitive on input


def test_qr_round_trip_with_product_8001_and_on_network():
    code = encode_qr(vendor_id=0xFFF1, product_id=0x8001, discriminator=3840, passcode=20202021, commissioning_flow=0,
                     discovery_capabilities=4)
    assert code.startswith("MT:") and len(code) == 22
    parsed = parse_qr(code)
    assert (parsed["vendor_id"], parsed["product_id"], parsed["discriminator"], parsed["passcode"]) == (65521, 32769, 3840, 20202021)
    assert parsed["discovery_capabilities"] == 4
    assert parse_onboarding_code(code)["discovery_capabilities"] == {"ble": False, "on_network": True, "soft_ap": False}
    assert base38_decode(base38_encode(b"\x01\x02\x03\x04\x05\x06\x07")) == b"\x01\x02\x03\x04\x05\x06\x07"


def test_qr_random_round_trips():
    rng = random.Random(1234)
    for _ in range(300):
        fields = {
            "vendor_id": rng.randrange(0, 1 << 16), "product_id": rng.randrange(0, 1 << 16),
            "discriminator": rng.randrange(0, 1 << 12), "commissioning_flow": rng.randrange(0, 3),
            "discovery_capabilities": rng.randrange(0, 8),
        }
        passcode = rng.randrange(1, (1 << 27))
        while passcode in INVALID_PASSCODES:
            passcode = rng.randrange(1, (1 << 27))
        fields["passcode"] = passcode
        code = encode_qr(**fields)
        parsed = parse_qr(code)
        for key, value in fields.items():
            assert parsed[key] == value, (key, code)
        assert parsed["version"] == 0 and parsed["short_discriminator"] == fields["discriminator"] >> 8
        assert encode_qr(**fields) == code


def test_qr_rejects_invalid_input():
    with pytest.raises(PayloadError):
        parse_qr("MT:Y.K9042C00KA0648G0")  # bad chunk length
    with pytest.raises(PayloadError):
        parse_qr("MT:Y.K9042C00KA0648G0!")  # bad character
    with pytest.raises(PayloadError):
        parse_qr("Y.K9042C00KA0648G00")  # missing prefix
    with pytest.raises(PayloadError):
        encode_qr(0xFFF1, 0x8000, 3840, 11111111)  # forbidden passcode
    with pytest.raises(PayloadError):
        encode_qr(0xFFF1, 0x8000, 4096, 20202021)  # discriminator overflow
    assert parse_onboarding_code(encode_qr(1, 2, 3, 20202021) + "*" + QR_VECTOR)["vendor_id"] == 1  # concatenated payloads
    assert parse_onboarding_code("MT:") is None


# ----------------------------------------------------------------------------- manual code
def test_manual_code_known_vector():
    parsed = parse_manual_code(MANUAL_VECTOR)
    assert parsed["short_discriminator"] == 15
    assert parsed["discriminator"] == 15 << 8 == 3840
    assert parsed["passcode"] == 20202021
    assert parsed["vendor_id"] is None and parsed["product_id"] is None
    assert parse_manual_code("3497-011-2332") == parsed
    assert parse_manual_code("3497 011 2332") == parsed
    assert format_manual_code(MANUAL_VECTOR) == "3497-011-2332"


def test_manual_code_verhoeff_rejects_wrong_check_digit():
    assert verhoeff_validate(MANUAL_VECTOR)
    assert verhoeff_checksum(MANUAL_VECTOR[:-1]) == 2
    assert not verhoeff_validate("34970112331")
    with pytest.raises(PayloadError):
        parse_manual_code("34970112331")
    assert parse_onboarding_code("34970112331") is None
    with pytest.raises(PayloadError):
        parse_manual_code("3497011233")  # wrong length
    with pytest.raises(PayloadError):
        parse_manual_code("3497O112332")  # letter O
    # Verhoeff also catches adjacent transpositions
    assert not verhoeff_validate("34790112332")


def test_encode_manual_code():
    assert encode_manual_code(3840, 20202021) == MANUAL_VECTOR
    assert encode_manual_code(0xFFF, 20202021) == MANUAL_VECTOR  # only the 4 upper discriminator bits are encoded
    long_code = encode_manual_code(3840, 20202021, vendor_id=0xFFF1, product_id=0x8001)
    assert len(long_code) == 21 and verhoeff_validate(long_code)
    parsed = parse_manual_code(long_code)
    assert (parsed["vendor_id"], parsed["product_id"], parsed["passcode"], parsed["short_discriminator"]) == (65521, 32769, 20202021, 15)
    with pytest.raises(PayloadError):
        encode_manual_code(3840, 12345678)


def test_manual_code_random_round_trips():
    rng = random.Random(99)
    for _ in range(300):
        discriminator = rng.randrange(0, 1 << 12)
        passcode = rng.randrange(1, 1 << 27)
        while passcode in INVALID_PASSCODES:
            passcode = rng.randrange(1, 1 << 27)
        with_ids = rng.random() < 0.5
        vid, pid = (rng.randrange(0, 1 << 16), rng.randrange(0, 1 << 16)) if with_ids else (None, None)
        code = encode_manual_code(discriminator, passcode, vid, pid)
        assert len(code) == (21 if with_ids else 11)
        parsed = parse_manual_code(code)
        assert parsed["passcode"] == passcode
        assert parsed["short_discriminator"] == discriminator >> 8
        assert parsed["vendor_id"] == vid and parsed["product_id"] == pid


def test_parse_onboarding_code_kinds():
    qr = parse_onboarding_code(QR_VECTOR)
    assert qr["kind"] == "matter_qr" and qr["vendor_name"] == "Test Vendor" and qr["code"] == QR_VECTOR
    assert qr["discovery_capabilities"] == {"ble": True, "on_network": False, "soft_ap": False}
    manual = parse_onboarding_code(" 3497-011-2332 ")
    assert manual["kind"] == "matter_manual" and manual["code"] == MANUAL_VECTOR and manual["vendor_name"] is None
    assert manual["passcode"] == 20202021 and manual["short_discriminator"] == 15
    assert parse_onboarding_code("https://example.com") is None
    assert parse_onboarding_code("") is None
    assert parse_onboarding_code("tuya:abcdef") is None
    helper = parse_code(QR_VECTOR)
    assert helper["brand"] == "matter" and helper["method"] == "qr_code" and helper["kind"] == "matter_qr"
    assert parse_code(MANUAL_VECTOR)["method"] == "manual_code"
    assert parse_code("nope") is None
    nanoleaf = parse_onboarding_code(encode_qr(0x1349, 1, 100, 20202021))
    assert nanoleaf["vendor_name"] == "Nanoleaf"


# ----------------------------------------------------------------------------- node classification
def test_classify_dimmable_light():
    parsed = parse_node(LIGHT)
    assert parsed.available and not parsed.is_bridge
    assert [ep.endpoint_id for ep in parsed.application_endpoints] == [1]
    drafts = build_drafts(parsed, SERVER_URL)
    assert len(drafts) == 1
    light = drafts[0]
    assert light.external_id == "7" and light.category == "light" and light.protocol == "matter"
    assert light.name == "Lampe bureau" and light.manufacturer == "Nanoleaf" and light.model == "Essentials A19" and light.firmware == "3.5.2"
    assert caps(light) == ["switch", "brightness"]
    assert light.state == {"switch": True, "brightness": 80}
    assert light.config["node_id"] == 7 and light.config["endpoint_id"] == 1 and light.config["server_url"] == SERVER_URL
    assert light.config["device_types"] == ["Dimmable Light"] and light.config["serial"] == "SN0007"
    assert light.online and light.parent_external_id is None


def test_classify_color_light_and_multi_gang():
    color = build_drafts(parse_node(COLOR_LIGHT), SERVER_URL)[0]
    assert caps(color) == ["switch", "brightness", "color_temp", "color", "work_mode"]
    assert color.state["color_temp"] == 4000 and color.state["color"] == {"h": 180, "s": 100, "v": 100} and color.state["work_mode"] == "colour"
    gangs = build_drafts(parse_node(MULTI_GANG), SERVER_URL)
    assert [d.external_id for d in gangs] == ["16:1", "16:2"]
    assert [d.name for d in gangs] == ["Double prise 1", "Double prise 2"]
    assert all(d.category == "plug" and d.parent_external_id is None for d in gangs)
    assert gangs[0].state == {"switch": True} and gangs[1].state == {"switch": False}


def test_classify_contact_sensor():
    drafts = build_drafts(parse_node(CONTACT), SERVER_URL)
    sensor = drafts[0]
    assert sensor.category == "sensor_contact" and sensor.external_id == "8"
    assert sensor.name == "Door and Window Sensor P2" and sensor.manufacturer == "Aqara"
    assert caps(sensor) == ["contact", "battery"]
    assert sensor.state == {"contact": False, "battery": 90}  # StateValue true = closed -> contact False


def test_classify_thermostat():
    thermo = build_drafts(parse_node(THERMOSTAT), SERVER_URL)[0]
    assert thermo.category == "thermostat" and thermo.name == "Radiateur salon"
    assert caps(thermo) == ["temp_current", "temp_set", "mode", "humidity_current"]
    assert thermo.state == {"temp_current": 21.5, "mode": "heat", "temp_set": 20.5, "humidity_current": 45.2}
    cooling = copy.deepcopy(THERMOSTAT)
    cooling["attributes"]["1/513/28"] = 3
    assert build_drafts(parse_node(cooling), SERVER_URL)[0].state["temp_set"] == 26.0


def test_classify_bridge_with_two_children():
    parsed = parse_node(BRIDGE)
    assert parsed.is_bridge and parsed.aggregator.endpoint_id == 1
    drafts = build_drafts(parsed, SERVER_URL)
    assert [d.external_id for d in drafts] == ["10", "10:2", "10:3"]
    gateway, light, motion = drafts
    assert gateway.category == "gateway" and gateway.name == "Pont Hue" and gateway.config["bridge"] is True
    assert caps(gateway) == ["child_count"] and gateway.state == {"child_count": 2}
    assert light.parent_external_id == "10" and motion.parent_external_id == "10"
    assert light.category == "light" and light.name == "Plafonnier" and light.model == "Hue white" and light.manufacturer == "Signify"
    assert light.state == {"switch": False} and light.online is True
    assert motion.category == "sensor_motion" and motion.name == "Détecteur couloir"
    assert motion.state == {"motion": True, "battery": 60}
    assert motion.online is False  # BridgedDeviceBasicInformation.Reachable = false
    # per-device state lookup on the same node
    assert device_state(parsed, ref("10", "gateway", 1)).state == {"child_count": 2}
    assert device_state(parsed, ref("10:3", "sensor_motion", 3, parent="10")).online is False
    with pytest.raises(AdapterError) as excinfo:
        device_state(parsed, ref("10:9", "light", 9, parent="10"))
    assert excinfo.value.code == "not_found"


def test_attribute_to_state_mapping():
    lock = build_drafts(parse_node(LOCK), SERVER_URL)[0]
    assert lock.category == "lock" and caps(lock) == ["locked", "door", "battery"]
    assert lock.state == {"locked": True, "door": False, "battery": 65}
    unlocked = copy.deepcopy(LOCK)
    unlocked["attributes"]["1/257/0"] = 2
    unlocked["attributes"]["1/257/3"] = 0
    assert build_drafts(parse_node(unlocked), SERVER_URL)[0].state == {"locked": False, "door": True, "battery": 65}

    lux = build_drafts(parse_node(LIGHT_SENSOR), SERVER_URL)[0]
    assert lux.category == "sensor_multi" and caps(lux) == ["illuminance", "battery"]
    assert lux.state == {"illuminance": 1000.0}

    temp = build_drafts(parse_node(TEMP_SENSOR), SERVER_URL)[0]
    assert temp.category == "sensor_temperature" and temp.state == {"temperature": 23.45, "battery": 100}

    cover = build_drafts(parse_node(COVER), SERVER_URL)[0]
    assert cover.category == "cover" and cover.state == {"position": 75, "control": "stop"}

    smoke = build_drafts(parse_node(SMOKE), SERVER_URL)[0]
    assert smoke.category == "sensor_smoke" and caps(smoke) == ["smoke", "co", "battery"]
    assert smoke.state == {"smoke": False, "co": True, "battery": 95}

    occupancy = copy.deepcopy(BRIDGE)
    occupancy["attributes"]["3/1030/0"] = 0b10  # other bits set, occupied bit clear
    motion_state = dict(device_state(parse_node(occupancy), ref("10:3", "sensor_motion", 3)).state)
    assert motion_state["motion"] is False
    # bare ints and "0"-keyed structs in DeviceTypeList are tolerated
    variant = node(30, {"1/29/0": [21], "1/69/0": False})
    assert build_drafts(parse_node(variant), SERVER_URL)[0].state == {"contact": True}
    variant = node(31, {"1/29/0": [{"0": 263, "1": 2}], "1/1030/0": 1})
    assert build_drafts(parse_node(variant), SERVER_URL)[0].category == "sensor_motion"


# ----------------------------------------------------------------------------- commands
def test_command_payloads():
    light = ref("7", "light", 1, state={"brightness": 80}, capabilities=[{"code": "switch"}, {"code": "brightness"}, {"code": "color"}])
    ops, partial = build_operations(light, "switch", True)
    assert len(ops) == 1 and ops[0].command == "device_command"
    assert ops[0].args == {"node_id": 7, "endpoint_id": 1, "cluster_id": 6, "command_name": "On", "payload": {}}
    assert partial == {"switch": True}
    assert build_operations(light, "switch", False)[0][0].args["command_name"] == "Off"

    ops, partial = build_operations(light, "brightness", 50)
    assert ops[0].args["cluster_id"] == 8 and ops[0].args["command_name"] == "MoveToLevelWithOnOff"
    assert ops[0].args["payload"] == {"level": 127, "transitionTime": 0, "optionsMask": 0, "optionsOverride": 0}
    assert partial == {"brightness": 50, "switch": True}

    ops, partial = build_operations(light, "color_temp", 4000)
    assert ops[0].args["cluster_id"] == 768 and ops[0].args["command_name"] == "MoveToColorTemperature"
    assert ops[0].args["payload"]["colorTemperatureMireds"] == 250
    assert partial["color_temp"] == 4000

    ops, partial = build_operations(light, "color", {"h": 180, "s": 100, "v": 50})
    assert ops[0].args["command_name"] == "MoveToHueAndSaturation"
    assert ops[0].args["payload"]["hue"] == 127 and ops[0].args["payload"]["saturation"] == 254
    assert ops[1].args["command_name"] == "MoveToLevelWithOnOff" and ops[1].args["payload"]["level"] == 127
    assert partial["brightness"] == 50 and partial["work_mode"] == "colour"

    lock = ref("11", "lock", 1)
    ops, partial = build_operations(lock, "locked", True)
    assert ops[0].args == {"node_id": 11, "endpoint_id": 1, "cluster_id": 257, "command_name": "LockDoor", "payload": {},
                           "timed_request_timeout_ms": 1000}
    assert build_operations(lock, "locked", False)[0][0].args["command_name"] == "UnlockDoor"
    assert partial == {"locked": True}

    thermo = ref("9", "thermostat", 1, state={"mode": "heat"})
    ops, partial = build_operations(thermo, "temp_set", 21.5)
    assert ops[0].command == "write_attribute" and ops[0].args == {"node_id": 9, "attribute_path": "1/513/18", "value": 2150}
    thermo.state["mode"] = "cool"
    assert build_operations(thermo, "temp_set", 24)[0][0].args["attribute_path"] == "1/513/17"
    ops, partial = build_operations(thermo, "mode", "cool")
    assert ops[0].args == {"node_id": 9, "attribute_path": "1/513/28", "value": 3} and partial == {"mode": "cool"}

    cover = ref("14", "cover", 1)
    ops, _ = build_operations(cover, "position", 30)
    assert ops[0].args["command_name"] == "GoToLiftPercentage" and ops[0].args["payload"] == {"liftPercent100thsValue": 7000}
    assert build_operations(cover, "control", "open")[0][0].args["command_name"] == "UpOrOpen"
    assert build_operations(cover, "control", "close")[0][0].args["command_name"] == "DownOrClose"
    assert build_operations(cover, "control", "stop")[0][0].args["command_name"] == "StopMotion"

    # endpoint from the external id when config lacks it
    ops, _ = build_operations(DeviceRef(id="x", external_id="16:2", brand="matter", protocol="matter", category="plug"), "switch", True)
    assert ops[0].args["node_id"] == 16 and ops[0].args["endpoint_id"] == 2

    with pytest.raises(AdapterError) as excinfo:
        build_operations(light, "illuminance", 1)
    assert excinfo.value.code == "unsupported"
    with pytest.raises(AdapterError) as excinfo:
        build_operations(cover, "control", "sideways")
    assert excinfo.value.code == "invalid_input"


# ----------------------------------------------------------------------------- brand info / registry
def test_brand_info_and_registry():
    adapter = registry.get("matter")
    assert isinstance(adapter, MatterAdapter) and adapter.supports_push
    info = adapter.info()
    assert info.id == "matter" and info.protocols == ["matter"]
    assert {m.id for m in info.methods} == {"qr_code", "manual_code", "on_network"}
    qr = adapter.method("qr_code")
    assert qr.requires_integration and [f.name for f in qr.fields] == ["code", "wifi_ssid", "wifi_password", "server_url"]
    assert qr.fields[0].type == "qr" and qr.fields[0].label == "Scanner le code QR Matter"
    assert qr.fields[2].type == "password" and not qr.fields[1].required
    assert qr.fields[3].default == "ws://localhost:5580/ws"
    on_network = adapter.method("on_network")
    assert not on_network.supports_discovery and on_network.requires_integration
    assert [f.name for f in on_network.fields] == ["setup_pin", "ip", "server_url"] and on_network.fields[0].type == "number"
    assert "light" in info.categories and "gateway" in info.categories
    with pytest.raises(AdapterError):
        adapter.method("bluetooth")


# ----------------------------------------------------------------------------- pairing through the fake server
async def test_pair_qr_code_via_fake_server():
    server = FakeMatterServer(ALL_NODES)
    adapter = make_adapter(server)
    result = await adapter.pair("qr_code", {"code": QR_VECTOR, "wifi_ssid": "SafeR-Home", "wifi_password": "hunter22"}, AdapterContext())
    assert result.message == "Appareil Matter ajouté"
    assert result.integration is not None and result.integration.key == f"matter:{SERVER_URL}"
    assert result.integration.config == {"server_url": SERVER_URL} and result.integration.name == "Matter (matter.test:5580)"
    assert server.wifi == ("SafeR-Home", "hunter22")
    commission = server.calls_for("commission_with_code")
    assert commission == [{"code": QR_VECTOR, "network_only": False}]
    assert [d.external_id for d in result.devices] == ["7"]
    light = result.devices[0]
    assert light.category == "light" and light.state == {"switch": True, "brightness": 80}
    assert light.config["vendor_id"] == 65521 and light.config["product_id"] == 32768
    assert all(conn.closed for conn in server.connections)  # connection released after pairing


async def test_pair_manual_code_and_on_network():
    server = FakeMatterServer(ALL_NODES, bluetooth=False)
    server.commission_result = {"node_id": 10}  # server answered with a bare reference -> get_node follows
    adapter = make_adapter(server)
    result = await adapter.pair("manual_code", {"code": "3497-011-2332", "server_url": SERVER_URL}, AdapterContext())
    assert server.calls_for("commission_with_code") == [{"code": MANUAL_VECTOR, "network_only": True}]
    assert server.calls_for("get_node") == [{"node_id": 10}]
    assert server.wifi is None
    assert [d.external_id for d in result.devices] == ["10", "10:2", "10:3"]
    assert result.devices[1].parent_external_id == "10"

    server.commission_result = 11
    result = await adapter.pair("on_network", {"setup_pin": "2020 2021", "ip": "192.168.1.50"}, AdapterContext())
    assert server.calls_for("commission_on_network") == [{"setup_pin_code": 20202021, "ip_addr": "192.168.1.50"}]
    assert result.devices[0].external_id == "11" and result.devices[0].category == "lock"

    # on-network only QR codes skip the BLE phase even when the server has Bluetooth
    server = FakeMatterServer(ALL_NODES)
    adapter = make_adapter(server)
    await adapter.pair("qr_code", {"code": encode_qr(0xFFF1, 0x8001, 3840, 20202021, 0, 4)}, AdapterContext())
    assert server.calls_for("commission_with_code")[0]["network_only"] is True


async def test_pair_errors():
    server = FakeMatterServer(ALL_NODES)
    adapter = make_adapter(server)
    ctx = AdapterContext()
    with pytest.raises(AdapterError) as excinfo:
        await adapter.pair("qr_code", {"code": "not-a-code"}, ctx)
    assert excinfo.value.code == "invalid_input" and not server.connections
    with pytest.raises(AdapterError) as excinfo:
        await adapter.pair("manual_code", {}, ctx)
    assert excinfo.value.code == "invalid_input"
    with pytest.raises(AdapterError) as excinfo:
        await adapter.pair("on_network", {"setup_pin": "11111111"}, ctx)
    assert excinfo.value.code == "invalid_input"
    with pytest.raises(AdapterError) as excinfo:
        await adapter.pair("qr_code", {"code": QR_VECTOR, "server_url": "http://matter.test"}, ctx)
    assert excinfo.value.code == "invalid_input"

    server.errors["commission_with_code"] = (5, "Commission with code failed for node 7")
    with pytest.raises(AdapterError) as excinfo:
        await adapter.pair("qr_code", {"code": QR_VECTOR}, ctx)
    assert excinfo.value.code == "invalid_input" and "Commission with code failed" in excinfo.value.message

    server.fail_connect = OSError("[Errno 111] Connection refused")
    with pytest.raises(AdapterError) as excinfo:
        await adapter.pair("qr_code", {"code": QR_VECTOR}, ctx)
    assert excinfo.value.code == "unreachable"
    assert "python-matter-server" in excinfo.value.message and "Connection refused" in excinfo.value.message


# ----------------------------------------------------------------------------- refresh / commands / errors
async def test_refresh_and_send_command_via_server():
    server = FakeMatterServer(ALL_NODES)
    adapter = make_adapter(server)
    ctx = AdapterContext()
    state = await adapter.refresh(ref("7", "light", 1), ctx)
    assert state.online and state.state == {"switch": True, "brightness": 80}
    assert server.calls_for("get_node") == [{"node_id": 7}]

    server.nodes[7]["available"] = False
    assert (await adapter.refresh(ref("7", "light", 1), ctx)).online is False

    partial = await adapter.send_command(ref("7", "light", 1), "brightness", 25, ctx)
    assert partial == {"brightness": 25, "switch": True}
    sent = server.calls_for("device_command")[-1]
    assert sent["node_id"] == 7 and sent["endpoint_id"] == 1 and sent["cluster_id"] == 8
    assert sent["payload"]["level"] == 64

    partial = await adapter.send_command(ref("9", "thermostat", 1, state={"mode": "heat"}), "temp_set", 19, ctx)
    assert partial == {"temp_set": 19.0}
    assert server.calls_for("write_attribute")[-1] == {"node_id": 9, "attribute_path": "1/513/18", "value": 1900}

    await adapter.unpair(ref("11", "lock", 1), ctx)
    assert server.calls_for("remove_node") == [{"node_id": 11}] and 11 not in server.nodes
    await adapter.unpair(ref("10:2", "light", 2, parent="10"), ctx)  # endpoint of a bridge: node kept
    assert server.calls_for("remove_node") == [{"node_id": 11}]


async def test_server_error_mapping():
    assert map_server_error(8, "Node 99 does not exist").code == "not_found"
    assert map_server_error(3, "Invalid arguments").code == "invalid_input"
    assert map_server_error(4, "Invalid command").code == "unsupported"
    assert map_server_error(7, "Node not ready").code == "unreachable"
    assert map_server_error(1, "Node 5 is unavailable").code == "unreachable"
    assert map_server_error(1, "something else").code == "invalid_input"
    assert map_server_error("x", None).code == "invalid_input"

    server = FakeMatterServer(ALL_NODES)
    adapter = make_adapter(server)
    ctx = AdapterContext()
    with pytest.raises(AdapterError) as excinfo:
        await adapter.refresh(ref("99", "light", 1), ctx)
    assert excinfo.value.code == "not_found" and "Node 99 does not exist" in excinfo.value.message

    server.errors["device_command"] = (11, "SDK error: Timeout waiting for response")
    with pytest.raises(AdapterError) as excinfo:
        await adapter.send_command(ref("7", "light", 1), "switch", True, ctx)
    assert excinfo.value.code == "unreachable"
    assert all(conn.closed for conn in server.connections)

    # connection dropped while a command is pending -> unreachable (no hang)
    client = MatterClient(SERVER_URL, connector=server.connect, timeout=1.0)
    await client.connect()
    assert client.server_info["schema_version"] == 11
    server.errors.pop("device_command")

    async def drop_soon() -> None:
        await asyncio.sleep(0.02)
        await server.drop_connections()

    conn = server.connections[-1]
    original_handle = server.handle

    async def slow_handle(message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if message["command"] == "device_command":
            return None  # never answers
        return await original_handle(message)

    server.handle = slow_handle  # type: ignore[assignment]
    asyncio.create_task(drop_soon())
    with pytest.raises(AdapterError) as excinfo:
        await client.send_command("device_command", node_id=7, endpoint_id=1, cluster_id=6, command_name="On", payload={})
    assert excinfo.value.code == "unreachable" and conn.closed
    await client.close()


# ----------------------------------------------------------------------------- push subscription
async def test_subscribe_emits_attribute_updates():
    server = FakeMatterServer(ALL_NODES)
    adapter = make_adapter(server)
    emitted: List[Tuple[str, str, Dict[str, Any]]] = []

    async def emit(event_type: str, external_id: str, payload: Dict[str, Any]) -> None:
        emitted.append((event_type, external_id, payload))

    ctx = AdapterContext(emit=emit)
    devices = [ref("7", "light", 1), ref("10", "gateway", 1), ref("10:3", "sensor_motion", 3, parent="10"), ref("9", "thermostat", 1)]
    unsubscribe = await adapter.subscribe(devices, ctx)
    assert unsubscribe is not None
    await wait_until(lambda: len(emitted) >= 4)
    assert server.calls_for("start_listening") == [{}]
    initial = {external_id: payload for _, external_id, payload in emitted}
    assert initial["7"] == {"state": {"switch": True, "brightness": 80}, "online": True}
    assert initial["10:3"] == {"state": {"motion": True, "battery": 60}, "online": False}
    assert initial["10"]["state"] == {"child_count": 2}
    emitted.clear()

    await server.push_event("attribute_updated", [7, "1/6/0", False])
    await wait_until(lambda: len(emitted) >= 1)
    assert emitted == [("state", "7", {"state": {"switch": False}, "online": True})]
    emitted.clear()

    await server.push_event("attribute_updated", [10, "3/1030/0", 0])
    await server.push_event("attribute_updated", [9, "1/513/0", 1980])
    await wait_until(lambda: len(emitted) >= 2)
    assert ("state", "10:3", {"state": {"motion": False}, "online": False}) in emitted
    assert ("state", "9", {"state": {"temp_current": 19.8}, "online": True}) in emitted
    emitted.clear()

    await server.push_event("attribute_updated", [7, "1/29/1", [3, 4, 6, 8, 29]])  # unmapped attribute -> nothing
    await server.push_event("attribute_updated", [42, "1/6/0", True])  # unknown node -> ignored
    await server.push_event("node_updated", {"node_id": 7, "available": False})
    await wait_until(lambda: len(emitted) >= 1)
    assert emitted == [("state", "7", {"state": {}, "online": False})]
    emitted.clear()

    await server.push_event("node_removed", 10)
    await wait_until(lambda: len(emitted) >= 2)
    assert {e[1] for e in emitted} == {"10", "10:3"} and all(e[2]["online"] is False for e in emitted)

    await unsubscribe()
    assert all(conn.closed for conn in server.connections)
    await server.push_event("attribute_updated", [7, "1/6/0", True])
    await asyncio.sleep(0.05)
    assert len(emitted) == 2  # nothing after unsubscribe


async def test_subscribe_reconnects_after_connection_loss():
    server = FakeMatterServer([LIGHT])
    adapter = make_adapter(server)
    emitted: List[Tuple[str, str, Dict[str, Any]]] = []

    async def emit(event_type: str, external_id: str, payload: Dict[str, Any]) -> None:
        emitted.append((event_type, external_id, payload))

    ctx = AdapterContext(emit=emit)
    unsubscribe = await adapter.subscribe([ref("7", "light", 1)], ctx)
    await wait_until(lambda: len(server.connections) == 1 and len(emitted) == 1)
    await server.drop_connections()
    await wait_until(lambda: len(server.connections) == 2)
    assert len(server.calls_for("start_listening")) == 2
    server.nodes[7]["attributes"]["1/8/0"] = 127
    await server.push_event("attribute_updated", [7, "1/8/0", 127])
    await wait_until(lambda: len(emitted) == 2)
    assert emitted[-1] == ("state", "7", {"state": {"brightness": 50}, "online": True})

    # a failing server keeps the task in back-off; stopping must return promptly
    server.fail_connect = OSError("refused")
    await server.drop_connections()
    await asyncio.sleep(0.05)
    await asyncio.wait_for(unsubscribe(), timeout=1.0)

    # devices without a valid server URL are skipped; nothing to subscribe -> None
    bad = DeviceRef(id="b", external_id="7", brand="matter", protocol="matter", category="light", config={"server_url": "nope"})
    assert await adapter.subscribe([bad], ctx) is None


def test_default_server_url_from_settings():
    adapter = MatterAdapter()
    assert adapter.default_server_url() == "ws://localhost:5580/ws"
    from app.hub.tests.conftest import make_settings  # pylint: disable=import-outside-toplevel

    ctx = AdapterContext(settings=make_settings(MATTER_SERVER_URL="ws://hub.local:5580/ws"))
    assert adapter.default_server_url(ctx) == "ws://hub.local:5580/ws"
    assert matter.DEFAULT_SERVER_URL == "ws://localhost:5580/ws"
