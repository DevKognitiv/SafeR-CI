"""Scene routes + SceneRunner tests (demo brand, no network)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

import httpx
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import select

from app.hub import events as ev
from app.hub.adapters.registry import registry
from app.hub.automation import runner as runner_module
from app.hub.automation.runner import MAX_DELAY_SECONDS, MAX_SCENE_DEPTH, SceneRunner
from app.hub.models import Home, Message, Scene
from app.hub.schemas import DeviceOut
from app.hub.tests.conftest import PREFIX, register_user


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


async def create_scene(client: httpx.AsyncClient, auth: Dict, home: Dict, name: str, actions: List[dict], **extra: Any) -> dict:
    body = {"name": name, "actions": actions}
    body.update(extra)
    response = await client.post(f"{PREFIX}/homes/{home['id']}/scenes", json=body, headers=auth["headers"])
    assert response.status_code == 201, response.text
    return response.json()


async def get_device(client: httpx.AsyncClient, auth: Dict, device_id: str) -> dict:
    response = await client.get(f"{PREFIX}/devices/{device_id}", headers=auth["headers"])
    assert response.status_code == 200, response.text
    return response.json()


async def messages_of(hub_app: FastAPI, home_id: str) -> List[Message]:
    async with hub_app.state.hub_runtime.db.session() as session:
        return list((await session.execute(select(Message).where(Message.home_id == home_id).order_by(Message.created_at))).scalars().all())


# ----------------------------------------------------------------------------- CRUD
async def test_create_list_get_scenes(client, auth, home, devices):
    plug, light = devices["demo-plug-1"], devices["demo-light-1"]
    first = await create_scene(client, auth, home, "Soirée", [
        {"type": "device_command", "device_id": light["id"], "code": "brightness", "value": 30},
        {"type": "delay", "seconds": 0},
        {"type": "notify", "title": "Soirée", "body": "Ambiance activée"},
    ], icon="movie", color="#7C3AED")
    second = await create_scene(client, auth, home, "Départ", [
        {"type": "device_command", "device_id": plug["id"], "code": "switch", "value": False},
        {"type": "security_mode", "mode": "armed_away"},
        {"type": "run_scene", "scene_id": first["id"]},
    ])
    assert first["home_id"] == home["id"] and first["icon"] == "movie" and first["color"] == "#7C3AED"
    assert first["enabled"] is True and first["last_run_at"] is None and first["sort_order"] == 0
    assert second["sort_order"] == 1 and len(second["actions"]) == 3

    listed = await client.get(f"{PREFIX}/homes/{home['id']}/scenes", headers=auth["headers"])
    assert listed.status_code == 200
    assert [item["name"] for item in listed.json()] == ["Soirée", "Départ"]

    one = await client.get(f"{PREFIX}/scenes/{first['id']}", headers=auth["headers"])
    assert one.status_code == 200 and one.json()["actions"][0]["code"] == "brightness"
    assert (await client.get(f"{PREFIX}/scenes/does-not-exist", headers=auth["headers"])).status_code == 404
    assert (await client.get(f"{PREFIX}/scenes/{first['id']}")).status_code == 401

    stranger = await register_user(client, email="eve@safer.ci", name="Eve")
    headers = {"Authorization": f"Bearer {stranger['token']}"}
    assert (await client.get(f"{PREFIX}/scenes/{first['id']}", headers=headers)).status_code == 404
    assert (await client.get(f"{PREFIX}/homes/{home['id']}/scenes", headers=headers)).status_code == 404


async def test_scene_validation(client, auth, home, devices, hub_app):
    url = f"{PREFIX}/homes/{home['id']}/scenes"
    plug, door = devices["demo-plug-1"], devices["demo-door-1"]

    async def post(actions: List[dict], name: str = "Test") -> httpx.Response:
        return await client.post(url, json={"name": name, "actions": actions}, headers=auth["headers"])

    # Shape errors are 422 (pydantic)
    assert (await post([{"type": "teleport", "device_id": plug["id"]}])).status_code == 422
    assert (await post([{"type": "device_command", "device_id": plug["id"]}])).status_code == 422
    assert (await post([{"type": "delay"}])).status_code == 422
    assert (await post([{"type": "security_mode", "mode": "panic"}])).status_code == 422
    assert (await post([{"type": "run_scene"}])).status_code == 422
    assert (await post([], name="")).status_code == 422
    assert (await post([], name="   ")).status_code == 400

    # Referential errors are 400
    other = await client.post(f"{PREFIX}/homes", json={"name": "Bureau"}, headers=auth["headers"])
    assert other.status_code == 201
    foreign = await pair_demo(hub_app, other.json()["id"])
    response = await post([{"type": "device_command", "device_id": foreign["demo-plug-1"]["id"], "code": "switch", "value": True}])
    assert response.status_code == 400 and foreign["demo-plug-1"]["id"] in response.json()["detail"]
    response = await post([{"type": "device_command", "device_id": "missing-device", "code": "switch", "value": True}])
    assert response.status_code == 400
    response = await post([{"type": "device_command", "device_id": plug["id"], "code": "brightness", "value": 10}])
    assert response.status_code == 400 and "unknown capability" in response.json()["detail"]
    response = await post([{"type": "device_command", "device_id": door["id"], "code": "contact", "value": True}])
    assert response.status_code == 400 and "read-only" in response.json()["detail"]
    response = await post([{"type": "device_command", "device_id": plug["id"], "code": "switch", "value": "maybe"}])
    assert response.status_code == 400 and "boolean" in response.json()["detail"]
    response = await post([{"type": "run_scene", "scene_id": "missing-scene"}])
    assert response.status_code == 400 and "scene" in response.json()["detail"].lower()

    # A scene cannot run itself
    scene = await create_scene(client, auth, home, "Boucle", [])
    response = await client.patch(f"{PREFIX}/scenes/{scene['id']}", json={"actions": [{"type": "run_scene", "scene_id": scene["id"]}]}, headers=auth["headers"])
    assert response.status_code == 400 and "itself" in response.json()["detail"]
    assert (await client.get(f"{PREFIX}/homes/{home['id']}/scenes", headers=auth["headers"])).json()[0]["actions"] == []


async def test_update_and_delete_scene(client, auth, home, devices):
    light = devices["demo-light-1"]
    scene = await create_scene(client, auth, home, "Lecture", [{"type": "device_command", "device_id": light["id"], "code": "switch", "value": True}])
    url = f"{PREFIX}/scenes/{scene['id']}"
    response = await client.patch(url, json={"name": "  Lecture calme ", "icon": "book", "enabled": False, "actions": [
        {"type": "device_command", "device_id": light["id"], "code": "brightness", "value": 20},
        {"type": "notify", "title": "Lecture"},
    ]}, headers=auth["headers"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Lecture calme" and body["icon"] == "book" and body["enabled"] is False
    assert [a["type"] for a in body["actions"]] == ["device_command", "notify"]
    # Empty patch and explicit null actions keep everything
    response = await client.patch(url, json={"actions": None}, headers=auth["headers"])
    assert response.status_code == 200 and len(response.json()["actions"]) == 2
    assert (await client.patch(url, json={"name": "   "}, headers=auth["headers"])).status_code == 400
    assert (await client.patch(url, json={"actions": [{"type": "nope"}]}, headers=auth["headers"])).status_code == 422

    assert (await client.delete(url, headers=auth["headers"])).status_code == 204
    assert (await client.get(url, headers=auth["headers"])).status_code == 404
    assert (await client.delete(url, headers=auth["headers"])).status_code == 404
    assert (await client.get(f"{PREFIX}/homes/{home['id']}/scenes", headers=auth["headers"])).json() == []


async def test_member_cannot_manage_but_can_run(client, auth, home, devices, member):
    plug = devices["demo-plug-1"]
    scene = await create_scene(client, auth, home, "Prise", [{"type": "device_command", "device_id": plug["id"], "code": "switch", "value": True}])
    assert (await client.post(f"{PREFIX}/homes/{home['id']}/scenes", json={"name": "X", "actions": []}, headers=member["headers"])).status_code == 403
    assert (await client.patch(f"{PREFIX}/scenes/{scene['id']}", json={"name": "Y"}, headers=member["headers"])).status_code == 403
    assert (await client.delete(f"{PREFIX}/scenes/{scene['id']}", headers=member["headers"])).status_code == 403
    assert (await client.post(f"{PREFIX}/homes/{home['id']}/scenes/reorder", json={"ids": [scene["id"]]}, headers=member["headers"])).status_code == 403
    response = await client.post(f"{PREFIX}/scenes/{scene['id']}/run", headers=member["headers"])
    assert response.status_code == 200, response.text
    assert response.json()["summary"] == {"ok": 1, "error": 0, "skipped": 0}
    assert (await get_device(client, auth, plug["id"]))["state"]["switch"] is True


async def test_reorder_scenes(client, auth, home):
    a = await create_scene(client, auth, home, "A", [])
    b = await create_scene(client, auth, home, "B", [])
    c = await create_scene(client, auth, home, "C", [])
    url = f"{PREFIX}/homes/{home['id']}/scenes/reorder"
    response = await client.post(url, json={"ids": [c["id"], a["id"]]}, headers=auth["headers"])
    assert response.status_code == 200, response.text
    assert [(s["name"], s["sort_order"]) for s in response.json()] == [("C", 0), ("A", 1), ("B", 2)]
    listed = await client.get(f"{PREFIX}/homes/{home['id']}/scenes", headers=auth["headers"])
    assert [s["name"] for s in listed.json()] == ["C", "A", "B"]
    assert (await client.post(url, json={"ids": ["nope"]}, headers=auth["headers"])).status_code == 400
    # sort_order is also patchable directly
    response = await client.patch(f"{PREFIX}/scenes/{b['id']}", json={"sort_order": -1}, headers=auth["headers"])
    assert response.status_code == 200
    assert [s["name"] for s in (await client.get(f"{PREFIX}/homes/{home['id']}/scenes", headers=auth["headers"])).json()] == ["B", "C", "A"]


# ----------------------------------------------------------------------------- running
async def test_run_scene_toggles_plug_and_records_run(client, auth, home, devices, hub_app):
    plug, light = devices["demo-plug-1"], devices["demo-light-1"]
    assert plug["state"]["switch"] is False
    ran = collect_events(hub_app, ev.SCENE_RAN)
    states = collect_events(hub_app, ev.DEVICE_STATE)
    scene = await create_scene(client, auth, home, "Télé", [
        {"type": "device_command", "device_id": plug["id"], "code": "switch", "value": True},
        {"type": "device_command", "device_id": light["id"], "code": "brightness", "value": 25},
        {"type": "notify", "title": "Télé", "body": "C'est l'heure du film"},
    ])
    before = datetime.utcnow()
    response = await client.post(f"{PREFIX}/scenes/{scene['id']}/run", headers=auth["headers"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["scene_id"] == scene["id"] and body["name"] == "Télé"
    assert [r["status"] for r in body["results"]] == ["ok", "ok", "ok"]
    assert body["results"][0]["state"] == {"switch": True} and body["results"][1]["state"] == {"brightness": 25}
    assert body["results"][2]["message_id"]
    assert body["summary"] == {"ok": 3, "error": 0, "skipped": 0} and body["ran_at"] is not None

    current = await get_device(client, auth, plug["id"])
    assert current["state"]["switch"] is True and current["state"]["power"] == 42.5
    assert (await get_device(client, auth, light["id"]))["state"]["brightness"] == 25
    stored = (await client.get(f"{PREFIX}/scenes/{scene['id']}", headers=auth["headers"])).json()
    assert stored["last_run_at"] is not None and datetime.fromisoformat(stored["last_run_at"]) >= before.replace(microsecond=0)

    messages = await messages_of(hub_app, home["id"])
    kinds = [(m.kind, m.title) for m in messages]
    assert ("notice", "Télé") in kinds
    assert ("home", "Scène exécutée: Télé") in kinds
    scene_message = next(m for m in messages if m.title == "Scène exécutée: Télé")
    assert "3 actions" in scene_message.body and scene_message.severity == "info"

    assert len(ran) == 1 and ran[0].home_id == home["id"]
    assert ran[0].payload["scene_id"] == scene["id"] and ran[0].payload["ok"] is True and ran[0].payload["actions"] == 3
    assert {e.device_id for e in states} == {plug["id"], light["id"]}


async def test_run_scene_collects_errors_per_action(client, auth, home, devices, hub_app):
    plug = devices["demo-plug-1"]
    target = await create_scene(client, auth, home, "Cible", [])
    scene = await create_scene(client, auth, home, "Fragile", [
        {"type": "run_scene", "scene_id": target["id"]},
        {"type": "device_command", "device_id": plug["id"], "code": "switch", "value": True},
    ])
    assert (await client.delete(f"{PREFIX}/scenes/{target['id']}", headers=auth["headers"])).status_code == 204
    response = await client.post(f"{PREFIX}/scenes/{scene['id']}/run", headers=auth["headers"])
    assert response.status_code == 200, response.text
    results = response.json()["results"]
    assert results[0]["status"] == "error" and results[0]["code"] == "not_found"
    assert results[1]["status"] == "ok"  # the failure did not stop the scene
    assert response.json()["summary"] == {"ok": 1, "error": 1, "skipped": 0}
    assert (await get_device(client, auth, plug["id"]))["state"]["switch"] is True
    message = next(m for m in await messages_of(hub_app, home["id"]) if m.title == "Scène exécutée: Fragile")
    assert "1 en échec" in message.body and message.severity == "warning"

    # The runner itself refuses foreign devices and unknown action types without raising
    runtime = hub_app.state.hub_runtime
    other = await client.post(f"{PREFIX}/homes", json={"name": "Bureau"}, headers=auth["headers"])
    foreign = await pair_demo(hub_app, other.json()["id"])
    async with runtime.db.session() as session:
        results = await SceneRunner(runtime).run_actions(session, home["id"], [
            {"type": "device_command", "device_id": foreign["demo-plug-1"]["id"], "code": "switch", "value": True},
            {"type": "device_command", "device_id": plug["id"], "code": "nope", "value": True},
            {"type": "warp"},
            {"type": "security_mode", "mode": "vacation"},
        ])
    assert [(r["status"], r["code"]) for r in results] == [
        ("error", "not_found"), ("error", "invalid_input"), ("error", "invalid_input"), ("error", "invalid_input"),
    ]
    assert (await get_device(client, auth, foreign["demo-plug-1"]["id"]))["state"]["switch"] is False


async def test_delay_action_is_capped(client, auth, home, hub_app, monkeypatch):
    runtime = hub_app.state.hub_runtime
    slept: List[float] = []
    real_sleep = runner_module.asyncio.sleep

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)
        await real_sleep(0)  # keep yielding to the loop for everything else that sleeps during the test

    monkeypatch.setattr(runner_module.asyncio, "sleep", fake_sleep)
    scene = await create_scene(client, auth, home, "Pause", [
        {"type": "delay", "seconds": 0},
        {"type": "delay", "seconds": 1.5},
        {"type": "delay", "seconds": 999},
        {"type": "delay", "seconds": -5},
    ])
    response = await client.post(f"{PREFIX}/scenes/{scene['id']}/run", headers=auth["headers"])
    assert response.status_code == 200, response.text
    assert [r["seconds"] for r in response.json()["results"]] == [0.0, 1.5, MAX_DELAY_SECONDS, 0.0]
    assert slept == [1.5, MAX_DELAY_SECONDS]  # zero delays never hit the loop
    async with runtime.db.session() as session:
        results = await SceneRunner(runtime).run_actions(session, home["id"], [{"type": "delay", "seconds": "abc"}])
    assert results[0]["status"] == "error" and results[0]["code"] == "invalid_input"


async def test_run_scene_nested(client, auth, home, devices, hub_app):
    light, plug = devices["demo-light-1"], devices["demo-plug-1"]
    ran = collect_events(hub_app, ev.SCENE_RAN)
    inner = await create_scene(client, auth, home, "Intérieure", [{"type": "device_command", "device_id": light["id"], "code": "switch", "value": False}])
    disabled = await create_scene(client, auth, home, "Désactivée", [{"type": "device_command", "device_id": plug["id"], "code": "switch", "value": True}], enabled=False)
    outer = await create_scene(client, auth, home, "Extérieure", [
        {"type": "run_scene", "scene_id": inner["id"]},
        {"type": "run_scene", "scene_id": disabled["id"]},
    ])
    response = await client.post(f"{PREFIX}/scenes/{outer['id']}/run", headers=auth["headers"])
    assert response.status_code == 200, response.text
    results = response.json()["results"]
    assert results[0]["status"] == "ok" and results[0]["name"] == "Intérieure"
    assert results[0]["results"][0]["state"] == {"switch": False}
    assert results[1]["status"] == "skipped" and "disabled" in results[1]["error"]
    assert response.json()["summary"] == {"ok": 1, "error": 0, "skipped": 1}
    assert (await get_device(client, auth, light["id"]))["state"]["switch"] is False
    assert (await get_device(client, auth, plug["id"]))["state"]["switch"] is False  # disabled scene did not run

    for scene_id in (inner["id"], outer["id"]):
        assert (await client.get(f"{PREFIX}/scenes/{scene_id}", headers=auth["headers"])).json()["last_run_at"] is not None
    assert (await client.get(f"{PREFIX}/scenes/{disabled['id']}", headers=auth["headers"])).json()["last_run_at"] is None
    assert [e.payload["name"] for e in ran] == ["Intérieure", "Extérieure"]
    titles = [m.title for m in await messages_of(hub_app, home["id"])]
    assert titles.count("Scène exécutée: Intérieure") == 1 and titles.count("Scène exécutée: Extérieure") == 1


async def test_run_scene_recursion_limit(client, auth, home, devices, hub_app):
    light = devices["demo-light-1"]
    a = await create_scene(client, auth, home, "A", [])
    b = await create_scene(client, auth, home, "B", [
        {"type": "device_command", "device_id": light["id"], "code": "brightness", "value": 5},
        {"type": "run_scene", "scene_id": a["id"]},
    ])
    response = await client.patch(f"{PREFIX}/scenes/{a['id']}", json={"actions": [{"type": "run_scene", "scene_id": b["id"]}]}, headers=auth["headers"])
    assert response.status_code == 200, response.text  # A -> B -> A cycle is only caught at run time

    ran = collect_events(hub_app, ev.SCENE_RAN)
    response = await client.post(f"{PREFIX}/scenes/{a['id']}/run", headers=auth["headers"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summary"]["error"] == 1  # the top-level run_scene reports the nested failure

    # Walk the nested results: exactly MAX_SCENE_DEPTH hops, then a refusal
    depth, node, last = 0, body["results"][0], None
    while node.get("results"):
        depth += 1
        last = node
        nested = [r for r in node["results"] if r["type"] == "run_scene"]
        node = nested[0]
    assert depth == MAX_SCENE_DEPTH
    assert node["status"] == "error" and node["code"] == "invalid_input" and "nesting" in node["error"]
    assert last is not None and last["status"] == "error"
    # Every scene that ran published scene.ran, innermost first, and the loop terminated
    assert [e.payload["name"] for e in ran] == ["B", "A", "B", "A"]
    assert (await get_device(client, auth, light["id"]))["state"]["brightness"] == 5


async def test_security_mode_action_sets_home_mode(client, auth, home, devices, hub_app):
    runtime = hub_app.state.hub_runtime
    modes = collect_events(hub_app, ev.SECURITY_MODE)
    scene = await create_scene(client, auth, home, "Départ", [{"type": "security_mode", "mode": "armed_away"}])
    response = await client.post(f"{PREFIX}/scenes/{scene['id']}/run", headers=auth["headers"])
    assert response.status_code == 200, response.text
    result = response.json()["results"][0]
    assert result["status"] == "ok" and result["mode"] == "armed_away" and result["previous"] == "disarmed"
    async with runtime.db.session() as session:
        stored = await session.get(Home, home["id"])
        assert stored.security_mode == "armed_away" and stored.security_changed_at is not None
    assert (await client.get(f"{PREFIX}/homes/{home['id']}", headers=auth["headers"])).json()["security_mode"] == "armed_away"
    assert modes and modes[-1].home_id == home["id"] and modes[-1].payload["mode"] == "armed_away"


async def test_scene_runner_direct_run_scene_source(hub_app, home, devices):
    """``run_scene`` can be driven without HTTP (automations use it with source="automation")."""
    runtime = hub_app.state.hub_runtime
    plug = devices["demo-plug-1"]
    ran = collect_events(hub_app, ev.SCENE_RAN)
    async with runtime.db.session() as session:
        scene = Scene(home_id=home["id"], name="Nuit", actions=[{"type": "device_command", "device_id": plug["id"], "code": "switch", "value": True}])
        session.add(scene)
        await session.commit()
        results = await SceneRunner(runtime).run_scene(session, scene, source="automation")
        assert results[0]["status"] == "ok" and scene.last_run_at is not None
    assert ran[0].payload["source"] == "automation"
    message = next(m for m in await messages_of(hub_app, home["id"]) if m.title == "Scène exécutée: Nuit")
    assert "automatisation" in message.body
