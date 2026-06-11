"""
SafeR CI — Health & readiness endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

router = APIRouter()


@router.get("/")
async def root():
    return {"service": "SafeR CI API", "status": "ok"}


@router.get("/health")
async def health():
    """Liveness probe — does not touch the database."""
    return {"status": "ok"}


@router.get("/health/db")
async def health_db(db: AsyncSession = Depends(get_db)):
    """Readiness probe — verifies database connectivity."""
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - surface as 503
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return {"status": "ok", "database": "connected"}
