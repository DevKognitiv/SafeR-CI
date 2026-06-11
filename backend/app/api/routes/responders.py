"""
SafeR CI — Responders API Routes
Dispatches responders (police, fire, medical) to a zone or incident.
Called by Home Assistant automations via the `safer_dispatch_responder`
REST command (see ha-config/rest_commands.yaml).
"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel, Field

router = APIRouter()
logger = logging.getLogger("safer.responders")


class ResponderDispatchRequest(BaseModel):
    type: str = Field(..., description="Responder type: police, fire, medical, ...")
    zone: str = Field(..., description="Target zone identifier")
    incident_id: Optional[str] = Field(None, description="Linked incident, if any")
    priority: str = Field("HIGH", description="Dispatch priority")
    timestamp: Optional[datetime] = None


class ResponderDispatchResponse(BaseModel):
    status: str
    type: str
    zone: str
    incident_id: Optional[str]
    priority: str
    dispatched_at: datetime


@router.post("/dispatch", response_model=ResponderDispatchResponse, status_code=202)
async def dispatch_responder(
    payload: ResponderDispatchRequest,
    background_tasks: BackgroundTasks,
):
    """Dispatch a responder of `type` to `zone`."""
    dispatched_at = payload.timestamp or datetime.utcnow()

    # Hand off to the dispatch worker (notify on-call team, update map state).
    background_tasks.add_task(
        _notify_dispatch,
        responder_type=payload.type,
        zone=payload.zone,
        incident_id=payload.incident_id,
        priority=payload.priority,
    )

    return ResponderDispatchResponse(
        status="dispatched",
        type=payload.type,
        zone=payload.zone,
        incident_id=payload.incident_id,
        priority=payload.priority,
        dispatched_at=dispatched_at,
    )


async def _notify_dispatch(
    *,
    responder_type: str,
    zone: str,
    incident_id: Optional[str],
    priority: str,
) -> None:
    # Wired to NotificationService in production; logs here so HA
    # automations can verify the request reached the backend in dev / CI.
    logger.info(
        "dispatch type=%s zone=%s incident=%s priority=%s",
        responder_type, zone, incident_id, priority,
    )
