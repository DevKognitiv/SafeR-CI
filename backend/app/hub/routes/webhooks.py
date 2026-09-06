"""Inbound webhooks: brand callbacks and ad-hoc device updates (mounted under ``/webhooks`` by ``app.py``).

No JWT is involved: the caller proves itself with a per-integration / per-device secret passed as the ``secret``
query parameter (or the ``X-Webhook-Secret`` header). Secrets are compared in constant time.

``POST /webhooks/{brand}/{integration_id}?secret=...``
    Hands the request body to ``BrandAdapter.handle_webhook`` (Ajax cloud callbacks, ...). The body is decoded
    as JSON when possible (any JSON value), as a dict for form-encoded posts, and as raw text otherwise. Every
    ``{"external_id", "type": "state"|"event", "payload"}`` item the adapter returns is applied through
    ``DeviceService.handle_push`` -- the same path push subscriptions use, so device events, message-center
    entries and the software alarm behave identically. Brands without webhook support answer 501.

``POST /webhooks/generic/{device_id}?secret=...``
    Lets scripts, ESPHome/Tasmota rules or Node-RED flows update a device without a dedicated adapter:
    ``{"state": {...}, "online": true}`` and/or ``{"event": {"type": "...", ...}}`` (or ``"events": [...]``).
    The secret lives in ``device.config["webhook_secret"]`` (``GET /devices/{id}/webhook`` creates it).
"""
from __future__ import annotations

import hmac
import json
import logging
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel

from app.hub.adapters.registry import registry
from app.hub.models import Device, Integration
from app.hub.runtime import HubRuntime, get_runtime
from app.hub.services.device_service import DeviceService

logger = logging.getLogger("safer.hub.webhooks")

router = APIRouter()

__all__ = [
    "router", "BRAND_WEBHOOK_ROUTE", "GENERIC_WEBHOOK_ROUTE", "SECRET_HEADER", "WebhookAck", "read_payload",
    "verify_secret", "generic_items",
]

# Route names (used by the onboarding routes to build webhook URLs with the right mount prefix)
BRAND_WEBHOOK_ROUTE = "hub_brand_webhook"
GENERIC_WEBHOOK_ROUTE = "hub_generic_webhook"
GENERIC_BRAND = "generic"
SECRET_HEADER = "X-Webhook-Secret"
MAX_BODY_BYTES = 1024 * 1024
ITEM_TYPES = ("state", "event")
TRUE_WORDS = ("true", "on", "1", "yes", "online")
FALSE_WORDS = ("false", "off", "0", "no", "offline")


class WebhookAck(BaseModel):
    """Webhook response: how many updates were applied / skipped."""

    accepted: int = 0
    ignored: int = 0


# ----------------------------------------------------------------------------- helpers
def _device_service(runtime: HubRuntime) -> DeviceService:
    service = runtime.services.get("devices")
    if service is None:
        service = DeviceService(runtime)
        runtime.services["devices"] = service
    return service


def verify_secret(expected: Optional[str], provided: Optional[str]) -> None:
    """401 unless ``provided`` matches ``expected`` (constant-time; an unset secret disables the endpoint)."""
    if not expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Webhook secret is not configured for this target")
    if not provided:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing webhook secret")
    if not hmac.compare_digest(expected.encode("utf-8"), provided.encode("utf-8")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook secret")


def _provided_secret(request: Request, secret: Optional[str]) -> Optional[str]:
    """Secret from ``?secret=`` or the ``X-Webhook-Secret`` header."""
    return secret or request.headers.get(SECRET_HEADER) or None


async def read_payload(request: Request) -> Any:
    """Decode the body: JSON (any value) when possible, a dict for form posts, raw text otherwise.

    Empty bodies decode to ``""``. A declared JSON content-type with a malformed body is a 400; bodies above
    ``MAX_BODY_BYTES`` are a 413.
    """
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Webhook body too large")
    if not raw:
        return ""
    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    text = raw.decode("utf-8", errors="replace")
    if content_type == "application/x-www-form-urlencoded":
        return dict(parse_qsl(text, keep_blank_values=True))
    declared_json = content_type.endswith("json")
    first = text.lstrip()[:1]
    if declared_json or content_type == "" or (first and first in "{["):
        try:
            return json.loads(text)
        except ValueError:
            if declared_json:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed JSON body") from None
    return text


def _coerce_online(value: Any) -> Optional[bool]:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        word = value.strip().lower()
        if word in TRUE_WORDS:
            return True
        if word in FALSE_WORDS:
            return False
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="'online' must be a boolean")


def _event_payload(event: Any) -> Dict[str, Any]:
    if isinstance(event, str):
        event = {"type": event}
    if not isinstance(event, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="'event' must be an object or a type string")
    payload = dict(event)
    payload["type"] = str(payload.get("type") or "event")
    return payload


def generic_items(payload: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any]]]:
    """Translate a generic webhook body into ``(event_type, payload)`` pairs for ``handle_push``.

    ``state``/``online`` become one ``state`` push; ``event`` (object or type string) and every entry of
    ``events`` become ``event`` pushes. Raises 400 on malformed fields.
    """
    items: List[Tuple[str, Dict[str, Any]]] = []
    if "state" in payload or "online" in payload:
        state = payload.get("state")
        if state is None:
            state = {}
        if not isinstance(state, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="'state' must be an object of capability codes")
        items.append(("state", {"state": dict(state), "online": _coerce_online(payload.get("online"))}))
    if "event" in payload:
        items.append(("event", _event_payload(payload["event"])))
    events = payload.get("events")
    if events is not None:
        if not isinstance(events, list):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="'events' must be a list")
        items.extend(("event", _event_payload(event)) for event in events)
    return items


async def _apply_items(runtime: HubRuntime, brand: str, items: Any, target: str) -> WebhookAck:
    """Push every well-formed adapter item through ``DeviceService.handle_push``."""
    service = _device_service(runtime)
    accepted = ignored = 0
    for item in items or []:
        if not isinstance(item, dict):
            ignored += 1
            continue
        external_id, event_type, payload = item.get("external_id"), item.get("type"), item.get("payload")
        if payload is None:
            payload = {}
        if not external_id or event_type not in ITEM_TYPES or not isinstance(payload, dict):
            logger.warning("Webhook %s/%s: skipping malformed item %r", brand, target, item)
            ignored += 1
            continue
        await service.handle_push(brand, str(external_id), event_type, dict(payload))
        accepted += 1
    logger.info("Webhook %s/%s: %d update(s) applied, %d ignored", brand, target, accepted, ignored)
    return WebhookAck(accepted=accepted, ignored=ignored)


# ----------------------------------------------------------------------------- routes
# Declared before the brand route so ``/webhooks/generic/<id>`` is never captured as brand "generic".
@router.post("/generic/{device_id}", response_model=WebhookAck, name=GENERIC_WEBHOOK_ROUTE)
async def generic_webhook(
    device_id: str,
    request: Request,
    secret: Optional[str] = Query(default=None, description="Device webhook secret (or X-Webhook-Secret header)"),
) -> WebhookAck:
    """Apply ``{"state": {...}, "online": bool}`` and/or ``{"event": {...}}`` to one device (no adapter needed)."""
    runtime = get_runtime()
    async with runtime.db.session() as session:
        device = await session.get(Device, device_id)
        if device is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
        verify_secret((device.config or {}).get("webhook_secret"), _provided_secret(request, secret))
        brand, external_id = device.brand, device.external_id
    payload = await read_payload(request)
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A JSON object body is required")
    items = generic_items(payload)
    if not items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Body must contain 'state', 'online', 'event' or 'events'")
    service = _device_service(runtime)
    for event_type, item_payload in items:
        await service.handle_push(brand, external_id, event_type, item_payload)
    logger.info("Generic webhook for device %s: %d update(s) applied", device_id, len(items))
    return WebhookAck(accepted=len(items))


@router.post("/{brand}/{integration_id}", response_model=WebhookAck, name=BRAND_WEBHOOK_ROUTE)
async def brand_webhook(
    brand: str,
    integration_id: str,
    request: Request,
    secret: Optional[str] = Query(default=None, description="Integration webhook secret (or X-Webhook-Secret header)"),
) -> WebhookAck:
    """Brand callback for an integration: 404 unknown integration/brand mismatch, 401 bad secret, 501 no webhook support."""
    runtime = get_runtime()
    async with runtime.db.session() as session:
        integration = await session.get(Integration, integration_id)
        if integration is None or integration.brand != brand:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")
        adapter = registry.get(brand)
        if adapter is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown brand '{brand}'")
        verify_secret(integration.webhook_secret, _provided_secret(request, secret))
        config = dict(integration.config or {})
        credentials = runtime.vault.decrypt(integration.credentials_enc)
    payload = await read_payload(request)
    # AdapterError (unsupported -> 501, invalid_input -> 400, ...) is mapped by the application handler.
    items = await adapter.handle_webhook(config, credentials, payload, runtime.ctx_for(brand))
    return await _apply_items(runtime, brand, items, integration_id)
