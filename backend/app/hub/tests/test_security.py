"""Security tab tests: state, arm/disarm propagation, software alarm, alarm clear and SOS (no network)."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from app.hub import events as ev
from app.hub.adapters.base import (
    AdapterContext, AdapterError, BrandAdapter, BrandInfo, DeviceDraft, DeviceRef, DeviceState, PairResult,
    PairingMethod,
)
from app.hub.adapters.registry import registry
from app.hub.app import create_app
from app.hub.capabilities import alarm_panel_caps
from app.hub.models import Device, Home
from app.hub.runtime import set_runtime
from app.hub.schemas import DeviceOut
from app.hub.services.security_service import MODE_LABELS, set_security_mode
from app.hub.tests.conftest import PREFIX, make_settings, register_user

INCIDENTS_URL = "https://api.test/incidents"


# ----------------------------------------------------------------------------- fake hardware panel
class FakePanelAdapter(BrandAdapter):
    """A hardware panel brand: records commands, fails on demand (``fail_arm`` / ``fail_clear`` = error code)."""

    brand_id = "fakepanel"

    def __init__(self) -> None:
        self.calls: List[tuple] = []
        self.fail_arm: Optional[str] = None
        self.fail_clear: Optional[str] = None
        self.clear_codes = {"clear_alarm"}
        self.state: Dict[str, Any] = {"arm_mode": "disarmed", "alarm": False, "triggered_zone": "", "ready": True}

    def info(self) -> BrandInfo:
        return BrandInfo(id=self.brand_id, name="Fake panel", protocols=["fake"], categories=["alarm_panel"],
                         methods=[PairingMethod(id="manual", title="Manual")])

    async def pair(self, method_id: str, payload: Dict[str, Any], ctx: AdapterContext) -> PairResult:
        return PairResult(devices=[panel_draft()])

    async def refresh(self, device: DeviceRef, ctx: AdapterContext) -> DeviceState:
        return DeviceState(online=True, state=dict(self.state))

    async def send_command(self, device: DeviceRef, code: str, value: Any, ctx: AdapterContext) -> Dict[str, Any]:
        self.calls.append((code, value))
        if code == "arm_mode":
            if self.fail_arm:
                raise AdapterError(f"simulated {self.fail_arm}", self.fail_arm)
            self.state.update({"arm_mode": value, "alarm": False})
            return {"arm_mode": value, "alarm": False}
        if code in self.clear_codes:
            if self.fail_clear:
                raise AdapterError(f"simulated {self.fail_clear}", self.fail_clear)
            self.state.update({"alarm": False, "triggered_zone": ""})
            return {"alarm": False, "triggered_zone": ""}
        raise AdapterError(f"Command '{code}' is not supported", "unsupported")


def panel_draft() -> DeviceDraft:
    return DeviceDraft(external_id="fp-panel", name="Centrale test", category="alarm_panel", protocol="fake",
                       capabilities=alarm_panel_caps(),
                       state={"arm_mode": "disarmed", "alarm": False, "triggered_zone": "", "ready": True})


@pytest.fixture
def fake_panel():
    adapter = FakePanelAdapter()
    registry.register(adapter)
    try:
        yield adapter
    finally:
        registry._adapters.pop(adapter.brand_id, None)  # pylint: disable=protected-access


# ----------------------------------------------------------------------------- helpers / fixtures
async def materialize(hub_app: FastAPI, home_id: str, brand: str, result: PairResult) -> Dict[str, dict]:
    runtime = hub_app.state.hub_runtime
    async with runtime.db.session() as session:
        rows, _ = await runtime.services["devices"].materialize(session, home_id, None, brand, result)
        return {row.external_id: DeviceOut.model_validate(row).model_dump(mode="json") for row in rows}


async def pair_demo(hub_app: FastAPI, home_id: str) -> Dict[str, dict]:
    """Pair the demo brand through the device service (the adapter is a process-wide singleton: reset it)."""
    adapter = registry.get("demo")
    adapter._state.clear()  # pylint: disable=protected-access
    result = await adapter.pair("virtual", {}, hub_app.state.hub_runtime.ctx_for("demo"))
    return await materialize(hub_app, home_id, "demo", result)


@pytest_asyncio.fixture
async def devices(hub_app: FastAPI, home: Dict) -> Dict[str, dict]:
    """Demo devices paired into ``home``, keyed by external id."""
    return await pair_demo(hub_app, home["id"])


async def report(hub_app: FastAPI, device_id: str, state: Dict[str, Any]) -> None:
    """Simulate a device reporting ``state`` (what the poller / push subscriptions do)."""
    runtime = hub_app.state.hub_runtime
    async with runtime.db.session() as session:
        device = await session.get(Device, device_id)
        await runtime.services["devices"].apply_state(session, device, state, online=True)


def collect_events(hub_app: FastAPI, *types: str) -> List[ev.HubEvent]:
    seen: List[ev.HubEvent] = []

    async def _listener(event: ev.HubEvent) -> None:
        if not types or event.type in types:
            seen.append(event)

    hub_app.state.hub_runtime.bus.subscribe(_listener)
    return seen


async def security(client: httpx.AsyncClient, auth: Dict, home_id: str) -> dict:
    response = await client.get(f"{PREFIX}/homes/{home_id}/security", headers=auth["headers"])
    assert response.status_code == 200, response.text
    return response.json()


async def set_mode(client: httpx.AsyncClient, auth: Dict, home_id: str, mode: str) -> dict:
    response = await client.post(f"{PREFIX}/homes/{home_id}/security/mode", json={"mode": mode}, headers=auth["headers"])
    assert response.status_code == 200, response.text
    return response.json()


async def messages(client: httpx.AsyncClient, auth: Dict, home_id: str, **params: Any) -> List[dict]:
    response = await client.get(f"{PREFIX}/homes/{home_id}/messages", params=params, headers=auth["headers"])
    assert response.status_code == 200, response.text
    return response.json()


async def device_state(client: httpx.AsyncClient, auth: Dict, device_id: str) -> dict:
    response = await client.get(f"{PREFIX}/devices/{device_id}", headers=auth["headers"])
    assert response.status_code == 200, response.text
    return response.json()["state"]


# ----------------------------------------------------------------------------- state
async def test_security_state_lists_panels_zones_and_sensors(client, auth, home, devices):
    body = await security(client, auth, home["id"])
    assert body["home_id"] == home["id"]
    assert body["mode"] == "disarmed" and body["alarm_active"] is False and body["alarm_device_id"] is None
    assert body["changed_at"] is None
    assert [p["external_id"] for p in body["panels"]] == ["demo-panel-1"]
    assert body["panels"][0]["state"]["arm_mode"] == "disarmed"
    assert [z["external_id"] for z in body["zones"]] == ["demo-zone-1"]
    assert body["zones"][0]["parent_id"] == devices["demo-panel-1"]["id"]
    sensors = {s["external_id"]: s["category"] for s in body["sensors"]}
    assert sensors == {
        "demo-door-1": "sensor_contact", "demo-pir-1": "sensor_motion", "demo-smoke-1": "sensor_smoke",
        "demo-water-1": "sensor_water", "demo-lock-1": "lock",
    }
    assert "credentials_enc" not in body["panels"][0]


async def test_security_state_requires_membership(client, home):
    outsider = await register_user(client, email="eve@safer.ci", name="Eve")
    headers = {"Authorization": f"Bearer {outsider['token']}"}
    assert (await client.get(f"{PREFIX}/homes/{home['id']}/security", headers=headers)).status_code == 404
    assert (await client.post(f"{PREFIX}/homes/{home['id']}/security/mode", json={"mode": "armed_away"}, headers=headers)).status_code == 404
    assert (await client.post(f"{PREFIX}/homes/{home['id']}/sos", json={}, headers=headers)).status_code == 404
    assert (await client.get(f"{PREFIX}/homes/{home['id']}/security")).status_code == 401


# ----------------------------------------------------------------------------- arm / disarm
async def test_set_mode_propagates_to_demo_panel_and_notifies(client, auth, home, devices, hub_app):
    modes = collect_events(hub_app, ev.SECURITY_MODE)
    news = collect_events(hub_app, ev.MESSAGE_NEW)
    body = await set_mode(client, auth, home["id"], "armed_away")
    assert body["mode"] == "armed_away" and body["changed_at"] is not None
    assert body["panels"][0]["state"]["arm_mode"] == "armed_away"  # response already reflects the panel
    # The virtual panel really received the command
    assert (await device_state(client, auth, devices["demo-panel-1"]["id"]))["arm_mode"] == "armed_away"
    adapter = registry.get("demo")
    assert adapter._state["demo-panel-1"]["arm_mode"] == "armed_away"  # pylint: disable=protected-access
    # Exactly one security.mode event (no duplicate from the panel state mirror), tagged as a user action
    assert len(modes) == 1
    assert modes[0].home_id == home["id"] and modes[0].payload == {"mode": "armed_away", "source": "user"}
    # A "home" message with the French label, pushed on the bus too
    items = await messages(client, auth, home["id"], kind="home")
    assert items[0]["title"] == "Mode sécurité: Armé (absence)" and items[0]["severity"] == "info" and items[0]["read"] is False
    assert any(e.payload["message"]["title"] == "Mode sécurité: Armé (absence)" for e in news)
    # Home listing mirrors the new mode
    homes = await client.get(f"{PREFIX}/homes", headers=auth["headers"])
    assert homes.json()[0]["security_mode"] == "armed_away"


async def test_set_mode_labels_every_mode(client, auth, home, devices):
    for mode, label in MODE_LABELS.items():
        assert (await set_mode(client, auth, home["id"], mode))["mode"] == mode
        assert (await messages(client, auth, home["id"], kind="home", limit=1))[0]["title"] == f"Mode sécurité: {label}"
    assert set(MODE_LABELS) == {"disarmed", "armed_home", "armed_away", "armed_night"}


async def test_set_mode_invalid_is_422(client, auth, home, devices):
    response = await client.post(f"{PREFIX}/homes/{home['id']}/security/mode", json={"mode": "party"}, headers=auth["headers"])
    assert response.status_code == 422
    assert (await client.post(f"{PREFIX}/homes/{home['id']}/security/mode", json={}, headers=auth["headers"])).status_code == 422
    assert (await security(client, auth, home["id"]))["mode"] == "disarmed"


async def test_set_mode_service_rejects_unknown_mode(hub_app, home):
    runtime = hub_app.state.hub_runtime
    async with runtime.db.session() as session:
        row = await session.get(Home, home["id"])
        with pytest.raises(AdapterError) as excinfo:
            await set_security_mode(runtime, session, row, "vacation", user_id=None)
        assert excinfo.value.code == "invalid_input"


async def test_automation_source_and_no_propagation(client, auth, home, devices, hub_app):
    """Scenes/automations call the service without a user; ``propagate=False`` leaves panels alone."""
    runtime = hub_app.state.hub_runtime
    modes = collect_events(hub_app, ev.SECURITY_MODE)
    async with runtime.db.session() as session:
        row = await session.get(Home, home["id"])
        await set_security_mode(runtime, session, row, "armed_night", user_id=None, propagate=False)
    assert modes[-1].payload == {"mode": "armed_night", "source": "automation"}
    assert (await security(client, auth, home["id"]))["mode"] == "armed_night"
    assert (await device_state(client, auth, devices["demo-panel-1"]["id"]))["arm_mode"] == "disarmed"
    body = (await messages(client, auth, home["id"], kind="home", limit=1))[0]
    assert body["title"] == "Mode sécurité: Mode nuit" and "automatisation" in body["body"]


async def test_set_mode_panel_failure_is_swallowed(client, auth, home, devices, hub_app, fake_panel):
    """An unreachable hardware panel does not fail the call; the user gets a notice instead."""
    panels = await materialize(hub_app, home["id"], "fakepanel", PairResult(devices=[panel_draft()]))
    fake_panel.fail_arm = "unreachable"
    body = await set_mode(client, auth, home["id"], "armed_home")
    assert body["mode"] == "armed_home"
    assert {p["external_id"]: p["state"]["arm_mode"] for p in body["panels"]} == {"demo-panel-1": "armed_home", "fp-panel": "disarmed"}
    assert fake_panel.calls == [("arm_mode", "armed_home")]
    notices = await messages(client, auth, home["id"], kind="notice")
    assert notices[0]["title"] == "Centrale non synchronisée — Centrale test" and notices[0]["device_id"] == panels["fp-panel"]["id"]
    assert notices[0]["severity"] == "warning"
    # One-way panels (unsupported) are skipped silently
    fake_panel.fail_arm = "unsupported"
    await set_mode(client, auth, home["id"], "armed_away")
    assert len(await messages(client, auth, home["id"], kind="notice")) == 1
    # Read-only arm_mode capability: never called
    fake_panel.fail_arm = None
    fake_panel.calls.clear()
    read_only = panel_draft()
    read_only.capabilities = [dict(c, writable=False) if c["code"] == "arm_mode" else c for c in read_only.capabilities]
    await materialize(hub_app, home["id"], "fakepanel", PairResult(devices=[read_only]))
    await set_mode(client, auth, home["id"], "disarmed")
    assert fake_panel.calls == []


async def test_hardware_panel_arm_mode_round_trip(client, auth, home, devices, hub_app, fake_panel):
    await materialize(hub_app, home["id"], "fakepanel", PairResult(devices=[panel_draft()]))
    body = await set_mode(client, auth, home["id"], "armed_night")
    assert {p["external_id"]: p["state"]["arm_mode"] for p in body["panels"]} == {"demo-panel-1": "armed_night", "fp-panel": "armed_night"}
    assert fake_panel.state["arm_mode"] == "armed_night"


# ----------------------------------------------------------------------------- software alarm
async def test_armed_away_contact_trips_alarm(client, auth, home, devices, hub_app):
    await set_mode(client, auth, home["id"], "armed_away")
    alarms = collect_events(hub_app, ev.SECURITY_ALARM)
    door = devices["demo-door-1"]
    await report(hub_app, door["id"], {"contact": True})
    body = await security(client, auth, home["id"])
    assert body["alarm_active"] is True and body["alarm_device_id"] == door["id"] and body["mode"] == "armed_away"
    assert len(alarms) == 1 and alarms[0].payload == {"active": True} and alarms[0].device_id == door["id"]
    items = await messages(client, auth, home["id"], kind="alarm")
    titles = [m["title"] for m in items]
    assert "🚨 Alarme — Porte d'entrée" in titles and "Ouverture détectée — Porte d'entrée" in titles
    # A second trip while the alarm is already active does not spam a second alarm
    await report(hub_app, devices["demo-pir-1"]["id"], {"motion": True})
    assert len(alarms) == 1
    assert (await security(client, auth, home["id"]))["alarm_device_id"] == door["id"]


async def test_armed_home_motion_does_not_trip_but_contact_does(client, auth, home, devices, hub_app):
    await set_mode(client, auth, home["id"], "armed_home")
    await report(hub_app, devices["demo-pir-1"]["id"], {"motion": True})
    body = await security(client, auth, home["id"])
    assert body["alarm_active"] is False and body["alarm_device_id"] is None
    assert not [m for m in await messages(client, auth, home["id"], kind="alarm") if m["title"].startswith("🚨")]
    await report(hub_app, devices["demo-door-1"]["id"], {"contact": True})
    body = await security(client, auth, home["id"])
    assert body["alarm_active"] is True and body["alarm_device_id"] == devices["demo-door-1"]["id"]


async def test_disarmed_ignores_intrusion_but_not_smoke(client, auth, home, devices, hub_app):
    await report(hub_app, devices["demo-door-1"]["id"], {"contact": True})
    assert (await security(client, auth, home["id"]))["alarm_active"] is False
    await report(hub_app, devices["demo-smoke-1"]["id"], {"smoke": True})
    body = await security(client, auth, home["id"])
    assert body["alarm_active"] is True and body["alarm_device_id"] == devices["demo-smoke-1"]["id"]


async def test_disarm_clears_alarm(client, auth, home, devices, hub_app):
    await set_mode(client, auth, home["id"], "armed_away")
    await report(hub_app, devices["demo-door-1"]["id"], {"contact": True})
    assert (await security(client, auth, home["id"]))["alarm_active"] is True
    alarms = collect_events(hub_app, ev.SECURITY_ALARM)
    body = await set_mode(client, auth, home["id"], "disarmed")
    assert body["mode"] == "disarmed" and body["alarm_active"] is False and body["alarm_device_id"] is None
    assert body["panels"][0]["state"] == {**body["panels"][0]["state"], "arm_mode": "disarmed", "alarm": False}
    assert [e.payload for e in alarms] == [{"active": False}]


async def test_clear_alarm_endpoint(client, auth, home, devices, hub_app):
    await set_mode(client, auth, home["id"], "armed_away")
    await report(hub_app, devices["demo-door-1"]["id"], {"contact": True})
    alarms = collect_events(hub_app, ev.SECURITY_ALARM)
    response = await client.post(f"{PREFIX}/homes/{home['id']}/security/alarm/clear", headers=auth["headers"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["alarm_active"] is False and body["alarm_device_id"] is None
    assert body["mode"] == "armed_away"  # acknowledging does not disarm
    assert len(alarms) == 1 and alarms[0].payload == {"active": False} and alarms[0].device_id == devices["demo-door-1"]["id"]
    notice = (await messages(client, auth, home["id"], kind="notice", limit=1))[0]
    assert notice["title"] == "Alarme acquittée" and notice["device_id"] == devices["demo-door-1"]["id"]
    # Idempotent when nothing is active
    assert (await client.post(f"{PREFIX}/homes/{home['id']}/security/alarm/clear", headers=auth["headers"])).status_code == 200


async def test_clear_alarm_reaches_hardware_panels_best_effort(client, auth, home, devices, hub_app, fake_panel):
    panels = await materialize(hub_app, home["id"], "fakepanel", PairResult(devices=[panel_draft()]))
    fake_panel.state.update({"alarm": True, "triggered_zone": "Zone 1"})
    await report(hub_app, panels["fp-panel"]["id"], {"alarm": True, "triggered_zone": "Zone 1"})
    assert (await security(client, auth, home["id"]))["alarm_active"] is True

    # 1. Hikvision-style ``clear_alarm`` command
    response = await client.post(f"{PREFIX}/homes/{home['id']}/security/alarm/clear", headers=auth["headers"])
    assert response.status_code == 200 and response.json()["alarm_active"] is False
    assert fake_panel.calls == [("clear_alarm", True)]
    panel_state = next(p for p in response.json()["panels"] if p["external_id"] == "fp-panel")["state"]
    assert panel_state["alarm"] is False and panel_state["triggered_zone"] == ""

    # 2. Panels that only know ``alarm=False`` get the fallback
    fake_panel.calls.clear()
    fake_panel.clear_codes = {"alarm"}
    assert (await client.post(f"{PREFIX}/homes/{home['id']}/security/alarm/clear", headers=auth["headers"])).status_code == 200
    assert fake_panel.calls == [("clear_alarm", True), ("alarm", False)]

    # 3. Unreachable / auth failures are swallowed
    for code in ("unreachable", "auth_failed"):
        fake_panel.calls.clear()
        fake_panel.clear_codes = {"clear_alarm"}
        fake_panel.fail_clear = code
        response = await client.post(f"{PREFIX}/homes/{home['id']}/security/alarm/clear", headers=auth["headers"])
        assert response.status_code == 200 and response.json()["alarm_active"] is False
        assert fake_panel.calls == [("clear_alarm", True)]


# ----------------------------------------------------------------------------- SOS
@pytest_asyncio.fixture
async def incidents():
    """Hub configured to forward SOS to SafeR CI, with the incident API mocked (``calls`` collects requests)."""
    calls: List[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(201, json={"id": "inc-123", "status": "open", "severity": "critical"})

    app = create_app(
        settings=make_settings(SAFER_INCIDENTS_URL=INCIDENTS_URL, SAFER_INCIDENTS_TOKEN="tok-abc"),
        database_url="sqlite+aiosqlite://", transport=httpx.MockTransport(handler), start_services=False,
    )
    runtime = app.state.hub_runtime
    await runtime.start()
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://hub") as http:
            user = await register_user(http)
            user["headers"] = {"Authorization": f"Bearer {user['token']}"}
            response = await http.post(f"{PREFIX}/homes", json={"name": "Maison Cocody", "lat": 5.36, "lon": -4.0}, headers=user["headers"])
            assert response.status_code == 201, response.text
            yield {"app": app, "client": http, "auth": user, "home": response.json(), "calls": calls}
    finally:
        await runtime.stop()
        set_runtime(None)


async def test_sos_creates_alert_message_event_and_forwards(incidents):
    app, http, auth, home, calls = (incidents[k] for k in ("app", "client", "auth", "home", "calls"))
    raised = collect_events(app, ev.SOS_RAISED)
    alarms = collect_events(app, ev.SECURITY_ALARM)
    response = await http.post(
        f"{PREFIX}/homes/{home['id']}/sos", json={"lat": 5.3456, "lon": -4.0123, "note": "Intrusion en cours"}, headers=auth["headers"]
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["home_id"] == home["id"] and body["user_id"] == auth["user"]["id"] and body["status"] == "open"
    assert body["lat"] == 5.3456 and body["lon"] == -4.0123 and body["note"] == "Intrusion en cours"
    assert body["forwarded"] is True and body["incident_id"] == "inc-123"
    # Forwarded through the injected transport with the incident contract
    assert len(calls) == 1
    request = calls[0]
    assert str(request.url) == INCIDENTS_URL and request.method == "POST"
    assert request.headers["Authorization"] == "Bearer tok-abc"
    sent = json.loads(request.content)
    assert sent["incident_type"] == "panic" and sent["severity"] == "critical" and sent["source"] == "mobile_app"
    assert sent["location_lat"] == 5.3456 and sent["location_lon"] == -4.0123
    assert sent["description"] == "Intrusion en cours" and sent["hub_id"] == "safer-hub" and sent["triggered_by"] == "alice@safer.ci"
    # Bus events + alarm message + home alarm
    assert len(raised) == 1 and raised[0].home_id == home["id"]
    assert raised[0].payload["sos_id"] == body["id"] and raised[0].payload["lat"] == 5.3456 and raised[0].payload["lon"] == -4.0123
    assert [e.payload["active"] for e in alarms] == [True]
    alarm = (await http.get(f"{PREFIX}/homes/{home['id']}/messages", params={"kind": "alarm"}, headers=auth["headers"])).json()
    assert alarm[0]["title"] == "🆘 SOS déclenché" and alarm[0]["severity"] == "critical" and "Intrusion en cours" in alarm[0]["body"]
    state = (await http.get(f"{PREFIX}/homes/{home['id']}/security", headers=auth["headers"])).json()
    assert state["alarm_active"] is True and state["alarm_device_id"] is None


async def test_sos_location_falls_back_to_home_then_abidjan(incidents):
    http, auth, home, calls = (incidents[k] for k in ("client", "auth", "home", "calls"))
    response = await http.post(f"{PREFIX}/homes/{home['id']}/sos", json={"incident_type": "medical"}, headers=auth["headers"])
    assert response.status_code == 201, response.text
    assert response.json()["lat"] is None and response.json()["note"] is None
    sent = json.loads(calls[-1].content)
    assert (sent["location_lat"], sent["location_lon"]) == (5.36, -4.0)
    assert sent["incident_type"] == "medical" and sent["description"] == "SOS SafeR app"
    # Home without coordinates -> Abidjan default
    other = await http.post(f"{PREFIX}/homes", json={"name": "Bureau"}, headers=auth["headers"])
    response = await http.post(f"{PREFIX}/homes/{other.json()['id']}/sos", json={}, headers=auth["headers"])
    assert response.status_code == 201
    sent = json.loads(calls[-1].content)
    assert (sent["location_lat"], sent["location_lon"]) == (5.36, -4.0083)


async def test_sos_forward_failure_is_not_fatal(incidents):
    """HTTP errors and network failures on the incident platform never fail the SOS."""
    http, auth, home, calls = (incidents[k] for k in ("client", "auth", "home", "calls"))
    runtime = incidents["app"].state.hub_runtime

    def swap_transport(handler) -> None:
        runtime.transport = httpx.MockTransport(handler)
        runtime._contexts.clear()  # pylint: disable=protected-access  # contexts cache the transport

    def failing(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(500, json={"detail": "boom"})

    swap_transport(failing)
    response = await http.post(f"{PREFIX}/homes/{home['id']}/sos", json={"note": "test"}, headers=auth["headers"])
    assert response.status_code == 201, response.text
    assert response.json()["forwarded"] is False and response.json()["incident_id"] is None
    assert len(calls) == 1

    def exploding(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise httpx.ConnectError("no route to host", request=request)

    swap_transport(exploding)
    response = await http.post(f"{PREFIX}/homes/{home['id']}/sos", json={}, headers=auth["headers"])
    assert response.status_code == 201 and response.json()["forwarded"] is False
    assert len(calls) == 2
    # Both alerts were stored regardless, and the alarm message was posted each time
    listed = (await http.get(f"{PREFIX}/homes/{home['id']}/sos", headers=auth["headers"])).json()
    assert len(listed) == 2 and all(s["forwarded"] is False for s in listed)
    alarms = (await http.get(f"{PREFIX}/homes/{home['id']}/messages", params={"kind": "alarm"}, headers=auth["headers"])).json()
    assert [m["title"] for m in alarms] == ["🆘 SOS déclenché", "🆘 SOS déclenché"]


async def test_sos_without_incidents_url_is_not_forwarded(client, auth, home, hub_app):
    raised = collect_events(hub_app, ev.SOS_RAISED)
    response = await client.post(f"{PREFIX}/homes/{home['id']}/sos", json={"note": "  "}, headers=auth["headers"])
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["forwarded"] is False and body["incident_id"] is None and body["note"] is None
    assert len(raised) == 1
    assert (await security(client, auth, home["id"]))["alarm_active"] is True
    assert (await messages(client, auth, home["id"], kind="alarm"))[0]["title"] == "🆘 SOS déclenché"


async def test_sos_list_and_patch(client, auth, home):
    first = (await client.post(f"{PREFIX}/homes/{home['id']}/sos", json={"note": "un"}, headers=auth["headers"])).json()
    second = (await client.post(f"{PREFIX}/homes/{home['id']}/sos", json={"note": "deux"}, headers=auth["headers"])).json()
    listed = (await client.get(f"{PREFIX}/homes/{home['id']}/sos", headers=auth["headers"])).json()
    assert [s["id"] for s in listed] == [second["id"], first["id"]]  # newest first
    assert [s["id"] for s in (await client.get(f"{PREFIX}/homes/{home['id']}/sos", params={"limit": 1}, headers=auth["headers"])).json()] == [second["id"]]
    assert (await client.get(f"{PREFIX}/homes/{home['id']}/sos", params={"limit": 0}, headers=auth["headers"])).status_code == 422

    response = await client.patch(f"{PREFIX}/homes/{home['id']}/sos/{first['id']}", json={"status": "false_alarm"}, headers=auth["headers"])
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "false_alarm"
    # One SOS still open -> the alarm stays on
    assert (await security(client, auth, home["id"]))["alarm_active"] is True
    response = await client.patch(f"{PREFIX}/homes/{home['id']}/sos/{second['id']}", json={"status": "resolved"}, headers=auth["headers"])
    assert response.status_code == 200 and response.json()["status"] == "resolved"
    # Last open SOS closed -> SOS-only alarm released
    assert (await security(client, auth, home["id"]))["alarm_active"] is False
    notices = [m["title"] for m in await messages(client, auth, home["id"], kind="notice")]
    assert "SOS: fausse alerte" in notices and "SOS résolu" in notices and "Alarme acquittée" in notices

    assert (await client.patch(f"{PREFIX}/homes/{home['id']}/sos/{first['id']}", json={"status": "open"}, headers=auth["headers"])).status_code == 422
    assert (await client.patch(f"{PREFIX}/homes/{home['id']}/sos/missing", json={"status": "resolved"}, headers=auth["headers"])).status_code == 404
    # Alerts of another home are invisible
    other = (await client.post(f"{PREFIX}/homes", json={"name": "Bureau"}, headers=auth["headers"])).json()
    assert (await client.patch(f"{PREFIX}/homes/{other['id']}/sos/{first['id']}", json={"status": "resolved"}, headers=auth["headers"])).status_code == 404
    assert (await client.get(f"{PREFIX}/homes/{other['id']}/sos", headers=auth["headers"])).json() == []
