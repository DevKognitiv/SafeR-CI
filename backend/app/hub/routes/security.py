"""Security routes: home arm mode, alarm acknowledgement and SOS (paths declared in full under ``/homes``).

Every route requires membership of the home (``home_access`` -> 404 for outsiders); any member may arm,
disarm, acknowledge and raise an SOS, like the Tuya "Security" tab. The logic lives in
``services.security_service`` and ``services.sos`` so scenes/automations can reuse it.
"""
from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.hub.deps import HomeAccess, get_db, home_access, runtime_dep
from app.hub.models import SosAlert
from app.hub.runtime import HubRuntime
from app.hub.schemas import SecurityModeIn, SecurityOut, SosIn, SosOut
from app.hub.services.device_service import DeviceService
from app.hub.services.security_service import clear_alarm, security_state, set_security_mode
from app.hub.services.sos import raise_sos

logger = logging.getLogger("safer.hub.routes.security")

router = APIRouter()

__all__ = ["router", "SosStatusIn", "SOS_STATUSES"]

SOS_STATUSES = ("resolved", "false_alarm")
SOS_STATUS_TITLES = {"resolved": "SOS résolu", "false_alarm": "SOS: fausse alerte"}
DEFAULT_SOS_LIMIT = 20
MAX_SOS_LIMIT = 200


class SosStatusIn(BaseModel):
    """Body of ``PATCH /homes/{home_id}/sos/{sos_id}``."""

    status: str

    @field_validator("status")
    @classmethod
    def _status(cls, value: str) -> str:
        if value not in SOS_STATUSES:
            raise ValueError(f"status must be one of {list(SOS_STATUSES)}")
        return value


def _device_service(runtime: HubRuntime) -> DeviceService:
    service = runtime.services.get("devices")
    if service is None:
        service = DeviceService(runtime)
        runtime.services["devices"] = service
    return service


# ----------------------------------------------------------------------------- security state / mode
@router.get("/homes/{home_id}/security", response_model=SecurityOut)
async def get_security(access: HomeAccess = Depends(home_access), db: AsyncSession = Depends(get_db)) -> SecurityOut:
    """Current mode, alarm flag and the panels / zones / security sensors of the home."""
    return await security_state(db, access.home)


@router.post("/homes/{home_id}/security/mode", response_model=SecurityOut)
async def set_mode(
    body: SecurityModeIn,
    access: HomeAccess = Depends(home_access),
    db: AsyncSession = Depends(get_db),
    runtime: HubRuntime = Depends(runtime_dep),
) -> SecurityOut:
    """Arm / disarm the home; the mode is pushed to every alarm panel (best effort) and recorded."""
    home = await set_security_mode(runtime, db, access.home, body.mode, user_id=access.user.id, propagate=True)
    return await security_state(db, home)


@router.post("/homes/{home_id}/security/alarm/clear", response_model=SecurityOut)
async def clear_home_alarm(
    access: HomeAccess = Depends(home_access),
    db: AsyncSession = Depends(get_db),
    runtime: HubRuntime = Depends(runtime_dep),
) -> SecurityOut:
    """Acknowledge the alarm (software flag + hardware panels, best effort)."""
    home = await clear_alarm(runtime, db, access.home)
    return await security_state(db, home)


# ----------------------------------------------------------------------------- SOS
@router.post("/homes/{home_id}/sos", response_model=SosOut, status_code=status.HTTP_201_CREATED)
async def create_sos(
    body: SosIn,
    access: HomeAccess = Depends(home_access),
    db: AsyncSession = Depends(get_db),
    runtime: HubRuntime = Depends(runtime_dep),
) -> SosOut:
    """Raise an SOS: alarm message, ``sos.raised`` event, home alarm and forwarding to SafeR CI when configured."""
    alert = await raise_sos(runtime, db, access.home, access.user, body)
    return SosOut.model_validate(alert)


@router.get("/homes/{home_id}/sos", response_model=List[SosOut])
async def list_sos(
    limit: int = Query(default=DEFAULT_SOS_LIMIT, ge=1, le=MAX_SOS_LIMIT),
    access: HomeAccess = Depends(home_access),
    db: AsyncSession = Depends(get_db),
) -> List[SosOut]:
    """Recent SOS alerts of the home, newest first."""
    rows = await db.execute(
        select(SosAlert).where(SosAlert.home_id == access.home.id)
        .order_by(SosAlert.created_at.desc(), SosAlert.id.desc()).limit(limit)
    )
    return [SosOut.model_validate(alert) for alert in rows.scalars().all()]


@router.patch("/homes/{home_id}/sos/{sos_id}", response_model=SosOut)
async def update_sos(
    sos_id: str,
    body: SosStatusIn,
    access: HomeAccess = Depends(home_access),
    db: AsyncSession = Depends(get_db),
    runtime: HubRuntime = Depends(runtime_dep),
) -> SosOut:
    """Close an SOS (``resolved`` / ``false_alarm``). The last open SOS also releases an SOS-only alarm."""
    alert = await db.get(SosAlert, sos_id)
    if alert is None or alert.home_id != access.home.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SOS alert not found")
    home = access.home
    changed = alert.status != body.status
    alert.status = body.status
    await db.commit()
    if changed:
        await _device_service(runtime).create_message(
            db, home.id, "notice", SOS_STATUS_TITLES[body.status],
            f"L'alerte SOS du {alert.created_at:%d/%m/%Y %H:%M} a été clôturée.", severity="info", publish=True,
        )
        await db.commit()
    still_open = (
        await db.execute(select(SosAlert.id).where(SosAlert.home_id == home.id, SosAlert.status == "open").limit(1))
    ).first()
    if home.alarm_active and home.alarm_device_id is None and still_open is None:
        # The alarm was tripped by an SOS (no device involved) and no SOS remains open: release it.
        await clear_alarm(runtime, db, home)
    logger.info("SOS %s of home %s -> %s by %s", alert.id, home.id, body.status, access.user.email)
    return SosOut.model_validate(alert)
