"""
SafeR CI — Broadcast API Routes
Broadcasts a critical alert to all configured zones / channels.
Called by Home Assistant via the `safer_broadcast_all` REST command.
"""
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel, Field

router = APIRouter()
logger = logging.getLogger("safer.broadcast")

ALLOWED_CHANNELS = {"push", "sms", "mqtt", "whatsapp", "email"}


class BroadcastRequest(BaseModel):
    message: str = Field(..., min_length=1)
    zone: str = Field("all", description="Target zone, or 'all'")
    channels: List[str] = Field(default_factory=lambda: ["push", "sms", "mqtt"])
    priority: str = Field("HIGH")
    timestamp: Optional[datetime] = None


class BroadcastResponse(BaseModel):
    status: str
    zone: str
    channels: List[str]
    priority: str
    broadcast_at: datetime


@router.post("/", response_model=BroadcastResponse, status_code=202)
async def broadcast_alert(
    payload: BroadcastRequest,
    background_tasks: BackgroundTasks,
):
    """Fan out `payload.message` to every channel in `payload.channels`."""
    channels = [c for c in payload.channels if c in ALLOWED_CHANNELS]
    broadcast_at = payload.timestamp or datetime.utcnow()

    background_tasks.add_task(
        _fanout_broadcast,
        message=payload.message,
        zone=payload.zone,
        channels=channels,
        priority=payload.priority,
    )

    return BroadcastResponse(
        status="queued",
        zone=payload.zone,
        channels=channels,
        priority=payload.priority,
        broadcast_at=broadcast_at,
    )


async def _fanout_broadcast(
    *,
    message: str,
    zone: str,
    channels: List[str],
    priority: str,
) -> None:
    # Production wires this to NotificationService.broadcast(); logs here so
    # HA can drive end-to-end integration tests against a fresh deploy.
    logger.info(
        "broadcast zone=%s channels=%s priority=%s message=%r",
        zone, channels, priority, message,
    )
