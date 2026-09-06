"""Onboarding routes: brand catalogue, "add manually" category grid, QR/code parsing, discovery, pairing and
per-home integrations (paths declared in full; the hub router mounts them under ``/api/v1/hub``).

The flow mirrors the Tuya Smart app: the client lists brands (``GET /onboarding/brands``) or the category grid
(``GET /onboarding/categories``), optionally scans a code (``POST /onboarding/parse-code``), runs discovery for
methods that support it (``POST /onboarding/{brand}/discover``, any member) and finally pairs
(``POST /onboarding/{brand}/pair``, admin/owner). Pairing goes through ``DeviceService.materialize`` so devices
and integrations are upserted (pairing twice updates instead of duplicating) and ``device.added`` events reach
WebSocket clients; a "Nouvel appareil" message is posted for every newly created device.

Adapter failures surface as ``AdapterError`` and are mapped by the application handler (400/401/404/501/502).
The demo brand disappears from every endpoint when ``HUB_DEMO_ENABLED`` is off.
"""
from __future__ import annotations

import json
import logging
import secrets
from typing import Any, Awaitable, Dict, List, Optional, Set, Tuple, TypeVar
from urllib.parse import parse_qsl, quote, urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.hub.adapters.base import AdapterError, BrandAdapter, BrandInfo, DiscoveredDevice
from app.hub.adapters.registry import registry
from app.hub.capabilities import CATEGORIES, CATEGORY_GROUPS, CATEGORY_INFO
from app.hub.deps import DeviceAccess, HomeAccess, device_access, get_current_user, get_db, home_access, load_home_access
from app.hub.models import Device, Integration, Room, User
from app.hub.routes.webhooks import BRAND_WEBHOOK_ROUTE, GENERIC_BRAND, GENERIC_WEBHOOK_ROUTE
from app.hub.runtime import get_runtime
from app.hub.schemas import (
    CategoryGroupOut, CategoryOut, DeviceOut, DiscoverIn, IntegrationOut, PairIn, PairOut, ParseCodeIn, ParseCodeOut,
)
from app.hub.services.device_service import DeviceService

logger = logging.getLogger("safer.hub.onboarding")

router = APIRouter()

__all__ = ["router", "parse_code", "visible_adapters", "build_category_catalog", "webhook_path", "WebhookUrlOut"]

T = TypeVar("T")

DEMO_BRAND = "demo"
HUB_PREFIX = "/api/v1/hub"  # fallback when the mounted path cannot be resolved from the request
WEBHOOK_SECRET_BYTES = 24
GROUP_ORDER = ["electrical", "lighting", "climate", "sensors", "cameras", "security", "gateway", "other"]
URL_SCHEMES = ("http", "https", "rtsp")
MATTER_METHODS = {"matter_qr": "qr_code", "matter_manual": "manual_code"}
TUYA_BRAND, TUYA_METHOD = "tuya", "cloud_project"
TUYA_TOKEN_KEYS = ("token", "t", "p", "code")
NO_DEVICES = "Aucun appareil trouvé"
NO_SELECTED_DEVICES = "Aucun des appareils sélectionnés n'a été trouvé"


class WebhookUrlOut(BaseModel):
    """Where a brand cloud / script must POST for one integration or ad-hoc device."""

    url: str
    absolute_url: str
    secret: str
    brand: str
    integration_id: Optional[str] = None
    device_id: Optional[str] = None


# ----------------------------------------------------------------------------- helpers
def _device_service() -> DeviceService:
    runtime = get_runtime()
    service = runtime.services.get("devices")
    if service is None:
        service = DeviceService(runtime)
        runtime.services["devices"] = service
    return service


def _demo_enabled() -> bool:
    return bool(get_runtime().settings.HUB_DEMO_ENABLED)


def visible_adapters() -> List[BrandAdapter]:
    """Registered adapters visible to the app (the demo brand is hidden when ``HUB_DEMO_ENABLED`` is off)."""
    demo = _demo_enabled()
    return [adapter for adapter in registry.all() if demo or adapter.brand_id != DEMO_BRAND]


def _adapter_or_404(brand: str) -> BrandAdapter:
    adapter = registry.get(brand)
    if adapter is None or (brand == DEMO_BRAND and not _demo_enabled()):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown brand '{brand}'")
    return adapter


def _brand_info(adapter: BrandAdapter) -> Optional[BrandInfo]:
    """``adapter.info()`` or None (a broken adapter must not take the whole catalogue down)."""
    try:
        return adapter.info()
    except Exception:  # pylint: disable=broad-except
        logger.exception("Adapter %s: info() failed, hidden from the catalogue", adapter.brand_id)
        return None


def build_category_catalog(adapters: List[BrandAdapter]) -> List[CategoryGroupOut]:
    """Category grid grouped per ``CATEGORY_GROUPS`` with the brand ids able to onboard each category."""
    brands_by_category: Dict[str, Set[str]] = {}
    for adapter in adapters:
        info = _brand_info(adapter)
        if info is None:
            continue
        for category in info.categories:
            brands_by_category.setdefault(category, set()).add(info.id)
    order = GROUP_ORDER + [group for group in CATEGORY_GROUPS if group not in GROUP_ORDER]
    groups: List[CategoryGroupOut] = []
    for group_id in order:
        meta = CATEGORY_GROUPS.get(group_id)
        if meta is None:
            continue
        categories = [
            CategoryOut(
                id=category_id, name=info["name"], name_en=info["name_en"], icon=info["icon"], group=group_id,
                brands=sorted(brands_by_category.get(category_id, set())),
            )
            for category_id, info in ((cid, CATEGORY_INFO[cid]) for cid in CATEGORIES if cid in CATEGORY_INFO)
            if info.get("group") == group_id
        ]
        groups.append(CategoryGroupOut(id=group_id, name=meta["name"], name_en=meta["name_en"], icon=meta["icon"], categories=categories))
    return groups


async def _guard(awaitable: Awaitable[T], brand: str) -> T:
    """Run an adapter call, mapping stray transport errors to ``AdapterError`` (adapters normally do it themselves)."""
    try:
        return await awaitable
    except AdapterError:
        raise
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        mapped = "auth_failed" if code in (401, 403) else "not_found" if code == 404 else "unreachable"
        logger.warning("%s: unhandled HTTP %s during onboarding", brand, code)
        raise AdapterError(f"{brand}: réponse HTTP {code} du service", mapped) from exc
    except (httpx.HTTPError, OSError) as exc:
        logger.warning("%s: network failure during onboarding: %s", brand, exc)
        raise AdapterError(f"{brand}: impossible de joindre l'appareil ou le service", "unreachable") from exc


async def _resolve_room(db: AsyncSession, room_id: str, home_id: str) -> Room:
    room = await db.get(Room, room_id)
    if room is None or room.home_id != home_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Room does not belong to this home")
    return room


def _clean_ids(values: Optional[List[str]]) -> Optional[List[str]]:
    """Strip/dedupe selected external ids; ``None``/empty means "every device"."""
    if not values:
        return None
    cleaned = list(dict.fromkeys(str(value).strip() for value in values if value is not None and str(value).strip()))
    return cleaned or None


def _new_secret() -> str:
    return secrets.token_urlsafe(WEBHOOK_SECRET_BYTES)


def _pair_message(created: int, updated: int) -> str:
    parts = []
    if created:
        parts.append(f"{created} appareil{'s' if created > 1 else ''} ajouté{'s' if created > 1 else ''}")
    if updated:
        parts.append(f"{updated} mis à jour")
    return ", ".join(parts) if parts else NO_DEVICES


async def _load_integration(integration_id: str, user: User, db: AsyncSession) -> Tuple[Integration, HomeAccess]:
    integration = await db.get(Integration, integration_id)
    if integration is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")
    access = await load_home_access(integration.home_id, user, db)
    return integration, access


def webhook_path(request: Optional[Request], route_name: str, **params: str) -> str:
    """Path of a webhook route with the prefix the hub is mounted under (falls back to ``/api/v1/hub``)."""
    if request is not None:
        try:
            return str(request.app.url_path_for(route_name, **params))
        except Exception:  # pylint: disable=broad-except
            logger.debug("Could not resolve route %s from the app, using the default prefix", route_name)
    if route_name == GENERIC_WEBHOOK_ROUTE:
        return f"{HUB_PREFIX}/webhooks/{GENERIC_BRAND}/{params.get('device_id', '')}"
    return f"{HUB_PREFIX}/webhooks/{params.get('brand', '')}/{params.get('integration_id', '')}"


def _webhook_out(request: Request, route_name: str, secret: str, brand: str, **params: str) -> WebhookUrlOut:
    route_params = dict(params)
    if route_name == BRAND_WEBHOOK_ROUTE:
        route_params["brand"] = brand
    path = webhook_path(request, route_name, **route_params)
    try:
        absolute = str(request.url_for(route_name, **route_params))
    except Exception:  # pylint: disable=broad-except
        absolute = path
    query = "?secret=" + quote(secret, safe="")
    return WebhookUrlOut(
        url=path + query, absolute_url=absolute + query, secret=secret, brand=brand,
        integration_id=params.get("integration_id"), device_id=params.get("device_id"),
    )


# ----------------------------------------------------------------------------- code parsing
def _matter_parser() -> Any:
    """``matter_payload.parse_onboarding_code`` when the Matter workstream is present, else None."""
    try:
        from app.hub.adapters.matter_payload import parse_onboarding_code  # pylint: disable=import-outside-toplevel
    except ImportError:
        return None
    return parse_onboarding_code


def _parse_matter(text: str) -> Optional[Dict[str, Any]]:
    parser = _matter_parser()
    if parser is None:
        return None
    try:
        parsed = parser(text)
    except Exception:  # pylint: disable=broad-except
        logger.debug("Matter parser rejected %r", text[:32], exc_info=True)
        return None
    if not isinstance(parsed, dict) or parsed.get("kind") not in MATTER_METHODS:
        return None
    return parsed


def _split_url(text: str) -> Optional[Dict[str, Any]]:
    parts = urlsplit(text)
    if parts.scheme.lower() not in URL_SCHEMES or not parts.netloc:
        return None
    try:
        port = parts.port
    except ValueError:
        port = None
    return {
        "url": text, "scheme": parts.scheme.lower(), "host": (parts.hostname or "").lower(), "port": port,
        "path": parts.path, "query": dict(parse_qsl(parts.query, keep_blank_values=True)),
    }


def _parse_json_object(text: str) -> Optional[Dict[str, Any]]:
    if not text.startswith("{"):
        return None
    try:
        value = json.loads(text)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _parse_tuya(text: str, url: Optional[Dict[str, Any]], obj: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Tuya app share/link codes: a ``*tuya*`` URL or a JSON document with a ``t``/``token`` key."""
    if "tuya" not in text.lower():
        return None
    if url is not None:
        query = url["query"]
        token = next((query[key] for key in TUYA_TOKEN_KEYS if query.get(key)), None)
        return {"url": text, "host": url["host"], "path": url["path"], "query": query, "token": token}
    if obj is not None and ("t" in obj or "token" in obj):
        data = dict(obj)
        data["token"] = obj.get("token") or obj.get("t")
        return data
    return None


def parse_code(code: str) -> ParseCodeOut:
    """Classify a scanned/typed code. Never raises: anything unrecognised is ``kind="unknown"``."""
    text = (code or "").strip()
    if not text:
        return ParseCodeOut(kind="unknown", data={"code": ""})
    try:
        matter = _parse_matter(text)
        if matter is not None:
            return ParseCodeOut(kind=matter["kind"], brand="matter", method=MATTER_METHODS[matter["kind"]], data=matter)
        url = _split_url(text)
        obj = _parse_json_object(text) if url is None else None
        tuya = _parse_tuya(text, url, obj)
        if tuya is not None:
            return ParseCodeOut(kind="tuya_qr", brand=TUYA_BRAND, method=TUYA_METHOD, data=tuya)
        if url is not None:
            return ParseCodeOut(kind="url", data=url)
        data: Dict[str, Any] = {"code": text}
        if obj is not None:
            data["json"] = obj
        return ParseCodeOut(kind="unknown", data=data)
    except Exception:  # pylint: disable=broad-except
        logger.exception("parse-code failed for a %d-character code", len(text))
        return ParseCodeOut(kind="unknown", data={"code": text})


# ----------------------------------------------------------------------------- catalogue
@router.get("/onboarding/brands", response_model=List[BrandInfo])
async def list_brands(_: User = Depends(get_current_user)) -> List[BrandInfo]:
    """Brand catalogue (pairing methods + form fields) for the "Add device" screen."""
    infos: List[BrandInfo] = []
    for adapter in visible_adapters():
        info = _brand_info(adapter)
        if info is not None:
            infos.append(info)
    return infos


@router.get("/onboarding/brands/{brand}", response_model=BrandInfo)
async def get_brand(brand: str, _: User = Depends(get_current_user)) -> BrandInfo:
    """One brand (404 unknown or hidden demo brand)."""
    return _adapter_or_404(brand).info()


@router.get("/onboarding/categories", response_model=List[CategoryGroupOut])
async def list_categories(_: User = Depends(get_current_user)) -> List[CategoryGroupOut]:
    """Category grid for "Add manually": groups in display order, each category with the brands supporting it."""
    return build_category_catalog(visible_adapters())


@router.post("/onboarding/parse-code", response_model=ParseCodeOut)
async def parse_onboarding_code(body: ParseCodeIn, _: User = Depends(get_current_user)) -> ParseCodeOut:
    """Classify a scanned QR / typed code: matter_qr | matter_manual | tuya_qr | url | unknown."""
    return parse_code(body.code)


# ----------------------------------------------------------------------------- discovery / pairing
@router.post("/onboarding/{brand}/discover", response_model=List[DiscoveredDevice])
async def discover_devices(
    brand: str, body: DiscoverIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> List[DiscoveredDevice]:
    """Find devices without pairing them (any member of the home). 404 unknown brand, 400 unknown method."""
    access = await load_home_access(body.home_id, user, db)
    adapter = _adapter_or_404(brand)
    method = adapter.method(body.method)
    found = await _guard(adapter.discover(body.method, dict(body.payload), get_runtime().ctx_for(brand)), brand)
    logger.info("Discovery %s/%s for home %s by %s: %d device(s)", brand, method.id, access.home.id, user.id, len(found))
    return list(found)


@router.post("/onboarding/{brand}/pair", response_model=PairOut, status_code=status.HTTP_201_CREATED)
async def pair_devices(
    brand: str, body: PairIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> PairOut:
    """Pair devices into a home (admin/owner): upserts devices + integration, posts "Nouvel appareil" messages.

    ``selected_external_ids`` restricts the persisted devices (parents of selected children are kept) and is
    also forwarded to the adapter inside ``payload``. 400 when nothing was found / the room is foreign.
    """
    access = await load_home_access(body.home_id, user, db)
    access.require("admin")
    adapter = _adapter_or_404(brand)
    adapter.method(body.method)
    room = await _resolve_room(db, body.room_id, access.home.id) if body.room_id else None
    selected = _clean_ids(body.selected_external_ids)
    payload = dict(body.payload)
    if selected is not None:
        payload["selected_external_ids"] = list(selected)

    result = await _guard(adapter.pair(body.method, payload, get_runtime().ctx_for(brand)), brand)
    if not result.devices:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=NO_DEVICES)

    existing = set(
        (await db.execute(select(Device.external_id).where(Device.home_id == access.home.id, Device.brand == brand))).scalars().all()
    )
    service = _device_service()
    devices, integration = await service.materialize(db, access.home.id, room.id if room else None, brand, result, selected)
    if not devices:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=NO_SELECTED_DEVICES)
    if integration is not None and not integration.webhook_secret:
        integration.webhook_secret = _new_secret()
        await db.commit()

    created = [device for device in devices if device.external_id not in existing]
    if created:
        info = _brand_info(adapter)
        brand_name = info.name if info is not None else brand
        where = f"{access.home.name}" + (f" ({room.name})" if room else "")
        for device in created:
            await service.create_message(
                db, access.home.id, "home", f"Nouvel appareil: {device.name}",
                f"{device.name} ({brand_name}) a été ajouté à {where}.", device_id=device.id, severity="info", publish=True,
            )
        await db.commit()
    logger.info(
        "Paired %d device(s) (%d new) of brand %s into home %s by %s", len(devices), len(created), brand, access.home.id, user.id
    )
    return PairOut(
        devices=[DeviceOut.model_validate(device) for device in devices],
        integration_id=integration.id if integration is not None else None,
        message=result.message or _pair_message(len(created), len(devices) - len(created)),
    )


# ----------------------------------------------------------------------------- integrations
@router.get("/homes/{home_id}/integrations", response_model=List[IntegrationOut])
async def list_integrations(access: HomeAccess = Depends(home_access), db: AsyncSession = Depends(get_db)) -> List[IntegrationOut]:
    """Integrations (cloud accounts, servers, panels) of a home, oldest first. Credentials are never returned."""
    rows = (
        await db.execute(
            select(Integration).where(Integration.home_id == access.home.id).order_by(Integration.created_at, Integration.name)
        )
    ).scalars().all()
    return [IntegrationOut.model_validate(integration) for integration in rows]


@router.delete("/integrations/{integration_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_integration(
    integration_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> Response:
    """Remove an integration and every device it brought (children included; adapters get ``unpair``). Admin/owner."""
    integration, access = await _load_integration(integration_id, user, db)
    access.require("admin")
    service = _device_service()
    rows = (await db.execute(select(Device).where(Device.integration_id == integration.id))).scalars().all()
    children: Dict[Optional[str], List[Device]] = {}
    for device in rows:
        children.setdefault(device.parent_id, []).append(device)
    removed: Set[str] = set()
    for device in sorted(rows, key=lambda d: 0 if d.parent_id is None else 1):
        if device.id in removed:
            continue
        # ``DeviceService.remove`` deletes direct children; mark the whole subtree so we never delete twice.
        stack = [device.id]
        while stack:
            current = stack.pop()
            removed.add(current)
            stack.extend(child.id for child in children.get(current, []))
        await service.remove(db, device)
    await db.delete(integration)
    await db.commit()
    logger.info("Integration %s (%s) removed with %d device(s) by %s", integration_id, integration.brand, len(rows), user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/integrations/{integration_id}/webhook", response_model=WebhookUrlOut)
async def integration_webhook(
    integration_id: str, request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> WebhookUrlOut:
    """Webhook URL (with secret) a brand cloud must call for this integration; the secret is created on demand."""
    integration, access = await _load_integration(integration_id, user, db)
    access.require("admin")
    if not integration.webhook_secret:
        integration.webhook_secret = _new_secret()
        await db.commit()
    return _webhook_out(request, BRAND_WEBHOOK_ROUTE, integration.webhook_secret, integration.brand, integration_id=integration.id)


@router.post("/integrations/{integration_id}/webhook/rotate", response_model=WebhookUrlOut)
async def rotate_integration_webhook(
    integration_id: str, request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> WebhookUrlOut:
    """Replace the webhook secret (previous URL stops working immediately). Admin/owner."""
    integration, access = await _load_integration(integration_id, user, db)
    access.require("admin")
    integration.webhook_secret = _new_secret()
    await db.commit()
    logger.info("Webhook secret rotated for integration %s by %s", integration_id, user.id)
    return _webhook_out(request, BRAND_WEBHOOK_ROUTE, integration.webhook_secret, integration.brand, integration_id=integration.id)


@router.get("/devices/{device_id}/webhook", response_model=WebhookUrlOut)
async def device_webhook(
    request: Request, ctx: DeviceAccess = Depends(device_access), db: AsyncSession = Depends(get_db)
) -> WebhookUrlOut:
    """Generic webhook URL for one device (``config.webhook_secret`` is created on demand). Admin/owner."""
    ctx.access.require("admin")
    device = ctx.device
    config = dict(device.config or {})
    secret = config.get("webhook_secret")
    if not secret:
        secret = _new_secret()
        config["webhook_secret"] = secret
        device.config = config
        await db.commit()
    return _webhook_out(request, GENERIC_WEBHOOK_ROUTE, secret, GENERIC_BRAND, device_id=device.id)
