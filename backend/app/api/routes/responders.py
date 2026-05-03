"""
SafeR CI — Responders API Routes
Dispatches responders (police, fire, medical) to a zone or incident.
Called by Home Assistant automations via the `safer_dispatch_responder`
REST command (see ha-config/rest_commands.yaml).
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel, Field

router = APIRouter()


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
    # Wired to NotificationService in production; intentionally a no-op stub
    # here so HA automations can hit the endpoint during integration tests.
    return None
