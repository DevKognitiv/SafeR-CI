"""Onboarding route tests: brand catalogue, categories, code parsing, discovery, pairing, integrations.

Uses the demo brand plus an in-module fake cloud brand (registered per test, removed afterwards). No network.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.hub.adapters.base import (
    AdapterContext, AdapterError, BrandAdapter, BrandInfo, DeviceDraft, DeviceRef, DeviceState, DiscoveredDevice,
    FormField, IntegrationDraft, PairResult, PairingMethod, require,
)
from app.hub.adapters.registry import registry
from app.hub.app import create_app
from app.hub.capabilities import CATEGORIES, cap, sensor_caps, switch_caps
from app.hub.models import Device, Integration, Message
from app.hub.routes.onboarding import GROUP_ORDER, parse_code
from app.hub.runtime import set_runtime
from app.hub.tests.conftest import PREFIX, make_settings, register_user

DEMO_DEVICE_COUNT = 13
BRAND = "fakecloud"


# ----------------------------------------------------------------------------- fake cloud brand
class FakeCloudAdapter(BrandAdapter):
    """Account-based brand returning an integration + a gateway with two children; supports webhooks."""

    brand_id = BRAND

    def __init__(self) -> None:
        self.pair_payloads: List[Dict[str, Any]] = []
        self.webhook_calls: List[Any] = []
        self.empty = False

    def info(self) -> BrandInfo:
        return BrandInfo(
            id=BRAND, name="Fake Cloud", vendor="SafeR QA", protocols=["fake_cloud"],
            categories=["gateway", "plug", "sensor_motion"],
            methods=[
                PairingMethod(
                    id="account", title="Compte cloud",
                    fields=[FormField(name="email", label="E-mail"), FormField(name="password", label="Mot de passe", type="password")],
                    supports_discovery=True, requires_integration=True,
                )
            ],
        )

    async def discover(self, method_id: str, payload: Dict[str, Any], ctx: AdapterContext) -> List[DiscoveredDevice]:
        self.method(method_id)
        return [DiscoveredDevice(external_id="gw-1", name="Passerelle", category="gateway"),
                DiscoveredDevice(external_id="plug-1", name="Prise", category="plug")]

    async def pair(self, method_id: str, payload: Dict[str, Any], ctx: AdapterContext) -> PairResult:
        self.method(method_id)
        require(payload, "email", "password")
        if payload["password"] == "wrong":
            raise AdapterError("Identifiants invalides", "auth_failed")
        self.pair_payloads.append(dict(payload))
        if self.empty:
            return PairResult(devices=[], message="rien")
        drafts = [
            DeviceDraft(external_id="gw-1", name="Passerelle", category="gateway", protocol="fake_cloud",
                        capabilities=[cap("child_count", "int")], state={"child_count": 2}, config={"region": "eu"}),
            DeviceDraft(external_id="plug-1", name="Prise", category="plug", protocol="fake_cloud",
                        capabilities=switch_caps(), state={"switch": False}, parent_external_id="gw-1"),
            DeviceDraft(external_id="pir-1", name="Détecteur", category="sensor_motion", protocol="fake_cloud",
                        capabilities=sensor_caps("sensor_motion"), state={"motion": False, "battery": 90},
                        parent_external_id="gw-1"),
        ]
        integration = IntegrationDraft(
            key=f"{BRAND}:{payload['email']}", name=f"Fake Cloud ({payload['email']})",
            config={"region": "eu", "account": payload["email"]}, credentials={"password": payload["password"]},
        )
        return PairResult(devices=drafts, integration=integration, message="Compte lié")

    async def refresh(self, device: DeviceRef, ctx: AdapterContext) -> DeviceState:
        return DeviceState(online=True, state=dict(device.state))

    async def send_command(self, device: DeviceRef, code: str, value: Any, ctx: AdapterContext) -> Dict[str, Any]:
        return {code: value}

    async def handle_webhook(self, integration_config: Dict[str, Any], integration_credentials: Dict[str, Any],
                             payload: Any, ctx: AdapterContext) -> List[Dict[str, Any]]:
        self.webhook_calls.append((dict(integration_config), dict(integration_credentials), payload))
        if isinstance(payload, str):
            return []  # raw text callbacks (health pings) carry nothing
        if not isinstance(payload, dict) or "events" not in payload:
            raise AdapterError("Unrecognised callback payload", "invalid_input")
        items: List[Dict[str, Any]] = []
        for event in payload["events"]:
            if "state" in event:
                items.append({"external_id": event["device"], "type": "state", "payload": {"state": event["state"], "online": True}})
            else:
                items.append({"external_id": event["device"], "type": "event", "payload": {"type": event["event"]}})
        return items


@pytest.fixture
def fake_cloud():
    """Register the fake cloud brand for one test (the registry is process-wide)."""
    adapter = FakeCloudAdapter()
    registry.register(adapter)
    try:
        yield adapter
    finally:
        registry._adapters.pop(adapter.brand_id, None)  # pylint: disable=protected-access


# ----------------------------------------------------------------------------- helpers / fixtures
async def pair(client: httpx.AsyncClient, headers: Dict, brand: str, home_id: str, **extra: Any) -> httpx.Response:
    body: Dict[str, Any] = {"home_id": home_id, "method": "virtual" if brand == "demo" else "account", "payload": {}}
    if brand != "demo":
        body["payload"] = {"email": "qa@safer.ci", "password": "s3cret"}
    body.update(extra)
    return await client.post(f"{PREFIX}/onboarding/{brand}/pair", json=body, headers=headers)


@pytest_asyncio.fixture
async def member(client: httpx.AsyncClient, auth: Dict, home: Dict) -> Dict:
    """Bob, plain member of ``home``."""
    data = await register_user(client, email="bob@safer.ci", name="Bob")
    data["headers"] = {"Authorization": f"Bearer {data['token']}"}
    response = await client.post(f"{PREFIX}/homes/{home['id']}/members", json={"email": "bob@safer.ci", "role": "member"}, headers=auth["headers"])
    assert response.status_code == 201, response.text
    return data


async def home_messages(hub_app, home_id: str) -> List[Message]:
    runtime = hub_app.state.hub_runtime
    async with runtime.db.session() as session:
        return list((await session.execute(select(Message).where(Message.home_id == home_id).order_by(Message.created_at))).scalars().all())


# ----------------------------------------------------------------------------- brands & categories
async def test_list_brands_contains_demo_with_methods_and_fields(client, auth):
    response = await client.get(f"{PREFIX}/onboarding/brands", headers=auth["headers"])
    assert response.status_code == 200, response.text
    brands = {brand["id"]: brand for brand in response.json()}
    assert "demo" in brands
    demo = brands["demo"]
    assert demo["name"] and demo["protocols"] == ["demo"] and "light" in demo["categories"]
    method = next(m for m in demo["methods"] if m["id"] == "virtual")
    assert method["supports_discovery"] is True
    assert method["fields"][0]["name"] == "prefix" and method["fields"][0]["required"] is False
    # brands are sorted by id and every one has at least one pairing method
    assert list(brands) == sorted(brands)
    assert all(brand["methods"] for brand in brands.values())

    single = await client.get(f"{PREFIX}/onboarding/brands/demo", headers=auth["headers"])
    assert single.status_code == 200 and single.json()["id"] == "demo"


async def test_brands_require_authentication(client):
    assert (await client.get(f"{PREFIX}/onboarding/brands")).status_code == 401
    assert (await client.post(f"{PREFIX}/onboarding/parse-code", json={"code": "x"})).status_code == 401


async def test_unknown_brand_404(client, auth, home):
    headers = auth["headers"]
    assert (await client.get(f"{PREFIX}/onboarding/brands/nope", headers=headers)).status_code == 404
    body = {"home_id": home["id"], "method": "x", "payload": {}}
    assert (await client.post(f"{PREFIX}/onboarding/nope/discover", json=body, headers=headers)).status_code == 404
    assert (await client.post(f"{PREFIX}/onboarding/nope/pair", json=body, headers=headers)).status_code == 404


async def test_demo_hidden_when_disabled():
    app = create_app(settings=make_settings(HUB_DEMO_ENABLED=False), database_url="sqlite+aiosqlite://", start_services=False)
    runtime = app.state.hub_runtime
    await runtime.start()
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://hub") as client:
            data = await register_user(client)
            headers = {"Authorization": f"Bearer {data['token']}"}
            response = await client.get(f"{PREFIX}/onboarding/brands", headers=headers)
            assert response.status_code == 200
            assert "demo" not in {brand["id"] for brand in response.json()}
            assert (await client.get(f"{PREFIX}/onboarding/brands/demo", headers=headers)).status_code == 404
            categories = (await client.get(f"{PREFIX}/onboarding/categories", headers=headers)).json()
            light = next(c for g in categories for c in g["categories"] if c["id"] == "light")
            assert "demo" not in light["brands"]
            home = (await client.post(f"{PREFIX}/homes", json={"name": "H"}, headers=headers)).json()
            paired = await client.post(f"{PREFIX}/onboarding/demo/pair", json={"home_id": home["id"], "method": "virtual", "payload": {}}, headers=headers)
            assert paired.status_code == 404
    finally:
        await runtime.stop()
        set_runtime(None)


async def test_categories_grouped(client, auth):
    response = await client.get(f"{PREFIX}/onboarding/categories", headers=auth["headers"])
    assert response.status_code == 200, response.text
    groups = response.json()
    assert [group["id"] for group in groups] == GROUP_ORDER
    listed = [category["id"] for group in groups for category in group["categories"]]
    assert sorted(listed) == sorted(CATEGORIES) and len(listed) == len(set(listed))
    lighting = next(group for group in groups if group["id"] == "lighting")
    assert lighting["name"] and lighting["icon"]
    light = next(category for category in lighting["categories"] if category["id"] == "light")
    assert light["group"] == "lighting" and light["icon"] == "lightbulb"
    assert "demo" in light["brands"]
    camera = next(c for g in groups for c in g["categories"] if c["id"] == "camera")
    assert camera["brands"] == sorted(camera["brands"]) and "demo" in camera["brands"]


# ----------------------------------------------------------------------------- parse-code
async def test_parse_code_matter(client, auth):
    payload = pytest.importorskip("app.hub.adapters.matter_payload")
    qr = payload.encode_qr(0xFFF1, 0x8000, 3840, 20202021)
    response = await client.post(f"{PREFIX}/onboarding/parse-code", json={"code": qr}, headers=auth["headers"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kind"] == "matter_qr" and body["brand"] == "matter" and body["method"] == "qr_code"
    assert body["data"]["passcode"] == 20202021 and body["data"]["discriminator"] == 3840
    assert body["data"]["vendor_id"] == 0xFFF1 and body["data"]["code"] == qr

    manual = payload.encode_manual_code(3840, 20202021)
    response = await client.post(f"{PREFIX}/onboarding/parse-code", json={"code": manual}, headers=auth["headers"])
    body = response.json()
    assert body["kind"] == "matter_manual" and body["method"] == "manual_code"
    assert body["data"]["passcode"] == 20202021 and body["data"]["short_discriminator"] == 15
    # A corrupted Matter payload must degrade to "unknown", never 500
    assert parse_code("MT:!!!not-base38!!!").kind == "unknown"


async def test_parse_code_tuya(client, auth):
    url = "https://smartapp.tuya.com/s/p?p=AbCdEf123&lang=fr"
    response = await client.post(f"{PREFIX}/onboarding/parse-code", json={"code": url}, headers=auth["headers"])
    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "tuya_qr" and body["brand"] == "tuya" and body["method"] == "cloud_project"
    assert body["data"]["token"] == "AbCdEf123" and body["data"]["host"] == "smartapp.tuya.com"
    assert body["data"]["query"]["lang"] == "fr"

    blob = json.dumps({"t": "tok-42", "expire": 1700000000, "app": "tuyaSmart"})
    body = (await client.post(f"{PREFIX}/onboarding/parse-code", json={"code": blob}, headers=auth["headers"])).json()
    assert body["kind"] == "tuya_qr" and body["data"]["token"] == "tok-42" and body["data"]["expire"] == 1700000000
    # JSON that mentions tuya without a token is not a share code
    assert parse_code('{"brand": "tuya", "x": 1}').kind == "unknown"


async def test_parse_code_url_and_unknown(client, auth):
    response = await client.post(f"{PREFIX}/onboarding/parse-code", json={"code": "http://192.168.1.64:8000/onvif/device_service?x=1"}, headers=auth["headers"])
    body = response.json()
    assert body["kind"] == "url" and body["brand"] is None
    assert body["data"]["host"] == "192.168.1.64" and body["data"]["port"] == 8000 and body["data"]["query"] == {"x": "1"}
    assert parse_code("rtsp://cam.local/stream1").kind == "url"

    for garbage in ("hello world", "12345", "http://", "{not json", "ftp://x/y", "éà" * 500):
        result = parse_code(garbage)
        assert result.kind == "unknown" and result.brand is None and result.data["code"] == garbage.strip()
    assert parse_code("   ").kind == "unknown"
    assert parse_code('{"a": 1}').data["json"] == {"a": 1}
    response = await client.post(f"{PREFIX}/onboarding/parse-code", json={"code": "nothing"}, headers=auth["headers"])
    assert response.status_code == 200 and response.json()["kind"] == "unknown"
    assert (await client.post(f"{PREFIX}/onboarding/parse-code", json={"code": ""}, headers=auth["headers"])).status_code == 422


# ----------------------------------------------------------------------------- discovery
async def test_discover_demo(client, auth, home, member):
    body = {"home_id": home["id"], "method": "virtual", "payload": {}}
    response = await client.post(f"{PREFIX}/onboarding/demo/discover", json=body, headers=auth["headers"])
    assert response.status_code == 200, response.text
    found = response.json()
    assert len(found) == DEMO_DEVICE_COUNT
    light = next(d for d in found if d["external_id"] == "demo-light-1")
    assert light["category"] == "light" and light["manufacturer"] == "SafeR"
    # plain members may discover too
    assert (await client.post(f"{PREFIX}/onboarding/demo/discover", json=body, headers=member["headers"])).status_code == 200
    # unknown method -> 400 (AdapterError invalid_input), foreign home -> 404
    bad = await client.post(f"{PREFIX}/onboarding/demo/discover", json={**body, "method": "bluetooth"}, headers=auth["headers"])
    assert bad.status_code == 400 and bad.json()["code"] == "invalid_input"
    other = await register_user(client, email="eve@safer.ci", name="Eve")
    foreign = await client.post(f"{PREFIX}/onboarding/demo/discover", json=body, headers={"Authorization": f"Bearer {other['token']}"})
    assert foreign.status_code == 404


async def test_discover_fake_cloud(client, auth, home, fake_cloud):
    body = {"home_id": home["id"], "method": "account", "payload": {"email": "qa@safer.ci"}}
    response = await client.post(f"{PREFIX}/onboarding/{BRAND}/discover", json=body, headers=auth["headers"])
    assert response.status_code == 200
    assert [d["external_id"] for d in response.json()] == ["gw-1", "plug-1"]


# ----------------------------------------------------------------------------- pairing
async def test_pair_demo_into_home(client, auth, home, hub_app):
    room_id = home["rooms"][0]["id"]
    response = await pair(client, auth["headers"], "demo", home["id"], room_id=room_id, payload={"prefix": "QA"})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["integration_id"] is None and body["message"]
    devices = body["devices"]
    assert len(devices) == DEMO_DEVICE_COUNT
    assert all(d["room_id"] == room_id and d["home_id"] == home["id"] and d["brand"] == "demo" for d in devices)
    assert all(d["name"].startswith("QA ") for d in devices)
    assert "credentials" not in devices[0] and "credentials_enc" not in devices[0]
    by_ext = {d["external_id"]: d for d in devices}
    assert by_ext["demo-zone-1"]["parent_id"] == by_ext["demo-panel-1"]["id"]
    assert by_ext["demo-panel-1"]["parent_id"] is None
    light = by_ext["demo-light-1"]
    assert light["state"]["brightness"] == 80 and any(c["code"] == "brightness" for c in light["capabilities"])

    # persisted and visible through the device routes
    listed = await client.get(f"{PREFIX}/homes/{home['id']}/devices", headers=auth["headers"])
    assert listed.status_code == 200 and len(listed.json()) == DEMO_DEVICE_COUNT
    rooms = await client.get(f"{PREFIX}/homes/{home['id']}/rooms", headers=auth["headers"])
    assert next(r for r in rooms.json() if r["id"] == room_id)["device_count"] == DEMO_DEVICE_COUNT
    children = await client.get(f"{PREFIX}/devices/{by_ext['demo-panel-1']['id']}/children", headers=auth["headers"])
    assert [c["external_id"] for c in children.json()] == ["demo-zone-1"]

    # one "Nouvel appareil" message per created device
    messages = [m for m in await home_messages(hub_app, home["id"]) if m.title.startswith("Nouvel appareil: ")]
    assert len(messages) == DEMO_DEVICE_COUNT
    assert all(m.kind == "home" and m.device_id for m in messages)
    assert any(m.title == "Nouvel appareil: QA Lampe salon" for m in messages)


async def test_pair_invalid_room_400(client, auth, home):
    response = await pair(client, auth["headers"], "demo", home["id"], room_id="not-a-room")
    assert response.status_code == 400
    other = (await client.post(f"{PREFIX}/homes", json={"name": "Bureau", "rooms": ["Open space"]}, headers=auth["headers"])).json()
    response = await pair(client, auth["headers"], "demo", home["id"], room_id=other["rooms"][0]["id"])
    assert response.status_code == 400 and "Room" in response.json()["detail"]
    listed = await client.get(f"{PREFIX}/homes/{home['id']}/devices", headers=auth["headers"])
    assert listed.json() == []


async def test_pair_member_forbidden(client, auth, home, member):
    response = await pair(client, member["headers"], "demo", home["id"])
    assert response.status_code == 403
    assert (await client.get(f"{PREFIX}/homes/{home['id']}/devices", headers=auth["headers"])).json() == []
    # admins may pair
    await client.patch(f"{PREFIX}/homes/{home['id']}/members/{member['user']['id']}", json={"role": "admin"}, headers=auth["headers"])
    assert (await pair(client, member["headers"], "demo", home["id"])).status_code == 201


async def test_pair_unknown_method_and_adapter_errors(client, auth, home, fake_cloud):
    response = await pair(client, auth["headers"], "demo", home["id"], method="magic")
    assert response.status_code == 400 and response.json()["code"] == "invalid_input"
    response = await pair(client, auth["headers"], BRAND, home["id"], payload={"email": "qa@safer.ci"})
    assert response.status_code == 400 and "password" in response.json()["detail"]
    response = await pair(client, auth["headers"], BRAND, home["id"], payload={"email": "qa@safer.ci", "password": "wrong"})
    assert response.status_code == 401 and response.json()["code"] == "auth_failed"
    fake_cloud.empty = True
    response = await pair(client, auth["headers"], BRAND, home["id"])
    assert response.status_code == 400 and response.json()["detail"] == "Aucun appareil trouvé"
    assert (await client.get(f"{PREFIX}/homes/{home['id']}/integrations", headers=auth["headers"])).json() == []


async def test_pair_selected_external_ids_subset(client, auth, home, fake_cloud):
    response = await pair(client, auth["headers"], "demo", home["id"], selected_external_ids=["demo-light-1", "demo-zone-1", " ", "ghost"])
    assert response.status_code == 201, response.text
    devices = {d["external_id"]: d for d in response.json()["devices"]}
    # the selected zone drags its parent panel in; nothing else is persisted
    assert set(devices) == {"demo-light-1", "demo-zone-1", "demo-panel-1"}
    assert devices["demo-zone-1"]["parent_id"] == devices["demo-panel-1"]["id"]
    listed = await client.get(f"{PREFIX}/homes/{home['id']}/devices", headers=auth["headers"])
    assert len(listed.json()) == 3

    # the adapter receives the (cleaned) selection inside its payload
    response = await pair(client, auth["headers"], BRAND, home["id"], selected_external_ids=["plug-1", "plug-1"])
    assert response.status_code == 201, response.text
    assert fake_cloud.pair_payloads[-1]["selected_external_ids"] == ["plug-1"]
    assert {d["external_id"] for d in response.json()["devices"]} == {"gw-1", "plug-1"}
    # selecting only unknown ids -> 400, nothing persisted
    response = await pair(client, auth["headers"], BRAND, home["id"], selected_external_ids=["nope"])
    assert response.status_code == 400
    # an explicit empty list means "everything"
    response = await pair(client, auth["headers"], BRAND, home["id"], selected_external_ids=[])
    assert response.status_code == 201 and len(response.json()["devices"]) == 3
    assert "selected_external_ids" not in fake_cloud.pair_payloads[-1]


async def test_pair_twice_updates_instead_of_duplicating(client, auth, home, hub_app):
    first = await pair(client, auth["headers"], "demo", home["id"])
    assert first.status_code == 201
    ids = {d["external_id"]: d["id"] for d in first.json()["devices"]}
    room_id = home["rooms"][1]["id"]
    second = await pair(client, auth["headers"], "demo", home["id"], room_id=room_id, payload={"prefix": "V2"})
    assert second.status_code == 201, second.text
    devices = second.json()["devices"]
    assert len(devices) == DEMO_DEVICE_COUNT
    assert {d["external_id"]: d["id"] for d in devices} == ids  # same rows, no duplicates
    listed = (await client.get(f"{PREFIX}/homes/{home['id']}/devices", headers=auth["headers"])).json()
    assert len(listed) == DEMO_DEVICE_COUNT
    # existing devices keep their name/room (materialize only updates protocol/capabilities/state/config)
    light = next(d for d in listed if d["external_id"] == "demo-light-1")
    assert light["name"] == "Lampe salon" and light["room_id"] is None
    messages = [m for m in await home_messages(hub_app, home["id"]) if m.title.startswith("Nouvel appareil: ")]
    assert len(messages) == DEMO_DEVICE_COUNT  # no new "added" messages on the second pass
    runtime = hub_app.state.hub_runtime
    async with runtime.db.session() as session:
        rows = (await session.execute(select(Device).where(Device.home_id == home["id"]))).scalars().all()
        assert len(rows) == DEMO_DEVICE_COUNT


# ----------------------------------------------------------------------------- integrations
async def test_integrations_list_and_delete(client, auth, home, member, fake_cloud, hub_app):
    headers = auth["headers"]
    response = await pair(client, headers, BRAND, home["id"])
    assert response.status_code == 201, response.text
    body = response.json()
    integration_id = body["integration_id"]
    assert integration_id and body["message"] == "Compte lié"
    devices = {d["external_id"]: d for d in body["devices"]}
    assert len(devices) == 3 and all(d["integration_id"] == integration_id for d in devices.values())
    assert devices["plug-1"]["parent_id"] == devices["gw-1"]["id"]

    listed = await client.get(f"{PREFIX}/homes/{home['id']}/integrations", headers=headers)
    assert listed.status_code == 200, listed.text
    integrations = listed.json()
    assert len(integrations) == 1
    item = integrations[0]
    assert item["id"] == integration_id and item["brand"] == BRAND and item["key"] == f"{BRAND}:qa@safer.ci"
    assert item["name"] == "Fake Cloud (qa@safer.ci)" and item["config"] == {"region": "eu", "account": "qa@safer.ci"}
    assert "credentials" not in item and "credentials_enc" not in item and "webhook_secret" not in item
    # credentials are stored encrypted and a webhook secret was generated at pairing time
    runtime = hub_app.state.hub_runtime
    async with runtime.db.session() as session:
        row = await session.get(Integration, integration_id)
        assert row.credentials_enc and "s3cret" not in row.credentials_enc
        assert runtime.vault.decrypt(row.credentials_enc) == {"password": "s3cret"}
        assert row.webhook_secret and len(row.webhook_secret) >= 24
    # pairing again with the same account reuses the integration
    again = await pair(client, headers, BRAND, home["id"])
    assert again.status_code == 201 and again.json()["integration_id"] == integration_id
    assert len((await client.get(f"{PREFIX}/homes/{home['id']}/integrations", headers=headers)).json()) == 1

    # members can list but not delete
    assert (await client.get(f"{PREFIX}/homes/{home['id']}/integrations", headers=member["headers"])).status_code == 200
    assert (await client.delete(f"{PREFIX}/integrations/{integration_id}", headers=member["headers"])).status_code == 403
    deleted = await client.delete(f"{PREFIX}/integrations/{integration_id}", headers=headers)
    assert deleted.status_code == 204, deleted.text
    assert (await client.get(f"{PREFIX}/homes/{home['id']}/integrations", headers=headers)).json() == []
    assert (await client.get(f"{PREFIX}/homes/{home['id']}/devices", headers=headers)).json() == []
    assert (await client.delete(f"{PREFIX}/integrations/{integration_id}", headers=headers)).status_code == 404
    async with runtime.db.session() as session:
        assert (await session.execute(select(Device).where(Device.home_id == home["id"]))).scalars().all() == []


async def test_integration_webhook_url(client, auth, home, member, fake_cloud, hub_app):
    headers = auth["headers"]
    integration_id = (await pair(client, headers, BRAND, home["id"])).json()["integration_id"]
    response = await client.get(f"{PREFIX}/integrations/{integration_id}/webhook", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    secret = body["secret"]
    assert body["url"] == f"{PREFIX}/webhooks/{BRAND}/{integration_id}?secret={secret}"
    assert body["absolute_url"].endswith(body["url"]) and body["absolute_url"].startswith("http://hub/")
    assert body["brand"] == BRAND and body["integration_id"] == integration_id
    assert (await client.get(f"{PREFIX}/integrations/{integration_id}/webhook", headers=headers)).json()["secret"] == secret
    assert (await client.get(f"{PREFIX}/integrations/{integration_id}/webhook", headers=member["headers"])).status_code == 403
    assert (await client.get(f"{PREFIX}/integrations/missing/webhook", headers=headers)).status_code == 404

    # a secret is generated on demand when the row has none
    runtime = hub_app.state.hub_runtime
    async with runtime.db.session() as session:
        row = await session.get(Integration, integration_id)
        row.webhook_secret = None
        await session.commit()
    regenerated = (await client.get(f"{PREFIX}/integrations/{integration_id}/webhook", headers=headers)).json()["secret"]
    assert regenerated and regenerated != secret
    rotated = await client.post(f"{PREFIX}/integrations/{integration_id}/webhook/rotate", headers=headers)
    assert rotated.status_code == 200 and rotated.json()["secret"] not in (secret, regenerated)


async def test_device_webhook_url(client, auth, home, member):
    headers = auth["headers"]
    devices = (await pair(client, headers, "demo", home["id"])).json()["devices"]
    pir = next(d for d in devices if d["external_id"] == "demo-pir-1")
    assert "webhook_secret" not in pir["config"]
    response = await client.get(f"{PREFIX}/devices/{pir['id']}/webhook", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["url"] == f"{PREFIX}/webhooks/generic/{pir['id']}?secret={body['secret']}"
    assert body["brand"] == "generic" and body["device_id"] == pir["id"] and body["integration_id"] is None
    # stable across calls and persisted in the device config
    assert (await client.get(f"{PREFIX}/devices/{pir['id']}/webhook", headers=headers)).json()["secret"] == body["secret"]
    device = (await client.get(f"{PREFIX}/devices/{pir['id']}", headers=headers)).json()
    assert device["config"]["webhook_secret"] == body["secret"]
    assert (await client.get(f"{PREFIX}/devices/{pir['id']}/webhook", headers=member["headers"])).status_code == 403
