"""
SafeR CI — Sensors API Routes
Receives sensor state updates from Home Assistant. Called by the
`safer_sensor_update` REST command whenever a tracked HA entity changes.
"""
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter()


class SensorUpdate(BaseModel):
    entity_id: str = Field(..., description="Home Assistant entity_id")
    state: str = Field(..., description="New state value as a string")
    timestamp: Optional[datetime] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)


class SensorUpdateResponse(BaseModel):
    status: str
    entity_id: str
    state: str
    received_at: datetime


@router.post("/update", response_model=SensorUpdateResponse, status_code=202)
async def update_sensor(payload: SensorUpdate):
    """Persist the latest reading for `entity_id` and forward to subscribers."""
    received_at = payload.timestamp or datetime.utcnow()

    # The hot path here is intentionally tiny: HA fires this many times per
    # minute. Heavy lifting (persistence, downstream MQTT fan-out) is done
    # by the sensor ingestion worker.
    await _ingest_sensor(
        entity_id=payload.entity_id,
        state=payload.state,
        attributes=payload.attributes,
        received_at=received_at,
    )

    return SensorUpdateResponse(
        status="accepted",
        entity_id=payload.entity_id,
        state=payload.state,
        received_at=received_at,
    )


async def _ingest_sensor(
    *,
    entity_id: str,
    state: str,
    attributes: Dict[str, Any],
    received_at: datetime,
) -> None:
    # Hook for SensorService.ingest(); stub for now.
    return None
