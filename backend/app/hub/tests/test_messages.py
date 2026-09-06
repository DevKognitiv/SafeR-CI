"""Message center tests: listing/filters/pagination, unread counters, read state, deletion and isolation."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import select

from app.hub.models import Message
from app.hub.tests.conftest import PREFIX, register_user


# ----------------------------------------------------------------------------- helpers / fixtures
async def add_message(
    hub_app: FastAPI, home_id: str, kind: str, title: str, body: str = "", severity: str = "info",
    created_at: Optional[datetime] = None, read: bool = False,
) -> dict:
    """Insert a message through ``DeviceService.create_message`` (optionally back-dated)."""
    runtime = hub_app.state.hub_runtime
    async with runtime.db.session() as session:
        message = await runtime.services["devices"].create_message(session, home_id, kind, title, body, severity=severity, publish=True)
        if created_at is not None:
            message.created_at = created_at
        message.read = read
        await session.commit()
        return {"id": message.id, "kind": kind, "title": title, "created_at": message.created_at}


@pytest_asyncio.fixture
async def seeded(hub_app: FastAPI, home: Dict) -> List[dict]:
    """Six messages of the three kinds, oldest first, one already read."""
    base = datetime(2026, 9, 6, 8, 0, 0)
    specs = [
        ("alarm", "Mouvement détecté — Couloir", "warning", False),
        ("home", "Nouvel appareil — Lampe salon", "info", True),
        ("notice", "Appareil hors ligne — Prise TV", "warning", False),
        ("alarm", "🚨 Alarme — Porte d'entrée", "critical", False),
        ("home", "Mode sécurité: Armé (absence)", "info", False),
        ("notice", "Mise à jour disponible", "info", False),
    ]
    rows = []
    for index, (kind, title, severity, read) in enumerate(specs):
        rows.append(await add_message(hub_app, home["id"], kind, title, severity=severity, created_at=base + timedelta(minutes=index), read=read))
    return rows


async def listing(client: httpx.AsyncClient, auth: Dict, home_id: str, **params: Any) -> List[dict]:
    response = await client.get(f"{PREFIX}/homes/{home_id}/messages", params=params, headers=auth["headers"])
    assert response.status_code == 200, response.text
    return response.json()


async def unread(client: httpx.AsyncClient, auth: Dict, home_id: str) -> dict:
    response = await client.get(f"{PREFIX}/homes/{home_id}/messages/unread-count", headers=auth["headers"])
    assert response.status_code == 200, response.text
    return response.json()


# ----------------------------------------------------------------------------- listing
async def test_list_messages_newest_first(client, auth, home, seeded):
    items = await listing(client, auth, home["id"])
    assert [m["title"] for m in items] == [row["title"] for row in reversed(seeded)]
    first = items[0]
    assert first["home_id"] == home["id"] and first["kind"] == "notice" and first["read"] is False
    assert first["severity"] == "info" and first["body"] == "" and first["device_id"] is None
    assert first["created_at"].startswith("2026-09-06T08:05:00")


async def test_list_messages_filters(client, auth, home, seeded):
    alarms = await listing(client, auth, home["id"], kind="alarm")
    assert [m["title"] for m in alarms] == ["🚨 Alarme — Porte d'entrée", "Mouvement détecté — Couloir"]
    assert all(m["kind"] == "alarm" for m in alarms)
    homes = await listing(client, auth, home["id"], kind="home", unread_only="true")
    assert [m["title"] for m in homes] == ["Mode sécurité: Armé (absence)"]  # the read one is filtered out
    assert len(await listing(client, auth, home["id"], unread_only="true")) == 5
    assert len(await listing(client, auth, home["id"], limit=2)) == 2
    assert (await client.get(f"{PREFIX}/homes/{home['id']}/messages", params={"kind": "spam"}, headers=auth["headers"])).status_code == 422
    assert (await client.get(f"{PREFIX}/homes/{home['id']}/messages", params={"limit": 0}, headers=auth["headers"])).status_code == 422
    assert (await client.get(f"{PREFIX}/homes/{home['id']}/messages", params={"limit": 999}, headers=auth["headers"])).status_code == 422


async def test_list_messages_before_pagination(client, auth, home, seeded):
    page = await listing(client, auth, home["id"], limit=2)
    assert [m["title"] for m in page] == [seeded[5]["title"], seeded[4]["title"]]
    older = await listing(client, auth, home["id"], limit=2, before=page[-1]["created_at"])
    assert [m["title"] for m in older] == [seeded[3]["title"], seeded[2]["title"]]
    # Aware timestamps are normalised to naive UTC before comparing
    aware = await listing(client, auth, home["id"], before="2026-09-06T10:02:30+02:00")
    assert [m["title"] for m in aware] == [seeded[2]["title"], seeded[1]["title"], seeded[0]["title"]]
    zulu = await listing(client, auth, home["id"], before="2026-09-06T08:01:00Z")
    assert [m["title"] for m in zulu] == [seeded[0]["title"]]
    assert await listing(client, auth, home["id"], before="2020-01-01T00:00:00") == []
    assert (await client.get(f"{PREFIX}/homes/{home['id']}/messages", params={"before": "yesterday"}, headers=auth["headers"])).status_code == 422


async def test_list_messages_empty_home(client, auth, home):
    assert await listing(client, auth, home["id"]) == []
    assert await unread(client, auth, home["id"]) == {"total": 0, "alarm": 0, "home": 0, "notice": 0}


# ----------------------------------------------------------------------------- unread / read
async def test_unread_count(client, auth, home, seeded):
    assert await unread(client, auth, home["id"]) == {"total": 5, "alarm": 2, "home": 1, "notice": 2}


async def test_mark_read(client, auth, home, seeded):
    target = seeded[0]
    response = await client.post(f"{PREFIX}/messages/{target['id']}/read", headers=auth["headers"])
    assert response.status_code == 200, response.text
    assert response.json()["id"] == target["id"] and response.json()["read"] is True
    assert (await unread(client, auth, home["id"]))["alarm"] == 1
    # Idempotent
    assert (await client.post(f"{PREFIX}/messages/{target['id']}/read", headers=auth["headers"])).json()["read"] is True
    assert (await unread(client, auth, home["id"]))["total"] == 4
    assert (await client.post(f"{PREFIX}/messages/missing/read", headers=auth["headers"])).status_code == 404
    assert (await client.post(f"{PREFIX}/messages/{target['id']}/read")).status_code == 401


async def test_read_all_with_kind(client, auth, home, seeded):
    response = await client.post(f"{PREFIX}/homes/{home['id']}/messages/read-all", params={"kind": "alarm"}, headers=auth["headers"])
    assert response.status_code == 200, response.text
    assert response.json() == {"updated": 2}
    assert await unread(client, auth, home["id"]) == {"total": 3, "alarm": 0, "home": 1, "notice": 2}
    response = await client.post(f"{PREFIX}/homes/{home['id']}/messages/read-all", headers=auth["headers"])
    assert response.json() == {"updated": 3}
    assert (await unread(client, auth, home["id"]))["total"] == 0
    assert all(m["read"] for m in await listing(client, auth, home["id"]))
    assert (await client.post(f"{PREFIX}/homes/{home['id']}/messages/read-all", headers=auth["headers"])).json() == {"updated": 0}
    assert (await client.post(f"{PREFIX}/homes/{home['id']}/messages/read-all", params={"kind": "x"}, headers=auth["headers"])).status_code == 422


# ----------------------------------------------------------------------------- deletion
async def test_delete_message(client, auth, home, seeded, hub_app):
    target = seeded[3]
    response = await client.delete(f"{PREFIX}/messages/{target['id']}", headers=auth["headers"])
    assert response.status_code == 204 and response.content == b""
    assert (await client.delete(f"{PREFIX}/messages/{target['id']}", headers=auth["headers"])).status_code == 404
    assert target["id"] not in {m["id"] for m in await listing(client, auth, home["id"])}
    assert (await unread(client, auth, home["id"]))["alarm"] == 1
    async with hub_app.state.hub_runtime.db.session() as session:
        assert await session.get(Message, target["id"]) is None


async def test_clear_messages(client, auth, home, seeded, hub_app):
    response = await client.delete(f"{PREFIX}/homes/{home['id']}/messages", params={"kind": "notice"}, headers=auth["headers"])
    assert response.status_code == 200, response.text
    assert response.json() == {"deleted": 2}
    assert {m["kind"] for m in await listing(client, auth, home["id"])} == {"alarm", "home"}
    response = await client.delete(f"{PREFIX}/homes/{home['id']}/messages", headers=auth["headers"])
    assert response.json() == {"deleted": 4}
    assert await listing(client, auth, home["id"]) == []
    assert (await client.delete(f"{PREFIX}/homes/{home['id']}/messages", headers=auth["headers"])).json() == {"deleted": 0}
    async with hub_app.state.hub_runtime.db.session() as session:
        assert (await session.execute(select(Message).where(Message.home_id == home["id"]))).scalars().all() == []


# ----------------------------------------------------------------------------- isolation
async def test_messages_of_another_home_are_invisible(client, auth, home, seeded, hub_app):
    bob = await register_user(client, email="bob@safer.ci", name="Bob")
    bob["headers"] = {"Authorization": f"Bearer {bob['token']}"}
    bob_home = (await client.post(f"{PREFIX}/homes", json={"name": "Chez Bob"}, headers=bob["headers"])).json()
    await add_message(hub_app, bob_home["id"], "home", "Bienvenue chez Bob")

    target = seeded[0]
    assert (await client.get(f"{PREFIX}/homes/{home['id']}/messages", headers=bob["headers"])).status_code == 404
    assert (await client.get(f"{PREFIX}/homes/{home['id']}/messages/unread-count", headers=bob["headers"])).status_code == 404
    assert (await client.post(f"{PREFIX}/messages/{target['id']}/read", headers=bob["headers"])).status_code == 404
    assert (await client.delete(f"{PREFIX}/messages/{target['id']}", headers=bob["headers"])).status_code == 404
    assert (await client.post(f"{PREFIX}/homes/{home['id']}/messages/read-all", headers=bob["headers"])).status_code == 404
    assert (await client.delete(f"{PREFIX}/homes/{home['id']}/messages", headers=bob["headers"])).status_code == 404
    # Alice's view is untouched and Bob only sees his own home
    assert len(await listing(client, auth, home["id"])) == 6
    assert (await unread(client, auth, home["id"]))["total"] == 5
    assert [m["title"] for m in await listing(client, bob, bob_home["id"])] == ["Bienvenue chez Bob"]
    assert (await client.get(f"{PREFIX}/homes/{bob_home['id']}/messages", headers=auth["headers"])).status_code == 404


async def test_member_can_use_message_center(client, auth, home, seeded):
    bob = await register_user(client, email="bob@safer.ci", name="Bob")
    bob["headers"] = {"Authorization": f"Bearer {bob['token']}"}
    response = await client.post(f"{PREFIX}/homes/{home['id']}/members", json={"email": "bob@safer.ci", "role": "member"}, headers=auth["headers"])
    assert response.status_code == 201, response.text
    visible = await listing(client, bob, home["id"])
    assert {row["title"] for row in seeded} <= {m["title"] for m in visible}  # (+ the "new member" home message)
    assert (await client.post(f"{PREFIX}/messages/{seeded[0]['id']}/read", headers=bob["headers"])).status_code == 200
    remaining = (await unread(client, bob, home["id"]))["total"]
    assert remaining == len([m for m in visible if not m["read"]]) - 1
    assert (await client.post(f"{PREFIX}/homes/{home['id']}/messages/read-all", headers=bob["headers"])).json() == {"updated": remaining}
    assert (await unread(client, auth, home["id"]))["total"] == 0  # read state is per home, shared by members


async def test_messages_created_by_device_events_are_listed(client, auth, home, hub_app):
    """End-to-end: a device alarm goes through DeviceService and lands in the message center."""
    from app.hub.adapters.registry import registry  # pylint: disable=import-outside-toplevel
    from app.hub.models import Device  # pylint: disable=import-outside-toplevel
    from app.hub.services.security_service import set_security_mode  # pylint: disable=import-outside-toplevel
    from app.hub.models import Home  # pylint: disable=import-outside-toplevel

    runtime = hub_app.state.hub_runtime
    adapter = registry.get("demo")
    adapter._state.clear()  # pylint: disable=protected-access
    result = await adapter.pair("virtual", {}, runtime.ctx_for("demo"))
    async with runtime.db.session() as session:
        rows, _ = await runtime.services["devices"].materialize(session, home["id"], None, "demo", result)
        smoke = next(d for d in rows if d.external_id == "demo-smoke-1")
        await set_security_mode(runtime, session, await session.get(Home, home["id"]), "armed_away", user_id=auth["user"]["id"])
        await runtime.services["devices"].apply_state(session, await session.get(Device, smoke.id), {"smoke": True}, online=True)
    items = await listing(client, auth, home["id"])
    titles = [m["title"] for m in items]
    assert "Mode sécurité: Armé (absence)" in titles
    assert "Fumée détectée — Détecteur fumée cuisine" in titles and "🚨 Alarme — Détecteur fumée cuisine" in titles
    alarm = next(m for m in items if m["title"].startswith("🚨"))
    assert alarm["kind"] == "alarm" and alarm["severity"] == "critical" and alarm["device_id"] == smoke.id
    counts = await unread(client, auth, home["id"])
    assert counts["alarm"] == 2 and counts["home"] == 1
