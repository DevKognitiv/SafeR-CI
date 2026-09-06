"""SQLAlchemy models for the SafeR Hub (portable: SQLite + PostgreSQL)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.hub.db import Base


def new_id() -> str:
    """UUID4 string primary key."""
    return str(uuid.uuid4())


def utcnow() -> datetime:
    """Naive UTC timestamp (portable across SQLite/PostgreSQL)."""
    return datetime.utcnow()


class User(Base):
    """Hub account (email + password)."""

    __tablename__ = "hub_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    phone: Mapped[Optional[str]] = mapped_column(String(40))
    locale: Mapped[str] = mapped_column(String(10), default="fr")
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    memberships: Mapped[List["HomeMember"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class PushToken(Base):
    """Mobile push token registered by a user."""

    __tablename__ = "hub_push_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("hub_users.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(20), default="android")
    token: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class Home(Base):
    """A home (Tuya "family") containing rooms, members and devices."""

    __tablename__ = "hub_homes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    lat: Mapped[Optional[float]] = mapped_column(Float)
    lon: Mapped[Optional[float]] = mapped_column(Float)
    address: Mapped[Optional[str]] = mapped_column(String(255))
    security_mode: Mapped[str] = mapped_column(String(20), default="disarmed", nullable=False)
    alarm_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    alarm_device_id: Mapped[Optional[str]] = mapped_column(String(36))
    security_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_by: Mapped[Optional[str]] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    members: Mapped[List["HomeMember"]] = relationship(back_populates="home", cascade="all, delete-orphan")
    rooms: Mapped[List["Room"]] = relationship(
        back_populates="home", cascade="all, delete-orphan", order_by="Room.sort_order"
    )


class HomeMember(Base):
    """Membership of a user in a home with a role (owner|admin|member)."""

    __tablename__ = "hub_home_members"
    __table_args__ = (UniqueConstraint("home_id", "user_id", name="uq_home_member"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    home_id: Mapped[str] = mapped_column(String(36), ForeignKey("hub_homes.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("hub_users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20), default="member", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    home: Mapped["Home"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(back_populates="memberships")


class Room(Base):
    """Room inside a home."""

    __tablename__ = "hub_rooms"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    home_id: Mapped[str] = mapped_column(String(36), ForeignKey("hub_homes.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    icon: Mapped[Optional[str]] = mapped_column(String(60))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    home: Mapped["Home"] = relationship(back_populates="rooms")


class Integration(Base):
    """Shared, per-home brand integration (Tuya cloud project, Ajax session, HA token...)."""

    __tablename__ = "hub_integrations"
    __table_args__ = (UniqueConstraint("home_id", "key", name="uq_integration_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    home_id: Mapped[str] = mapped_column(String(36), ForeignKey("hub_homes.id", ondelete="CASCADE"), index=True)
    brand: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    config: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    credentials_enc: Mapped[Optional[str]] = mapped_column(Text)
    webhook_secret: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class Device(Base):
    """Unified device record (see docs: unified device model)."""

    __tablename__ = "hub_devices"
    __table_args__ = (
        UniqueConstraint("home_id", "brand", "external_id", name="uq_device_external"),
        Index("ix_device_home_room", "home_id", "room_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    home_id: Mapped[str] = mapped_column(String(36), ForeignKey("hub_homes.id", ondelete="CASCADE"), index=True)
    room_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("hub_rooms.id", ondelete="SET NULL"))
    integration_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("hub_integrations.id", ondelete="SET NULL")
    )
    parent_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("hub_devices.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    brand: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    protocol: Mapped[str] = mapped_column(String(40), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    model: Mapped[Optional[str]] = mapped_column(String(120))
    manufacturer: Mapped[Optional[str]] = mapped_column(String(120))
    firmware: Mapped[Optional[str]] = mapped_column(String(120))
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    online: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    icon: Mapped[Optional[str]] = mapped_column(String(60))
    capabilities: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    state: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    config: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    credentials_enc: Mapped[Optional[str]] = mapped_column(Text)
    webhook_secret: Mapped[Optional[str]] = mapped_column(String(64))  # generic webhook; never serialised
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class DeviceEvent(Base):
    """Notable device event (motion, door opened, alarm...)."""

    __tablename__ = "hub_device_events"
    __table_args__ = (Index("ix_device_event_device_created", "device_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("hub_devices.id", ondelete="CASCADE"), index=True)
    home_id: Mapped[str] = mapped_column(String(36), index=True)
    type: Mapped[str] = mapped_column(String(60), nullable=False)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class Scene(Base):
    """Tap-to-run scene."""

    __tablename__ = "hub_scenes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    home_id: Mapped[str] = mapped_column(String(36), ForeignKey("hub_homes.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    icon: Mapped[Optional[str]] = mapped_column(String(60))
    color: Mapped[Optional[str]] = mapped_column(String(20))
    actions: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class Automation(Base):
    """If-this-then-that automation."""

    __tablename__ = "hub_automations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    home_id: Mapped[str] = mapped_column(String(36), ForeignKey("hub_homes.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    match: Mapped[str] = mapped_column(String(10), default="all", nullable=False)
    triggers: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    conditions: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    actions: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    last_triggered_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class Message(Base):
    """Message-center entry (kind: alarm | home | notice)."""

    __tablename__ = "hub_messages"
    __table_args__ = (Index("ix_message_home_created", "home_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    home_id: Mapped[str] = mapped_column(String(36), ForeignKey("hub_homes.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20), default="notice", nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="")
    device_id: Mapped[Optional[str]] = mapped_column(String(36))
    severity: Mapped[str] = mapped_column(String(20), default="info")
    read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class SosAlert(Base):
    """SOS raised from the app (bridges to the SafeR CI incident platform)."""

    __tablename__ = "hub_sos_alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    home_id: Mapped[str] = mapped_column(String(36), ForeignKey("hub_homes.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(36))
    lat: Mapped[Optional[float]] = mapped_column(Float)
    lon: Mapped[Optional[float]] = mapped_column(Float)
    note: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)
    forwarded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    incident_id: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
