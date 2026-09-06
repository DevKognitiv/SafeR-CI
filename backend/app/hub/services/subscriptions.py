"""Push subscriptions: keeps ``adapter.subscribe()`` alive for every brand that supports push.

For each brand whose adapter implements ``subscribe`` the manager builds ``DeviceRef``s (decrypted credentials,
integration config, parent host) for all devices of that brand and hands them to the adapter, keeping the
returned unsubscribe callable. Refs are handed to the adapter per home (``ctx_for(brand, home_id)``) so pushed
events are applied to the right home only. ``device.added`` / ``device.updated`` / ``device.removed`` bus events
schedule a debounced ``resync`` that only re-subscribes brands whose device set *or* connection data (host,
credentials, integration...) actually changed. ``stop()`` tears everything down.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, FrozenSet, List, Optional

from sqlalchemy import select

from app.hub import events as ev
from app.hub.adapters.base import AdapterError, BrandAdapter, DeviceRef, Unsubscribe
from app.hub.adapters.registry import registry
from app.hub.models import Device, utcnow
from app.hub.services.device_service import DeviceService

logger = logging.getLogger("safer.hub.subscriptions")

DEFAULT_DEBOUNCE = 2.0
UNSUBSCRIBE_TIMEOUT = 10.0


@dataclass
class Subscription:
    """A live subscription for one brand."""

    brand: str
    device_ids: FrozenSet[str]
    unsubscribe: Optional[Unsubscribe]
    created_at: datetime
    fingerprint: FrozenSet[str] = field(default_factory=frozenset)


def ref_fingerprint(ref: DeviceRef) -> str:
    """Digest of everything an adapter binds at subscribe time (no plaintext credentials are kept)."""
    material = {
        "id": ref.id, "home": ref.home_id, "integration": ref.integration_id, "parent": ref.parent_external_id,
        "config": ref.config, "credentials": ref.credentials, "integration_config": ref.integration_config,
        "integration_credentials": ref.integration_credentials,
    }
    return hashlib.sha256(json.dumps(material, sort_keys=True, default=str).encode("utf-8")).hexdigest()


class SubscriptionManager:
    """Owns push subscriptions for all push-capable brands and keeps them in sync with the device table."""

    def __init__(self, runtime: Any, debounce: float = DEFAULT_DEBOUNCE):
        self.runtime = runtime
        self.debounce = max(0.0, float(debounce))
        self.resyncs = 0
        self._subscriptions: Dict[str, Subscription] = {}
        self._bus_unsubscribe = None
        self._resync_task: Optional["asyncio.Task[None]"] = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ helpers
    def _service(self) -> DeviceService:
        service = self.runtime.services.get("devices")
        if service is None:
            service = DeviceService(self.runtime)
            self.runtime.services["devices"] = service
        return service

    @staticmethod
    def push_adapters() -> List[BrandAdapter]:
        """Adapters implementing ``subscribe``."""
        return [adapter for adapter in registry.all() if adapter.supports_push]

    @property
    def subscribed_brands(self) -> List[str]:
        """Brands with a live subscription."""
        return sorted(self._subscriptions)

    def subscription(self, brand: str) -> Optional[Subscription]:
        """Live subscription of a brand (or None)."""
        return self._subscriptions.get(brand)

    @property
    def resync_pending(self) -> bool:
        """True while a debounced resync is scheduled or running (tests wait on it to settle)."""
        return self._resync_task is not None and not self._resync_task.done()

    async def _refs_for(self, brand: str) -> List[DeviceRef]:
        service = self._service()
        async with self.runtime.db.session() as session:
            devices = (
                await session.execute(select(Device).where(Device.brand == brand).order_by(Device.created_at))
            ).scalars().all()
            refs: List[DeviceRef] = []
            for device in devices:
                try:
                    refs.append(await service.ref_for(session, device))
                except Exception:  # pylint: disable=broad-except
                    logger.exception("Cannot build a reference for %s/%s", brand, device.external_id)
            return refs

    # ------------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        """Subscribe to the bus and open every push subscription."""
        if self._bus_unsubscribe is None:
            self._bus_unsubscribe = self.runtime.bus.subscribe(self._on_event)
        opened = await self.resync(force=True)
        logger.info("Subscription manager started (%d brand(s) subscribed: %s)", opened, self.subscribed_brands)

    async def stop(self) -> None:
        """Stop listening to the bus, cancel a pending resync and call every unsubscribe."""
        if self._bus_unsubscribe is not None:
            self._bus_unsubscribe()
            self._bus_unsubscribe = None
        task, self._resync_task = self._resync_task, None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # pylint: disable=broad-except
                pass
        async with self._lock:
            for brand in list(self._subscriptions):
                await self._teardown(brand)
        logger.info("Subscription manager stopped")

    async def resync(self, force: bool = False) -> int:
        """Bring subscriptions in line with the device table.

        Brands whose device set is unchanged are left alone unless ``force`` is set. Returns the number of
        brands (re)subscribed.
        """
        async with self._lock:
            changed = 0
            push_brands = set()
            for adapter in self.push_adapters():
                brand = adapter.brand_id
                push_brands.add(brand)
                refs = await self._refs_for(brand)
                wanted = frozenset(ref.id for ref in refs)
                fingerprint = frozenset(ref_fingerprint(ref) for ref in refs)
                current = self._subscriptions.get(brand)
                if current is not None and not force and current.fingerprint == fingerprint:
                    continue
                if current is not None:
                    await self._teardown(brand)
                if not refs:
                    continue
                unsubscribe = await self._subscribe_per_home(adapter, refs)
                if unsubscribe is None:
                    continue
                self._subscriptions[brand] = Subscription(
                    brand=brand, device_ids=wanted, unsubscribe=unsubscribe, created_at=utcnow(), fingerprint=fingerprint,
                )
                changed += 1
                logger.info("Subscribed %s for %d device(s)", brand, len(refs))
            # Adapters that disappeared from the registry (hot reload) lose their subscription
            for brand in [b for b in self._subscriptions if b not in push_brands]:
                await self._teardown(brand)
            self.resyncs += 1
            return changed

    async def _subscribe_per_home(self, adapter: BrandAdapter, refs: List[DeviceRef]) -> Optional[Unsubscribe]:
        """Call ``adapter.subscribe`` once per home with a home-bound context; returns a combined unsubscribe."""
        brand = adapter.brand_id
        groups: Dict[Optional[str], List[DeviceRef]] = {}
        for ref in refs:
            groups.setdefault(ref.home_id, []).append(ref)
        unsubscribes: List[Unsubscribe] = []
        for home_id, group in groups.items():
            try:
                unsubscribe = await adapter.subscribe(group, self.runtime.ctx_for(brand, home_id))
            except AdapterError as exc:
                logger.warning("Subscribe %s (home %s) failed: %s [%s]", brand, home_id, exc.message, exc.code)
                continue
            except Exception:  # pylint: disable=broad-except
                logger.exception("Subscribe %s (home %s) crashed", brand, home_id)
                continue
            if unsubscribe is not None:
                unsubscribes.append(unsubscribe)
        if not unsubscribes:
            return None

        async def _unsubscribe_all() -> None:
            for unsubscribe in unsubscribes:
                await unsubscribe()

        return _unsubscribe_all

    async def _teardown(self, brand: str) -> None:
        subscription = self._subscriptions.pop(brand, None)
        if subscription is None or subscription.unsubscribe is None:
            return
        try:
            await asyncio.wait_for(subscription.unsubscribe(), timeout=UNSUBSCRIBE_TIMEOUT)
            logger.info("Unsubscribed %s", brand)
        except asyncio.TimeoutError:
            logger.warning("Unsubscribe %s timed out after %.0fs", brand, UNSUBSCRIBE_TIMEOUT)
        except asyncio.CancelledError:
            raise
        except Exception:  # pylint: disable=broad-except
            logger.exception("Unsubscribe %s failed", brand)

    # ------------------------------------------------------------------ bus
    async def _on_event(self, event: ev.HubEvent) -> None:
        if event.type not in (ev.DEVICE_ADDED, ev.DEVICE_UPDATED, ev.DEVICE_REMOVED):
            return
        if event.type in (ev.DEVICE_ADDED, ev.DEVICE_UPDATED):
            brand = (event.payload.get("device") or {}).get("brand")
            adapter = registry.get(brand) if brand else None
            if adapter is not None and not adapter.supports_push:
                return  # a polled brand: nothing to resubscribe
        self.schedule_resync()

    def schedule_resync(self) -> None:
        """Run ``resync`` after the debounce delay, restarting the timer on every call."""
        if self._resync_task is not None and not self._resync_task.done():
            self._resync_task.cancel()
        self._resync_task = asyncio.create_task(self._delayed_resync(), name="safer-hub-subscriptions-resync")

    async def _delayed_resync(self) -> None:
        try:
            if self.debounce > 0:
                await asyncio.sleep(self.debounce)
            await self.resync()
        except asyncio.CancelledError:
            raise
        except Exception:  # pylint: disable=broad-except
            logger.exception("Subscription resync failed")
