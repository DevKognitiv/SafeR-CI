"""
SafeR CI — Incident schemas
Pydantic request/response models for the incidents API.
"""
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.incident import (
    IncidentSeverity,
    IncidentStatus,
    IncidentType,
)


class IncidentBase(BaseModel):
    incident_type: IncidentType = IncidentType.OTHER
    severity: IncidentSeverity = IncidentSeverity.MEDIUM
    location_lat: float = Field(..., ge=-90, le=90)
    location_lon: float = Field(..., ge=-180, le=180)
    location_name: Optional[str] = None
    commune: Optional[str] = None
    region: Optional[str] = None
    description: Optional[str] = None


class IncidentCreate(IncidentBase):
    hub_id: Optional[str] = None
    triggered_by: Optional[str] = None
    source: str = "api"


class IncidentUpdate(BaseModel):
    status: Optional[IncidentStatus] = None
    severity: Optional[IncidentSeverity] = None
    responder_id: Optional[str] = None
    is_verified: Optional[bool] = None
    description: Optional[str] = None
    resolved_at: Optional[datetime] = None


class IncidentResponse(IncidentBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: IncidentStatus
    hub_id: Optional[str] = None
    triggered_by: Optional[str] = None
    source: str
    responder_id: Optional[str] = None
    is_verified: bool = False
    created_at: datetime
    updated_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
