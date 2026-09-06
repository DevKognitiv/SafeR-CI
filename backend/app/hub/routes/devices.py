"""Device routes: list / get / update / delete, refresh, commands, stream, snapshot, events, children.

Paths are declared in full (``/homes/{home_id}/devices`` and ``/devices/{device_id}/...``); the hub router
mounts them under ``/api/v1/hub``. Every route checks home membership through ``deps`` and every adapter
interaction goes through ``DeviceService`` so events, messages and the software alarm stay consistent.
``AdapterError`` is left to the application-level handler (400/401/404/501/502).
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.hub.adapters.base import AdapterError, StreamInfo
from app.hub.capabilities import coerce_value, find_capability
from app.hub.deps import DeviceAccess, HomeAccess, device_access, get_db, home_access
from app.hub.models import Device, DeviceEvent, Room
from app.hub.runtime import get_runtime
from app.hub.schemas import CommandsIn, DeviceEventOut, DeviceOut, DeviceUpdate
from app.hub.services.device_service import DeviceService

logger = logging.getLogger("safer.hub.routes.devices")

router = APIRouter()

__all__ = ["router", "device_to_out"]

MAX_EVENT_LIMIT = 200
DEFAULT_EVENT_LIMIT = 50


# ----------------------------------------------------------------------------- helpers
def _device_service() -> DeviceService:
    runtime = get_runtime()
    service = runtime.services.get("devices")
    if service is None:
        service = DeviceService(runtime)
        runtime.services["devices"] = service
    return service


def device_to_out(device: Device) -> DeviceOut:
    """API representation of a device (credentials are never included)."""
    return DeviceOut.model_validate(device)


async def _resolve_room(db: AsyncSession, room_id: str, home_id: str) -> Room:
    """Room by id, 400 unless it belongs to ``home_id``."""
    room = await db.get(Room, room_id)
    if room is None or room.home_id != home_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Room does not belong to this home")
    return room


def _prepare_commands(device: Device, body: CommandsIn) -> List[Tuple[str, Any]]:
    """Validate every command against the device capabilities before anything is executed.

    Raises ``AdapterError(invalid_input)`` (-> 400) for unknown codes, read-only capabilities and bad values,
    so a faulty second command never leaves the first one half applied.
    """
    prepared: List[Tuple[str, Any]] = []
    capabilities = device.capabilities or []
    for command in body.commands:
        capability = find_capability(capabilities, command.code)
        if capability is None:
            raise AdapterError(f"Unknown capability '{command.code}'", "invalid_input")
        if not capability.get("writable"):
            raise AdapterError(f"Capability '{command.code}' is read-only", "invalid_input")
        try:
            value = coerce_value(capability, command.value)
        except ValueError as exc:
            raise AdapterError(str(exc), "invalid_input") from exc
        prepared.append((command.code, value))
    return prepared


# ----------------------------------------------------------------------------- listing
@router.get("/homes/{home_id}/devices", response_model=List[DeviceOut])
async def list_devices(
    room_id: Optional[str] = Query(default=None, description="Only devices in this room"),
    category: Optional[str] = Query(default=None, description="Only devices of this category"),
    brand: Optional[str] = Query(default=None, description="Only devices of this brand"),
    access: HomeAccess = Depends(home_access),
    db: AsyncSession = Depends(get_db),
) -> List[DeviceOut]:
    """Devices of a home (oldest first), optionally filtered by room, category and brand."""
    query = select(Device).where(Device.home_id == access.home.id)
    if room_id:
        query = query.where(Device.room_id == room_id)
    if category:
        query = query.where(Device.category == category)
    if brand:
        query = query.where(Device.brand == brand)
    rows = (await db.execute(query.order_by(Device.created_at, Device.name))).scalars().all()
    return [device_to_out(device) for device in rows]


@router.get("/devices/{device_id}", response_model=DeviceOut)
async def get_device(ctx: DeviceAccess = Depends(device_access)) -> DeviceOut:
    """One device (404 unless the caller is a member of its home)."""
    return device_to_out(ctx.device)


# ----------------------------------------------------------------------------- management
@router.patch("/devices/{device_id}", response_model=DeviceOut)
async def update_device(
    body: DeviceUpdate, ctx: DeviceAccess = Depends(device_access), db: AsyncSession = Depends(get_db)
) -> DeviceOut:
    """Rename / re-icon / move a device to a room of the same home (admin or owner).

    ``clear_room`` (or an explicit ``"room_id": null``) detaches the device from its room.
    """
    ctx.access.require("admin")
    device = ctx.device
    changes = body.model_dump(exclude_unset=True)
    if "name" in changes:
        name = (changes["name"] or "").strip()
        if not name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Device name is required")
        device.name = name
    if "icon" in changes:
        device.icon = (changes["icon"] or "").strip() or None
    if changes.get("clear_room") or ("room_id" in changes and changes["room_id"] is None):
        device.room_id = None
    elif changes.get("room_id"):
        room = await _resolve_room(db, changes["room_id"], device.home_id)
        device.room_id = room.id
    await db.commit()
    logger.info("Device %s updated by %s (%s)", device.id, ctx.access.user.id, ", ".join(sorted(changes)))
    return device_to_out(device)


@router.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_device(ctx: DeviceAccess = Depends(device_access), db: AsyncSession = Depends(get_db)) -> Response:
    """Unpair (best effort) and delete a device together with its children (admin or owner)."""
    ctx.access.require("admin")
    device_id, brand, external_id = ctx.device.id, ctx.device.brand, ctx.device.external_id
    await _device_service().remove(db, ctx.device)
    logger.info("Device %s (%s/%s) removed by %s", device_id, brand, external_id, ctx.access.user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ----------------------------------------------------------------------------- adapter operations
@router.post("/devices/{device_id}/refresh", response_model=DeviceOut)
async def refresh_device(ctx: DeviceAccess = Depends(device_access), db: AsyncSession = Depends(get_db)) -> DeviceOut:
    """Read fresh state from the adapter and apply it (an unreachable device is marked offline -> 502)."""
    device = await _device_service().refresh(db, ctx.device)
    return device_to_out(device)


@router.post("/devices/{device_id}/commands", response_model=DeviceOut)
async def send_commands(
    body: CommandsIn, ctx: DeviceAccess = Depends(device_access), db: AsyncSession = Depends(get_db)
) -> DeviceOut:
    """Execute commands in order (any member). Values are validated against the capabilities first."""
    device = ctx.device
    prepared = _prepare_commands(device, body)
    service = _device_service()
    for code, value in prepared:
        device = await service.command(db, device, code, value)
    return device_to_out(device)


@router.get("/devices/{device_id}/stream", response_model=StreamInfo)
async def device_stream(
    quality: str = Query(default="main", pattern="^(main|sub)$"),
    ctx: DeviceAccess = Depends(device_access),
    db: AsyncSession = Depends(get_db),
) -> StreamInfo:
    """How to play the main/sub stream of a camera (404 when the device has no stream)."""
    info = await _device_service().stream(db, ctx.device, quality)
    if info is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No stream available for this device")
    return info


@router.get(
    "/devices/{device_id}/snapshot",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}}, "description": "JPEG snapshot"}, 404: {"description": "No snapshot"}},
)
async def device_snapshot(ctx: DeviceAccess = Depends(device_access), db: AsyncSession = Depends(get_db)) -> Response:
    """Current JPEG snapshot of a camera (404 when the device has none)."""
    data = await _device_service().snapshot(db, ctx.device)
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No snapshot available for this device")
    return Response(content=data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


# ----------------------------------------------------------------------------- history / hierarchy
@router.get("/devices/{device_id}/events", response_model=List[DeviceEventOut])
async def device_events(
    limit: int = Query(default=DEFAULT_EVENT_LIMIT, ge=1, le=MAX_EVENT_LIMIT),
    event_type: Optional[str] = Query(default=None, alias="type", description="Only events of this type"),
    ctx: DeviceAccess = Depends(device_access),
    db: AsyncSession = Depends(get_db),
) -> List[DeviceEventOut]:
    """Recent notable events of a device, newest first (``limit`` <= 200)."""
    query = select(DeviceEvent).where(DeviceEvent.device_id == ctx.device.id)
    if event_type:
        query = query.where(DeviceEvent.type == event_type)
    rows = (
        await db.execute(query.order_by(DeviceEvent.created_at.desc(), DeviceEvent.id.desc()).limit(limit))
    ).scalars().all()
    return [DeviceEventOut.model_validate(event) for event in rows]


@router.get("/devices/{device_id}/children", response_model=List[DeviceOut])
async def device_children(ctx: DeviceAccess = Depends(device_access), db: AsyncSession = Depends(get_db)) -> List[DeviceOut]:
    """Child devices (NVR channels, alarm zones...) of a device, oldest first."""
    rows = (
        await db.execute(
            select(Device).where(Device.parent_id == ctx.device.id).order_by(Device.created_at, Device.name)
        )
    ).scalars().all()
    return [device_to_out(device) for device in rows]
