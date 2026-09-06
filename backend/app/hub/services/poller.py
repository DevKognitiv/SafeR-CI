"""Poller: periodically refreshes devices whose brand adapter has no push channel.

Every ``HUB_POLL_INTERVAL`` seconds each device of a polled brand (``adapter.supports_push`` is False) is
refreshed through ``DeviceService.refresh`` in its own database session, at most ``concurrency`` devices at a
time. Failures are logged and never abort the cycle; an ``unreachable`` adapter error marks the device offline
(``DeviceService.refresh`` takes care of that and of the ``online`` event / message).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import select
from sqlalchemy.pool import StaticPool

from app.hub.adapters.base import AdapterError
from app.hub.adapters.registry import registry
from app.hub.models import Device, utcnow
from app.hub.services.device_service import DeviceService

logger = logging.getLogger("safer.hub.poller")

DEFAULT_CONCURRENCY = 5


class Poller:
    """Background task refreshing polled brands. ``poll_once`` runs a single cycle (used by tests)."""

    def __init__(self, runtime: Any, interval: Optional[float] = None, concurrency: Optional[int] = None):
        self.runtime = runtime
        self.interval = float(interval if interval is not None else runtime.settings.HUB_POLL_INTERVAL)
        self.concurrency = max(1, int(concurrency)) if concurrency else self._default_concurrency()
        self.runs = 0
        self.last_run_at: Optional[datetime] = None
        self.last_refreshed = 0
        self._task: Optional["asyncio.Task[None]"] = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ configuration
    def _default_concurrency(self) -> int:
        """5 parallel refreshes, except on a single shared connection (in-memory SQLite) that cannot
        interleave transactions safely: there refreshes run one after the other."""
        engine = getattr(self.runtime.db, "engine", None)
        pool = getattr(engine, "pool", None)
        if pool is not None and isinstance(pool, StaticPool):
            return 1
        return DEFAULT_CONCURRENCY

    def _service(self) -> DeviceService:
        service = self.runtime.services.get("devices")
        if service is None:
            service = DeviceService(self.runtime)
            self.runtime.services["devices"] = service
        return service

    @staticmethod
    def polled_brands() -> List[str]:
        """Brand ids whose adapter has no push channel."""
        return [adapter.brand_id for adapter in registry.all() if not adapter.supports_push]

    @property
    def running(self) -> bool:
        """True while the background loop is alive."""
        return self._task is not None and not self._task.done()

    # ------------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        """Start the background loop (no-op when already running or when the interval is <= 0)."""
        if self.running:
            return
        if self.interval <= 0:
            logger.info("Poller disabled (HUB_POLL_INTERVAL=%s)", self.interval)
            return
        self._task = asyncio.create_task(self._run(), name="safer-hub-poller")
        logger.info("Poller started: every %.0fs, concurrency %d, brands %s", self.interval, self.concurrency, self.polled_brands())

    async def stop(self) -> None:
        """Cancel the background loop and wait for it."""
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:  # pylint: disable=broad-except
            logger.exception("Poller loop ended with an error")
        logger.info("Poller stopped after %d cycle(s)", self.runs)

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self.interval)
            try:
                await self.poll_once()
            except Exception:  # pylint: disable=broad-except
                logger.exception("Polling cycle failed")

    # ------------------------------------------------------------------ one cycle
    async def poll_once(self) -> int:
        """Refresh every device of every polled brand once. Returns the number of successful refreshes."""
        async with self._lock:
            brands = self.polled_brands()
            refreshed = 0
            if brands:
                async with self.runtime.db.session() as session:
                    device_ids = list(
                        (
                            await session.execute(
                                select(Device.id).where(Device.brand.in_(brands)).order_by(Device.created_at)
                            )
                        ).scalars().all()
                    )
                if device_ids:
                    semaphore = asyncio.Semaphore(self.concurrency)
                    results = await asyncio.gather(*(self._refresh_one(device_id, semaphore) for device_id in device_ids))
                    refreshed = sum(1 for ok in results if ok)
                    logger.debug("Poll cycle: %d/%d device(s) refreshed", refreshed, len(device_ids))
            self.runs += 1
            self.last_run_at = utcnow()
            self.last_refreshed = refreshed
            return refreshed

    async def _refresh_one(self, device_id: str, semaphore: asyncio.Semaphore) -> bool:
        """Refresh a single device in its own session; True on success."""
        async with semaphore:
            async with self.runtime.db.session() as session:
                device = await session.get(Device, device_id)
                if device is None:  # removed while the cycle was running
                    return False
                try:
                    await self._service().refresh(session, device)
                    return True
                except AdapterError as exc:
                    logger.warning(
                        "Poll %s/%s (%s) failed: %s [%s]", device.brand, device.external_id, device.name, exc.message, exc.code
                    )
                except Exception:  # pylint: disable=broad-except
                    logger.exception("Poll %s/%s (%s) crashed", device.brand, device.external_id, device.name)
                return False
