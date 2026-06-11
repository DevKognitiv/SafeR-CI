"""
SafeR CI — Alerts API

Derives an alert feed from incidents. An "alert" is the lightweight,
notification-oriented projection of an incident that the web dashboard and
mobile app subscribe to.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.incident_service import IncidentService

router = APIRouter()


class AlertResponse(BaseModel):
    incident_id: str
    incident_type: str
    severity: str
    status: str
    commune: Optional[str] = None
    location_name: Optional[str] = None
    created_at: str


@router.get("/", response_model=List[AlertResponse])
async def list_alerts(
    status: Optional[str] = Query("open"),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Recent incidents, projected into alert feed entries."""
    service = IncidentService(db)
    incidents = await service.get_incidents(status=status, limit=limit)
    return [
        AlertResponse(
            incident_id=str(i.id),
            incident_type=i.incident_type,
            severity=i.severity,
            status=i.status,
            commune=i.commune,
            location_name=i.location_name,
            created_at=i.created_at.isoformat(),
        )
        for i in incidents
    ]
