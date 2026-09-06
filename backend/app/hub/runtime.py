"""Hub runtime: one object owning settings, database, event bus, vault and background services."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

from app.hub.adapters.base import AdapterContext
from app.hub.db import Database
from app.hub.events import EventBus
from app.hub.security import CredentialVault
from app.hub.settings import HubSettings, get_settings

logger = logging.getLogger("safer.hub.runtime")


class HubRuntime:
    """Process-wide hub state. Created by ``create_app``/``attach``; tests create their own."""

    def __init__(
        self,
        settings: Optional[HubSettings] = None,
        database_url: Optional[str] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        start_services: bool = True,
    ):
        self.settings = settings or get_settings()
        self.db = Database(database_url or self.settings.database_url)
        self.bus = EventBus()
        self.vault = CredentialVault(self.settings.encryption_key)
        self.transport = transport
        self.start_services = start_services
        self.started = False
        # Filled lazily by services to avoid import cycles
        self.services: Dict[str, Any] = {}
        self._contexts: Dict[str, AdapterContext] = {}

    # ------------------------------------------------------------------ adapters
    def ctx_for(self, brand_id: str) -> AdapterContext:
        """Adapter context bound to a brand (so pushed events know their brand)."""
        if brand_id not in self._contexts:

            async def _emit(event_type: str, external_id: str, payload: Dict[str, Any]) -> None:
                device_service = self.services.get("devices")
                if device_service is not None:
                    await device_service.handle_push(brand_id, external_id, event_type, payload)

            async def _update_credentials(integration_id: str, updates: Dict[str, Any]) -> None:
                from app.hub.models import Integration  # pylint: disable=import-outside-toplevel

                async with self.db.session() as session:
                    integration = await session.get(Integration, integration_id)
                    if integration is None:
                        return
                    merged = dict(self.vault.decrypt(integration.credentials_enc))
                    merged.update(updates)
                    integration.credentials_enc = self.vault.encrypt(merged)
                    await session.commit()

            self._contexts[brand_id] = AdapterContext(
                settings=self.settings,
                transport=self.transport,
                emit=_emit,
                logger=logging.getLogger(f"safer.hub.adapters.{brand_id}"),
                timeout=self.settings.HUB_HTTP_TIMEOUT,
                update_credentials=_update_credentials,
            )
        return self._contexts[brand_id]

    # ------------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        """Create tables and start background services (idempotent)."""
        if self.started:
            return
        await self.db.create_all()
        # Late imports: services import models/runtime
        from app.hub.services.device_service import DeviceService  # pylint: disable=import-outside-toplevel

        self.services.setdefault("devices", DeviceService(self))
        if self.start_services:
            await self._start_background()
        self.started = True
        logger.info("SafeR Hub runtime started (db=%s)", self.db.url.split("@")[-1])

    async def _start_background(self) -> None:
        try:
            from app.hub.automation.engine import AutomationEngine  # pylint: disable=import-outside-toplevel
            from app.hub.services.poller import Poller  # pylint: disable=import-outside-toplevel
            from app.hub.services.sia_receiver import SiaReceiver  # pylint: disable=import-outside-toplevel
            from app.hub.services.subscriptions import SubscriptionManager  # pylint: disable=import-outside-toplevel
        except ImportError as exc:  # pragma: no cover - only while services are being built
            logger.warning("Background services unavailable: %s", exc)
            return
        engine = AutomationEngine(self)
        await engine.start()
        self.services["automations"] = engine
        poller = Poller(self)
        await poller.start()
        self.services["poller"] = poller
        subs = SubscriptionManager(self)
        await subs.start()
        self.services["subscriptions"] = subs
        if self.settings.HUB_SIA_PORT:
            sia = SiaReceiver(self)
            await sia.start()
            self.services["sia"] = sia

    async def stop(self) -> None:
        """Stop services and dispose the database."""
        for name in ("sia", "subscriptions", "poller", "automations"):
            service = self.services.pop(name, None)
            if service is not None:
                try:
                    await service.stop()
                except Exception:  # pylint: disable=broad-except
                    logger.exception("Failed stopping %s", name)
        await self.db.dispose()
        self.started = False


_runtime: Optional[HubRuntime] = None


def get_runtime() -> HubRuntime:
    """Current runtime (raises if the hub was never configured)."""
    if _runtime is None:
        raise RuntimeError("SafeR Hub runtime is not configured; call create_app()/attach() first")
    return _runtime


def set_runtime(runtime: Optional[HubRuntime]) -> None:
    """Install the runtime used by API dependencies."""
    global _runtime  # pylint: disable=global-statement
    _runtime = runtime
