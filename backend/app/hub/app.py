"""Hub FastAPI application factory + integration helpers for the main SafeR API."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

import httpx
from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.hub import __version__
from app.hub import adapters  # noqa: F401  pylint: disable=unused-import  (registers adapters)
from app.hub.adapters.base import AdapterError
from app.hub.runtime import HubRuntime, get_runtime, set_runtime
from app.hub.settings import HubSettings

logger = logging.getLogger("safer.hub")

ADAPTER_ERROR_STATUS = {
    "invalid_input": 400,
    "auth_failed": 401,
    "not_found": 404,
    "unsupported": 501,
    "unreachable": 502,
}


def build_router() -> APIRouter:
    """Assemble every hub route module under one router."""
    from app.hub.routes import (  # pylint: disable=import-outside-toplevel
        auth, devices, health, homes, messages, onboarding, scenes, security, webhooks, ws,
    )

    router = APIRouter()
    router.include_router(health.router, tags=["hub:health"])
    router.include_router(auth.router, prefix="/auth", tags=["hub:auth"])
    router.include_router(homes.router, tags=["hub:homes"])
    router.include_router(devices.router, tags=["hub:devices"])
    router.include_router(onboarding.router, tags=["hub:onboarding"])
    router.include_router(scenes.router, tags=["hub:scenes"])
    router.include_router(security.router, tags=["hub:security"])
    router.include_router(messages.router, tags=["hub:messages"])
    router.include_router(webhooks.router, prefix="/webhooks", tags=["hub:webhooks"])
    router.include_router(ws.router, tags=["hub:realtime"])
    return router


async def adapter_error_handler(_: Request, exc: AdapterError) -> JSONResponse:
    """Map adapter errors to HTTP statuses."""
    return JSONResponse(status_code=ADAPTER_ERROR_STATUS.get(exc.code, 400), content={"detail": exc.message, "code": exc.code})


def install_error_handlers(app: FastAPI) -> None:
    """Register hub exception handlers on an app."""
    app.add_exception_handler(AdapterError, adapter_error_handler)


@asynccontextmanager
async def hub_lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Start/stop the current runtime (compose into the host app's lifespan)."""
    runtime = get_runtime()
    await runtime.start()
    try:
        yield
    finally:
        await runtime.stop()


def create_app(
    settings: Optional[HubSettings] = None,
    database_url: Optional[str] = None,
    transport: Optional[httpx.AsyncBaseTransport] = None,
    start_services: bool = True,
    prefix: str = "/api/v1/hub",
) -> FastAPI:
    """Standalone hub application (also used by tests)."""
    runtime = HubRuntime(settings=settings, database_url=database_url, transport=transport, start_services=start_services)
    set_runtime(runtime)
    app = FastAPI(title="SafeR Hub API", version=__version__, lifespan=hub_lifespan,
                  description="Multi-brand smart home & security hub for the SafeR app")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
    install_error_handlers(app)
    app.include_router(build_router(), prefix=prefix)
    app.state.hub_runtime = runtime
    return app


def attach(app: FastAPI, prefix: str = "/api/v1/hub", settings: Optional[HubSettings] = None) -> HubRuntime:
    """Mount the hub inside the main SafeR API. Compose ``hub_lifespan`` into the host lifespan."""
    runtime = HubRuntime(settings=settings)
    set_runtime(runtime)
    install_error_handlers(app)
    app.include_router(build_router(), prefix=prefix)
    app.state.hub_runtime = runtime
    return runtime


app = create_app()
