"""
SafeR CI — FastAPI Backend
Main application entry point
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.api.routes import incidents, alerts, users, health
from app.core.config import settings
from app.core.database import init_db
from app.hub.app import attach as attach_hub, hub_lifespan


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle manager."""
    await init_db()
    async with hub_lifespan(app):
        yield


app = FastAPI(
    title="SafeR CI API",
    description="Safety & Emergency Response Platform for Côte d'Ivoire",
    version="0.1.0",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)

# Middleware
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health.router, tags=["health"])
app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
app.include_router(incidents.router, prefix="/api/v1/incidents", tags=["incidents"])
app.include_router(alerts.router, prefix="/api/v1/alerts", tags=["alerts"])

# SafeR Hub — multi-brand smart home & security API used by the SafeR mobile app
attach_hub(app, prefix="/api/v1/hub")
