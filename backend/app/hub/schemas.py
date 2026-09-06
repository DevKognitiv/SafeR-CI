"""Pydantic request/response schemas for the Hub API."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.hub.adapters.base import BrandInfo, DiscoveredDevice, StreamInfo  # noqa: F401  (re-exported)
from app.hub.capabilities import CATEGORIES, SECURITY_MODES


class ORMModel(BaseModel):
    """Base for models built from ORM rows."""

    model_config = ConfigDict(from_attributes=True)


EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def validate_email(value: str) -> str:
    """Lightweight e-mail validation (no external dependency)."""
    value = (value or "").strip().lower()
    if not EMAIL_RE.match(value) or len(value) > 255:
        raise ValueError("invalid e-mail address")
    return value


# --- Auth -----------------------------------------------------------------------
class RegisterIn(BaseModel):
    email: str
    password: str = Field(min_length=6, max_length=128)
    name: str = Field(default="", max_length=120)
    phone: Optional[str] = Field(default=None, max_length=40)
    locale: str = "fr"

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return validate_email(value)


class LoginIn(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return validate_email(value)


class UserUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=120)
    phone: Optional[str] = Field(default=None, max_length=40)
    locale: Optional[str] = Field(default=None, max_length=10)
    avatar_url: Optional[str] = Field(default=None, max_length=500)


class PushTokenIn(BaseModel):
    platform: str = "android"
    token: str = Field(min_length=8, max_length=500)


class UserOut(ORMModel):
    id: str
    email: str
    name: str
    phone: Optional[str] = None
    locale: str = "fr"
    avatar_url: Optional[str] = None
    is_admin: bool = False
    created_at: datetime


class TokenOut(BaseModel):
    token: str
    token_type: str = "bearer"
    user: UserOut


# --- Homes / rooms / members ----------------------------------------------------------
class RoomCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    icon: Optional[str] = None


class RoomUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    icon: Optional[str] = None
    sort_order: Optional[int] = None


class RoomOut(ORMModel):
    id: str
    home_id: str
    name: str
    icon: Optional[str] = None
    sort_order: int = 0
    device_count: int = 0


class ReorderIn(BaseModel):
    ids: List[str]


class HomeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    lat: Optional[float] = None
    lon: Optional[float] = None
    address: Optional[str] = Field(default=None, max_length=255)
    rooms: List[str] = Field(default_factory=list)


class HomeUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    lat: Optional[float] = None
    lon: Optional[float] = None
    address: Optional[str] = Field(default=None, max_length=255)


class HomeOut(ORMModel):
    id: str
    name: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    address: Optional[str] = None
    security_mode: str = "disarmed"
    alarm_active: bool = False
    role: str = "member"
    rooms: List[RoomOut] = Field(default_factory=list)
    member_count: int = 0
    device_count: int = 0
    created_at: datetime


class MemberCreate(BaseModel):
    email: str
    role: str = "member"

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return validate_email(value)

    @field_validator("role")
    @classmethod
    def _role(cls, value: str) -> str:
        if value not in ("admin", "member"):
            raise ValueError("role must be admin or member")
        return value


class MemberUpdate(BaseModel):
    role: str

    @field_validator("role")
    @classmethod
    def _role(cls, value: str) -> str:
        if value not in ("owner", "admin", "member"):
            raise ValueError("role must be owner, admin or member")
        return value


class MemberOut(BaseModel):
    user_id: str
    email: str
    name: str
    role: str
    avatar_url: Optional[str] = None
    joined_at: datetime


class WeatherOut(BaseModel):
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    condition: str = "unknown"
    icon: str = "cloud"
    wind_kmh: Optional[float] = None
    updated_at: Optional[datetime] = None
    available: bool = False


# --- Devices -----------------------------------------------------------------------
class DeviceOut(ORMModel):
    id: str
    home_id: str
    room_id: Optional[str] = None
    integration_id: Optional[str] = None
    parent_id: Optional[str] = None
    name: str
    brand: str
    protocol: str
    category: str
    model: Optional[str] = None
    manufacturer: Optional[str] = None
    firmware: Optional[str] = None
    external_id: str
    online: bool = True
    icon: Optional[str] = None
    capabilities: List[Dict[str, Any]] = Field(default_factory=list)
    state: Dict[str, Any] = Field(default_factory=dict)
    config: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    last_seen_at: Optional[datetime] = None


class DeviceUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    room_id: Optional[str] = None
    icon: Optional[str] = None
    clear_room: bool = False


class CommandIn(BaseModel):
    code: str
    value: Any = None


class CommandsIn(BaseModel):
    commands: List[CommandIn] = Field(min_length=1)


class DeviceEventOut(ORMModel):
    id: str
    device_id: str
    home_id: str
    type: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


# --- Onboarding -----------------------------------------------------------------
class DiscoverIn(BaseModel):
    home_id: str
    method: str
    payload: Dict[str, Any] = Field(default_factory=dict)


class PairIn(BaseModel):
    home_id: str
    room_id: Optional[str] = None
    method: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    selected_external_ids: Optional[List[str]] = None


class PairOut(BaseModel):
    devices: List[DeviceOut]
    integration_id: Optional[str] = None
    message: str = ""


class ParseCodeIn(BaseModel):
    code: str = Field(min_length=1, max_length=2000)


class ParseCodeOut(BaseModel):
    kind: str  # matter_qr | matter_manual | tuya_qr | url | unknown
    brand: Optional[str] = None
    method: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)


class IntegrationOut(ORMModel):
    id: str
    home_id: str
    brand: str
    key: str
    name: str
    config: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class CategoryOut(BaseModel):
    id: str
    name: str
    name_en: str
    icon: str
    group: str
    brands: List[str] = Field(default_factory=list)


class CategoryGroupOut(BaseModel):
    id: str
    name: str
    name_en: str
    icon: str
    categories: List[CategoryOut] = Field(default_factory=list)


# --- Scenes & automations ---------------------------------------------------------------
ACTION_TYPES = {"device_command", "delay", "security_mode", "notify", "run_scene"}
TRIGGER_TYPES = {"device_state", "schedule", "security_mode"}
CONDITION_TYPES = {"device_state", "time_range", "security_mode"}
OPS = {"eq", "ne", "gt", "lt", "gte", "lte", "changed"}


def _validate_actions(actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    for action in actions:
        atype = action.get("type")
        if atype not in ACTION_TYPES:
            raise ValueError(f"unknown action type {atype}")
        if atype == "device_command" and not (action.get("device_id") and action.get("code")):
            raise ValueError("device_command requires device_id and code")
        if atype == "delay" and not isinstance(action.get("seconds"), (int, float)):
            raise ValueError("delay requires seconds")
        if atype == "security_mode" and action.get("mode") not in SECURITY_MODES:
            raise ValueError("security_mode requires a valid mode")
        if atype == "run_scene" and not action.get("scene_id"):
            raise ValueError("run_scene requires scene_id")
    return actions


def _validate_triggers(items: List[Dict[str, Any]], allowed: set, name: str) -> List[Dict[str, Any]]:
    for item in items:
        itype = item.get("type")
        if itype not in allowed:
            raise ValueError(f"unknown {name} type {itype}")
        if itype == "device_state":
            if not (item.get("device_id") and item.get("code")):
                raise ValueError(f"device_state {name} requires device_id and code")
            if item.get("op", "eq") not in OPS:
                raise ValueError(f"invalid op {item.get('op')}")
        if itype == "schedule" and not item.get("time"):
            raise ValueError("schedule trigger requires time HH:MM")
        if itype == "time_range" and not (item.get("start") and item.get("end")):
            raise ValueError("time_range requires start and end")
        if itype == "security_mode" and item.get("mode") not in SECURITY_MODES:
            raise ValueError("security_mode requires a valid mode")
    return items


class SceneIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    icon: Optional[str] = None
    color: Optional[str] = None
    actions: List[Dict[str, Any]] = Field(default_factory=list)
    enabled: bool = True

    @field_validator("actions")
    @classmethod
    def _actions(cls, value: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return _validate_actions(value)


class SceneUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    icon: Optional[str] = None
    color: Optional[str] = None
    actions: Optional[List[Dict[str, Any]]] = None
    enabled: Optional[bool] = None
    sort_order: Optional[int] = None

    @field_validator("actions")
    @classmethod
    def _actions(cls, value: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
        return _validate_actions(value) if value is not None else None


class SceneOut(ORMModel):
    id: str
    home_id: str
    name: str
    icon: Optional[str] = None
    color: Optional[str] = None
    actions: List[Dict[str, Any]] = Field(default_factory=list)
    enabled: bool = True
    sort_order: int = 0
    last_run_at: Optional[datetime] = None
    created_at: datetime


class AutomationIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    enabled: bool = True
    match: str = "all"
    triggers: List[Dict[str, Any]] = Field(default_factory=list)
    conditions: List[Dict[str, Any]] = Field(default_factory=list)
    actions: List[Dict[str, Any]] = Field(default_factory=list)

    @field_validator("match")
    @classmethod
    def _match(cls, value: str) -> str:
        if value not in ("all", "any"):
            raise ValueError("match must be all or any")
        return value

    @field_validator("actions")
    @classmethod
    def _actions(cls, value: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return _validate_actions(value)

    @field_validator("triggers")
    @classmethod
    def _triggers(cls, value: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return _validate_triggers(value, TRIGGER_TYPES, "trigger")

    @field_validator("conditions")
    @classmethod
    def _conditions(cls, value: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return _validate_triggers(value, CONDITION_TYPES, "condition")


class AutomationUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    enabled: Optional[bool] = None
    match: Optional[str] = None
    triggers: Optional[List[Dict[str, Any]]] = None
    conditions: Optional[List[Dict[str, Any]]] = None
    actions: Optional[List[Dict[str, Any]]] = None

    @field_validator("match")
    @classmethod
    def _match(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in ("all", "any"):
            raise ValueError("match must be all or any")
        return value

    @field_validator("actions")
    @classmethod
    def _actions(cls, value: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
        return _validate_actions(value) if value is not None else None

    @field_validator("triggers")
    @classmethod
    def _triggers(cls, value: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
        return _validate_triggers(value, TRIGGER_TYPES, "trigger") if value is not None else None

    @field_validator("conditions")
    @classmethod
    def _conditions(cls, value: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
        return _validate_triggers(value, CONDITION_TYPES, "condition") if value is not None else None


class AutomationOut(ORMModel):
    id: str
    home_id: str
    name: str
    enabled: bool = True
    match: str = "all"
    triggers: List[Dict[str, Any]] = Field(default_factory=list)
    conditions: List[Dict[str, Any]] = Field(default_factory=list)
    actions: List[Dict[str, Any]] = Field(default_factory=list)
    last_triggered_at: Optional[datetime] = None
    created_at: datetime


# --- Security / SOS / messages ---------------------------------------------------------
class SecurityModeIn(BaseModel):
    mode: str

    @field_validator("mode")
    @classmethod
    def _mode(cls, value: str) -> str:
        if value not in SECURITY_MODES:
            raise ValueError(f"mode must be one of {SECURITY_MODES}")
        return value


class SecurityOut(BaseModel):
    home_id: str
    mode: str
    alarm_active: bool = False
    alarm_device_id: Optional[str] = None
    changed_at: Optional[datetime] = None
    panels: List[DeviceOut] = Field(default_factory=list)
    zones: List[DeviceOut] = Field(default_factory=list)
    sensors: List[DeviceOut] = Field(default_factory=list)


class SosIn(BaseModel):
    lat: Optional[float] = None
    lon: Optional[float] = None
    note: Optional[str] = Field(default=None, max_length=1000)
    incident_type: str = "panic"


class SosOut(ORMModel):
    id: str
    home_id: str
    user_id: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    note: Optional[str] = None
    status: str = "open"
    forwarded: bool = False
    incident_id: Optional[str] = None
    created_at: datetime


class MessageOut(ORMModel):
    id: str
    home_id: str
    kind: str
    title: str
    body: str = ""
    device_id: Optional[str] = None
    severity: str = "info"
    read: bool = False
    created_at: datetime


class UnreadCountOut(BaseModel):
    total: int = 0
    alarm: int = 0
    home: int = 0
    notice: int = 0


class HealthOut(BaseModel):
    status: str = "ok"
    version: str
    adapters: List[str] = Field(default_factory=list)
    sia_receiver: bool = False
    categories: List[str] = Field(default_factory=lambda: list(CATEGORIES))
