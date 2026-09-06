"""FastAPI dependencies: db session, current user, home/device access checks."""
from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator, Optional

from fastapi import Depends, HTTPException, WebSocket, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.hub.models import Device, Home, HomeMember, User
from app.hub.runtime import HubRuntime, get_runtime
from app.hub.security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)

ROLE_RANK = {"member": 1, "admin": 2, "owner": 3}


def runtime_dep() -> HubRuntime:
    """Runtime dependency."""
    return get_runtime()


async def get_db() -> AsyncIterator[AsyncSession]:
    """Per-request database session."""
    async with get_runtime().db.session() as session:
        yield session


async def user_from_token(token: Optional[str], db: AsyncSession) -> Optional[User]:
    """Resolve a user from a raw bearer token (also used by the WebSocket route)."""
    if not token:
        return None
    user_id = decode_access_token(token, get_runtime().settings.SECRET_KEY)
    if not user_id:
        return None
    return await db.get(User, user_id)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Authenticated user or 401."""
    user = await user_from_token(credentials.credentials if credentials else None, db)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


@dataclass
class HomeAccess:
    """Home + the caller's membership."""

    home: Home
    member: HomeMember
    user: User

    @property
    def role(self) -> str:
        return self.member.role

    def require(self, *roles: str) -> None:
        """403 unless the caller has one of ``roles`` (or a higher one)."""
        needed = min(ROLE_RANK.get(r, 99) for r in roles) if roles else 1
        if ROLE_RANK.get(self.member.role, 0) < needed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role for this home")


async def load_home_access(home_id: str, user: User, db: AsyncSession) -> HomeAccess:
    """Load a home and verify membership (404 if the home is invisible to the caller)."""
    home = await db.get(Home, home_id)
    if home is None:
        raise HTTPException(status_code=404, detail="Home not found")
    member = (
        await db.execute(select(HomeMember).where(HomeMember.home_id == home_id, HomeMember.user_id == user.id))
    ).scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="Home not found")
    return HomeAccess(home=home, member=member, user=user)


async def home_access(
    home_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> HomeAccess:
    """Dependency for ``/homes/{home_id}/...`` routes."""
    return await load_home_access(home_id, user, db)


@dataclass
class DeviceAccess:
    """Device + home access of the caller."""

    device: Device
    access: HomeAccess


async def device_access(
    device_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> DeviceAccess:
    """Dependency for ``/devices/{device_id}/...`` routes."""
    device = await db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    access = await load_home_access(device.home_id, user, db)
    return DeviceAccess(device=device, access=access)


async def websocket_user(websocket: WebSocket, db: AsyncSession) -> Optional[User]:
    """Authenticate a WebSocket via ``?token=`` or ``Authorization`` header."""
    token = websocket.query_params.get("token")
    if not token:
        header = websocket.headers.get("authorization", "")
        if header.lower().startswith("bearer "):
            token = header[7:]
    return await user_from_token(token, db)
