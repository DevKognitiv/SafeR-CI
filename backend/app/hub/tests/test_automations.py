"""Automation routes + AutomationEngine tests (demo brand, injected clock, no network)."""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import select

from app.hub import events as ev
from app.hub.adapters.registry import registry
from app.hub.automation.engine import AUTOMATION_RAN, AutomationEngine, compare_values, in_time_range, parse_hhmm
from app.hub.models import Device, Home, Message
from app.hub.schemas import DeviceOut
from app.hub.tests.conftest import PREFIX, register_user

MONDAY_0730 = datetime(2026, 9, 7, 7, 30)  # a Monday


# ----------------------------------------------------------------------------- helpers / fixtures
async def pair_demo(hub_app: FastAPI, home_id: str) -> Dict[str, dict]:
    """Pair the demo brand straight through the device service; devices keyed by external id."""
    runtime = hub_app.state.hub_runtime
    adapter = registry.get("demo")
    adapter._state.clear()  # pylint: disable=protected-access  # process-wide singleton: start from the blueprint
    result = await adapter.pair("virtual", {}, runtime.ctx_for("demo"))
    async with runtime.db.session() as session:
        rows, _ = await runtime.services["devices"].materialize(session, home_id, None, "demo", result)
        return {row.external_id: DeviceOut.model_validate(row).model_dump(mode="json") for row in rows}


@pytest_asyncio.fixture
async def devices(hub_app: FastAPI, home: Dict) -> Dict[str, dict]:
    """Demo devices paired into ``home``, keyed by external id."""
    return await pair_demo(hub_app, home["id"])


@pytest_asyncio.fixture
async def engine(hub_app: FastAPI) -> AutomationEngine:
    """An engine driven by hand through ``evaluate_event`` (no worker, no tick, no re-entrancy window)."""
    return AutomationEngine(hub_app.state.hub_runtime, now=lambda: MONDAY_0730, tick_interval=0, reentry_seconds=0)


@pytest_asyncio.fixture
async def member(client: httpx.AsyncClient, auth: Dict, home: Dict) -> Dict:
    """A plain member of ``home`` (Bob)."""
    data = await register_user(client, email="bob@safer.ci", name="Bob")
    data["headers"] = {"Authorization": f"Bearer {data['token']}"}
    response = await client.post(f"{PREFIX}/homes/{home['id']}/members", json={"email": "bob@safer.ci", "role": "member"}, headers=auth["headers"])
    assert response.status_code == 201, response.text
    return data


def collect_events(hub_app: FastAPI, *types: str) -> List[ev.HubEvent]:
    seen: List[ev.HubEvent] = []

    async def _listener(event: ev.HubEvent) -> None:
        if not types or event.type in types:
            seen.append(event)

    hub_app.state.hub_runtime.bus.subscribe(_listener)
    return seen


async def create_automation(
    client: httpx.AsyncClient, auth: Dict, home: Dict, name: str, triggers: List[dict], actions: List[dict],
    conditions: Optional[List[dict]] = None, **extra: Any,
) -> dict:
    body = {"name": name, "triggers": triggers, "conditions": conditions or [], "actions": actions}
    body.update(extra)
    response = await client.post(f"{PREFIX}/homes/{home['id']}/automations", json=body, headers=auth["headers"])
    assert response.status_code == 201, response.text
    return response.json()


async def get_automation(client: httpx.AsyncClient, auth: Dict, automation_id: str) -> dict:
    response = await client.get(f"{PREFIX}/automations/{automation_id}", headers=auth["headers"])
    assert response.status_code == 200, response.text
    return response.json()


async def device_state(hub_app: FastAPI, device_id: str) -> Dict[str, Any]:
    async with hub_app.state.hub_runtime.db.session() as session:
        return dict((await session.get(Device, device_id)).state or {})


async def set_home_mode(hub_app: FastAPI, home_id: str, mode: str) -> None:
    async with hub_app.state.hub_runtime.db.session() as session:
        (await session.get(Home, home_id)).security_mode = mode
        await session.commit()


def state_event(home: Dict, device: dict, changed: Dict[str, Any], state: Optional[Dict[str, Any]] = None) -> ev.HubEvent:
    """A ``device.state`` event as ``DeviceService.apply_state`` publishes it."""
    merged = dict(device["state"])
    merged.update(state or {})
    merged.update(changed)
    return ev.HubEvent(ev.DEVICE_STATE, home_id=home["id"], device_id=device["id"], payload={"state": merged, "online": True, "changed": changed})


def plug_on(devices: Dict[str, dict]) -> dict:
    return {"type": "device_command", "device_id": devices["demo-plug-1"]["id"], "code": "switch", "value": True}


async def wait_for(predicate, timeout: float = 3.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() > deadline:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.01)


# ----------------------------------------------------------------------------- CRUD
async def test_automation_crud_and_validation(client, auth, home, devices, hub_app):
    door, plug, light = devices["demo-door-1"], devices["demo-plug-1"], devices["demo-light-1"]
    url = f"{PREFIX}/homes/{home['id']}/automations"
    created = await create_automation(
        client, auth, home, "Porte ouverte",
        triggers=[{"type": "device_state", "device_id": door["id"], "code": "contact", "op": "eq", "value": True},
                  {"type": "schedule", "time": "07:30", "days": [0, 1, 2, 3, 4]}],
        actions=[plug_on(devices), {"type": "notify", "title": "Porte", "body": "Ouverte"}],
        conditions=[{"type": "time_range", "start": "22:00", "end": "06:00"}, {"type": "security_mode", "mode": "armed_away"}],
        match="any",
    )
    assert created["home_id"] == home["id"] and created["enabled"] is True and created["match"] == "any"
    assert created["last_triggered_at"] is None and len(created["triggers"]) == 2 and len(created["conditions"]) == 2
    listed = await client.get(url, headers=auth["headers"])
    assert listed.status_code == 200 and [a["id"] for a in listed.json()] == [created["id"]]
    assert (await get_automation(client, auth, created["id"]))["name"] == "Porte ouverte"

    response = await client.patch(f"{PREFIX}/automations/{created['id']}", json={
        "name": " Lumière ", "match": "all",
        "triggers": [{"type": "device_state", "device_id": light["id"], "code": "brightness", "op": "gt", "value": 50}],
        "conditions": [],
    }, headers=auth["headers"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Lumière" and body["match"] == "all" and body["conditions"] == []
    assert body["triggers"][0]["device_id"] == light["id"] and len(body["actions"]) == 2
    response = await client.patch(f"{PREFIX}/automations/{created['id']}", json={"triggers": None, "match": None}, headers=auth["headers"])
    assert response.status_code == 200 and len(response.json()["triggers"]) == 1 and response.json()["match"] == "all"

    async def post(**body: Any) -> httpx.Response:
        payload = {"name": "T", "triggers": [], "conditions": [], "actions": []}
        payload.update(body)
        return await client.post(url, json=payload, headers=auth["headers"])

    # 422: shapes
    assert (await post(triggers=[{"type": "weather", "value": "rain"}])).status_code == 422
    assert (await post(triggers=[{"type": "device_state", "device_id": door["id"], "code": "contact", "op": "like", "value": 1}])).status_code == 422
    assert (await post(triggers=[{"type": "schedule", "days": [1]}])).status_code == 422
    assert (await post(triggers=[{"type": "security_mode", "mode": "holiday"}])).status_code == 422
    assert (await post(conditions=[{"type": "time_range", "start": "22:00"}])).status_code == 422
    assert (await post(conditions=[{"type": "schedule", "time": "07:00"}])).status_code == 422
    assert (await post(match="some")).status_code == 422
    assert (await post(actions=[{"type": "explode"}])).status_code == 422
    # 400: references
    other = await client.post(f"{PREFIX}/homes", json={"name": "Bureau"}, headers=auth["headers"])
    foreign = await pair_demo(hub_app, other.json()["id"])
    response = await post(triggers=[{"type": "device_state", "device_id": foreign["demo-door-1"]["id"], "code": "contact", "value": True}])
    assert response.status_code == 400 and foreign["demo-door-1"]["id"] in response.json()["detail"]
    assert (await post(conditions=[{"type": "device_state", "device_id": "ghost", "code": "contact", "value": True}])).status_code == 400
    assert (await post(actions=[{"type": "device_command", "device_id": plug["id"], "code": "contact", "value": True}])).status_code == 400
    assert (await post(actions=[{"type": "run_scene", "scene_id": "ghost"}])).status_code == 400
    assert (await post(name="  ")).status_code == 400

    assert (await client.delete(f"{PREFIX}/automations/{created['id']}", headers=auth["headers"])).status_code == 204
    assert (await client.get(f"{PREFIX}/automations/{created['id']}", headers=auth["headers"])).status_code == 404
    assert (await client.delete(f"{PREFIX}/automations/{created['id']}", headers=auth["headers"])).status_code == 404
    assert (await client.get(url, headers=auth["headers"])).json() == []
    stranger = await register_user(client, email="eve@safer.ci", name="Eve")
    assert (await client.get(url, headers={"Authorization": f"Bearer {stranger['token']}"})).status_code == 404
    assert (await client.get(url)).status_code == 401


async def test_enable_disable_and_manual_trigger(client, auth, home, devices, member, hub_app):
    plug = devices["demo-plug-1"]
    ran = collect_events(hub_app, AUTOMATION_RAN)
    automation = await create_automation(
        client, auth, home, "Test manuel",
        triggers=[{"type": "schedule", "time": "03:00"}],
        conditions=[{"type": "security_mode", "mode": "armed_night"}],
        actions=[plug_on(devices), {"type": "notify", "title": "Manuel", "body": "ok"}],
    )
    url = f"{PREFIX}/automations/{automation['id']}"
    response = await client.post(f"{url}/disable", headers=auth["headers"])
    assert response.status_code == 200 and response.json()["enabled"] is False
    assert (await get_automation(client, auth, automation["id"]))["enabled"] is False
    # Members can look and test, not manage
    assert (await client.post(f"{url}/enable", headers=member["headers"])).status_code == 403
    assert (await client.patch(url, json={"name": "X"}, headers=member["headers"])).status_code == 403
    assert (await client.delete(url, headers=member["headers"])).status_code == 403
    assert (await client.post(f"{PREFIX}/homes/{home['id']}/automations", json={"name": "X"}, headers=member["headers"])).status_code == 403
    assert (await client.get(url, headers=member["headers"])).status_code == 200

    # Manual trigger ignores enabled / triggers / conditions
    response = await client.post(f"{url}/trigger", headers=member["headers"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["automation_id"] == automation["id"] and body["name"] == "Test manuel"
    assert [r["status"] for r in body["results"]] == ["ok", "ok"] and body["summary"] == {"ok": 2, "error": 0, "skipped": 0}
    assert body["triggered_at"] is not None
    assert (await device_state(hub_app, plug["id"]))["switch"] is True
    assert (await get_automation(client, auth, automation["id"]))["last_triggered_at"] is not None
    assert len(ran) == 1 and ran[0].payload == {"automation_id": automation["id"], "name": "Test manuel", "source": "manual", "ok": True, "actions": 2}
    async with hub_app.state.hub_runtime.db.session() as session:
        titles = [m.title for m in (await session.execute(select(Message).where(Message.home_id == home["id"]))).scalars().all()]
    assert "Manuel" in titles

    response = await client.post(f"{url}/enable", headers=auth["headers"])
    assert response.status_code == 200 and response.json()["enabled"] is True
    assert (await client.post(f"{PREFIX}/automations/ghost/trigger", headers=auth["headers"])).status_code == 404


# ----------------------------------------------------------------------------- engine: bus path
async def test_device_state_trigger_fires_when_contact_opens(client, auth, home, devices, hub_app):
    """End to end: the demo door opens (push) -> bus -> engine worker -> plug switched on."""
    runtime = hub_app.state.hub_runtime
    door, plug = devices["demo-door-1"], devices["demo-plug-1"]
    ran = collect_events(hub_app, AUTOMATION_RAN)
    automation = await create_automation(
        client, auth, home, "Porte -> prise",
        triggers=[{"type": "device_state", "device_id": door["id"], "code": "contact", "op": "eq", "value": True}],
        actions=[plug_on(devices)],
    )
    engine = AutomationEngine(runtime, tick_interval=0)
    await engine.start()
    try:
        assert engine.running and engine.concurrency == 1  # in-memory SQLite: one run at a time
        adapter = registry.get("demo")
        before = datetime.utcnow().replace(microsecond=0)
        await adapter.simulate("demo-door-1", {"contact": True}, runtime.ctx_for("demo"))
        await engine.drain()
        assert (await device_state(hub_app, plug["id"]))["switch"] is True
        assert engine.evaluated >= 1 and engine.fired == 1 and engine.last_fired_at is not None
        stored = await get_automation(client, auth, automation["id"])
        assert stored["last_triggered_at"] is not None and datetime.fromisoformat(stored["last_triggered_at"]) >= before
        assert len(ran) == 1 and ran[0].home_id == home["id"]
        assert ran[0].payload["automation_id"] == automation["id"] and ran[0].payload["source"] == "automation" and ran[0].payload["ok"] is True

        # Closing the door is not "eq True"; the plug being switched (by the automation) is not the door either
        await adapter.simulate("demo-door-1", {"contact": False}, runtime.ctx_for("demo"))
        await engine.drain()
        assert engine.fired == 1 and len(ran) == 1
    finally:
        await engine.stop()
    assert not engine.running and engine.pending == 0


async def test_engine_lifecycle_and_tick_loop(client, auth, home, devices, hub_app):
    """The minute tick is published on the bus and evaluates schedule triggers with the engine clock."""
    runtime = hub_app.state.hub_runtime
    ticks = collect_events(hub_app, ev.TICK)
    ran = collect_events(hub_app, AUTOMATION_RAN)
    automation = await create_automation(
        client, auth, home, "Réveil",
        triggers=[{"type": "schedule", "time": "07:30", "days": []}],
        actions=[{"type": "notify", "title": "Réveil", "body": "Bonjour"}],
    )
    engine = AutomationEngine(runtime, now=lambda: MONDAY_0730, tick_interval=0.2)
    await engine.start()
    await engine.start()  # idempotent
    try:
        await wait_for(lambda: engine.ticks >= 2 and len(ran) >= 1)
        await engine.drain()
        assert ticks and ticks[0].home_id is None and ticks[0].payload["at"].startswith("2026-09-07T07:30")
        assert engine.last_tick_at is not None
        # Several ticks landed in the same (frozen) minute: the schedule fired exactly once
        assert len(ran) == 1 and engine.fired == 1
        assert (await get_automation(client, auth, automation["id"]))["last_triggered_at"] is not None
    finally:
        await engine.stop()
    assert not engine.running
    await engine.stop()  # idempotent


# ----------------------------------------------------------------------------- engine: triggers
async def test_trigger_is_edge_based(client, auth, home, devices, engine):
    door = devices["demo-door-1"]
    automation = await create_automation(
        client, auth, home, "Bord",
        triggers=[{"type": "device_state", "device_id": door["id"], "code": "contact", "op": "eq", "value": True}],
        actions=[plug_on(devices)],
    )
    # contact True in the state but not part of the change -> nothing
    assert await engine.evaluate_event(state_event(home, door, {"battery": 50}, {"contact": True})) == []
    # the transition itself fires
    assert await engine.evaluate_event(state_event(home, door, {"contact": True})) == [automation["id"]]
    # publishers without "changed" (foreign bridges) fall back to the full state
    assert await engine.evaluate_event(ev.HubEvent(ev.DEVICE_STATE, home_id=home["id"], device_id=door["id"], payload={"state": {"contact": True}})) == [automation["id"]]
    assert await engine.evaluate_event(ev.HubEvent(ev.DEVICE_STATE, home_id=home["id"], device_id=door["id"], payload={"state": {"battery": 1}})) == []
    # string "true" from a bridge still equals True
    assert await engine.evaluate_event(state_event(home, door, {"contact": "true"})) == [automation["id"]]
    assert await engine.evaluate_event(state_event(home, door, {"contact": False})) == []
    # another device with the same code does not match
    pir = devices["demo-pir-1"]
    assert await engine.evaluate_event(state_event(home, pir, {"contact": True})) == []


async def test_numeric_ops_tolerate_strings(client, auth, home, devices, engine):
    thermo = devices["demo-thermo-1"]

    async def automation(op: str, value: Any) -> str:
        created = await create_automation(
            client, auth, home, f"temp {op} {value}",
            triggers=[{"type": "device_state", "device_id": thermo["id"], "code": "temp_current", "op": op, "value": value}],
            actions=[{"type": "notify", "title": op}],
        )
        return created["id"]

    gt, lt, gte, lte, ne, eq = (await automation("gt", 30), await automation("lt", "20"), await automation("gte", 30),
                                await automation("lte", 20.0), await automation("ne", 25), await automation("eq", "25"))

    async def fired(value: Any) -> set:
        return set(await engine.evaluate_event(state_event(home, thermo, {"temp_current": value})))

    assert await fired("31.5") == {gt, gte, ne}
    assert await fired(30) == {gte, ne}
    assert await fired("19") == {lt, lte, ne}
    assert await fired(20) == {lte, ne}
    assert await fired(25) == {eq}
    assert await fired("25.0") == {eq}
    assert await fired("hot") == {ne}  # not a number: only ne can be true


async def test_changed_op(client, auth, home, devices, engine):
    light = devices["demo-light-1"]
    automation = await create_automation(
        client, auth, home, "Luminosité",
        triggers=[{"type": "device_state", "device_id": light["id"], "code": "brightness", "op": "changed"}],
        actions=[{"type": "notify", "title": "Luminosité"}],
    )
    assert await engine.evaluate_event(state_event(home, light, {"brightness": 10})) == [automation["id"]]
    assert await engine.evaluate_event(state_event(home, light, {"brightness": 0})) == [automation["id"]]
    assert await engine.evaluate_event(state_event(home, light, {"switch": False})) == []
    assert await engine.evaluate_event(state_event(home, light, {})) == []


async def test_security_mode_trigger_and_condition(client, auth, home, devices, engine, hub_app):
    door = devices["demo-door-1"]
    ran = collect_events(hub_app, AUTOMATION_RAN)
    armed = await create_automation(
        client, auth, home, "Armement",
        triggers=[{"type": "security_mode", "mode": "armed_away"}],
        actions=[plug_on(devices)],
    )
    guarded = await create_automation(
        client, auth, home, "Porte armée",
        triggers=[{"type": "device_state", "device_id": door["id"], "code": "contact", "value": True}],
        conditions=[{"type": "security_mode", "mode": "armed_home"}],
        actions=[{"type": "notify", "title": "Intrusion"}],
    )
    assert await engine.evaluate_event(ev.HubEvent(ev.SECURITY_MODE, home_id=home["id"], payload={"mode": "disarmed"})) == []
    assert await engine.evaluate_event(ev.HubEvent(ev.SECURITY_MODE, home_id=home["id"], payload={"mode": "armed_away", "source": "x"})) == [armed["id"]]
    assert (await device_state(hub_app, devices["demo-plug-1"]["id"]))["switch"] is True
    assert [e.payload["automation_id"] for e in ran] == [armed["id"]]

    door_open = state_event(home, door, {"contact": True})
    assert await engine.evaluate_event(door_open) == []  # home is disarmed
    await set_home_mode(hub_app, home["id"], "armed_home")
    assert await engine.evaluate_event(door_open) == [guarded["id"]]
    await set_home_mode(hub_app, home["id"], "armed_away")
    assert await engine.evaluate_event(door_open) == []


async def test_schedule_trigger_via_tick_with_injected_now(client, auth, home, devices, engine, hub_app):
    assert MONDAY_0730.weekday() == 0
    weekdays = await create_automation(
        client, auth, home, "Semaine 07:30",
        triggers=[{"type": "schedule", "time": "07:30", "days": [0, 1, 2, 3, 4]}],
        actions=[{"type": "notify", "title": "Semaine"}],
    )
    weekend = await create_automation(
        client, auth, home, "Week-end 7:30",
        triggers=[{"type": "schedule", "time": "7:30", "days": ["5", 6]}],
        actions=[{"type": "notify", "title": "Week-end"}],
    )
    daily = await create_automation(
        client, auth, home, "Tous les jours 07:31",
        triggers=[{"type": "schedule", "time": "07:31"}],
        actions=[{"type": "notify", "title": "Quotidien"}],
    )
    tick = ev.HubEvent(ev.TICK)
    assert await engine.evaluate_event(tick) == [weekdays["id"]]  # engine clock: Monday 07:30
    assert await engine.evaluate_event(tick) == []  # same minute slot: never twice
    assert await engine.evaluate_event(tick, now=datetime(2026, 9, 7, 7, 31)) == [daily["id"]]
    assert await engine.evaluate_event(tick, now=datetime(2026, 9, 12, 7, 30)) == [weekend["id"]]  # Saturday
    assert await engine.evaluate_event(tick, now=datetime(2026, 9, 8, 7, 30)) == [weekdays["id"]]  # Tuesday, new slot
    assert await engine.evaluate_event(tick, now=datetime(2026, 9, 8, 19, 30)) == []
    stored = await get_automation(client, auth, weekdays["id"])
    assert stored["last_triggered_at"] is not None
    # A device event never evaluates schedules, and a disabled schedule stays quiet
    assert await engine.evaluate_event(state_event(home, devices["demo-door-1"], {"contact": True}), now=datetime(2026, 9, 9, 7, 30)) == []
    assert (await client.post(f"{PREFIX}/automations/{daily['id']}/disable", headers=auth["headers"])).status_code == 200
    assert await engine.evaluate_event(tick, now=datetime(2026, 9, 9, 7, 31)) == []
    async with hub_app.state.hub_runtime.db.session() as session:
        titles = [m.title for m in (await session.execute(select(Message).where(Message.home_id == home["id"]))).scalars().all()]
    assert titles.count("Semaine") == 2 and titles.count("Week-end") == 1 and titles.count("Quotidien") == 1


# ----------------------------------------------------------------------------- engine: conditions
async def test_conditions_match_all_and_any(client, auth, home, devices, engine, hub_app):
    door, light = devices["demo-door-1"], devices["demo-light-1"]
    assert light["state"]["switch"] is True
    conditions = [
        {"type": "device_state", "device_id": light["id"], "code": "switch", "op": "eq", "value": False},
        {"type": "security_mode", "mode": "disarmed"},
    ]
    trigger = [{"type": "device_state", "device_id": door["id"], "code": "contact", "op": "eq", "value": True}]
    every = await create_automation(client, auth, home, "Toutes", trigger, [{"type": "notify", "title": "all"}], conditions, match="all")
    some = await create_automation(client, auth, home, "Au moins une", trigger, [{"type": "notify", "title": "any"}], conditions, match="any")
    none = await create_automation(client, auth, home, "Sans condition", trigger, [{"type": "notify", "title": "none"}])
    event = state_event(home, door, {"contact": True})
    # light on: "all" fails on the first condition, "any" passes thanks to the security mode
    assert set(await engine.evaluate_event(event)) == {some["id"], none["id"]}
    async with hub_app.state.hub_runtime.db.session() as session:
        stored = await session.get(Device, light["id"])
        stored.state = {**stored.state, "switch": False}
        await session.commit()
    assert set(await engine.evaluate_event(event)) == {every["id"], some["id"], none["id"]}
    await set_home_mode(hub_app, home["id"], "armed_away")
    assert set(await engine.evaluate_event(event)) == {some["id"], none["id"]}
    async with hub_app.state.hub_runtime.db.session() as session:
        stored = await session.get(Device, light["id"])
        stored.state = {**stored.state, "switch": True}
        await session.commit()
    assert set(await engine.evaluate_event(event)) == {none["id"]}
    # a condition on a foreign / unknown device never passes
    other = await client.post(f"{PREFIX}/homes", json={"name": "Bureau"}, headers=auth["headers"])
    foreign = await pair_demo(hub_app, other.json()["id"])
    async with hub_app.state.hub_runtime.db.session() as session:
        from app.hub.models import Automation  # pylint: disable=import-outside-toplevel

        row = await session.get(Automation, none["id"])
        row.conditions = [{"type": "device_state", "device_id": foreign["demo-light-1"]["id"], "code": "switch", "value": True}]
        await session.commit()
    assert await engine.evaluate_event(event) == []


async def test_time_range_condition_overnight(client, auth, home, devices, engine):
    door = devices["demo-door-1"]
    night = await create_automation(
        client, auth, home, "Nuit",
        triggers=[{"type": "device_state", "device_id": door["id"], "code": "contact", "value": True}],
        conditions=[{"type": "time_range", "start": "22:00", "end": "06:00"}],
        actions=[{"type": "notify", "title": "Nuit"}],
    )
    day = await create_automation(
        client, auth, home, "Jour",
        triggers=[{"type": "device_state", "device_id": door["id"], "code": "contact", "value": True}],
        conditions=[{"type": "time_range", "start": "08:00", "end": "18:00"}],
        actions=[{"type": "notify", "title": "Jour"}],
    )
    event = state_event(home, door, {"contact": True})

    async def fired(hour: int, minute: int) -> set:
        return set(await engine.evaluate_event(event, now=datetime(2026, 9, 7, hour, minute)))

    assert await fired(23, 30) == {night["id"]}
    assert await fired(2, 15) == {night["id"]}
    assert await fired(22, 0) == {night["id"]}  # start inclusive
    assert await fired(5, 59) == {night["id"]}
    assert await fired(6, 0) == set()  # end exclusive
    assert await fired(12, 0) == {day["id"]}
    assert await fired(8, 0) == {day["id"]}
    assert await fired(18, 0) == set()
    assert await fired(7, 30) == set()


async def test_disabled_automation_does_not_fire(client, auth, home, devices, engine):
    door = devices["demo-door-1"]
    automation = await create_automation(
        client, auth, home, "Off",
        triggers=[{"type": "device_state", "device_id": door["id"], "code": "contact", "value": True}],
        actions=[plug_on(devices)], enabled=False,
    )
    event = state_event(home, door, {"contact": True})
    assert await engine.evaluate_event(event) == []
    assert (await client.post(f"{PREFIX}/automations/{automation['id']}/enable", headers=auth["headers"])).status_code == 200
    assert await engine.evaluate_event(event) == [automation["id"]]
    assert (await client.post(f"{PREFIX}/automations/{automation['id']}/disable", headers=auth["headers"])).status_code == 200
    assert await engine.evaluate_event(event) == []
    assert (await get_automation(client, auth, automation["id"]))["last_triggered_at"] is not None


async def test_reentrancy_guard_stops_ping_pong(client, auth, home, devices, hub_app):
    """Two automations reacting to the light and changing it would loop forever without the 2 s guard."""
    runtime = hub_app.state.hub_runtime
    light = devices["demo-light-1"]
    ran = collect_events(hub_app, AUTOMATION_RAN)
    trigger = [{"type": "device_state", "device_id": light["id"], "code": "brightness", "op": "changed"}]
    a = await create_automation(client, auth, home, "A", trigger, [{"type": "device_command", "device_id": light["id"], "code": "brightness", "value": 30}])
    b = await create_automation(client, auth, home, "B", trigger, [{"type": "device_command", "device_id": light["id"], "code": "brightness", "value": 60}])
    engine = AutomationEngine(runtime, tick_interval=0)
    assert engine.reentry_seconds == 2.0
    await engine.start()
    try:
        await registry.get("demo").simulate("demo-light-1", {"brightness": 20}, runtime.ctx_for("demo"))
        await engine.drain()
        assert sorted(e.payload["automation_id"] for e in ran) == sorted([a["id"], b["id"]])
        assert engine.fired == 2 and engine.evaluated >= 3  # the initial change + one per automation run
        assert (await device_state(hub_app, light["id"]))["brightness"] == 60
        for automation_id in (a["id"], b["id"]):
            assert (await get_automation(client, auth, automation_id))["last_triggered_at"] is not None
    finally:
        await engine.stop()
    # The guard is per automation and expires: with a zero window the same event fires again
    engine = AutomationEngine(runtime, tick_interval=0, reentry_seconds=0)
    assert await engine.evaluate_event(state_event(home, light, {"brightness": 5})) == [a["id"], b["id"]]


async def test_engine_ignores_irrelevant_events(client, auth, home, devices, engine, hub_app):
    door = devices["demo-door-1"]
    await create_automation(
        client, auth, home, "Porte",
        triggers=[{"type": "device_state", "device_id": door["id"], "code": "contact", "value": True}],
        actions=[plug_on(devices)],
    )
    assert await engine.evaluate_event(ev.HubEvent(ev.DEVICE_EVENT, home_id=home["id"], device_id=door["id"], payload={"event": {"type": "contact"}})) == []
    assert await engine.evaluate_event(ev.HubEvent(ev.DEVICE_STATE, device_id=door["id"], payload={"changed": {"contact": True}})) == []
    assert await engine.evaluate_event(ev.HubEvent(ev.DEVICE_STATE, home_id="other-home", device_id=door["id"], payload={"changed": {"contact": True}})) == []
    assert await engine.evaluate_event(ev.HubEvent(ev.DEVICE_STATE, home_id=home["id"], device_id=door["id"], payload={})) == []
    assert (await device_state(hub_app, devices["demo-plug-1"]["id"]))["switch"] is False
    assert engine.fired == 0


# ----------------------------------------------------------------------------- pure helpers
@pytest.mark.parametrize("op,actual,expected,result", [
    ("eq", True, True, True), ("eq", True, "true", True), ("eq", True, "on", True), ("eq", False, "off", True),
    ("eq", 1, True, True), ("eq", "10", 10, True), ("eq", "armed_home", "armed_home", True), ("eq", "Open", "open", True),
    ("eq", {"h": 1, "s": 2, "v": 3}, {"v": 3, "s": 2, "h": 1}, True), ("eq", None, None, True), ("eq", 1, 2, False),
    ("ne", "20", 20.0, False), ("ne", "hot", 20, True),
    ("gt", "31.5", 30, True), ("gt", 30, 30, False), ("gte", 30, "30", True), ("lt", 19, "20", True), ("lte", "20", 20, True),
    ("lt", "cold", 20, False), ("gt", None, 1, False), ("gt", True, 0, True),
    ("changed", 1, None, True), ("", 5, "5", True), ("unknown", 5, "5", True),
])
def test_compare_values(op, actual, expected, result):
    assert compare_values(op, actual, expected) is result


def test_time_helpers():
    assert parse_hhmm("07:30") == (7, 30) and parse_hhmm("7:5") == (7, 5) and parse_hhmm("23:59:59") == (23, 59)
    assert parse_hhmm("24:00") is None and parse_hhmm("7") is None and parse_hhmm(None) is None and parse_hhmm("a:b") is None
    at = lambda h, m: datetime(2026, 9, 7, h, m)  # pylint: disable=unnecessary-lambda-assignment
    assert in_time_range("22:00", "06:00", at(23, 0)) and in_time_range("22:00", "06:00", at(0, 0))
    assert not in_time_range("22:00", "06:00", at(6, 0)) and not in_time_range("22:00", "06:00", at(12, 0))
    assert in_time_range("08:00", "18:00", at(8, 0)) and not in_time_range("08:00", "18:00", at(18, 0))
    assert in_time_range("10:00", "10:00", at(3, 0))  # start == end: whole day
    assert not in_time_range("bad", "18:00", at(12, 0)) and not in_time_range("08:00", None, at(12, 0))
