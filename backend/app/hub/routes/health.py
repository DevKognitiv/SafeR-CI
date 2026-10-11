"""Health endpoint and the app/hub version negotiation contract.

``GET /health`` answers without authentication and never blocks: the NTP probe (``timedatectl``) runs in a
background thread with a cached result, and a missing or failing ``timedatectl`` simply contributes nothing.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import time
from datetime import datetime, timezone
from typing import Callable, Dict, Optional

from fastapi import APIRouter

from app.hub import __version__
from app.hub.adapters.registry import registry
from app.hub.runtime import get_runtime
from app.hub.schemas import HealthOut
from app.hub.settings import HubSettings

logger = logging.getLogger("safer.hub.health")

router = APIRouter()

__all__ = ["router", "API_VERSION", "BUILD_EPOCH_FLOOR", "NtpProbe", "clock_synced", "hub_flags", "iso_utc", "utcnow"]

API_VERSION = "1"
# This build cannot predate its own code: a system clock earlier than this date is not synchronised (typically a
# Raspberry Pi without RTC after a power cut). Bump it with each release.
BUILD_EPOCH_FLOOR = datetime(2026, 10, 11, tzinfo=timezone.utc)
NTP_PROBE_TTL = 60.0  # seconds a timedatectl answer is reused
NTP_PROBE_TIMEOUT = 1.0


def utcnow() -> datetime:
    """Current UTC time (tests monkeypatch this to inject the clock)."""
    return datetime.now(timezone.utc)


def iso_utc(moment: datetime) -> str:
    """ISO-8601 with a ``Z`` suffix, second precision."""
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def query_timedatectl() -> Optional[bool]:
    """``NTPSynchronized`` from ``timedatectl show``: True/False, or None when unavailable (no systemd, no binary...)."""
    binary = shutil.which("timedatectl")
    if not binary:
        return None
    try:
        result = subprocess.run(
            [binary, "show", "-p", "NTPSynchronized", "--value"],
            capture_output=True, text=True, timeout=NTP_PROBE_TIMEOUT, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip().lower()
    if value == "yes":
        return True
    if value == "no":
        return False
    return None


class NtpProbe:
    """Cached, non-blocking NTP synchronisation signal.

    ``peek()`` returns the last known answer immediately and schedules a refresh in a worker thread when the
    cached value is older than ``NTP_PROBE_TTL``; ``refresh()`` awaits a fresh answer (tests).
    """

    def __init__(self, query: Callable[[], Optional[bool]] = query_timedatectl, ttl: float = NTP_PROBE_TTL):
        self.query = query
        self.ttl = ttl
        self.value: Optional[bool] = None
        self._checked_at: Optional[float] = None
        self._task: Optional["asyncio.Task[None]"] = None

    async def refresh(self) -> Optional[bool]:
        """Run the query now (in a thread) and cache its answer; failures count as "unknown"."""
        self._checked_at = time.monotonic()
        try:
            self.value = await asyncio.wait_for(asyncio.to_thread(self.query), NTP_PROBE_TIMEOUT + 1.0)
        except Exception:  # pylint: disable=broad-except
            logger.debug("NTP probe failed", exc_info=True)
            self.value = None
        return self.value

    def peek(self) -> Optional[bool]:
        """Cached answer; kicks off a background refresh when stale (never waits for it)."""
        now = time.monotonic()
        stale = self._checked_at is None or now - self._checked_at >= self.ttl
        if stale and (self._task is None or self._task.done()):
            self._checked_at = now
            self._task = asyncio.ensure_future(self.refresh())
        return self.value


ntp_probe = NtpProbe()


def clock_synced(now: datetime, ntp_synchronized: Optional[bool]) -> bool:
    """True when the clock is past the build floor and, if ``timedatectl`` answered, NTP reports synchronised."""
    return now >= BUILD_EPOCH_FLOOR and ntp_synchronized is not False


def hub_flags(settings: HubSettings) -> Dict[str, bool]:
    """Feature flags the app adapts to."""
    return {
        "sos_require_address": bool(settings.SAFER_SOS_REQUIRE_ADDRESS),
        "stream_credentials_to_clients": bool(settings.HUB_STREAM_CREDENTIALS_TO_CLIENTS),
        "demo_enabled": bool(settings.HUB_DEMO_ENABLED),
        "rate_limit_enabled": bool(settings.HUB_RATE_LIMIT_ENABLED),
        "open_registration": bool(settings.HUB_ALLOW_OPEN_REGISTRATION),
    }


@router.get("/health", response_model=HealthOut)
async def health() -> HealthOut:
    """Liveness, registered adapters and the version/flags/clock contract the app negotiates with."""
    runtime = get_runtime()
    settings = runtime.settings
    now = utcnow()
    return HealthOut(
        status="ok",
        version=__version__,
        adapters=registry.ids(),
        sia_receiver="sia" in runtime.services,
        hub_version=__version__,
        api_version=API_VERSION,
        min_app_version=settings.HUB_MIN_APP_VERSION,
        flags=hub_flags(settings),
        clock_synced=clock_synced(now, ntp_probe.peek()),
        server_time=iso_utc(now),
    )
