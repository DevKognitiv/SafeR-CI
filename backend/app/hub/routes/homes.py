"""Homes, rooms, members and weather routes (paths declared in full: ``/homes/...`` and ``/rooms/...``)."""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Sequence, Tuple

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.functions import count

from app.hub import events as ev
from app.hub.deps import ROLE_RANK, HomeAccess, get_current_user, get_db, home_access, load_home_access
from app.hub.models import (
    Automation, Device, DeviceEvent, Home, HomeMember, Integration, Message, Room, Scene, SosAlert, User,
)
from app.hub.runtime import get_runtime
from app.hub.schemas import (
    HomeCreate, HomeOut, HomeUpdate, MemberCreate, MemberOut, MemberUpdate, ReorderIn, RoomCreate, RoomOut,
    RoomUpdate, WeatherOut,
)
from app.hub.services.device_service import DeviceService
from app.hub.services.weather import get_weather

logger = logging.getLogger("safer.hub.homes")

router = APIRouter()

__all__ = ["router", "home_to_out", "homes_to_out", "room_to_out", "rooms_for_home"]


# ----------------------------------------------------------------------------- helpers
def _device_service() -> DeviceService:
    runtime = get_runtime()
    service = runtime.services.get("devices")
    if service is None:
        service = DeviceService(runtime)
        runtime.services["devices"] = service
    return service


def _display_name(user: User) -> str:
    return (user.name or "").strip() or user.email


def room_to_out(room: Room, device_count: int = 0) -> RoomOut:
    """Serialise a room with its device count."""
    return RoomOut(
        id=room.id, home_id=room.home_id, name=room.name, icon=room.icon, sort_order=room.sort_order or 0,
        device_count=device_count,
    )


async def _device_counts(session: AsyncSession, home_ids: Sequence[str]) -> Dict[str, Dict[Optional[str], int]]:
    """``{home_id: {room_id|None: count}}`` for the given homes."""
    counts: Dict[str, Dict[Optional[str], int]] = {home_id: {} for home_id in home_ids}
    if not home_ids:
        return counts
    rows = await session.execute(
        select(Device.home_id, Device.room_id, count(Device.id))
        .where(Device.home_id.in_(list(home_ids)))
        .group_by(Device.home_id, Device.room_id)
    )
    for home_id, room_id, total in rows.all():
        counts.setdefault(home_id, {})[room_id] = int(total)
    return counts


async def _member_counts(session: AsyncSession, home_ids: Sequence[str]) -> Dict[str, int]:
    if not home_ids:
        return {}
    rows = await session.execute(
        select(HomeMember.home_id, count(HomeMember.id))
        .where(HomeMember.home_id.in_(list(home_ids)))
        .group_by(HomeMember.home_id)
    )
    return {home_id: int(total) for home_id, total in rows.all()}


async def _rooms_by_home(session: AsyncSession, home_ids: Sequence[str]) -> Dict[str, List[Room]]:
    rooms: Dict[str, List[Room]] = {home_id: [] for home_id in home_ids}
    if not home_ids:
        return rooms
    rows = await session.execute(
        select(Room).where(Room.home_id.in_(list(home_ids))).order_by(Room.sort_order, Room.created_at, Room.name)
    )
    for room in rows.scalars().all():
        rooms.setdefault(room.home_id, []).append(room)
    return rooms


async def rooms_for_home(session: AsyncSession, home_id: str) -> List[RoomOut]:
    """Sorted rooms of a home, each with its device count."""
    rooms = (await _rooms_by_home(session, [home_id]))[home_id]
    counts = (await _device_counts(session, [home_id]))[home_id]
    return [room_to_out(room, counts.get(room.id, 0)) for room in rooms]


async def homes_to_out(session: AsyncSession, pairs: Sequence[Tuple[Home, Optional[HomeMember]]]) -> List[HomeOut]:
    """Serialise several ``(home, membership)`` pairs with three grouped queries."""
    home_ids = [home.id for home, _ in pairs]
    rooms = await _rooms_by_home(session, home_ids)
    device_counts = await _device_counts(session, home_ids)
    member_counts = await _member_counts(session, home_ids)
    result: List[HomeOut] = []
    for home, member in pairs:
        per_room = device_counts.get(home.id, {})
        result.append(
            HomeOut(
                id=home.id,
                name=home.name,
                lat=home.lat,
                lon=home.lon,
                address=home.address,
                security_mode=home.security_mode or "disarmed",
                alarm_active=bool(home.alarm_active),
                role=member.role if member is not None else "member",
                rooms=[room_to_out(room, per_room.get(room.id, 0)) for room in rooms.get(home.id, [])],
                member_count=member_counts.get(home.id, 0),
                device_count=sum(per_room.values()),
                created_at=home.created_at,
            )
        )
    return result


async def home_to_out(session: AsyncSession, home: Home, member: Optional[HomeMember]) -> HomeOut:
    """Build the API representation of a home for ``member`` (role, rooms, member/device counts).

    Never touches lazy relationships, so it is safe with ``db.get(Home, ...)`` rows in async sessions.
    """
    return (await homes_to_out(session, [(home, member)]))[0]


async def _load_room(room_id: str, user: User, db: AsyncSession) -> Tuple[Room, HomeAccess]:
    """Room + the caller's access to its home (404 for unknown rooms or homes the caller is not in)."""
    room = await db.get(Room, room_id)
    if room is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    access = await load_home_access(room.home_id, user, db)
    return room, access


async def _room_device_count(db: AsyncSession, room_id: str) -> int:
    return int((await db.execute(select(count()).select_from(Device).where(Device.room_id == room_id))).scalar_one())


async def _load_member(db: AsyncSession, home_id: str, user_id: str) -> Tuple[HomeMember, User]:
    row = (
        await db.execute(
            select(HomeMember, User)
            .join(User, User.id == HomeMember.user_id)
            .where(HomeMember.home_id == home_id, HomeMember.user_id == user_id)
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    return row[0], row[1]


def _member_out(member: HomeMember, user: User) -> MemberOut:
    return MemberOut(
        user_id=user.id, email=user.email, name=user.name or "", role=member.role, avatar_url=user.avatar_url,
        joined_at=member.created_at,
    )


async def _notify_home(db: AsyncSession, home: Home, title: str, body: str) -> None:
    """Message-center entry (kind ``home``) + ``message.new`` on the bus."""
    await _device_service().create_message(db, home.id, "home", title, body, severity="info", publish=True)
    await db.commit()


def _clean_name(value: str, what: str) -> str:
    name = (value or "").strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{what} name is required")
    return name


# ----------------------------------------------------------------------------- homes
@router.post("/homes", response_model=HomeOut, status_code=status.HTTP_201_CREATED)
async def create_home(body: HomeCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> HomeOut:
    """Create a home; the caller becomes its owner and ``rooms`` are created in order."""
    home = Home(name=_clean_name(body.name, "Home"), lat=body.lat, lon=body.lon, address=body.address, created_by=user.id)
    db.add(home)
    await db.flush()
    member = HomeMember(home_id=home.id, user_id=user.id, role="owner")
    db.add(member)
    position = 0
    for room_name in body.rooms:
        room_name = (room_name or "").strip()
        if not room_name:
            continue
        db.add(Room(home_id=home.id, name=room_name, sort_order=position))
        position += 1
    await db.commit()
    logger.info("Home %s created by %s with %d room(s)", home.id, user.id, position)
    return await home_to_out(db, home, member)


@router.get("/homes", response_model=List[HomeOut])
async def list_homes(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> List[HomeOut]:
    """Homes the caller is a member of."""
    rows = await db.execute(
        select(Home, HomeMember)
        .join(HomeMember, HomeMember.home_id == Home.id)
        .where(HomeMember.user_id == user.id)
        .order_by(Home.created_at, Home.name)
    )
    return await homes_to_out(db, [(home, member) for home, member in rows.all()])


@router.get("/homes/{home_id}", response_model=HomeOut)
async def get_home(access: HomeAccess = Depends(home_access), db: AsyncSession = Depends(get_db)) -> HomeOut:
    """One home (404 unless the caller is a member)."""
    return await home_to_out(db, access.home, access.member)


@router.patch("/homes/{home_id}", response_model=HomeOut)
async def update_home(body: HomeUpdate, access: HomeAccess = Depends(home_access), db: AsyncSession = Depends(get_db)) -> HomeOut:
    """Update name / location (admin or owner)."""
    access.require("admin")
    changes = body.model_dump(exclude_unset=True)
    if "name" in changes:
        changes["name"] = _clean_name(changes["name"], "Home")
    for field, value in changes.items():
        setattr(access.home, field, value)
    await db.commit()
    return await home_to_out(db, access.home, access.member)


@router.delete("/homes/{home_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_home(access: HomeAccess = Depends(home_access), db: AsyncSession = Depends(get_db)) -> Response:
    """Delete a home and everything in it (owner only)."""
    access.require("owner")
    home_id = access.home.id
    # Explicit cascade: SQLite does not enforce ON DELETE unless foreign keys are switched on.
    for model in (DeviceEvent, Device, Integration, Scene, Automation, Message, SosAlert, Room, HomeMember):
        await db.execute(delete(model).where(model.home_id == home_id))
    await db.execute(delete(Home).where(Home.id == home_id))
    await db.commit()
    # Every open WebSocket stops receiving this home (user_id None = everyone).
    await get_runtime().bus.publish(ev.HubEvent(ev.MEMBER_REMOVED, home_id=home_id, payload={"user_id": None}))
    logger.info("Home %s deleted by %s", home_id, access.user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ----------------------------------------------------------------------------- rooms
@router.get("/homes/{home_id}/rooms", response_model=List[RoomOut])
async def list_rooms(access: HomeAccess = Depends(home_access), db: AsyncSession = Depends(get_db)) -> List[RoomOut]:
    """Rooms of a home, sorted, with device counts."""
    return await rooms_for_home(db, access.home.id)


@router.post("/homes/{home_id}/rooms", response_model=RoomOut, status_code=status.HTTP_201_CREATED)
async def create_room(body: RoomCreate, access: HomeAccess = Depends(home_access), db: AsyncSession = Depends(get_db)) -> RoomOut:
    """Add a room at the end of the list (admin or owner)."""
    access.require("admin")
    last = (await db.execute(select(func.max(Room.sort_order)).where(Room.home_id == access.home.id))).scalar_one()
    room = Room(home_id=access.home.id, name=_clean_name(body.name, "Room"), icon=body.icon, sort_order=(last if last is not None else -1) + 1)
    db.add(room)
    await db.commit()
    return room_to_out(room, 0)


@router.patch("/rooms/{room_id}", response_model=RoomOut)
async def update_room(
    room_id: str, body: RoomUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> RoomOut:
    """Rename / re-icon / reposition a room (admin or owner of its home)."""
    room, access = await _load_room(room_id, user, db)
    access.require("admin")
    changes = body.model_dump(exclude_unset=True)
    if "name" in changes:
        changes["name"] = _clean_name(changes["name"], "Room")
    for field, value in changes.items():
        setattr(room, field, value)
    await db.commit()
    return room_to_out(room, await _room_device_count(db, room.id))


@router.delete("/rooms/{room_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_room(room_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> Response:
    """Delete a room; its devices stay in the home without a room (admin or owner)."""
    room, access = await _load_room(room_id, user, db)
    access.require("admin")
    await db.execute(update(Device).where(Device.room_id == room.id).values(room_id=None))
    await db.delete(room)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/homes/{home_id}/rooms/reorder", response_model=List[RoomOut])
async def reorder_rooms(body: ReorderIn, access: HomeAccess = Depends(home_access), db: AsyncSession = Depends(get_db)) -> List[RoomOut]:
    """Apply a new order: listed ids first (in order), the others keep their relative order after them."""
    access.require("admin")
    rooms = (await _rooms_by_home(db, [access.home.id]))[access.home.id]
    by_id = {room.id: room for room in rooms}
    unknown = [room_id for room_id in body.ids if room_id not in by_id]
    if unknown:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown room id(s): {', '.join(unknown)}")
    ordered = list(dict.fromkeys(body.ids))
    listed = set(ordered)
    ordered.extend(room.id for room in rooms if room.id not in listed)
    for position, room_id in enumerate(ordered):
        by_id[room_id].sort_order = position
    await db.commit()
    return await rooms_for_home(db, access.home.id)


# ----------------------------------------------------------------------------- members
@router.get("/homes/{home_id}/members", response_model=List[MemberOut])
async def list_members(access: HomeAccess = Depends(home_access), db: AsyncSession = Depends(get_db)) -> List[MemberOut]:
    """Members of a home (owner first, then admins, then members by join date)."""
    rows = (
        await db.execute(
            select(HomeMember, User).join(User, User.id == HomeMember.user_id).where(HomeMember.home_id == access.home.id)
        )
    ).all()
    rows.sort(key=lambda row: (-ROLE_RANK.get(row[0].role, 0), row[0].created_at, row[1].email))
    return [_member_out(member, user) for member, user in rows]


@router.post("/homes/{home_id}/members", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
async def add_member(body: MemberCreate, access: HomeAccess = Depends(home_access), db: AsyncSession = Depends(get_db)) -> MemberOut:
    """Add an existing hub user to the home (admin or owner). 404 unknown e-mail, 409 already a member."""
    access.require("admin")
    target = (await db.execute(select(User).where(User.email == body.email))).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    existing = (
        await db.execute(select(HomeMember).where(HomeMember.home_id == access.home.id, HomeMember.user_id == target.id))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already a member of this home")
    member = HomeMember(home_id=access.home.id, user_id=target.id, role=body.role)
    db.add(member)
    await db.commit()
    name = _display_name(target)
    await _notify_home(
        db, access.home, f"Nouveau membre: {name}",
        f"{name} a rejoint {access.home.name} (rôle: {body.role}), ajouté par {_display_name(access.user)}.",
    )
    logger.info("User %s added to home %s as %s by %s", target.id, access.home.id, body.role, access.user.id)
    return _member_out(member, target)


@router.patch("/homes/{home_id}/members/{user_id}", response_model=MemberOut)
async def update_member(
    user_id: str, body: MemberUpdate, access: HomeAccess = Depends(home_access), db: AsyncSession = Depends(get_db)
) -> MemberOut:
    """Change a member's role (owner only). Giving ``owner`` transfers ownership and demotes the caller to admin."""
    access.require("owner")
    member, target = await _load_member(db, access.home.id, user_id)
    if body.role == "owner":
        if member.user_id != access.user.id:
            access.member.role = "admin"
            member.role = "owner"
            logger.info("Ownership of home %s transferred from %s to %s", access.home.id, access.user.id, target.id)
    else:
        if member.user_id == access.user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Transfer ownership to another member before changing your own role"
            )
        member.role = body.role
    await db.commit()
    return _member_out(member, target)


@router.delete("/homes/{home_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def remove_member(
    user_id: str, access: HomeAccess = Depends(home_access), db: AsyncSession = Depends(get_db)
) -> Response:
    """Remove a member (admin/owner) or leave the home yourself. The owner can never be removed."""
    member, target = await _load_member(db, access.home.id, user_id)
    self_leave = member.user_id == access.user.id
    if member.role == "owner":
        detail = "The owner cannot leave the home; transfer ownership first" if self_leave else "The owner cannot be removed"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
    if not self_leave:
        access.require("admin")
        if member.role == "admin" and access.role != "owner":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the owner can remove an admin")
    await db.delete(member)
    await db.commit()
    # Revoke the realtime feed before the "member removed" notice so the removed user never receives it.
    await get_runtime().bus.publish(ev.HubEvent(ev.MEMBER_REMOVED, home_id=access.home.id, payload={"user_id": target.id}))
    name = _display_name(target)
    if self_leave:
        await _notify_home(db, access.home, f"Membre parti: {name}", f"{name} a quitté {access.home.name}.")
    else:
        await _notify_home(
            db, access.home, f"Membre retiré: {name}",
            f"{name} a été retiré de {access.home.name} par {_display_name(access.user)}.",
        )
    logger.info("User %s removed from home %s by %s", target.id, access.home.id, access.user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ----------------------------------------------------------------------------- weather
@router.get("/homes/{home_id}/weather", response_model=WeatherOut)
async def home_weather(access: HomeAccess = Depends(home_access)) -> WeatherOut:
    """Current weather at the home's coordinates (``available=False`` when disabled/unknown/offline)."""
    runtime = get_runtime()
    return await get_weather(access.home.lat, access.home.lon, runtime.ctx_for("weather"))
