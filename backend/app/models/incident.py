"""
SafeR CI — Incident Model
Represents a safety incident reported by a hub or citizen
"""
from datetime import datetime
from enum import Enum
from sqlalchemy import Column, String, Float, DateTime, Boolean, Text, Index
from sqlalchemy.dialects.postgresql import UUID
from geoalchemy2 import Geography
import uuid

from app.core.database import Base


class IncidentType(str, Enum):
    PANIC = "panic"
    FIRE = "fire"
    FLOOD = "flood"
    ACCIDENT = "accident"
    CRIME = "crime"
    MEDICAL = "medical"
    OTHER = "other"


class IncidentSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentStatus(str, Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESPONDING = "responding"
    RESOLVED = "resolved"
    FALSE_ALARM = "false_alarm"


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_type = Column(String(50), nullable=False, index=True)
    severity = Column(String(20), nullable=False, default=IncidentSeverity.MEDIUM)
    status = Column(String(30), nullable=False, default=IncidentStatus.OPEN)

    # Location (PostGIS geography point)
    location = Column(Geography(geometry_type="POINT", srid=4326))
    location_lat = Column(Float, nullable=False)
    location_lon = Column(Float, nullable=False)
    location_name = Column(String(255))  # Commune/quartier name
    commune = Column(String(100), index=True)   # e.g., Cocody, Yopougon
    region = Column(String(100), index=True)    # e.g., Abidjan, Bouaké

    # Source
    hub_id = Column(String(100), index=True)   # HA node that triggered
    triggered_by = Column(String(255))          # entity_id or user_id
    source = Column(String(50), default="ha_node")  # ha_node, mobile_app, sms, api

    # Details
    description = Column(Text)
    photo_url = Column(String(500))

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at = Column(DateTime)

    # Responder
    responder_id = Column(String(100))
    is_verified = Column(Boolean, default=False)
    alert_sent = Column(Boolean, default=False)

    __table_args__ = (
        Index("idx_incident_location", "location_lat", "location_lon"),
        Index("idx_incident_created", "created_at"),
        Index("idx_incident_status_type", "status", "incident_type"),
    )
