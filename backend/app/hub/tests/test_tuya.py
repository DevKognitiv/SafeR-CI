"""Tuya adapter tests: OpenAPI signing/token flow against a signature-checking fake cloud, code mapping, local control."""
from __future__ import annotations

import hashlib
import hmac
import json
import types
from typing import Any, Dict, List, Optional, Tuple

import httpx
import pytest

from app.hub.adapters import tuya
from app.hub.adapters.base import AdapterContext, AdapterError, DeviceRef
from app.hub.adapters.registry import registry
from app.hub.adapters.tuya import (
    TokenBundle, TuyaAdapter, TuyaCloudClient, build_capabilities, cloud_error, encode_command, map_category,
    map_status, sign_request, string_to_sign,
)
from app.hub.capabilities import CATEGORIES

ACCESS_ID = "abcdefghijklmnopqrst"
SECRET = "0123456789abcdef0123456789abcdef"
BASE = "https://openapi.tuyaeu.com"

# ----------------------------------------------------------------------------- sample cloud data
LIGHT = {
    "id": "bf0light001", "name": "Lampe salon", "category": "dj", "product_name": "Smart Bulb RGBCW", "product_id": "p1",
    "online": True, "uid": "uid-1",
    "status": [
        {"code": "switch_led", "value": True}, {"code": "work_mode", "value": "white"},
        {"code": "bright_value_v2", "value": 505}, {"code": "temp_value_v2", "value": 1000},
        {"code": "colour_data_v2", "value": "{\"h\":120,\"s\":1000,\"v\":500}"}, {"code": "countdown_1", "value": 0},
    ],
}
LIGHT_FUNCTIONS = [
    {"code": "switch_led", "type": "Boolean", "values": "{}"},
    {"code": "work_mode", "type": "Enum", "values": "{\"range\":[\"white\",\"colour\",\"scene\",\"music\"]}"},
    {"code": "bright_value_v2", "type": "Integer", "values": "{\"min\":10,\"max\":1000,\"scale\":0,\"step\":1}"},
    {"code": "temp_value_v2", "type": "Integer", "values": "{\"min\":0,\"max\":1000,\"scale\":0,\"step\":1}"},
    {"code": "colour_data_v2", "type": "Json", "values": "{\"h\":{\"min\":0,\"scale\":0,\"unit\":\"\",\"max\":360,\"step\":1},"
                                                         "\"s\":{\"min\":0,\"scale\":0,\"unit\":\"\",\"max\":1000,\"step\":1},"
                                                         "\"v\":{\"min\":0,\"scale\":0,\"unit\":\"\",\"max\":1000,\"step\":1}}"},
    {"code": "countdown_1", "type": "Integer", "values": "{\"unit\":\"s\",\"min\":0,\"max\":86400,\"scale\":0,\"step\":1}"},
]
DOOR = {
    "id": "bf0door001", "name": "Porte entrée", "category": "mcs", "product_name": "Door Sensor", "online": False,
    "status": [{"code": "doorcontact_state", "value": True}, {"code": "battery_state", "value": "low"}, {"code": "temper_alarm", "value": False}],
}
THERMO = {
    "id": "bf0therm001", "name": "Chauffage", "category": "wk", "product_name": "Thermostat", "online": True,
    "status": [
        {"code": "switch", "value": True}, {"code": "temp_set", "value": 215}, {"code": "temp_current", "value": 235},
        {"code": "mode", "value": "heat"}, {"code": "humidity_value", "value": 45},
    ],
}
THERMO_FUNCTIONS = [
    {"code": "switch", "type": "Boolean", "values": "{}"},
    {"code": "temp_set", "type": "Integer", "values": "{\"unit\":\"℃\",\"min\":50,\"max\":350,\"scale\":1,\"step\":5}"},
    {"code": "mode", "type": "Enum", "values": "{\"range\":[\"auto\",\"heat\",\"cool\",\"off\"]}"},
]
CAMERA = {
    "id": "bf0cam001", "name": "Caméra jardin", "category": "sp", "product_name": "Outdoor Cam", "online": True,
    "status": [{"code": "basic_private", "value": False}, {"code": "basic_nightvision", "value": "0"}],
}
CAMERA_FUNCTIONS = [
    {"code": "basic_private", "type": "Boolean", "values": "{}"},
    {"code": "basic_nightvision", "type": "Enum", "values": "{\"range\":[\"0\",\"1\",\"2\"]}"},
    {"code": "ptz_control", "type": "Enum", "values": "{\"range\":[\"0\",\"1\",\"2\",\"3\",\"4\",\"5\",\"6\",\"7\"]}"},
]
DEVICES = {LIGHT["id"]: LIGHT, DOOR["id"]: DOOR, THERMO["id"]: THERMO, CAMERA["id"]: CAMERA}
FUNCTIONS = {LIGHT["id"]: LIGHT_FUNCTIONS, THERMO["id"]: THERMO_FUNCTIONS, CAMERA["id"]: CAMERA_FUNCTIONS}


def reference_sign(method: str, path: str, query: Dict[str, Any], body: str, t: str, token: str = "", nonce: str = "") -> str:
    """Independent implementation of the Tuya v2 signature (the oracle for the adapter's signing)."""
    url = path
    if query:
        url += "?" + "&".join(f"{key}={query[key]}" for key in sorted(query))
    body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    str_to_sign = method + "\n" + body_hash + "\n" + "" + "\n" + url
    return hmac.new(SECRET.encode("utf-8"), (ACCESS_ID + token + t + nonce + str_to_sign).encode("utf-8"), hashlib.sha256).hexdigest().upper()


class FakeTuyaCloud:
    """Tuya OpenAPI stand-in: verifies every signature, issues/refreshes tokens, serves devices, records commands."""

    def __init__(self) -> None:
        self.token_count = 0
        self.valid_tokens: List[str] = []
        self.refresh_tokens: Dict[str, str] = {}
        self.requests: List[Tuple[str, str, Dict[str, Any]]] = []
        self.commands: List[Tuple[str, Any]] = []
        self.fail_next: List[Dict[str, Any]] = []
        self.http_fail_next: Optional[int] = None
        self.reject_business = False  # every business call answers 1010 even with a fresh token
        self.uid = "uid-1"

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def _issue(self) -> Dict[str, Any]:
        self.token_count += 1
        token, refresh = f"tok-{self.token_count}", f"ref-{self.token_count}"
        self.valid_tokens.append(token)
        self.refresh_tokens[refresh] = token
        return {"access_token": token, "refresh_token": refresh, "uid": self.uid, "expire_time": 7200}

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        query = {k: v for k, v in request.url.params.items()}
        body = request.content.decode("utf-8") if request.content else ""
        self.requests.append((request.method, path, query))
        headers = request.headers
        expected = reference_sign(request.method, path, query, body, headers["t"], headers.get("access_token", ""), headers.get("nonce", ""))
        if headers.get("client_id") != ACCESS_ID or headers.get("sign_method") != "HMAC-SHA256" or headers.get("sign") != expected:
            return httpx.Response(200, json={"success": False, "code": 1004, "msg": "sign invalid", "t": 0})
        if self.http_fail_next:
            status, self.http_fail_next = self.http_fail_next, None
            return httpx.Response(status, text="bad gateway")
        if self.fail_next:
            failure = self.fail_next.pop(0)
            return httpx.Response(200, json={"success": False, **failure})
        if path == "/v1.0/token":
            assert query == {"grant_type": "1"}
            assert "access_token" not in headers
            return self._ok(self._issue())
        if path.startswith("/v1.0/token/"):
            refresh = path.rsplit("/", 1)[1]
            if refresh not in self.refresh_tokens:
                return httpx.Response(200, json={"success": False, "code": 1010, "msg": "token invalid"})
            return self._ok(self._issue())
        if headers.get("access_token") not in self.valid_tokens:
            return httpx.Response(200, json={"success": False, "code": 1010, "msg": "token invalid"})
        if path == "/v1.0/iot-01/associated-users/devices":
            if query.get("last_row_key") == "page2":
                return self._ok({"devices": [THERMO, CAMERA], "has_more": False, "last_row_key": "", "total": 4})
            return self._ok({"devices": [LIGHT, DOOR], "has_more": True, "last_row_key": "page2", "total": 4})
        if path == f"/v1.0/users/{self.uid}/devices":
            return self._ok([LIGHT, DOOR])
        parts = path.split("/")
        if len(parts) >= 4 and parts[2] == "devices":
            device = DEVICES.get(parts[3])
            if device is None:
                return httpx.Response(200, json={"success": False, "code": 1108, "msg": "uri path invalid"})
            tail = parts[4] if len(parts) > 4 else ""
            if tail == "":
                return self._ok(device)
            if tail == "status":
                return self._ok(device["status"])
            if tail == "functions":
                if parts[3] not in FUNCTIONS:
                    return httpx.Response(200, json={"success": False, "code": 2009, "msg": "not support this device"})
                return self._ok({"category": device["category"], "devId": parts[3], "functions": FUNCTIONS[parts[3]]})
            if tail == "commands" and request.method == "POST":
                self.commands.append((parts[3], json.loads(body)["commands"]))
                return self._ok(True)
            if tail == "stream" and request.method == "POST":
                return self._ok({"url": f"rtsps://stream.tuya/{parts[3]}/{json.loads(body)['type']}"})
        return httpx.Response(404, json={"success": False, "code": 1108, "msg": "uri path invalid"})

    @staticmethod
    def _ok(result: Any) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "result": result, "t": 1700000000000})


@pytest.fixture
def cloud() -> FakeTuyaCloud:
    return FakeTuyaCloud()


@pytest.fixture
def ctx(cloud: FakeTuyaCloud) -> AdapterContext:
    return AdapterContext(transport=cloud.transport())


@pytest.fixture
def adapter() -> TuyaAdapter:
    return TuyaAdapter()


def cloud_payload(**extra: Any) -> Dict[str, Any]:
    payload = {"region": "eu", "access_id": ACCESS_ID, "access_secret": SECRET}
    payload.update(extra)
    return payload


def cloud_ref(device: Dict[str, Any], functions: List[Dict[str, Any]], credentials: Dict[str, Any], category: Optional[str] = None) -> DeviceRef:
    category = category or map_category(device["category"])
    return DeviceRef(
        id="dev", external_id=device["id"], brand="tuya", protocol="tuya_cloud", category=category,
        config={"region": "eu", "device_id": device["id"], "functions": tuya.functions_meta(functions),
                "code_map": tuya.build_code_map(functions, category)},
        integration_config={"region": "eu", "access_id": ACCESS_ID},
        integration_credentials={"access_secret": SECRET, **credentials},
    )


# ----------------------------------------------------------------------------- signing
def test_sign_request_matches_independent_hmac():
    t, nonce = "1700000000000", "5138cc3a9033d69856923fd07b491173"
    headers = sign_request("GET", "/v1.0/token", {"grant_type": 1}, "", ACCESS_ID, SECRET, t, nonce=nonce)
    assert headers["sign"] == reference_sign("GET", "/v1.0/token", {"grant_type": 1}, "", t, "", nonce)
    assert headers["client_id"] == ACCESS_ID and headers["t"] == t and headers["nonce"] == nonce
    assert headers["sign_method"] == "HMAC-SHA256" and "access_token" not in headers

    body = json.dumps({"commands": [{"code": "switch_led", "value": True}]})
    headers = sign_request("POST", "/v1.0/devices/bf0light001/commands", None, body, ACCESS_ID, SECRET, t, "tok-1", nonce)
    assert headers["sign"] == reference_sign("POST", "/v1.0/devices/bf0light001/commands", {}, body, t, "tok-1", nonce)
    assert headers["access_token"] == "tok-1"
    # Sanity: a concrete vector, so a regression in the algorithm cannot hide behind the oracle
    assert sign_request("GET", "/v1.0/token", {"grant_type": 1}, "", "id", "secret", "1", nonce="")["sign"] == hmac.new(
        b"secret", ("id" + "1" + "GET\n" + hashlib.sha256(b"").hexdigest() + "\n\n/v1.0/token?grant_type=1").encode(), hashlib.sha256
    ).hexdigest().upper()


def test_string_to_sign_sorts_query_and_hashes_body():
    assert string_to_sign("get", "/v1.0/x", {"z": 1, "a": "b"}, "") == "GET\n" + tuya.EMPTY_BODY_SHA256 + "\n\n/v1.0/x?a=b&z=1"
    body = "{\"k\": 1}"
    assert string_to_sign("POST", "/v1.0/x", None, body).split("\n")[1] == hashlib.sha256(body.encode()).hexdigest()


# ----------------------------------------------------------------------------- token flow
async def test_token_fetch_then_cached(cloud: FakeTuyaCloud, ctx: AdapterContext):
    async with ctx.http(base_url=BASE) as client:
        api = TuyaCloudClient(client, ACCESS_ID, SECRET)
        token = await api.ensure_token()
        assert token.access_token == "tok-1" and token.refresh_token == "ref-1" and token.uid == "uid-1"
        await api.get_status(LIGHT["id"])
        assert await api.ensure_token() is token
    assert cloud.token_count == 1
    assert [p for _, p, _ in cloud.requests] == ["/v1.0/token", "/v1.0/devices/bf0light001/status"]


async def test_token_refresh_when_expired(cloud: FakeTuyaCloud, ctx: AdapterContext):
    cloud._issue()  # tok-1 / ref-1 known to the cloud
    async with ctx.http(base_url=BASE) as client:
        api = TuyaCloudClient(client, ACCESS_ID, SECRET, token=TokenBundle("tok-1", "ref-1", expires_at=0.0), clock=lambda: 1000.0)
        status = await api.get_status(LIGHT["id"])
        assert api.token.access_token == "tok-2"
        assert api.token.expires_at == 1000.0 + 7200 - tuya.TOKEN_MARGIN_SECONDS
        assert api.token.as_credentials()["refresh_token"] == "ref-2"
    assert status[0]["code"] == "switch_led"
    assert [p for _, p, _ in cloud.requests][:2] == ["/v1.0/token/ref-1", "/v1.0/devices/bf0light001/status"]


async def test_expired_token_with_dead_refresh_falls_back_to_new_token(cloud: FakeTuyaCloud, ctx: AdapterContext):
    async with ctx.http(base_url=BASE) as client:
        api = TuyaCloudClient(client, ACCESS_ID, SECRET, token=TokenBundle("old", "unknown-refresh", expires_at=0.0))
        await api.get_status(LIGHT["id"])
        assert api.token.access_token == "tok-1"
    assert [p for _, p, _ in cloud.requests] == ["/v1.0/token/unknown-refresh", "/v1.0/token", "/v1.0/devices/bf0light001/status"]


async def test_invalid_token_error_triggers_single_reauth(cloud: FakeTuyaCloud, ctx: AdapterContext):
    async with ctx.http(base_url=BASE) as client:
        api = TuyaCloudClient(client, ACCESS_ID, SECRET, token=TokenBundle("stale", "", expires_at=9e12))
        assert (await api.get_status(LIGHT["id"]))[2]["value"] == 505
        assert api.token.access_token == "tok-1"
        cloud.valid_tokens.clear()
        cloud.fail_next = [{"code": 1010, "msg": "token invalid"}]
        with pytest.raises(AdapterError) as excinfo:
            await api.get_status(LIGHT["id"])
        assert excinfo.value.code == "auth_failed"


async def test_list_devices_pagination_and_uid(cloud: FakeTuyaCloud, ctx: AdapterContext):
    async with ctx.http(base_url=BASE) as client:
        api = TuyaCloudClient(client, ACCESS_ID, SECRET)
        devices = await api.list_devices()
        assert [d["id"] for d in devices] == ["bf0light001", "bf0door001", "bf0therm001", "bf0cam001"]
        pages = [(p, q) for _, p, q in cloud.requests if p.endswith("associated-users/devices")]
        assert pages == [("/v1.0/iot-01/associated-users/devices", {}), ("/v1.0/iot-01/associated-users/devices", {"last_row_key": "page2"})]
        by_uid = await api.list_devices("uid-1")
        assert [d["id"] for d in by_uid] == ["bf0light001", "bf0door001"]


# ----------------------------------------------------------------------------- error mapping
def test_cloud_error_code_mapping():
    assert cloud_error(1004, "sign invalid").code == "auth_failed"
    assert cloud_error(1010, "token invalid").code == "auth_failed"
    assert cloud_error(1106, "permission deny").code == "auth_failed"
    assert cloud_error(1400, "token invalid").code == "auth_failed"
    assert cloud_error(28841105, "No permissions. This project is not authorized").code == "auth_failed"
    assert cloud_error(2001, "device is offline").code == "unreachable"
    assert cloud_error(1000, "system error").code == "unreachable"
    assert cloud_error(1108, "uri path invalid").code == "not_found"
    assert cloud_error(2007, "device does not exist").code == "not_found"
    assert cloud_error(1100, "param is empty").code == "invalid_input"
    assert cloud_error("garbage", None).code == "invalid_input"


async def test_transport_and_http_errors_map_to_adapter_errors(cloud: FakeTuyaCloud, ctx: AdapterContext):
    async with ctx.http(base_url=BASE) as client:
        api = TuyaCloudClient(client, ACCESS_ID, SECRET)
        cloud.http_fail_next = 502
        with pytest.raises(AdapterError) as excinfo:
            await api.fetch_token()
        assert excinfo.value.code == "unreachable"
        cloud.fail_next = [{"code": 1004, "msg": "sign invalid"}]
        with pytest.raises(AdapterError) as excinfo:
            await api.fetch_token()
        assert excinfo.value.code == "auth_failed"

    def boom(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    async with AdapterContext(transport=httpx.MockTransport(boom)).http(base_url=BASE) as client:
        with pytest.raises(AdapterError) as excinfo:
            await TuyaCloudClient(client, ACCESS_ID, SECRET).fetch_token()
        assert excinfo.value.code == "unreachable"

    with pytest.raises(AdapterError) as excinfo:
        await TuyaAdapter().pair("cloud_project", cloud_payload(region="mars"), ctx)
    assert excinfo.value.code == "invalid_input"


# ----------------------------------------------------------------------------- mapping tables
def test_map_category():
    assert map_category("kg") == "switch" and map_category("cz") == "plug" and map_category("dj") == "light"
    assert map_category("cl") == "cover" and map_category("wk") == "thermostat" and map_category("mcs") == "sensor_contact"
    assert map_category("pir") == "sensor_motion" and map_category("wsdcg") == "sensor_temperature"
    assert map_category("ywbj") == "sensor_smoke" and map_category("sj") == "sensor_water" and map_category("rqbj") == "sensor_gas"
    assert map_category("sp") == "camera" and map_category("ms") == "lock" and map_category("sgbj") == "siren"
    assert map_category("mal") == "alarm_panel" and map_category("wg2") == "gateway" and map_category("wgsxj") == "gateway"
    assert map_category("zigbee_gw") == "gateway" and map_category("xyz") == "generic" and map_category(None) == "generic"
    assert set(tuya.TUYA_CATEGORY_MAP.values()) <= set(CATEGORIES)


def test_map_status_light():
    state = map_status(LIGHT["status"], "dj", tuya.functions_meta(LIGHT_FUNCTIONS))
    assert state["switch"] is True and state["work_mode"] == "white"
    assert state["brightness"] == 50  # (505-10)/990
    assert state["color_temp"] == 6500
    assert state["color"] == {"h": 120.0, "s": 100.0, "v": 50.0}
    assert state["raw_countdown_1"] == 0
    # v1 codes without metadata: 25-255 brightness, 0-255 colour hex string
    v1 = map_status([{"code": "bright_value", "value": 255}, {"code": "temp_value", "value": 0},
                     {"code": "colour_data", "value": "ff00000000ffff"}], "light")
    assert v1["brightness"] == 100 and v1["color_temp"] == 2700
    assert v1["color"] == {"h": 0.0, "s": 100.0, "v": 100.0}


def test_map_status_contact_sensor_and_flags():
    state = map_status(DOOR["status"], "mcs")
    assert state == {"contact": True, "battery": 10, "tamper": False}
    sensors = map_status([{"code": "pir", "value": "pir"}, {"code": "smoke_sensor_status", "value": "alarm"},
                          {"code": "watersensor_state", "value": "normal"}, {"code": "gas_sensor_status", "value": "1"},
                          {"code": "battery_percentage", "value": 87}, {"code": "va_temperature", "value": 236},
                          {"code": "va_humidity", "value": 61}], "sensor_multi")
    assert sensors == {"motion": True, "smoke": True, "water_leak": False, "gas": True, "battery": 87, "temperature": 23.6, "humidity": 61}
    assert map_status([{"code": "pir", "value": "none"}], "pir") == {"motion": False}
    assert map_status([{"code": "temp_current", "value": 245}], "wsdcg") == {"temperature": 24.5}
    assert map_status([{"code": "battery_state", "value": "high"}], "mcs") == {"battery": 100}


def test_map_status_thermostat_scale_from_functions():
    state = map_status(THERMO["status"], "wk", tuya.functions_meta(THERMO_FUNCTIONS))
    assert state == {"switch": True, "temp_set": 21.5, "temp_current": 23.5, "mode": "heat", "humidity_current": 45}
    # Without metadata the plausibility heuristic kicks in (235 -> 23.5, 22 stays 22)
    assert map_status([{"code": "temp_current", "value": 235}, {"code": "temp_set", "value": 22}], "thermostat") == {"temp_current": 23.5, "temp_set": 22}


def test_map_status_panel_siren_plug():
    assert map_status([{"code": "master_mode", "value": "arm"}, {"code": "sos_state", "value": True}], "mal") == {"arm_mode": "armed_away", "alarm": True}
    assert map_status([{"code": "master_mode", "value": "home"}], "alarm_panel") == {"arm_mode": "armed_home"}
    assert map_status([{"code": "alarm_switch", "value": True}, {"code": "alarm_volume", "value": "high"}], "sgbj") == {"siren": True, "volume": "high"}
    plug = map_status([{"code": "switch_1", "value": True}, {"code": "cur_power", "value": 1234}, {"code": "add_ele", "value": 2500}], "cz")
    assert plug == {"switch_1": True, "power": 123.4, "energy": 2.5}
    cover = map_status([{"code": "percent_control", "value": 30}, {"code": "percent_state", "value": 80}, {"code": "control", "value": "open"}], "cl")
    assert cover == {"position": 80, "control": "open"}


def test_encode_command_reverse_mapping():
    meta = tuya.functions_meta(LIGHT_FUNCTIONS)
    code_map = tuya.build_code_map(LIGHT_FUNCTIONS, "light")
    assert encode_command("brightness", 50, code_map, "light", meta) == [{"code": "bright_value_v2", "value": 505}]
    assert encode_command("brightness", 0, code_map, "light", meta) == [{"code": "bright_value_v2", "value": 10}]
    assert encode_command("color_temp", 4600, code_map, "light", meta) == [{"code": "temp_value_v2", "value": 500}]
    assert encode_command("switch", False, code_map, "light", meta) == [{"code": "switch_led", "value": False}]
    color = encode_command("color", {"h": 120, "s": 100, "v": 50}, code_map, "light", meta)
    assert color[0]["code"] == "colour_data_v2" and json.loads(color[0]["value"]) == {"h": 120, "s": 1000, "v": 500}
    assert encode_command("raw_countdown_1", 30, code_map, "light", meta) == [{"code": "countdown_1", "value": 30}]

    thermo_meta = tuya.functions_meta(THERMO_FUNCTIONS)
    thermo_map = tuya.build_code_map(THERMO_FUNCTIONS, "thermostat")
    assert encode_command("temp_set", 21.5, thermo_map, "thermostat", thermo_meta) == [{"code": "temp_set", "value": 215}]
    assert encode_command("mode", "cool", thermo_map, "thermostat", thermo_meta) == [{"code": "mode", "value": "cool"}]

    assert encode_command("arm_mode", "armed_away", {"arm_mode": "master_mode"}, "alarm_panel") == [{"code": "master_mode", "value": "arm"}]
    assert encode_command("arm_mode", "disarmed", {"arm_mode": "master_mode"}, "alarm_panel") == [{"code": "master_mode", "value": "disarmed"}]
    assert encode_command("position", 40, {"position": "percent_control"}, "cover") == [{"code": "percent_control", "value": 40}]
    assert encode_command("night_vision", "on", {"night_vision": "basic_nightvision"}, "camera") == [{"code": "basic_nightvision", "value": "2"}]
    assert encode_command("ptz", "left", {}, "camera") == [{"code": "ptz_control", "value": "6"}]
    assert encode_command("ptz", "stop", {}, "camera") == [{"code": "ptz_stop", "value": True}]
    assert encode_command("ptz", "zoom_in", {}, "camera") == [{"code": "zoom_control", "value": "0"}]
    with pytest.raises(AdapterError) as excinfo:
        encode_command("temperature", 20, {}, "sensor_temperature")
    assert excinfo.value.code == "unsupported"


def test_build_capabilities_light_and_sensor():
    caps = {c["code"]: c for c in build_capabilities(LIGHT_FUNCTIONS, LIGHT["status"], "dj")}
    assert caps["switch"]["writable"] and caps["switch"]["type"] == "bool"
    assert caps["brightness"] == {"code": "brightness", "type": "int", "writable": True, "unit": "%", "min": 0, "max": 100, "step": 1}
    assert caps["color_temp"]["min"] == 2700 and caps["color_temp"]["max"] == 6500 and caps["color_temp"]["unit"] == "K"
    assert caps["color"]["type"] == "color" and caps["color"]["writable"]
    assert caps["work_mode"]["values"] == ["white", "colour", "scene", "music"]
    assert caps["raw_countdown_1"] == {"code": "raw_countdown_1", "type": "int", "writable": True, "label": "countdown_1",
                                       "min": 0, "max": 86400, "step": 1, "unit": "s"}
    assert len(caps) == 6 and len(TuyaAdapter.build_capabilities(LIGHT_FUNCTIONS, LIGHT["status"], "light")) == 6

    sensor = {c["code"]: c for c in build_capabilities([], DOOR["status"], "mcs")}
    assert sensor["contact"] == {"code": "contact", "type": "bool", "writable": False}
    assert sensor["battery"]["unit"] == "%" and not sensor["battery"]["writable"] and sensor["tamper"]["type"] == "bool"

    thermo = {c["code"]: c for c in build_capabilities(THERMO_FUNCTIONS, THERMO["status"], "wk")}
    assert thermo["temp_set"]["min"] == 5.0 and thermo["temp_set"]["max"] == 35.0 and thermo["temp_set"]["step"] == 0.5
    assert thermo["mode"]["values"] == ["auto", "heat", "cool", "off"] and not thermo["temp_current"]["writable"]
    assert thermo["humidity_current"]["unit"] == "%"


# ----------------------------------------------------------------------------- adapter: cloud
def test_brand_info_and_registration():
    adapter = registry.get("tuya")
    assert isinstance(adapter, TuyaAdapter)
    info = adapter.info()
    assert info.id == "tuya" and info.protocols == ["tuya_cloud", "tuya_local"]
    cloud_method = adapter.method("cloud_project")
    assert cloud_method.requires_integration and cloud_method.supports_discovery
    region = next(f for f in cloud_method.fields if f.name == "region")
    assert {o["value"] for o in region.options} == {"us", "eu", "cn", "in"}
    assert next(f for f in cloud_method.fields if f.name == "uid").required is False
    local = adapter.method("local_key")
    assert [f.name for f in local.fields] == ["device_id", "local_key", "host", "version", "name", "category"]
    version = next(f for f in local.fields if f.name == "version")
    assert version.default == "3.3" and [o["value"] for o in version.options] == ["3.1", "3.3", "3.4", "3.5"]
    category = next(f for f in local.fields if f.name == "category")
    assert [o["value"] for o in category.options] == CATEGORIES and all(o["label"] for o in category.options)
    with pytest.raises(AdapterError):
        adapter.method("nope")


async def test_discover_cloud(adapter: TuyaAdapter, ctx: AdapterContext):
    found = await adapter.discover("cloud_project", cloud_payload(), ctx)
    assert [d.external_id for d in found] == ["bf0light001", "bf0door001", "bf0therm001", "bf0cam001"]
    assert [d.category for d in found] == ["light", "sensor_contact", "thermostat", "camera"]
    assert found[0].manufacturer == "Tuya" and found[0].model == "Smart Bulb RGBCW"
    assert found[1].extra == {"tuya_category": "mcs", "online": False, "product_id": None}
    assert await adapter.discover("local_key", {}, ctx) == []


async def test_pair_cloud_returns_integration_and_drafts(adapter: TuyaAdapter, cloud: FakeTuyaCloud, ctx: AdapterContext):
    result = await adapter.pair("cloud_project", cloud_payload(), ctx)
    assert result.integration is not None
    assert result.integration.key == f"tuya_cloud:{ACCESS_ID}" and result.integration.name == "Tuya Cloud (eu)"
    assert result.integration.config == {"region": "eu", "access_id": ACCESS_ID, "uid": "uid-1"}
    creds = result.integration.credentials
    assert creds["access_secret"] == SECRET and creds["access_token"] == "tok-1" and creds["refresh_token"] == "ref-1"
    assert creds["expires_at"] > 0
    assert cloud.token_count == 1

    assert [d.external_id for d in result.devices] == ["bf0light001", "bf0door001", "bf0therm001", "bf0cam001"]
    assert all(d.parent_external_id is None and d.protocol == "tuya_cloud" and d.credentials == {} for d in result.devices)
    light, door, thermo, camera = result.devices
    assert light.category == "light" and light.model == "Smart Bulb RGBCW" and light.manufacturer == "Tuya"
    assert light.config["region"] == "eu" and light.config["device_id"] == "bf0light001" and light.config["tuya_category"] == "dj"
    assert light.config["code_map"]["brightness"] == "bright_value_v2"
    assert light.state["brightness"] == 50 and light.state["color"]["h"] == 120.0
    assert {c["code"] for c in light.capabilities} == {"switch", "work_mode", "brightness", "color_temp", "color", "raw_countdown_1"}
    assert door.category == "sensor_contact" and door.online is False and door.state == {"contact": True, "battery": 10, "tamper": False}
    assert all(not c["writable"] for c in door.capabilities)  # /functions answered "not supported" -> read-only device
    assert thermo.state["temp_set"] == 21.5 and thermo.config["functions"]["temp_set"]["scale"] == 1
    assert camera.category == "camera" and camera.state == {"privacy_mode": False, "night_vision": "auto"}


async def test_pair_cloud_selected_ids_and_uid(adapter: TuyaAdapter, cloud: FakeTuyaCloud, ctx: AdapterContext):
    result = await adapter.pair("cloud_project", cloud_payload(uid="uid-1", selected_external_ids=["bf0door001"]), ctx)
    assert [d.external_id for d in result.devices] == ["bf0door001"]
    assert result.integration.config["uid"] == "uid-1"
    assert any(p == "/v1.0/users/uid-1/devices" for _, p, _ in cloud.requests)
    assert not any(p.startswith("/v1.0/devices/bf0light001") for _, p, _ in cloud.requests)


async def test_pair_cloud_bad_secret_is_auth_failed(adapter: TuyaAdapter, ctx: AdapterContext):
    with pytest.raises(AdapterError) as excinfo:
        await adapter.pair("cloud_project", cloud_payload(access_secret="wrong-secret"), ctx)
    assert excinfo.value.code == "auth_failed"
    with pytest.raises(AdapterError) as excinfo:
        await adapter.pair("cloud_project", {"region": "eu"}, ctx)
    assert excinfo.value.code == "invalid_input" and "access_id" in excinfo.value.message


async def test_refresh_cloud_uses_stored_token_and_maps_state(adapter: TuyaAdapter, cloud: FakeTuyaCloud, ctx: AdapterContext):
    cloud._issue()  # tok-1 is valid on the cloud side
    ref = cloud_ref(THERMO, THERMO_FUNCTIONS, {"access_token": "tok-1", "refresh_token": "ref-1", "expires_at": 9e12})
    state = await adapter.refresh(ref, ctx)
    assert state.online is True
    assert state.state == {"switch": True, "temp_set": 21.5, "temp_current": 23.5, "mode": "heat", "humidity_current": 45}
    assert [p for _, p, _ in cloud.requests] == ["/v1.0/devices/bf0therm001"]  # no token round-trip

    door = await adapter.refresh(cloud_ref(DOOR, [], {"access_token": "tok-1", "refresh_token": "ref-1", "expires_at": 9e12}), ctx)
    assert door.online is False and door.state["contact"] is True

    with pytest.raises(AdapterError) as excinfo:
        await adapter.refresh(cloud_ref({**DOOR, "id": "missing"}, [], {"access_token": "tok-1", "expires_at": 9e12}), ctx)
    assert excinfo.value.code == "not_found"


async def test_refresh_cloud_refreshes_expired_token_and_caches_it(adapter: TuyaAdapter, cloud: FakeTuyaCloud, ctx: AdapterContext):
    cloud._issue()
    ref = cloud_ref(LIGHT, LIGHT_FUNCTIONS, {"access_token": "tok-1", "refresh_token": "ref-1", "expires_at": 1.0})
    state = await adapter.refresh(ref, ctx)
    assert state.state["brightness"] == 50
    assert [p for _, p, _ in cloud.requests] == ["/v1.0/token/ref-1", "/v1.0/devices/bf0light001"]
    assert adapter._tokens[ACCESS_ID].access_token == "tok-2"  # pylint: disable=protected-access
    await adapter.refresh(ref, ctx)  # second poll reuses the in-memory token even though stored creds are stale
    assert [p for _, p, _ in cloud.requests][2:] == ["/v1.0/devices/bf0light001"]


async def test_send_command_cloud_posts_encoded_commands(adapter: TuyaAdapter, cloud: FakeTuyaCloud, ctx: AdapterContext):
    cloud._issue()
    creds = {"access_token": "tok-1", "refresh_token": "ref-1", "expires_at": 9e12}
    light = cloud_ref(LIGHT, LIGHT_FUNCTIONS, creds)
    assert await adapter.send_command(light, "brightness", 75, ctx) == {"brightness": 75}
    assert await adapter.send_command(light, "color", {"h": 200.0, "s": 50.0, "v": 100.0}, ctx) == {"color": {"h": 200.0, "s": 50.0, "v": 100.0}}
    panel = cloud_ref({"id": "bf0light001", "category": "mal"}, [{"code": "master_mode", "type": "Enum", "values": "{\"range\":[\"disarmed\",\"arm\",\"home\"]}"}], creds)
    await adapter.send_command(panel, "arm_mode", "armed_home", ctx)
    camera = cloud_ref(CAMERA, CAMERA_FUNCTIONS, creds)
    assert await adapter.send_command(camera, "ptz", "up", ctx) == {}
    assert cloud.commands[0] == ("bf0light001", [{"code": "bright_value_v2", "value": 753}])
    assert cloud.commands[1][1][0]["code"] == "colour_data_v2" and json.loads(cloud.commands[1][1][0]["value"]) == {"h": 200, "s": 500, "v": 1000}
    assert cloud.commands[2] == ("bf0light001", [{"code": "master_mode", "value": "home"}])
    assert cloud.commands[3] == ("bf0cam001", [{"code": "ptz_control", "value": "0"}])
    with pytest.raises(AdapterError) as excinfo:
        await adapter.send_command(cloud_ref(DOOR, [], creds), "contact", True, ctx)
    assert excinfo.value.code == "unsupported"


async def test_stream_cloud_camera(adapter: TuyaAdapter, cloud: FakeTuyaCloud, ctx: AdapterContext):
    cloud._issue()
    creds = {"access_token": "tok-1", "expires_at": 9e12}
    info = await adapter.stream(cloud_ref(CAMERA, CAMERA_FUNCTIONS, creds), "main", ctx)
    assert info is not None and info.url == "rtsps://stream.tuya/bf0cam001/rtsp" and info.type == "rtsp"
    sub = await adapter.stream(cloud_ref(CAMERA, CAMERA_FUNCTIONS, creds), "sub", ctx)
    assert sub.type == "hls" and sub.url.endswith("/hls")
    assert await adapter.stream(cloud_ref(LIGHT, LIGHT_FUNCTIONS, creds), "main", ctx) is None


async def test_cloud_ref_without_integration_is_auth_failed(adapter: TuyaAdapter, ctx: AdapterContext):
    ref = DeviceRef(id="d", external_id="bf0light001", brand="tuya", protocol="tuya_cloud", category="light", config={"region": "eu"})
    with pytest.raises(AdapterError) as excinfo:
        await adapter.refresh(ref, ctx)
    assert excinfo.value.code == "auth_failed"


# ----------------------------------------------------------------------------- adapter: local (tinytuya)
def fake_tinytuya(dps: Dict[str, Any], error: Optional[Dict[str, Any]] = None) -> Tuple[Any, List[Tuple[Any, ...]]]:
    """A stand-in for the tinytuya module (Device.status / Device.set_value)."""
    calls: List[Tuple[Any, ...]] = []

    class Device:  # pylint: disable=too-few-public-methods
        def __init__(self, dev_id: str, address: str, local_key: str, version: float):
            calls.append(("init", dev_id, address, local_key, version))

        def set_socketTimeout(self, seconds: int) -> None:  # pylint: disable=invalid-name
            calls.append(("timeout", seconds))

        def status(self) -> Dict[str, Any]:
            return dict(error) if error else {"dps": dict(dps)}

        def set_value(self, index: int, value: Any, nowait: bool = False) -> Dict[str, Any]:
            del nowait
            calls.append(("set", index, value))
            if error:
                return dict(error)
            dps[str(index)] = value
            return {"dps": {str(index): value}}

    return types.SimpleNamespace(Device=Device), calls


LOCAL_PAYLOAD = {"device_id": "bf1234567890abcdef01", "local_key": "0123456789abcdef", "host": "192.168.1.50", "version": "3.3",
                 "name": "Ampoule bureau", "category": "light"}


async def test_local_key_validation_without_tinytuya(adapter: TuyaAdapter, ctx: AdapterContext, monkeypatch):
    monkeypatch.setattr(tuya, "_load_tinytuya", lambda: None)
    with pytest.raises(AdapterError) as excinfo:
        await adapter.pair("local_key", {"device_id": "x"}, ctx)
    assert excinfo.value.code == "invalid_input" and "local_key" in excinfo.value.message and "host" in excinfo.value.message
    with pytest.raises(AdapterError) as excinfo:
        await adapter.pair("local_key", {**LOCAL_PAYLOAD, "local_key": "short"}, ctx)
    assert excinfo.value.code == "invalid_input" and "16" in excinfo.value.message
    with pytest.raises(AdapterError) as excinfo:
        await adapter.pair("local_key", {**LOCAL_PAYLOAD, "version": "2.0"}, ctx)
    assert excinfo.value.code == "invalid_input"
    with pytest.raises(AdapterError) as excinfo:
        await adapter.pair("local_key", {**LOCAL_PAYLOAD, "category": "toaster"}, ctx)
    assert excinfo.value.code == "invalid_input"
    # Valid input but no library: unsupported, with an actionable message
    with pytest.raises(AdapterError) as excinfo:
        await adapter.pair("local_key", LOCAL_PAYLOAD, ctx)
    assert excinfo.value.code == "unsupported" and "tinytuya" in excinfo.value.message
    ref = DeviceRef(id="d", external_id="bf1", brand="tuya", protocol="tuya_local", category="light",
                    config={"host": "192.168.1.50", "version": "3.3"}, credentials={"local_key": "0123456789abcdef"})
    with pytest.raises(AdapterError) as excinfo:
        await adapter.refresh(ref, ctx)
    assert excinfo.value.code == "unsupported"
    with pytest.raises(AdapterError) as excinfo:
        await adapter.send_command(ref, "switch", True, ctx)
    assert excinfo.value.code == "unsupported"
    assert adapter.method("local_key").fields  # form still available


async def test_local_pair_refresh_and_command_with_fake_tinytuya(adapter: TuyaAdapter, ctx: AdapterContext, monkeypatch):
    module, calls = fake_tinytuya({"20": True, "21": "colour", "22": 1000, "23": 500, "24": "{\"h\":30,\"s\":400,\"v\":1000}", "26": 0})
    monkeypatch.setattr(tuya, "_load_tinytuya", lambda: module)
    result = await adapter.pair("local_key", LOCAL_PAYLOAD, ctx)
    assert result.integration is None and len(result.devices) == 1
    draft = result.devices[0]
    assert draft.protocol == "tuya_local" and draft.name == "Ampoule bureau" and draft.category == "light"
    assert draft.credentials == {"local_key": "0123456789abcdef"}
    assert draft.config["host"] == "192.168.1.50" and draft.config["version"] == "3.3" and draft.config["dps_map"]["22"] == "bright_value_v2"
    assert draft.state == {"switch": True, "work_mode": "colour", "brightness": 100, "color_temp": 4600,
                           "color": {"h": 30.0, "s": 40.0, "v": 100.0}, "raw_countdown": 0}
    caps = {c["code"]: c for c in draft.capabilities}
    assert caps["brightness"]["writable"] and caps["color"]["writable"] and caps["work_mode"]["writable"]
    assert not caps["raw_countdown"]["writable"]
    assert calls[0] == ("init", LOCAL_PAYLOAD["device_id"], "192.168.1.50", "0123456789abcdef", 3.3)

    ref = DeviceRef(id="d", external_id=draft.external_id, brand="tuya", protocol="tuya_local", category="light",
                    config=draft.config, credentials=draft.credentials, state=draft.state, capabilities=draft.capabilities)
    partial = await adapter.send_command(ref, "brightness", 50, ctx)
    assert ("set", 22, 505) in calls and partial == {"brightness": 50}
    partial = await adapter.send_command(ref, "color", {"h": 200.0, "s": 50.0, "v": 100.0}, ctx)
    assert calls[-1][1] == 24 and json.loads(calls[-1][2]) == {"h": 200, "s": 500, "v": 1000}
    assert partial["color"] == {"h": 200.0, "s": 50.0, "v": 100.0}
    state = await adapter.refresh(ref, ctx)
    assert state.online and state.state["brightness"] == 50 and state.state["color"]["h"] == 200.0
    with pytest.raises(AdapterError) as excinfo:
        await adapter.send_command(ref, "position", 10, ctx)
    assert excinfo.value.code == "unsupported"


async def test_local_switch_gangs_sensor_and_errors(adapter: TuyaAdapter, ctx: AdapterContext, monkeypatch):
    module, calls = fake_tinytuya({"1": True, "9": 0})
    monkeypatch.setattr(tuya, "_load_tinytuya", lambda: module)
    single = (await adapter.pair("local_key", {**LOCAL_PAYLOAD, "category": "switch", "name": ""}, ctx)).devices[0]
    assert single.state == {"switch": True, "raw_dps_9": 0} and single.name.startswith("Tuya ")
    assert [c["code"] for c in single.capabilities if c["writable"]] == ["switch"]
    ref = DeviceRef(id="d", external_id=single.external_id, brand="tuya", protocol="tuya_local", category="switch",
                    config=single.config, credentials=single.credentials)
    assert await adapter.send_command(ref, "switch", False, ctx) == {"switch": False}
    assert calls[-1] == ("set", 1, False)

    module, _ = fake_tinytuya({"1": True, "2": False, "3": True})
    monkeypatch.setattr(tuya, "_load_tinytuya", lambda: module)
    multi = (await adapter.pair("local_key", {**LOCAL_PAYLOAD, "category": "switch"}, ctx)).devices[0]
    assert multi.state == {"switch_1": True, "switch_2": False, "switch_3": True}

    module, _ = fake_tinytuya({"1": True, "15": 42})
    monkeypatch.setattr(tuya, "_load_tinytuya", lambda: module)
    door = (await adapter.pair("local_key", {**LOCAL_PAYLOAD, "category": "sensor_contact"}, ctx)).devices[0]
    assert door.state == {"contact": True, "battery": 42} and all(not c["writable"] for c in door.capabilities)

    module, _ = fake_tinytuya({"1": "open", "101": 25}, None)
    monkeypatch.setattr(tuya, "_load_tinytuya", lambda: module)
    cover = (await adapter.pair("local_key", {**LOCAL_PAYLOAD, "category": "cover", "dps_map": "{\"101\": \"percent_state\"}", "invert_position": True}, ctx)).devices[0]
    assert cover.state == {"control": "open", "position": 75} and cover.config["dps_map"]["101"] == "percent_state"

    for err, expected in ((("901", "Network Error: Unable to Connect"), "unreachable"), (("914", "Check device key or version"), "auth_failed"),
                          (("903", "Function not supported"), "invalid_input")):
        module, _ = fake_tinytuya({}, {"Error": err[1], "Err": err[0], "Payload": None})
        monkeypatch.setattr(tuya, "_load_tinytuya", lambda mod=module: mod)
        with pytest.raises(AdapterError) as excinfo:
            await adapter.pair("local_key", LOCAL_PAYLOAD, ctx)
        assert excinfo.value.code == expected, err
