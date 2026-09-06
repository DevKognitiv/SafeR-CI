"""Brand adapter contract. Adapters are pure (no DB access) and talk to devices/clouds via ``ctx.http()``."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

import httpx
from pydantic import BaseModel, Field


class AdapterError(Exception):
    """Raised by adapters. ``code`` drives the HTTP status returned by the API."""

    def __init__(self, message: str, code: str = "invalid_input"):
        super().__init__(message)
        self.message = message
        self.code = code


class FormField(BaseModel):
    """One input of a pairing form (rendered dynamically by the app)."""

    name: str
    label: str
    type: str = "text"  # text|password|number|select|qr|toggle|textarea
    required: bool = True
    placeholder: Optional[str] = None
    options: Optional[List[Dict[str, str]]] = None
    default: Optional[Any] = None
    help: Optional[str] = None


class PairingMethod(BaseModel):
    """A way to onboard devices for a brand (cloud account, IP + credentials, QR code...)."""

    id: str
    title: str
    description: str = ""
    fields: List[FormField] = Field(default_factory=list)
    supports_discovery: bool = False
    requires_integration: bool = False
    icon: Optional[str] = None


class BrandInfo(BaseModel):
    """Brand catalogue entry."""

    id: str
    name: str
    vendor: str = ""
    description: str = ""
    protocols: List[str] = Field(default_factory=list)
    categories: List[str] = Field(default_factory=list)
    methods: List[PairingMethod] = Field(default_factory=list)
    icon: str = "devices"
    docs_url: str = ""
    color: str = "#2563EB"


class DiscoveredDevice(BaseModel):
    """Device found during discovery, before pairing."""

    external_id: str
    name: str
    category: str = "generic"
    model: Optional[str] = None
    manufacturer: Optional[str] = None
    address: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class DeviceDraft(BaseModel):
    """Device returned by ``pair`` — persisted by the hub."""

    external_id: str
    name: str
    category: str = "generic"
    protocol: str
    model: Optional[str] = None
    manufacturer: Optional[str] = None
    firmware: Optional[str] = None
    capabilities: List[Dict[str, Any]] = Field(default_factory=list)
    state: Dict[str, Any] = Field(default_factory=dict)
    config: Dict[str, Any] = Field(default_factory=dict)
    credentials: Dict[str, Any] = Field(default_factory=dict)
    parent_external_id: Optional[str] = None
    icon: Optional[str] = None
    online: bool = True


class IntegrationDraft(BaseModel):
    """Shared per-home integration (cloud project / account / server)."""

    key: str
    name: str
    config: Dict[str, Any] = Field(default_factory=dict)
    credentials: Dict[str, Any] = Field(default_factory=dict)


class PairResult(BaseModel):
    """Result of a pairing call."""

    devices: List[DeviceDraft] = Field(default_factory=list)
    integration: Optional[IntegrationDraft] = None
    message: str = ""


class StreamInfo(BaseModel):
    """How to play a camera stream."""

    url: str
    type: str = "rtsp"  # rtsp|hls|mjpeg|webrtc|http
    headers: Dict[str, str] = Field(default_factory=dict)
    username: Optional[str] = None
    password: Optional[str] = None


class DeviceState(BaseModel):
    """Result of ``refresh``."""

    online: bool = True
    state: Dict[str, Any] = Field(default_factory=dict)


@dataclass
class DeviceRef:
    """Everything an adapter needs to talk to one device (credentials already decrypted)."""

    id: str
    external_id: str
    brand: str
    protocol: str
    category: str
    config: Dict[str, Any] = field(default_factory=dict)
    credentials: Dict[str, Any] = field(default_factory=dict)
    integration_config: Dict[str, Any] = field(default_factory=dict)
    integration_credentials: Dict[str, Any] = field(default_factory=dict)
    parent_external_id: Optional[str] = None
    state: Dict[str, Any] = field(default_factory=dict)
    capabilities: List[Dict[str, Any]] = field(default_factory=list)
    name: str = ""

    def cfg(self, key: str, default: Any = None) -> Any:
        """Config lookup: device config first, then integration config."""
        if key in self.config:
            return self.config[key]
        return self.integration_config.get(key, default)

    def cred(self, key: str, default: Any = None) -> Any:
        """Credential lookup: device credentials first, then integration credentials."""
        if key in self.credentials:
            return self.credentials[key]
        return self.integration_credentials.get(key, default)


EmitCallback = Callable[[str, str, Dict[str, Any]], Awaitable[None]]
Unsubscribe = Callable[[], Awaitable[None]]


class AdapterContext:
    """Runtime services handed to adapters (HTTP client factory, settings, logger, event emitter)."""

    def __init__(
        self,
        settings: Any = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        emit: Optional[EmitCallback] = None,
        logger: Optional[logging.Logger] = None,
        timeout: float = 10.0,
    ):
        self.settings = settings
        self.transport = transport
        self._emit = emit
        self.logger = logger or logging.getLogger("safer.hub.adapters")
        self.timeout = timeout

    def http(self, **kwargs: Any) -> httpx.AsyncClient:
        """Create an ``httpx.AsyncClient`` (tests inject a MockTransport through ``transport``)."""
        kwargs.setdefault("timeout", self.timeout)
        if self.transport is not None:
            kwargs["transport"] = self.transport
        return httpx.AsyncClient(**kwargs)

    async def emit(self, event_type: str, external_id: str, payload: Dict[str, Any]) -> None:
        """Push an event from a subscription. ``event_type``: ``state`` or ``event``.

        ``payload`` for ``state``: {"state": {...}, "online": bool}; for ``event``: {"type": str, ...}.
        """
        if self._emit is not None:
            await self._emit(event_type, external_id, payload)


class BrandAdapter:
    """Base class for brand adapters. Subclass and register on ``registry``."""

    brand_id: str = "generic"

    def info(self) -> BrandInfo:  # pragma: no cover - abstract
        """Brand catalogue entry (name, protocols, pairing methods)."""
        raise NotImplementedError

    def method(self, method_id: str) -> PairingMethod:
        """Look up a pairing method or raise ``AdapterError``."""
        for method in self.info().methods:
            if method.id == method_id:
                return method
        raise AdapterError(f"Unknown pairing method '{method_id}' for {self.brand_id}", "invalid_input")

    async def discover(self, method_id: str, payload: Dict[str, Any], ctx: AdapterContext) -> List[DiscoveredDevice]:
        """Find devices without pairing them (optional)."""
        del method_id, payload, ctx
        return []

    async def pair(self, method_id: str, payload: Dict[str, Any], ctx: AdapterContext) -> PairResult:  # pragma: no cover
        """Onboard devices. Must be implemented."""
        raise NotImplementedError

    async def refresh(self, device: DeviceRef, ctx: AdapterContext) -> DeviceState:  # pragma: no cover
        """Read current state. Must be implemented."""
        raise NotImplementedError

    async def send_command(self, device: DeviceRef, code: str, value: Any, ctx: AdapterContext) -> Dict[str, Any]:
        """Write a capability. Returns the partial state to merge."""
        del device, code, value, ctx
        raise AdapterError("This device does not accept commands", "unsupported")

    async def stream(self, device: DeviceRef, quality: str, ctx: AdapterContext) -> Optional[StreamInfo]:
        """Return stream info for cameras (optional)."""
        del device, quality, ctx
        return None

    async def snapshot(self, device: DeviceRef, ctx: AdapterContext) -> Optional[bytes]:
        """Return a JPEG snapshot for cameras (optional)."""
        del device, ctx
        return None

    async def subscribe(self, devices: List[DeviceRef], ctx: AdapterContext) -> Optional[Unsubscribe]:
        """Start push subscriptions for devices; return an async unsubscribe (optional)."""
        del devices, ctx
        return None

    async def unpair(self, device: DeviceRef, ctx: AdapterContext) -> None:
        """Clean up on the device/cloud side (optional)."""
        del device, ctx

    async def handle_webhook(
        self, integration_config: Dict[str, Any], integration_credentials: Dict[str, Any], payload: Any, ctx: AdapterContext
    ) -> List[Dict[str, Any]]:
        """Translate an inbound webhook body into hub updates (optional).

        Return items shaped ``{"external_id": str, "type": "state"|"event", "payload": {...}}`` where
        ``payload`` follows ``AdapterContext.emit``.
        """
        del integration_config, integration_credentials, payload, ctx
        raise AdapterError("This brand does not accept webhooks", "unsupported")

    @property
    def supports_push(self) -> bool:
        """True when ``subscribe`` is implemented (poller skips those devices)."""
        return type(self).subscribe is not BrandAdapter.subscribe


def require(payload: Dict[str, Any], *names: str) -> None:
    """Raise AdapterError when required payload fields are missing/blank."""
    missing = [n for n in names if payload.get(n) in (None, "")]
    if missing:
        raise AdapterError(f"Missing required field(s): {', '.join(missing)}", "invalid_input")
