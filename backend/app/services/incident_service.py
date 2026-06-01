"""
SafeR CI — Incident service
Persistence and query logic for incidents, including PostGIS radius search.
"""
import uuid
from datetime import datetime
from typing import List, Optional

from geoalchemy2.elements import WKTElement
from geoalchemy2.functions import ST_DWithin
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.incident import Incident, IncidentStatus
from app.schemas.incident import IncidentCreate, IncidentUpdate


def _point(lat: float, lon: float) -> WKTElement:
    """Build a WGS84 geography point. PostGIS expects (lon lat) order."""
    return WKTElement(f"POINT({lon} {lat})", srid=4326)


class IncidentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_incident(self, data: IncidentCreate) -> Incident:
        incident = Incident(
            incident_type=data.incident_type.value,
            severity=data.severity.value,
            status=IncidentStatus.OPEN.value,
            location=_point(data.location_lat, data.location_lon),
            location_lat=data.location_lat,
            location_lon=data.location_lon,
            location_name=data.location_name,
            commune=data.commune,
            region=data.region,
            hub_id=data.hub_id,
            triggered_by=data.triggered_by,
            source=data.source,
            description=data.description,
        )
        self.db.add(incident)
        await self.db.commit()
        await self.db.refresh(incident)
        return incident

    async def get_incidents(
        self,
        *,
        incident_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Incident]:
        stmt = select(Incident)
        stmt = self._apply_filters(stmt, incident_type, status)
        stmt = stmt.order_by(Incident.created_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_incidents_near(
        self,
        *,
        lat: float,
        lon: float,
        radius_km: float = 5.0,
        incident_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Incident]:
        center = func.ST_GeogFromText(f"POINT({lon} {lat})")
        stmt = select(Incident).where(
            ST_DWithin(Incident.location, center, radius_km * 1000)
        )
        stmt = self._apply_filters(stmt, incident_type, status)
        stmt = stmt.order_by(Incident.created_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_incident(self, incident_id: str) -> Optional[Incident]:
        parsed = self._parse_uuid(incident_id)
        if parsed is None:
            return None
        result = await self.db.execute(
            select(Incident).where(Incident.id == parsed)
        )
        return result.scalar_one_or_none()

    async def update_incident(
        self, incident_id: str, update_data: IncidentUpdate
    ) -> Optional[Incident]:
        incident = await self.get_incident(incident_id)
        if incident is None:
            return None

        changes = update_data.model_dump(exclude_unset=True)
        for field, value in changes.items():
            if value is None:
                continue
            # Enum fields arrive as enum members; store their string value.
            setattr(incident, field, getattr(value, "value", value))

        if changes.get("status") == IncidentStatus.RESOLVED and not incident.resolved_at:
            incident.resolved_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(incident)
        return incident

    @staticmethod
    def _apply_filters(stmt, incident_type: Optional[str], status: Optional[str]):
        if incident_type:
            stmt = stmt.where(Incident.incident_type == incident_type)
        if status and status != "all":
            stmt = stmt.where(Incident.status == status)
        return stmt

    @staticmethod
    def _parse_uuid(value: str) -> Optional[uuid.UUID]:
        try:
            return uuid.UUID(str(value))
        except (ValueError, TypeError, AttributeError):
            return None
