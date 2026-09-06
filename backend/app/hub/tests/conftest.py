"""Shared pytest fixtures: in-memory SQLite hub app + authenticated HTTP client."""
from __future__ import annotations

import os
from typing import AsyncIterator, Dict

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from app.hub.app import create_app
from app.hub.runtime import HubRuntime, set_runtime
from app.hub.settings import HubSettings

os.environ.setdefault("SECRET_KEY", "test-secret-key")
PREFIX = "/api/v1/hub"


def make_settings(**overrides) -> HubSettings:
    """Settings for tests (no background services, no weather calls)."""
    values = {"SECRET_KEY": "test-secret-key", "HUB_WEATHER_ENABLED": False, "HUB_SIA_PORT": 0}
    values.update(overrides)
    return HubSettings(**values)


@pytest_asyncio.fixture
async def hub_app() -> AsyncIterator[FastAPI]:
    """Fresh app + runtime with an in-memory database per test."""
    app = create_app(settings=make_settings(), database_url="sqlite+aiosqlite://", start_services=False)
    runtime: HubRuntime = app.state.hub_runtime
    await runtime.start()
    try:
        yield app
    finally:
        await runtime.stop()
        set_runtime(None)


@pytest_asyncio.fixture
async def client(hub_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """Unauthenticated client."""
    transport = httpx.ASGITransport(app=hub_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://hub") as http:
        yield http


async def register_user(client: httpx.AsyncClient, email: str = "alice@safer.ci", password: str = "secret123", name: str = "Alice") -> Dict:
    """Register and return {token, user}."""
    response = await client.post(f"{PREFIX}/auth/register", json={"email": email, "password": password, "name": name})
    assert response.status_code == 201, response.text
    return response.json()


@pytest_asyncio.fixture
async def auth(client: httpx.AsyncClient) -> Dict:
    """Registered user; returns {token, user, headers}."""
    data = await register_user(client)
    data["headers"] = {"Authorization": f"Bearer {data['token']}"}
    return data


@pytest_asyncio.fixture
async def home(client: httpx.AsyncClient, auth: Dict) -> Dict:
    """A home owned by ``auth`` with two rooms."""
    response = await client.post(f"{PREFIX}/homes", json={"name": "Maison Cocody", "lat": 5.36, "lon": -4.0, "rooms": ["Salon", "Chambre"]}, headers=auth["headers"])
    assert response.status_code == 201, response.text
    return response.json()


@pytest_asyncio.fixture
async def demo_devices(client: httpx.AsyncClient, auth: Dict, home: Dict) -> list:
    """Pair the demo brand into ``home`` and return the devices."""
    response = await client.post(
        f"{PREFIX}/onboarding/demo/pair",
        json={"home_id": home["id"], "method": "virtual", "payload": {}},
        headers=auth["headers"],
    )
    assert response.status_code == 201, response.text
    return response.json()["devices"]
