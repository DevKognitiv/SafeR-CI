"""Auth route tests: register / login / me / push tokens (all through httpx.ASGITransport)."""
from __future__ import annotations

import httpx
from sqlalchemy import select

from app.hub.app import create_app
from app.hub.models import PushToken
from app.hub.runtime import set_runtime
from app.hub.security import create_access_token
from app.hub.tests.conftest import PREFIX, make_settings, register_user


async def test_register_login_me_patch(client):
    data = await register_user(client)
    assert data["token"]
    assert data["token_type"] == "bearer"
    user = data["user"]
    assert user["email"] == "alice@safer.ci"
    assert user["name"] == "Alice"
    assert user["is_admin"] is True  # first user of a fresh hub
    assert "password" not in user and "password_hash" not in user

    # login is case-insensitive on the e-mail and returns a fresh token
    login = await client.post(f"{PREFIX}/auth/login", json={"email": "Alice@Safer.CI", "password": "secret123"})
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['token']}"}
    assert login.json()["user"]["id"] == user["id"]

    me = await client.get(f"{PREFIX}/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["id"] == user["id"]
    assert me.json()["locale"] == "fr"

    patch = await client.patch(
        f"{PREFIX}/auth/me",
        json={"name": "  Alice K. ", "phone": "+2250700000000", "locale": "en", "avatar_url": "https://cdn.safer.ci/a.png"},
        headers=headers,
    )
    assert patch.status_code == 200, patch.text
    body = patch.json()
    assert body["name"] == "Alice K."
    assert body["phone"] == "+2250700000000"
    assert body["locale"] == "en"
    assert body["avatar_url"] == "https://cdn.safer.ci/a.png"
    assert body["email"] == "alice@safer.ci"

    # partial update leaves the other fields alone
    patch2 = await client.patch(f"{PREFIX}/auth/me", json={"name": "Alice"}, headers=headers)
    assert patch2.status_code == 200
    assert patch2.json()["phone"] == "+2250700000000"
    assert patch2.json()["locale"] == "en"


async def test_second_user_is_not_admin(client):
    first = await register_user(client)
    second = await register_user(client, email="bob@safer.ci", name="Bob")
    assert first["user"]["is_admin"] is True
    assert second["user"]["is_admin"] is False
    assert first["user"]["id"] != second["user"]["id"]


async def test_register_duplicate_email_409(client):
    await register_user(client)
    response = await client.post(
        f"{PREFIX}/auth/register", json={"email": "ALICE@safer.ci", "password": "another1", "name": "Alice 2"}
    )
    assert response.status_code == 409
    assert "already" in response.json()["detail"].lower()


async def test_register_validation_422(client):
    bad_email = await client.post(f"{PREFIX}/auth/register", json={"email": "not-an-email", "password": "secret123"})
    assert bad_email.status_code == 422
    short_password = await client.post(f"{PREFIX}/auth/register", json={"email": "x@safer.ci", "password": "abc"})
    assert short_password.status_code == 422


async def test_login_bad_credentials_401(client):
    await register_user(client)
    wrong = await client.post(f"{PREFIX}/auth/login", json={"email": "alice@safer.ci", "password": "wrong-pass"})
    assert wrong.status_code == 401
    unknown = await client.post(f"{PREFIX}/auth/login", json={"email": "nobody@safer.ci", "password": "secret123"})
    assert unknown.status_code == 401
    # same message for both so the endpoint does not leak which accounts exist
    assert wrong.json()["detail"] == unknown.json()["detail"]


async def test_unauthenticated_401(client, auth):
    assert (await client.get(f"{PREFIX}/auth/me")).status_code == 401
    assert (await client.get(f"{PREFIX}/auth/me", headers={"Authorization": "Bearer not-a-token"})).status_code == 401
    forged = create_access_token(auth["user"]["id"], "some-other-secret")
    assert (await client.get(f"{PREFIX}/auth/me", headers={"Authorization": f"Bearer {forged}"})).status_code == 401
    assert (await client.patch(f"{PREFIX}/auth/me", json={"name": "x"})).status_code == 401
    assert (await client.post(f"{PREFIX}/auth/push-token", json={"platform": "android", "token": "abcdefgh1234"})).status_code == 401
    assert (await client.get(f"{PREFIX}/homes")).status_code == 401


async def test_push_token_upsert_and_delete(client, auth, hub_app):
    fcm_token = "dQw4w9WgXcQ:APA91bHun4MxP5egoKMwt2l4WkHm-example-token"
    payload = {"platform": "android", "token": fcm_token}
    for _ in range(2):  # registering the same token twice must not create a second row
        response = await client.post(f"{PREFIX}/auth/push-token", json=payload, headers=auth["headers"])
        assert response.status_code == 204, response.text

    runtime = hub_app.state.hub_runtime
    async with runtime.db.session() as session:
        rows = (await session.execute(select(PushToken).where(PushToken.token == fcm_token))).scalars().all()
        assert len(rows) == 1
        assert rows[0].user_id == auth["user"]["id"]
        assert rows[0].platform == "android"

    # the token moves to whoever registers it last (device handed to another account)
    bob = await register_user(client, email="bob@safer.ci", name="Bob")
    bob_headers = {"Authorization": f"Bearer {bob['token']}"}
    response = await client.post(f"{PREFIX}/auth/push-token", json={"platform": "ios", "token": fcm_token}, headers=bob_headers)
    assert response.status_code == 204
    async with runtime.db.session() as session:
        rows = (await session.execute(select(PushToken).where(PushToken.token == fcm_token))).scalars().all()
        assert len(rows) == 1
        assert rows[0].user_id == bob["user"]["id"]
        assert rows[0].platform == "ios"

    # deleting only affects the caller's own tokens (idempotent 204 either way)
    response = await client.delete(f"{PREFIX}/auth/push-token/{fcm_token}", headers=auth["headers"])
    assert response.status_code == 204
    async with runtime.db.session() as session:
        assert (await session.execute(select(PushToken).where(PushToken.token == fcm_token))).scalar_one_or_none() is not None
    response = await client.delete(f"{PREFIX}/auth/push-token/{fcm_token}", headers=bob_headers)
    assert response.status_code == 204
    async with runtime.db.session() as session:
        assert (await session.execute(select(PushToken).where(PushToken.token == fcm_token))).scalar_one_or_none() is None

    too_short = await client.post(f"{PREFIX}/auth/push-token", json={"platform": "android", "token": "abc"}, headers=auth["headers"])
    assert too_short.status_code == 422


async def test_closed_registration_403():
    app = create_app(
        settings=make_settings(HUB_ALLOW_OPEN_REGISTRATION=False), database_url="sqlite+aiosqlite://", start_services=False
    )
    runtime = app.state.hub_runtime
    await runtime.start()
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://hub") as client:
            first = await register_user(client)  # the very first account is always allowed (it becomes admin)
            assert first["user"]["is_admin"] is True
            response = await client.post(
                f"{PREFIX}/auth/register", json={"email": "bob@safer.ci", "password": "secret123", "name": "Bob"}
            )
            assert response.status_code == 403
            # ...but existing accounts still log in
            login = await client.post(f"{PREFIX}/auth/login", json={"email": "alice@safer.ci", "password": "secret123"})
            assert login.status_code == 200
    finally:
        await runtime.stop()
        set_runtime(None)
