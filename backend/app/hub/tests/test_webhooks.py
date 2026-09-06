"""Webhook route tests: brand callbacks through a fake cloud adapter and the generic per-device endpoint.

No JWT is involved on the webhook routes; everything else (pairing, reading devices) uses the conftest client.
"""
from __future__ import annotations

from typing import Any, Dict, List

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.hub import events as ev
from app.hub.adapters.registry import registry
from app.hub.models import DeviceEvent, Integration, Message
from app.hub.routes.webhooks import SECRET_HEADER
from app.hub.tests.conftest import PREFIX
from app.hub.tests.test_onboarding import BRAND, FakeCloudAdapter, pair

WEBHOOKS = f"{PREFIX}/webhooks"


@pytest.fixture
def fake_cloud():
    """Register the fake cloud brand for one test (the registry is process-wide)."""
    adapter = FakeCloudAdapter()
    registry.register(adapter)
    try:
        yield adapter
    finally:
        registry._adapters.pop(adapter.brand_id, None)  # pylint: disable=protected-access


@pytest_asyncio.fixture
async def cloud(client: httpx.AsyncClient, auth: Dict, home: Dict, fake_cloud: FakeCloudAdapter) -> Dict[str, Any]:
    """Fake cloud paired into ``home``: ``{integration_id, secret, url, devices{external_id: device}}``."""
    response = await pair(client, auth["headers"], BRAND, home["id"])
    assert response.status_code == 201, response.text
    integration_id = response.json()["integration_id"]
    hook = (await client.get(f"{PREFIX}/integrations/{integration_id}/webhook", headers=auth["headers"])).json()
    return {
        "integration_id": integration_id, "secret": hook["secret"], "url": hook["url"],
        "devices": {d["external_id"]: d for d in response.json()["devices"]}, "adapter": fake_cloud,
    }


@pytest_asyncio.fixture
async def pir(client: httpx.AsyncClient, auth: Dict, home: Dict) -> Dict[str, Any]:
    """Demo motion sensor with a generic webhook secret: ``{device, secret, url}``."""
    devices = (await pair(client, auth["headers"], "demo", home["id"])).json()["devices"]
    device = next(d for d in devices if d["external_id"] == "demo-pir-1")
    hook = (await client.get(f"{PREFIX}/devices/{device['id']}/webhook", headers=auth["headers"])).json()
    return {"device": device, "secret": hook["secret"], "url": hook["url"]}


async def device_events(client: httpx.AsyncClient, headers: Dict, device_id: str) -> List[Dict[str, Any]]:
    response = await client.get(f"{PREFIX}/devices/{device_id}/events", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def get_device(client: httpx.AsyncClient, headers: Dict, device_id: str) -> Dict[str, Any]:
    response = await client.get(f"{PREFIX}/devices/{device_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def callback(*events: Dict[str, Any]) -> Dict[str, Any]:
    return {"account": "qa@safer.ci", "events": list(events)}


# ----------------------------------------------------------------------------- brand webhooks
async def test_webhook_secret_required(client, cloud):
    base = f"{WEBHOOKS}/{BRAND}/{cloud['integration_id']}"
    body = callback({"device": "plug-1", "state": {"switch": True}})
    response = await client.post(base, json=body)
    assert response.status_code == 401 and "secret" in response.json()["detail"].lower()
    assert (await client.post(f"{base}?secret=", json=body)).status_code == 401
    assert (await client.post(f"{base}?secret=wrong-{cloud['secret']}", json=body)).status_code == 401
    assert (await client.post(f"{base}?secret={cloud['secret'][:-1]}", json=body)).status_code == 401
    assert cloud["adapter"].webhook_calls == []  # the adapter is never reached without a valid secret
    # the secret may also travel in a header, and the URL handed out by the API works as-is
    assert (await client.post(base, json=body, headers={SECRET_HEADER: cloud["secret"]})).status_code == 200
    assert (await client.post(cloud["url"], json=body)).status_code == 200


async def test_webhook_unknown_integration_or_brand_mismatch_404(client, cloud, home, hub_app):
    body = callback({"device": "plug-1", "state": {"switch": True}})
    secret = cloud["secret"]
    assert (await client.post(f"{WEBHOOKS}/{BRAND}/does-not-exist?secret={secret}", json=body)).status_code == 404
    # right id, wrong brand in the path
    assert (await client.post(f"{WEBHOOKS}/demo/{cloud['integration_id']}?secret={secret}", json=body)).status_code == 404
    assert (await client.post(f"{WEBHOOKS}/ghost/{cloud['integration_id']}?secret={secret}", json=body)).status_code == 404
    # an integration whose adapter is no longer registered
    runtime = hub_app.state.hub_runtime
    async with runtime.db.session() as session:
        session.add(Integration(home_id=home["id"], brand="vanished", key="vanished:1", name="Old", webhook_secret="s"))
        await session.commit()
        orphan = (await session.execute(select(Integration).where(Integration.brand == "vanished"))).scalar_one()
    assert (await client.post(f"{WEBHOOKS}/vanished/{orphan.id}?secret=s", json=body)).status_code == 404
    assert cloud["adapter"].webhook_calls == []


async def test_webhook_accepted_applies_state_and_events(client, auth, cloud, hub_app):
    runtime = hub_app.state.hub_runtime
    seen: List[ev.HubEvent] = []

    async def _collect(event: ev.HubEvent) -> None:
        seen.append(event)

    unsubscribe = runtime.bus.subscribe(_collect)
    try:
        body = callback({"device": "plug-1", "state": {"switch": True}}, {"device": "pir-1", "event": "tamper"})
        response = await client.post(cloud["url"], json=body)
    finally:
        unsubscribe()
    assert response.status_code == 200, response.text
    assert response.json() == {"accepted": 2, "ignored": 0}

    plug, pir = cloud["devices"]["plug-1"], cloud["devices"]["pir-1"]
    assert (await get_device(client, auth["headers"], plug["id"]))["state"]["switch"] is True
    events = await device_events(client, auth["headers"], pir["id"])
    assert [e["type"] for e in events] == ["tamper"] and events[0]["device_id"] == pir["id"]
    state_events = [e for e in seen if e.type == ev.DEVICE_STATE and e.device_id == plug["id"]]
    assert state_events and state_events[0].payload["changed"] == {"switch": True}
    assert any(e.type == ev.DEVICE_EVENT and e.device_id == pir["id"] for e in seen)

    # the adapter got the integration config and the *decrypted* credentials
    config, credentials, payload = cloud["adapter"].webhook_calls[-1]
    assert config == {"region": "eu", "account": "qa@safer.ci"}
    assert credentials == {"password": "s3cret"}
    assert payload == body

    # a state push may also flip the sensor and record a notable event + alarm message
    response = await client.post(cloud["url"], json=callback({"device": "pir-1", "state": {"motion": True, "battery": 12}}))
    assert response.json()["accepted"] == 1
    device = await get_device(client, auth["headers"], pir["id"])
    assert device["state"]["motion"] is True and device["state"]["battery"] == 12 and device["online"] is True
    assert [e["type"] for e in await device_events(client, auth["headers"], pir["id"])] == ["motion", "tamper"]
    async with runtime.db.session() as session:
        titles = [m.title for m in (await session.execute(select(Message).where(Message.device_id == pir["id"]))).scalars().all()]
    assert any(title.startswith("Mouvement détecté") for title in titles)


async def test_webhook_unknown_devices_and_malformed_items(client, auth, cloud):
    body = callback(
        {"device": "not-paired", "state": {"switch": True}},
        {"raw": {"external_id": "plug-1", "type": "bogus", "payload": {}}},
        {"raw": {"type": "state", "payload": {"state": {"switch": True}}}},
        {"raw": "garbage"},
        {"raw": {"external_id": "plug-1", "type": "event", "payload": None}},
    )
    response = await client.post(cloud["url"], json=body)
    assert response.status_code == 200, response.text
    assert response.json() == {"accepted": 2, "ignored": 3}
    plug = cloud["devices"]["plug-1"]
    assert (await get_device(client, auth["headers"], plug["id"]))["state"]["switch"] is False
    assert [e["type"] for e in await device_events(client, auth["headers"], plug["id"])] == ["event"]


async def test_webhook_body_decoding(client, cloud):
    adapter = cloud["adapter"]
    url = cloud["url"]
    # raw text (health ping)
    response = await client.post(url, content=b"ping", headers={"Content-Type": "text/plain"})
    assert response.status_code == 200 and response.json()["accepted"] == 0
    assert adapter.webhook_calls[-1][2] == "ping"
    # empty body -> ""
    assert (await client.post(url)).status_code == 200
    assert adapter.webhook_calls[-1][2] == ""
    # form-encoded -> dict (the fake adapter rejects it: no "events")
    response = await client.post(url, data={"hubId": "1", "event": "ARMED"})
    assert response.status_code == 400 and response.json()["code"] == "invalid_input"
    assert adapter.webhook_calls[-1][2] == {"hubId": "1", "event": "ARMED"}
    # JSON without a content-type is still decoded
    response = await client.post(url, content=b'{"events": []}', headers={"Content-Type": ""})
    assert response.status_code == 200 and adapter.webhook_calls[-1][2] == {"events": []}
    # a JSON array is passed as-is (any JSON value)
    response = await client.post(url, content=b"[1, 2]", headers={"Content-Type": "application/json"})
    assert response.status_code == 400 and adapter.webhook_calls[-1][2] == [1, 2]
    # declared JSON but malformed -> 400 before the adapter is called
    calls = len(adapter.webhook_calls)
    response = await client.post(url, content=b"{not json", headers={"Content-Type": "application/json"})
    assert response.status_code == 400 and len(adapter.webhook_calls) == calls
    # unicode in text bodies survives
    response = await client.post(url, content="événement".encode("utf-8"), headers={"Content-Type": "text/plain; charset=utf-8"})
    assert response.status_code == 200 and adapter.webhook_calls[-1][2] == "événement"


async def test_webhook_body_too_large_413(client, cloud):
    response = await client.post(cloud["url"], content=b"x" * (1024 * 1024 + 1), headers={"Content-Type": "text/plain"})
    assert response.status_code == 413
    assert cloud["adapter"].webhook_calls == []


async def test_webhook_unsupported_brand_501(client, home, hub_app):
    runtime = hub_app.state.hub_runtime
    async with runtime.db.session() as session:
        integration = Integration(home_id=home["id"], brand="demo", key="demo:hooks", name="Demo", webhook_secret="demo-secret")
        session.add(integration)
        await session.commit()
        integration_id = integration.id
    response = await client.post(f"{WEBHOOKS}/demo/{integration_id}?secret=demo-secret", json={"anything": True})
    assert response.status_code == 501, response.text
    assert response.json()["code"] == "unsupported"
    assert (await client.post(f"{WEBHOOKS}/demo/{integration_id}?secret=nope", json={})).status_code == 401


# ----------------------------------------------------------------------------- generic webhooks
async def test_generic_webhook_secret_required(client, auth, home):
    devices = (await pair(client, auth["headers"], "demo", home["id"])).json()["devices"]
    door = next(d for d in devices if d["external_id"] == "demo-door-1")
    body = {"state": {"contact": True}}
    # no secret configured on the device yet -> the endpoint is disabled
    assert (await client.post(f"{WEBHOOKS}/generic/{door['id']}?secret=anything", json=body)).status_code == 401
    hook = (await client.get(f"{PREFIX}/devices/{door['id']}/webhook", headers=auth["headers"])).json()
    assert (await client.post(f"{WEBHOOKS}/generic/{door['id']}", json=body)).status_code == 401
    assert (await client.post(f"{WEBHOOKS}/generic/{door['id']}?secret=wrong", json=body)).status_code == 401
    assert (await client.post(f"{WEBHOOKS}/generic/missing?secret={hook['secret']}", json=body)).status_code == 404
    assert (await get_device(client, auth["headers"], door["id"]))["state"]["contact"] is False
    response = await client.post(hook["url"], json=body)
    assert response.status_code == 200 and response.json()["accepted"] == 1
    assert (await get_device(client, auth["headers"], door["id"]))["state"]["contact"] is True
    # header form
    response = await client.post(f"{WEBHOOKS}/generic/{door['id']}", json={"state": {"contact": False}}, headers={SECRET_HEADER: hook["secret"]})
    assert response.status_code == 200


async def test_generic_webhook_applies_state_and_records_events(client, auth, pir, hub_app):
    headers = auth["headers"]
    device_id = pir["device"]["id"]
    response = await client.post(pir["url"], json={"state": {"motion": True, "battery": 55}})
    assert response.status_code == 200, response.text
    assert response.json() == {"accepted": 1, "ignored": 0}
    device = await get_device(client, headers, device_id)
    assert device["state"]["motion"] is True and device["state"]["battery"] == 55 and device["online"] is True
    events = await device_events(client, headers, device_id)
    assert [e["type"] for e in events] == ["motion"] and events[0]["payload"]["value"] is True

    # online flag -> offline event + notice message
    response = await client.post(pir["url"], json={"online": False})
    assert response.status_code == 200 and response.json()["accepted"] == 1
    device = await get_device(client, headers, device_id)
    assert device["online"] is False and device["state"]["motion"] is True
    assert [e["type"] for e in await device_events(client, headers, device_id)] == ["online", "motion"]

    # ad-hoc event with extra payload, plus a state update in the same body
    response = await client.post(pir["url"], json={"event": {"type": "button_pressed", "button": 2}, "state": {"motion": False}, "online": "on"})
    assert response.status_code == 200 and response.json()["accepted"] == 2
    device = await get_device(client, headers, device_id)
    assert device["online"] is True and device["state"]["motion"] is False
    events = await device_events(client, headers, device_id)
    assert events[0]["type"] == "button_pressed" and events[0]["payload"] == {"button": 2}
    # event given as a bare type string and an "events" list
    response = await client.post(pir["url"], json={"event": "ping", "events": ["a", {"type": "b", "n": 1}]})
    assert response.json()["accepted"] == 3
    assert [e["type"] for e in await device_events(client, headers, device_id)][:3] == ["b", "a", "ping"]

    runtime = hub_app.state.hub_runtime
    async with runtime.db.session() as session:
        rows = (await session.execute(select(DeviceEvent).where(DeviceEvent.device_id == device_id))).scalars().all()
        assert len(rows) == 7 and all(row.home_id == pir["device"]["home_id"] for row in rows)
        titles = [m.title for m in (await session.execute(select(Message).where(Message.device_id == device_id))).scalars().all()]
    assert any(t.startswith("Mouvement détecté") for t in titles) and any(t.startswith("Appareil hors ligne") for t in titles)


async def test_generic_webhook_validation(client, auth, pir):
    url = pir["url"]
    for bad in ({}, {"foo": 1}, {"state": 5}, {"state": {"motion": True}, "online": "maybe"}, {"event": 5}, {"events": "x"}):
        response = await client.post(url, json=bad)
        assert response.status_code == 400, (bad, response.text)
    assert (await client.post(url, json=[1, 2])).status_code == 400
    assert (await client.post(url, content=b"plain text", headers={"Content-Type": "text/plain"})).status_code == 400
    assert (await client.post(url, content=b"{oops", headers={"Content-Type": "application/json"})).status_code == 400
    device = await get_device(client, auth["headers"], pir["device"]["id"])
    assert device["state"]["motion"] is False and device["online"] is True
    assert await device_events(client, auth["headers"], pir["device"]["id"]) == []
    # "online" alone with a textual boolean is accepted
    response = await client.post(url, json={"online": "off"})
    assert response.status_code == 200
    assert (await get_device(client, auth["headers"], pir["device"]["id"]))["online"] is False
