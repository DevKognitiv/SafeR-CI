"""Core hub tests: settings, security helpers, capability coercion, event bus, demo adapter, health."""
import pytest

from app.hub.adapters.base import AdapterContext, DeviceRef
from app.hub.adapters.registry import registry
from app.hub.capabilities import cap, coerce_value
from app.hub.events import EventBus, HubEvent
from app.hub.security import CredentialVault, create_access_token, decode_access_token, hash_password, verify_password
from app.hub.settings import HubSettings
from app.hub.tests.conftest import PREFIX


def test_password_roundtrip():
    hashed = hash_password("s3cret!")
    assert verify_password("s3cret!", hashed)
    assert not verify_password("wrong", hashed)


def test_jwt_roundtrip():
    token = create_access_token("user-1", "k", ttl_days=1)
    assert decode_access_token(token, "k") == "user-1"
    assert decode_access_token(token, "other") is None
    assert decode_access_token("garbage", "k") is None


def test_vault_roundtrip():
    vault = CredentialVault(HubSettings(SECRET_KEY="abc").encryption_key)
    blob = vault.encrypt({"password": "p@ss", "n": 1})
    assert blob and "p@ss" not in blob
    assert vault.decrypt(blob) == {"password": "p@ss", "n": 1}
    assert vault.decrypt(None) == {}
    assert vault.decrypt("not-a-token") == {}
    assert vault.encrypt({}) is None


def test_settings_defaults_and_sia_accounts():
    settings = HubSettings(SECRET_KEY="x", HUB_SIA_ACCOUNTS="1234:home-a, abcd:home-b")
    assert settings.database_url.startswith("sqlite+aiosqlite")
    assert settings.sia_accounts == {"1234": "home-a", "ABCD": "home-b"}
    assert HubSettings(SECRET_KEY="x", DATABASE_URL="postgresql+asyncpg://u:p@h/db").database_url.startswith("postgresql")


def test_coerce_value():
    assert coerce_value(cap("switch", "bool", True), "on") is True
    assert coerce_value(cap("brightness", "int", True, min=0, max=100), "50") == 50
    with pytest.raises(ValueError):
        coerce_value(cap("brightness", "int", True, min=0, max=100), 150)
    with pytest.raises(ValueError):
        coerce_value(cap("mode", "enum", True, values=["a", "b"]), "c")
    assert coerce_value(cap("color", "color", True), {"h": 370, "s": 120, "v": -1}) == {"h": 10.0, "s": 100.0, "v": 0.0}


@pytest.mark.asyncio
async def test_event_bus_isolates_failures():
    bus = EventBus()
    seen = []

    async def bad(_):
        raise RuntimeError("boom")

    async def good(event):
        seen.append(event.type)

    bus.subscribe(bad)
    unsubscribe = bus.subscribe(good)
    await bus.publish(HubEvent("device.state"))
    assert seen == ["device.state"]
    unsubscribe()
    await bus.publish(HubEvent("device.state"))
    assert seen == ["device.state"]


@pytest.mark.asyncio
async def test_demo_adapter_pair_and_command():
    adapter = registry.get("demo")
    assert adapter is not None
    ctx = AdapterContext()
    result = await adapter.pair("virtual", {"prefix": "Test"}, ctx)
    assert len(result.devices) >= 10
    light = next(d for d in result.devices if d.category == "light")
    assert light.name.startswith("Test ")
    ref = DeviceRef(id="x", external_id=light.external_id, brand="demo", protocol="demo", category="light", state=light.state)
    partial = await adapter.send_command(ref, "brightness", 10, ctx)
    assert partial == {"brightness": 10}
    state = await adapter.refresh(ref, ctx)
    assert state.state["brightness"] == 10
    zone = next(d for d in result.devices if d.category == "alarm_zone")
    assert zone.parent_external_id == "demo-panel-1"


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get(f"{PREFIX}/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "demo" in body["adapters"]


@pytest.mark.asyncio
async def test_adapter_context_persists_rotated_credentials(hub_app, home):
    """``ctx.update_integration_credentials`` merges rotated tokens into ``Integration.credentials_enc``."""
    from app.hub.models import Integration  # pylint: disable=import-outside-toplevel

    runtime = hub_app.state.hub_runtime
    async with runtime.db.session() as session:
        integration = Integration(
            home_id=home["id"], brand="tuya", key="tuya_cloud:abc", name="Tuya", config={"region": "eu"},
            credentials_enc=runtime.vault.encrypt({"access_secret": "s3", "access_token": "old"}),
        )
        session.add(integration)
        await session.commit()
        integration_id = integration.id

    ctx = runtime.ctx_for("tuya")
    await ctx.update_integration_credentials(integration_id, {"access_token": "new", "refresh_token": "r1", "expires_at": 42})
    await ctx.update_integration_credentials(None, {"access_token": "ignored"})  # no integration -> no-op
    await ctx.update_integration_credentials("missing", {"access_token": "ignored"})  # unknown id -> no-op
    async with runtime.db.session() as session:
        stored = await session.get(Integration, integration_id)
        assert runtime.vault.decrypt(stored.credentials_enc) == {"access_secret": "s3", "access_token": "new", "refresh_token": "r1", "expires_at": 42}

    # Plain contexts (adapter unit tests) have no persistence hook and stay silent.
    await AdapterContext().update_integration_credentials(integration_id, {"access_token": "x"})
