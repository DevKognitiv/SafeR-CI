"""Pydantic request/response schemas for the Hub API."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.hub.adapters.base import BrandInfo, DiscoveredDevice, StreamInfo  # noqa: F401  # pylint: disable=unused-import
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

    @field_validator("config", mode="before")
    @classmethod
    def _public_config(cls, value: Any) -> Any:
        """``config`` is non-secret; drop the webhook secret older releases stored there."""
        if isinstance(value, dict) and "webhook_secret" in value:
            return {k: v for k, v in value.items() if k != "webhook_secret"}
        return value

    @field_validator("state", mode="before")
    @classmethod
    def _public_state(cls, value: Any) -> Any:
        """Credentials a camera embedded in an advertised URL (pairings older than the stripping) never leave the hub."""
        return scrub_credentials(value)


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


# Request headers that carry credentials: stripped from client-facing stream descriptors like username/password.
SENSITIVE_STREAM_HEADERS = frozenset({"authorization", "proxy-authorization", "cookie", "x-api-key", "x-auth-token"})


def split_userinfo(url: str) -> Tuple[str, Optional[str], Optional[str]]:
    """``(url without userinfo, username, password)`` -- ``rtsp://u:p@cam/x`` -> ``("rtsp://cam/x", "u", "p")``."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return url, None, None
    if "@" not in parts.netloc:
        return url, None, None
    userinfo, _, hostport = parts.netloc.rpartition("@")
    user, has_password, password = userinfo.partition(":")
    clean = urlunsplit((parts.scheme, hostport, parts.path, parts.query, parts.fragment))
    return clean, unquote(user) or None, unquote(password) if has_password else None


# Query parameters that carry a credential (Home Assistant's camera proxy ``?token=``, signed URLs, API keys).
SENSITIVE_QUERY_KEYS = frozenset({
    "token", "access_token", "auth", "authorization", "password", "passwd", "pwd", "pass", "apikey", "api_key",
    "key", "secret", "sig", "signature", "session", "sessionid", "session_id",
})


def strip_query_secrets(url: str) -> Tuple[str, bool]:
    """``(url without credential query parameters, whether any were removed)``; other parameters are kept."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return url, False
    if not parts.query:
        return url, False
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    kept = [(k, v) for k, v in pairs if k.lower() not in SENSITIVE_QUERY_KEYS]
    if len(kept) == len(pairs):
        return url, False
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept), parts.fragment)), True


def scrub_credentials(value: Any) -> Any:
    """``value`` with ``user:pass@`` removed from every URL-shaped string, recursively (dicts and lists).

    Device state is readable by every member of a home and travels in ``DeviceOut`` and in the WebSocket device
    events. Cameras paired before the hub stripped advertised URIs may still hold credentials there; this keeps
    them inside the hub whatever payload carries the state (``stream()`` injects them when a player needs them).
    """
    if isinstance(value, dict):
        return {key: scrub_credentials(item) for key, item in value.items()}
    if isinstance(value, list):
        return [scrub_credentials(item) for item in value]
    if isinstance(value, str) and "@" in value and "://" in value:
        return split_userinfo(value)[0]
    return value


class StreamOut(BaseModel):
    """Client-facing stream descriptor (``GET /devices/{id}/stream``).

    Camera credentials never leave the hub by default: ``username``/``password``, any ``user:pass@`` embedded in
    the URL, credential query parameters (``?token=`` of a Home Assistant camera proxy, signed URLs) and credential
    headers are stripped (``auth_required`` tells the app that the stream needs them). Only when the owner sets
    ``HUB_STREAM_CREDENTIALS_TO_CLIENTS`` are they included, with ``credentials_included`` set to true.
    """

    url: str
    type: str = "rtsp"  # rtsp|hls|mjpeg|webrtc|http
    headers: Dict[str, str] = Field(default_factory=dict)
    auth_required: bool = False
    credentials_included: bool = False
    username: Optional[str] = None
    password: Optional[str] = None

    @classmethod
    def from_info(cls, info: StreamInfo, include_credentials: bool = False) -> "StreamOut":
        """Build the public descriptor from the adapter's ``StreamInfo`` (left untouched)."""
        url, url_user, url_password = split_userinfo(info.url)
        public_url, query_secret = strip_query_secrets(url)
        username = info.username or url_user
        password = info.password if info.password is not None else url_password
        headers = dict(info.headers or {})
        sensitive = {k: v for k, v in headers.items() if k.lower() in SENSITIVE_STREAM_HEADERS}
        auth_required = bool(username or password is not None or sensitive or query_secret)
        if include_credentials and auth_required:
            # The query credential is the stream's key: it stays in the URL only on explicit opt-in.
            return cls(url=url, type=info.type, headers=headers, auth_required=True, credentials_included=True,
                       username=username, password=password)
        safe_headers = {k: v for k, v in headers.items() if k.lower() not in SENSITIVE_STREAM_HEADERS}
        return cls(url=public_url, type=info.type, headers=safe_headers, auth_required=auth_required)


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
    """Body of ``POST /homes/{id}/sos``.

    ``lat``/``lon`` are the phone position (both or neither). ``address`` is a free-text address or landmark and
    ``address_confirmed`` is the user's assertion that help is needed there; the hub cannot verify it, so with
    ``SAFER_SOS_REQUIRE_ADDRESS`` an SOS without any position is refused (422 ``position_required``) unless the
    address is given and confirmed.
    """

    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lon: Optional[float] = Field(default=None, ge=-180, le=180)
    note: Optional[str] = Field(default=None, max_length=1000)
    incident_type: str = Field(default="panic", max_length=40)
    address: Optional[str] = Field(default=None, max_length=300)
    address_confirmed: bool = False

    @field_validator("address")
    @classmethod
    def _address(cls, value: Optional[str]) -> Optional[str]:
        cleaned = " ".join((value or "").split())
        return cleaned or None

    @model_validator(mode="after")
    def _position(self) -> "SosIn":
        if (self.lat is None) != (self.lon is None):
            raise ValueError("lat and lon must be given together")
        return self


class SosOut(ORMModel):
    id: str
    home_id: str
    user_id: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    note: Optional[str] = None
    address: Optional[str] = None
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
    """``GET /health``: liveness plus the app/hub version negotiation contract.

    The app compares its own version with ``min_app_version`` (forced-update screen when older), reads ``flags``
    to adapt its flows (e.g. ask for an address before an SOS when ``sos_require_address`` is on) and hides
    relative ages when ``clock_synced`` is false.
    """

    status: str = "ok"
    version: str
    adapters: List[str] = Field(default_factory=list)
    sia_receiver: bool = False
    categories: List[str] = Field(default_factory=lambda: list(CATEGORIES))
    hub_version: str
    api_version: str = "1"
    min_app_version: str = "0.2.0"
    flags: Dict[str, bool] = Field(default_factory=dict)
    clock_synced: bool = True
    server_time: str  # ISO-8601 UTC, e.g. 2026-10-11T12:00:00Z
