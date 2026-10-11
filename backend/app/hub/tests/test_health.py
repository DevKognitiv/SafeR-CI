"""``GET /health`` version negotiation contract: versions, flags, clock_synced (injected clock) and server_time."""
from __future__ import annotations

import re
import subprocess
from datetime import datetime, timedelta, timezone

import httpx

from app.hub import __version__
from app.hub.app import create_app
from app.hub.routes import health
from app.hub.runtime import set_runtime
from app.hub.tests.conftest import PREFIX, make_settings

ISO_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


async def test_health_contract(client, monkeypatch):
    probe = health.NtpProbe(query=lambda: None)
    monkeypatch.setattr(health, "ntp_probe", probe)
    response = await client.get(f"{PREFIX}/health")
    assert response.status_code == 200, response.text
    body = response.json()
    # legacy fields
    assert body["status"] == "ok" and body["version"] == __version__
    assert "demo" in body["adapters"] and body["sia_receiver"] is False and "light" in body["categories"]
    # negotiation contract
    assert body["hub_version"] == __version__ and body["api_version"] == "1" and body["min_app_version"] == "0.2.0"
    assert body["flags"] == {
        "sos_require_address": False, "stream_credentials_to_clients": False, "demo_enabled": True,
        "rate_limit_enabled": True, "open_registration": True,
    }
    assert body["clock_synced"] is True
    assert ISO_UTC.match(body["server_time"]), body["server_time"]
    server_time = datetime.strptime(body["server_time"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    assert abs(datetime.now(timezone.utc) - server_time) < timedelta(seconds=5)


async def test_health_flags_follow_settings():
    app = create_app(
        settings=make_settings(
            SAFER_SOS_REQUIRE_ADDRESS=True, HUB_STREAM_CREDENTIALS_TO_CLIENTS=True, HUB_DEMO_ENABLED=False,
            HUB_RATE_LIMIT_ENABLED=False, HUB_ALLOW_OPEN_REGISTRATION=False, HUB_MIN_APP_VERSION="0.3.1",
        ),
        database_url="sqlite+aiosqlite://", start_services=False,
    )
    runtime = app.state.hub_runtime
    await runtime.start()
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://hub") as http:
            body = (await http.get(f"{PREFIX}/health")).json()
    finally:
        await runtime.stop()
        set_runtime(None)
    assert body["min_app_version"] == "0.3.1"
    assert body["flags"] == {
        "sos_require_address": True, "stream_credentials_to_clients": True, "demo_enabled": False,
        "rate_limit_enabled": False, "open_registration": False,
    }


async def test_health_reports_unsynced_clock(client, monkeypatch):
    """A Raspberry Pi without RTC boots in the past after a power cut: the hub must say so."""
    monkeypatch.setattr(health, "ntp_probe", health.NtpProbe(query=lambda: None))
    monkeypatch.setattr(health, "utcnow", lambda: datetime(2020, 1, 1, 8, 30, tzinfo=timezone.utc))
    body = (await client.get(f"{PREFIX}/health")).json()
    assert body["clock_synced"] is False
    assert body["server_time"] == "2020-01-01T08:30:00Z"
    # one second before the floor is unsynced, the floor itself is fine
    monkeypatch.setattr(health, "utcnow", lambda: health.BUILD_EPOCH_FLOOR - timedelta(seconds=1))
    assert (await client.get(f"{PREFIX}/health")).json()["clock_synced"] is False
    monkeypatch.setattr(health, "utcnow", lambda: health.BUILD_EPOCH_FLOOR)
    assert (await client.get(f"{PREFIX}/health")).json()["clock_synced"] is True


async def test_health_uses_timedatectl_as_additional_signal(client, monkeypatch):
    for answer, expected in ((True, True), (None, True), (False, False)):
        probe = health.NtpProbe(query=lambda answer=answer: answer)
        await probe.refresh()
        monkeypatch.setattr(health, "ntp_probe", probe)
        assert (await client.get(f"{PREFIX}/health")).json()["clock_synced"] is expected, answer
    # NTP synchronised but the clock is before the floor: still unsynced
    probe = health.NtpProbe(query=lambda: True)
    await probe.refresh()
    monkeypatch.setattr(health, "ntp_probe", probe)
    monkeypatch.setattr(health, "utcnow", lambda: datetime(2019, 6, 1, tzinfo=timezone.utc))
    assert (await client.get(f"{PREFIX}/health")).json()["clock_synced"] is False


async def test_ntp_probe_never_blocks_or_raises():
    def exploding() -> bool:
        raise RuntimeError("no dbus")

    probe = health.NtpProbe(query=exploding, ttl=0.0)
    assert probe.peek() is None  # first call schedules the refresh and answers immediately
    assert await probe.refresh() is None
    slow = health.NtpProbe(query=lambda: True)
    assert slow.peek() is None
    await slow.refresh()
    assert slow.peek() is True


def test_query_timedatectl_handles_missing_binary_and_failures(monkeypatch):
    monkeypatch.setattr(health.shutil, "which", lambda name: None)
    assert health.query_timedatectl() is None
    monkeypatch.setattr(health.shutil, "which", lambda name: "/usr/bin/timedatectl")

    def failing_run(*args, **kwargs):
        raise OSError("cannot execute")

    monkeypatch.setattr(health.subprocess, "run", failing_run)
    assert health.query_timedatectl() is None
    for stdout, code, expected in (("yes\n", 0, True), ("no\n", 0, False), ("", 1, None), ("maybe", 0, None)):
        monkeypatch.setattr(
            health.subprocess, "run",
            lambda *a, stdout=stdout, code=code, **k: subprocess.CompletedProcess(a, code, stdout=stdout, stderr=""),
        )
        assert health.query_timedatectl() is expected, (stdout, code)


def test_clock_synced_pure_function():
    past = health.BUILD_EPOCH_FLOOR - timedelta(days=1)
    future = health.BUILD_EPOCH_FLOOR + timedelta(days=1)
    assert health.clock_synced(future, None) is True
    assert health.clock_synced(future, True) is True
    assert health.clock_synced(future, False) is False
    assert health.clock_synced(past, True) is False
    assert health.iso_utc(datetime(2026, 10, 11, 12, 0, 5, 123456, tzinfo=timezone.utc)) == "2026-10-11T12:00:05Z"
