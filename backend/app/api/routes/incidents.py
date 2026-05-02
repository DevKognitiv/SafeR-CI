"""
SafeR CI — Incidents API Routes
Handles incident creation from HA nodes, mobile app, and SMS gateway
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.incident import IncidentCreate, IncidentResponse, IncidentUpdate
from app.services.incident_service import IncidentService
from app.services.notification_service import NotificationService

router = APIRouter()


@router.post("/", response_model=IncidentResponse, status_code=201)
async def create_incident(
    incident_data: IncidentCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new incident.
    Called by: HA node webhooks, mobile app, SMS gateway.
    """
    service = IncidentService(db)
    incident = await service.create_incident(incident_data)

    # Send alerts asynchronously (don't block the response)
    notification_service = NotificationService()
    background_tasks.add_task(
        notification_service.broadcast_incident_alert,
        incident=incident,
    )

    return incident


@router.get("/", response_model=List[IncidentResponse])
async def get_incidents(
    lat: Optional[float] = Query(None, description="Center latitude"),
    lon: Optional[float] = Query(None, description="Center longitude"),
    radius_km: float = Query(5.0, description="Search radius in km"),
    incident_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None, default="open"),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
):
    """
    Get incidents, optionally filtered by location radius.
    Used by mobile app map view.
    """
    service = IncidentService(db)

    if lat and lon:
        incidents = await service.get_incidents_near(
            lat=lat, lon=lon, radius_km=radius_km,
            incident_type=incident_type, status=status,
            limit=limit, offset=offset
        )
    else:
        incidents = await service.get_incidents(
            incident_type=incident_type, status=status,
            limit=limit, offset=offset
        )

    return incidents


@router.get("/{incident_id}", response_model=IncidentResponse)
async def get_incident(incident_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single incident by ID."""
    service = IncidentService(db)
    incident = await service.get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


@router.patch("/{incident_id}", response_model=IncidentResponse)
async def update_incident(
    incident_id: str,
    update_data: IncidentUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update incident status (for responders)."""
    service = IncidentService(db)
    incident = await service.update_incident(incident_id, update_data)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


@router.post("/webhook/ha")
async def ha_webhook(
    payload: dict,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Webhook endpoint called by Home Assistant automations.
    Translates HA event data to SafeR incident format.
    """
    service = IncidentService(db)
    incident_data = IncidentCreate(
        incident_type=payload.get("incident_type", "other"),
        severity=payload.get("severity", "medium"),
        location_lat=float(payload.get("location_lat", 5.3600)),
        location_lon=float(payload.get("location_lon", -4.0083)),
        hub_id=payload.get("hub_id"),
        triggered_by=payload.get("triggered_by"),
        source="ha_node",
    )
    incident = await service.create_incident(incident_data)

    notification_service = NotificationService()
    background_tasks.add_task(
        notification_service.broadcast_incident_alert,
        incident=incident,
    )

    return {"status": "ok", "incident_id": str(incident.id)}
