"""Homes / rooms / members / weather route tests."""
from __future__ import annotations

from typing import Dict, List

import httpx
from sqlalchemy import select

from app.hub import events as ev
from app.hub.adapters.base import AdapterContext
from app.hub.app import create_app
from app.hub.models import Device, Home, HomeMember, Message, Room
from app.hub.runtime import set_runtime
from app.hub.services import weather
from app.hub.tests.conftest import PREFIX, make_settings, register_user

# Realistic Open-Meteo /v1/forecast body for Abidjan (current block only)
OPEN_METEO_SAMPLE = {
    "latitude": 5.375,
    "longitude": -4.0,
    "generationtime_ms": 0.0810623,
    "utc_offset_seconds": 0,
    "timezone": "GMT",
    "timezone_abbreviation": "GMT",
    "elevation": 30.0,
    "current_units": {
        "time": "iso8601", "interval": "seconds", "temperature_2m": "°C", "relative_humidity_2m": "%",
        "weather_code": "wmo code", "wind_speed_10m": "km/h",
    },
    "current": {
        "time": "2026-09-06T10:15", "interval": 900, "temperature_2m": 28.4, "relative_humidity_2m": 74,
        "weather_code": 2, "wind_speed_10m": 12.3,
    },
}


async def other_user(client: httpx.AsyncClient, email: str = "bob@safer.ci", name: str = "Bob") -> Dict:
    """Register another account and return {token, user, headers}."""
    data = await register_user(client, email=email, name=name)
    data["headers"] = {"Authorization": f"Bearer {data['token']}"}
    return data


async def add_member(client: httpx.AsyncClient, home_id: str, headers: Dict, email: str, role: str = "member") -> httpx.Response:
    return await client.post(f"{PREFIX}/homes/{home_id}/members", json={"email": email, "role": role}, headers=headers)


# ----------------------------------------------------------------------------- homes
async def test_create_home_with_rooms(home):
    assert home["name"] == "Maison Cocody"
    assert home["role"] == "owner"
    assert home["lat"] == 5.36 and home["lon"] == -4.0
    assert home["security_mode"] == "disarmed"
    assert home["alarm_active"] is False
    assert [room["name"] for room in home["rooms"]] == ["Salon", "Chambre"]
    assert [room["sort_order"] for room in home["rooms"]] == [0, 1]
    assert all(room["home_id"] == home["id"] and room["device_count"] == 0 for room in home["rooms"])
    assert home["member_count"] == 1
    assert home["device_count"] == 0
    assert home["created_at"]


async def test_create_home_validation(client, auth):
    assert (await client.post(f"{PREFIX}/homes", json={"name": ""}, headers=auth["headers"])).status_code == 422
    assert (await client.post(f"{PREFIX}/homes", json={"name": "   "}, headers=auth["headers"])).status_code == 400
    minimal = await client.post(f"{PREFIX}/homes", json={"name": "Bureau"}, headers=auth["headers"])
    assert minimal.status_code == 201
    assert minimal.json()["rooms"] == []
    assert minimal.json()["lat"] is None


async def test_list_and_get_home(client, auth, home):
    listed = await client.get(f"{PREFIX}/homes", headers=auth["headers"])
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [home["id"]]
    assert listed.json()[0]["role"] == "owner"
    assert [room["name"] for room in listed.json()[0]["rooms"]] == ["Salon", "Chambre"]

    single = await client.get(f"{PREFIX}/homes/{home['id']}", headers=auth["headers"])
    assert single.status_code == 200
    assert single.json() == listed.json()[0]

    # another account sees nothing: the home is invisible (404), not forbidden
    bob = await other_user(client)
    assert (await client.get(f"{PREFIX}/homes", headers=bob["headers"])).json() == []
    assert (await client.get(f"{PREFIX}/homes/{home['id']}", headers=bob["headers"])).status_code == 404
    assert (await client.get(f"{PREFIX}/homes/does-not-exist", headers=auth["headers"])).status_code == 404


async def test_patch_home_permissions(client, auth, home):
    url = f"{PREFIX}/homes/{home['id']}"
    ok = await client.patch(url, json={"name": "Villa Cocody", "address": "Riviera 3, Abidjan"}, headers=auth["headers"])
    assert ok.status_code == 200, ok.text
    assert ok.json()["name"] == "Villa Cocody"
    assert ok.json()["address"] == "Riviera 3, Abidjan"
    assert ok.json()["lat"] == 5.36  # untouched

    bob = await other_user(client)
    assert (await client.patch(url, json={"name": "Hacked"}, headers=bob["headers"])).status_code == 404
    assert (await add_member(client, home["id"], auth["headers"], "bob@safer.ci")).status_code == 201
    assert (await client.patch(url, json={"name": "Hacked"}, headers=bob["headers"])).status_code == 403
    promote = await client.patch(f"{url}/members/{bob['user']['id']}", json={"role": "admin"}, headers=auth["headers"])
    assert promote.status_code == 200
    assert (await client.patch(url, json={"name": "Villa Bob"}, headers=bob["headers"])).status_code == 200
    assert (await client.get(url, headers=auth["headers"])).json()["name"] == "Villa Bob"


async def test_delete_home_permissions(client, auth, home, hub_app):
    url = f"{PREFIX}/homes/{home['id']}"
    bob = await other_user(client)
    assert (await add_member(client, home["id"], auth["headers"], "bob@safer.ci", role="admin")).status_code == 201
    assert (await client.delete(url, headers=bob["headers"])).status_code == 403  # admin is not enough
    assert (await client.delete(url, headers=auth["headers"])).status_code == 204
    assert (await client.get(url, headers=auth["headers"])).status_code == 404
    assert (await client.get(f"{PREFIX}/homes", headers=auth["headers"])).json() == []
    assert (await client.get(f"{PREFIX}/homes", headers=bob["headers"])).json() == []
    async with hub_app.state.hub_runtime.db.session() as session:
        assert await session.get(Home, home["id"]) is None
        assert (await session.execute(select(Room).where(Room.home_id == home["id"]))).scalars().all() == []
        assert (await session.execute(select(HomeMember).where(HomeMember.home_id == home["id"]))).scalars().all() == []


# ----------------------------------------------------------------------------- rooms
async def test_rooms_crud(client, auth, home):
    rooms_url = f"{PREFIX}/homes/{home['id']}/rooms"
    listed = await client.get(rooms_url, headers=auth["headers"])
    assert listed.status_code == 200
    assert [room["name"] for room in listed.json()] == ["Salon", "Chambre"]
    assert all(room["device_count"] == 0 for room in listed.json())

    created = await client.post(rooms_url, json={"name": "Cuisine", "icon": "kitchen"}, headers=auth["headers"])
    assert created.status_code == 201, created.text
    room = created.json()
    assert room["name"] == "Cuisine" and room["icon"] == "kitchen"
    assert room["sort_order"] == 2 and room["device_count"] == 0 and room["home_id"] == home["id"]

    patched = await client.patch(f"{PREFIX}/rooms/{room['id']}", json={"name": "Cuisine ouverte", "icon": "restaurant"}, headers=auth["headers"])
    assert patched.status_code == 200, patched.text
    assert patched.json()["name"] == "Cuisine ouverte"
    assert patched.json()["icon"] == "restaurant"
    assert patched.json()["sort_order"] == 2
    assert (await client.patch(f"{PREFIX}/rooms/{room['id']}", json={"name": "   "}, headers=auth["headers"])).status_code == 400

    # non-member -> 404, plain member -> 403 (room routes resolve the home through the room)
    bob = await other_user(client)
    assert (await client.patch(f"{PREFIX}/rooms/{room['id']}", json={"name": "x"}, headers=bob["headers"])).status_code == 404
    assert (await client.delete(f"{PREFIX}/rooms/{room['id']}", headers=bob["headers"])).status_code == 404
    assert (await add_member(client, home["id"], auth["headers"], "bob@safer.ci")).status_code == 201
    assert (await client.patch(f"{PREFIX}/rooms/{room['id']}", json={"name": "x"}, headers=bob["headers"])).status_code == 403
    assert (await client.post(rooms_url, json={"name": "Garage"}, headers=bob["headers"])).status_code == 403
    assert (await client.get(rooms_url, headers=bob["headers"])).status_code == 200

    deleted = await client.delete(f"{PREFIX}/rooms/{room['id']}", headers=auth["headers"])
    assert deleted.status_code == 204
    assert [r["name"] for r in (await client.get(rooms_url, headers=auth["headers"])).json()] == ["Salon", "Chambre"]
    assert (await client.patch(f"{PREFIX}/rooms/{room['id']}", json={"name": "x"}, headers=auth["headers"])).status_code == 404
    assert (await client.patch(f"{PREFIX}/rooms/nope", json={"name": "x"}, headers=auth["headers"])).status_code == 404


async def test_rooms_reorder(client, auth, home):
    salon, chambre = home["rooms"]
    url = f"{PREFIX}/homes/{home['id']}/rooms/reorder"
    response = await client.post(url, json={"ids": [chambre["id"], salon["id"]]}, headers=auth["headers"])
    assert response.status_code == 200, response.text
    assert [(r["name"], r["sort_order"]) for r in response.json()] == [("Chambre", 0), ("Salon", 1)]
    assert [r["name"] for r in (await client.get(f"{PREFIX}/homes/{home['id']}", headers=auth["headers"])).json()["rooms"]] == ["Chambre", "Salon"]

    # a partial list moves the listed rooms first and keeps the others in their relative order
    cuisine = (await client.post(f"{PREFIX}/homes/{home['id']}/rooms", json={"name": "Cuisine"}, headers=auth["headers"])).json()
    response = await client.post(url, json={"ids": [cuisine["id"]]}, headers=auth["headers"])
    assert [r["name"] for r in response.json()] == ["Cuisine", "Chambre", "Salon"]
    assert [r["sort_order"] for r in response.json()] == [0, 1, 2]

    bad = await client.post(url, json={"ids": [salon["id"], "unknown-room"]}, headers=auth["headers"])
    assert bad.status_code == 400
    assert "unknown-room" in bad.json()["detail"]

    bob = await other_user(client)
    assert (await add_member(client, home["id"], auth["headers"], "bob@safer.ci")).status_code == 201
    assert (await client.post(url, json={"ids": [salon["id"]]}, headers=bob["headers"])).status_code == 403


async def test_room_delete_unassigns_devices(client, auth, home, hub_app):
    salon = home["rooms"][0]
    runtime = hub_app.state.hub_runtime
    async with runtime.db.session() as session:
        session.add(Device(home_id=home["id"], room_id=salon["id"], name="Lampe salon", brand="demo", protocol="demo",
                           category="light", external_id="test-light-1"))
        session.add(Device(home_id=home["id"], room_id=None, name="Capteur", brand="demo", protocol="demo",
                           category="sensor_motion", external_id="test-pir-1"))
        await session.commit()

    rooms = (await client.get(f"{PREFIX}/homes/{home['id']}/rooms", headers=auth["headers"])).json()
    assert [(r["name"], r["device_count"]) for r in rooms] == [("Salon", 1), ("Chambre", 0)]
    detail = (await client.get(f"{PREFIX}/homes/{home['id']}", headers=auth["headers"])).json()
    assert detail["device_count"] == 2  # includes the device without a room
    assert detail["rooms"][0]["device_count"] == 1

    assert (await client.delete(f"{PREFIX}/rooms/{salon['id']}", headers=auth["headers"])).status_code == 204
    async with runtime.db.session() as session:
        device = (await session.execute(select(Device).where(Device.external_id == "test-light-1"))).scalar_one()
        assert device.room_id is None
        assert await session.get(Room, salon["id"]) is None
    detail = (await client.get(f"{PREFIX}/homes/{home['id']}", headers=auth["headers"])).json()
    assert detail["device_count"] == 2
    assert [r["name"] for r in detail["rooms"]] == ["Chambre"]


# ----------------------------------------------------------------------------- members
async def test_members_add_patch_delete_rules(client, auth, home, hub_app):
    runtime = hub_app.state.hub_runtime
    seen: List[ev.HubEvent] = []

    async def collect(event: ev.HubEvent) -> None:
        seen.append(event)

    runtime.bus.subscribe(collect)
    members_url = f"{PREFIX}/homes/{home['id']}/members"
    bob = await other_user(client)
    carol = await other_user(client, email="carol@safer.ci", name="Carol")

    # unknown e-mail -> 404, bad role -> 422
    missing = await add_member(client, home["id"], auth["headers"], "nobody@safer.ci")
    assert missing.status_code == 404 and missing.json()["detail"] == "User not found"
    assert (await add_member(client, home["id"], auth["headers"], "bob@safer.ci", role="owner")).status_code == 422

    added = await add_member(client, home["id"], auth["headers"], "Bob@Safer.ci")
    assert added.status_code == 201, added.text
    assert added.json()["user_id"] == bob["user"]["id"]
    assert added.json()["email"] == "bob@safer.ci" and added.json()["name"] == "Bob"
    assert added.json()["role"] == "member" and added.json()["joined_at"]
    assert (await add_member(client, home["id"], auth["headers"], "bob@safer.ci")).status_code == 409

    listed = await client.get(members_url, headers=auth["headers"])
    assert listed.status_code == 200
    assert [(m["name"], m["role"]) for m in listed.json()] == [("Alice", "owner"), ("Bob", "member")]
    mine = await client.get(f"{PREFIX}/homes/{home['id']}", headers=bob["headers"])
    assert mine.status_code == 200 and mine.json()["role"] == "member" and mine.json()["member_count"] == 2

    # a plain member can list but not manage members
    assert (await client.get(members_url, headers=bob["headers"])).status_code == 200
    assert (await add_member(client, home["id"], bob["headers"], "carol@safer.ci")).status_code == 403
    assert (await client.patch(f"{members_url}/{bob['user']['id']}", json={"role": "admin"}, headers=bob["headers"])).status_code == 403
    assert (await client.delete(f"{members_url}/{auth['user']['id']}", headers=bob["headers"])).status_code == 400  # owner is untouchable

    # owner promotes bob; bob (admin) can add carol but cannot promote (owner only) or remove another admin
    promoted = await client.patch(f"{members_url}/{bob['user']['id']}", json={"role": "admin"}, headers=auth["headers"])
    assert promoted.status_code == 200 and promoted.json()["role"] == "admin"
    assert (await add_member(client, home["id"], bob["headers"], "carol@safer.ci", role="admin")).status_code == 201
    assert (await client.patch(f"{members_url}/{carol['user']['id']}", json={"role": "member"}, headers=bob["headers"])).status_code == 403
    assert (await client.delete(f"{members_url}/{carol['user']['id']}", headers=bob["headers"])).status_code == 403
    assert (await client.delete(f"{members_url}/{auth['user']['id']}", headers=bob["headers"])).status_code == 400
    assert (await client.patch(f"{members_url}/unknown-user", json={"role": "member"}, headers=auth["headers"])).status_code == 404

    # owner removes carol, then bob; bob loses access entirely
    assert (await client.delete(f"{members_url}/{carol['user']['id']}", headers=auth["headers"])).status_code == 204
    assert (await client.delete(f"{members_url}/{bob['user']['id']}", headers=auth["headers"])).status_code == 204
    assert (await client.delete(f"{members_url}/{bob['user']['id']}", headers=auth["headers"])).status_code == 404
    assert [m["role"] for m in (await client.get(members_url, headers=auth["headers"])).json()] == ["owner"]
    assert (await client.get(f"{PREFIX}/homes/{home['id']}", headers=bob["headers"])).status_code == 404

    # message-center entries (kind "home") + message.new events for the 2 additions and 2 removals
    async with runtime.db.session() as session:
        messages = (await session.execute(select(Message).where(Message.home_id == home["id"]).order_by(Message.created_at))).scalars().all()
    assert [m.kind for m in messages] == ["home"] * 4
    assert messages[0].title == "Nouveau membre: Bob"
    assert messages[1].title == "Nouveau membre: Carol"
    assert messages[2].title == "Membre retiré: Carol"
    assert messages[3].title == "Membre retiré: Bob"
    message_events = [e for e in seen if e.type == ev.MESSAGE_NEW]
    assert len(message_events) == 4
    assert message_events[0].home_id == home["id"]
    assert message_events[0].payload["message"]["title"] == "Nouveau membre: Bob"
    assert message_events[0].payload["message"]["kind"] == "home"


async def test_member_self_leave_and_owner_transfer(client, auth, home):
    members_url = f"{PREFIX}/homes/{home['id']}/members"
    bob = await other_user(client)
    assert (await add_member(client, home["id"], auth["headers"], "bob@safer.ci")).status_code == 201

    # the owner cannot demote themself without transferring first, and cannot leave
    assert (await client.patch(f"{members_url}/{auth['user']['id']}", json={"role": "admin"}, headers=auth["headers"])).status_code == 400
    assert (await client.delete(f"{members_url}/{auth['user']['id']}", headers=auth["headers"])).status_code == 400

    # transfer: bob becomes owner, alice is demoted to admin
    transfer = await client.patch(f"{members_url}/{bob['user']['id']}", json={"role": "owner"}, headers=auth["headers"])
    assert transfer.status_code == 200, transfer.text
    assert transfer.json()["role"] == "owner"
    roles = {m["name"]: m["role"] for m in (await client.get(members_url, headers=auth["headers"])).json()}
    assert roles == {"Alice": "admin", "Bob": "owner"}
    assert (await client.get(f"{PREFIX}/homes/{home['id']}", headers=auth["headers"])).json()["role"] == "admin"
    assert (await client.patch(f"{members_url}/{bob['user']['id']}", json={"role": "member"}, headers=auth["headers"])).status_code == 403
    assert (await client.delete(f"{PREFIX}/homes/{home['id']}", headers=auth["headers"])).status_code == 403

    # a non-owner may leave on their own; the (new) owner may not
    assert (await client.delete(f"{members_url}/{auth['user']['id']}", headers=auth["headers"])).status_code == 204
    assert (await client.get(f"{PREFIX}/homes/{home['id']}", headers=auth["headers"])).status_code == 404
    assert (await client.delete(f"{members_url}/{bob['user']['id']}", headers=bob["headers"])).status_code == 400
    assert (await client.get(f"{PREFIX}/homes/{home['id']}", headers=bob["headers"])).json()["member_count"] == 1


# ----------------------------------------------------------------------------- weather
async def test_weather_disabled(client, auth, home):
    weather.clear_cache()
    response = await client.get(f"{PREFIX}/homes/{home['id']}/weather", headers=auth["headers"])
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["temperature"] is None
    assert body["condition"] == "unknown"
    bob = await other_user(client)
    assert (await client.get(f"{PREFIX}/homes/{home['id']}/weather", headers=bob["headers"])).status_code == 404


async def test_weather_route_with_mock_transport():
    weather.clear_cache()
    requests: List[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=OPEN_METEO_SAMPLE)

    app = create_app(
        settings=make_settings(HUB_WEATHER_ENABLED=True), database_url="sqlite+aiosqlite://",
        transport=httpx.MockTransport(handler), start_services=False,
    )
    runtime = app.state.hub_runtime
    await runtime.start()
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://hub") as client:
            alice = await other_user(client, email="alice@safer.ci", name="Alice")
            created = await client.post(f"{PREFIX}/homes", json={"name": "Maison", "lat": 5.36, "lon": -4.0}, headers=alice["headers"])
            assert created.status_code == 201
            home_id = created.json()["id"]

            response = await client.get(f"{PREFIX}/homes/{home_id}/weather", headers=alice["headers"])
            assert response.status_code == 200, response.text
            body = response.json()
            assert body == {
                "temperature": 28.4, "humidity": 74.0, "condition": "partly_cloudy", "icon": "wb_cloudy",
                "wind_kmh": 12.3, "updated_at": "2026-09-06T10:15:00", "available": True,
            }
            assert len(requests) == 1
            request = requests[0]
            assert request.method == "GET"
            assert request.url.scheme == "https" and request.url.host == "api.open-meteo.com" and request.url.path == "/v1/forecast"
            assert request.url.params["latitude"] == "5.36"
            assert request.url.params["longitude"] == "-4.0"
            assert request.url.params["current"] == "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"

            # second call within 60 s is served from the cache
            again = await client.get(f"{PREFIX}/homes/{home_id}/weather", headers=alice["headers"])
            assert again.json() == body
            assert len(requests) == 1

            # a home without coordinates never triggers a request
            no_coords = await client.post(f"{PREFIX}/homes", json={"name": "Bureau"}, headers=alice["headers"])
            response = await client.get(f"{PREFIX}/homes/{no_coords.json()['id']}/weather", headers=alice["headers"])
            assert response.status_code == 200
            assert response.json()["available"] is False
            assert len(requests) == 1
    finally:
        await runtime.stop()
        set_runtime(None)
        weather.clear_cache()


async def test_weather_service_mapping_and_failures():
    weather.clear_cache()
    settings = make_settings(HUB_WEATHER_ENABLED=True)
    codes = iter([0, 3, 45, 55, 63, 75, 81, 95, 1234])

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.open-meteo.com"
        sample = {**OPEN_METEO_SAMPLE, "current": {**OPEN_METEO_SAMPLE["current"], "weather_code": next(codes)}}
        return httpx.Response(200, json=sample)

    ctx = AdapterContext(settings=settings, transport=httpx.MockTransport(handler))
    expected = [
        ("clear", "wb_sunny"), ("cloudy", "cloud"), ("fog", "foggy"), ("drizzle", "grain"), ("rain", "water_drop"),
        ("snow", "ac_unit"), ("rain_showers", "umbrella"), ("thunderstorm", "thunderstorm"), ("unknown", "cloud"),
    ]
    for index, (condition, icon) in enumerate(expected):
        result = await weather.get_weather(48.85 + index, 2.35, ctx)  # distinct cache keys
        assert result.available is True
        assert (result.condition, result.icon) == (condition, icon)
        assert result.temperature == 28.4 and result.humidity == 74.0 and result.wind_kmh == 12.3

    # disabled / missing coordinates: no request at all
    disabled = AdapterContext(settings=make_settings(HUB_WEATHER_ENABLED=False), transport=httpx.MockTransport(handler))
    assert (await weather.get_weather(5.36, -4.0, disabled)).available is False
    assert (await weather.get_weather(None, -4.0, ctx)).available is False
    assert (await weather.get_weather(5.36, None, ctx)).available is False

    # upstream errors degrade gracefully instead of raising
    def failing(request: httpx.Request) -> httpx.Response:
        if request.url.params["latitude"] == "1.0":
            raise httpx.ConnectError("offline", request=request)
        if request.url.params["latitude"] == "2.0":
            return httpx.Response(400, json={"error": True, "reason": "Latitude must be in range of -90 to 90°."})
        return httpx.Response(200, content=b"<html>not json</html>", headers={"content-type": "text/html"})

    failing_ctx = AdapterContext(settings=settings, transport=httpx.MockTransport(failing))
    for lat in (1.0, 2.0, 3.0):
        result = await weather.get_weather(lat, 0.0, failing_ctx)
        assert result.available is False
        assert result.condition == "unknown"
    weather.clear_cache()
