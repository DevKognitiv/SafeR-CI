"""Message center routes (Tuya "Message Center": ``alarm`` | ``home`` | ``notice``).

Messages belong to a home; every route resolves membership (``home_access`` for ``/homes/{home_id}/...``,
the message's ``home_id`` for ``/messages/{message_id}/...``) and answers 404 to outsiders. Listing is newest
first with optional ``kind`` / ``unread_only`` filters and ``before=<iso>`` keyset pagination.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.hub.deps import HomeAccess, get_current_user, get_db, home_access, load_home_access
from app.hub.models import Message, User
from app.hub.schemas import MessageOut, UnreadCountOut

logger = logging.getLogger("safer.hub.routes.messages")

router = APIRouter()

__all__ = ["router", "MESSAGE_KINDS", "UpdatedOut", "DeletedOut"]

MESSAGE_KINDS: Tuple[str, ...] = ("alarm", "home", "notice")
KIND_PATTERN = "^(alarm|home|notice)$"
DEFAULT_LIMIT = 50
MAX_LIMIT = 200


class UpdatedOut(BaseModel):
    """Result of a bulk update."""

    updated: int = 0


class DeletedOut(BaseModel):
    """Result of a bulk delete."""

    deleted: int = 0


def _naive_utc(value: datetime) -> datetime:
    """Timestamps are stored naive UTC; normalise aware inputs (``...Z``/``+02:00``) before comparing."""
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


async def _load_message(message_id: str, user: User, db: AsyncSession) -> Message:
    """Message + membership check on its home (404 for unknown ids and non-members)."""
    message = await db.get(Message, message_id)
    if message is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    await load_home_access(message.home_id, user, db)
    return message


# ----------------------------------------------------------------------------- listing
@router.get("/homes/{home_id}/messages", response_model=List[MessageOut])
async def list_messages(
    kind: Optional[str] = Query(default=None, pattern=KIND_PATTERN, description="alarm | home | notice"),
    unread_only: bool = Query(default=False),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    before: Optional[datetime] = Query(default=None, description="Only messages created before this ISO timestamp"),
    access: HomeAccess = Depends(home_access),
    db: AsyncSession = Depends(get_db),
) -> List[MessageOut]:
    """Messages of a home, newest first."""
    query = select(Message).where(Message.home_id == access.home.id)
    if kind:
        query = query.where(Message.kind == kind)
    if unread_only:
        query = query.where(Message.read.is_(False))
    if before is not None:
        query = query.where(Message.created_at < _naive_utc(before))
    rows = await db.execute(query.order_by(Message.created_at.desc(), Message.id.desc()).limit(limit))
    return [MessageOut.model_validate(message) for message in rows.scalars().all()]


@router.get("/homes/{home_id}/messages/unread-count", response_model=UnreadCountOut)
async def unread_count(access: HomeAccess = Depends(home_access), db: AsyncSession = Depends(get_db)) -> UnreadCountOut:
    """Unread counters per kind (badge of the "Me" tab / message center tabs)."""
    rows = await db.execute(
        select(Message.kind, func.count(Message.id))  # pylint: disable=not-callable
        .where(Message.home_id == access.home.id, Message.read.is_(False))
        .group_by(Message.kind)
    )
    counts: Dict[str, int] = {kind: int(total) for kind, total in rows.all()}
    return UnreadCountOut(
        total=sum(counts.values()),
        alarm=counts.get("alarm", 0),
        home=counts.get("home", 0),
        notice=counts.get("notice", 0),
    )


# ----------------------------------------------------------------------------- read state
@router.post("/messages/{message_id}/read", response_model=MessageOut)
async def mark_read(
    message_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> MessageOut:
    """Mark one message as read (membership resolved through the message's home)."""
    message = await _load_message(message_id, user, db)
    if not message.read:
        message.read = True
        await db.commit()
    return MessageOut.model_validate(message)


@router.post("/homes/{home_id}/messages/read-all", response_model=UpdatedOut)
async def mark_all_read(
    kind: Optional[str] = Query(default=None, pattern=KIND_PATTERN, description="Restrict to one kind"),
    access: HomeAccess = Depends(home_access),
    db: AsyncSession = Depends(get_db),
) -> UpdatedOut:
    """Mark every unread message of the home (optionally of one kind) as read."""
    statement = update(Message).where(Message.home_id == access.home.id, Message.read.is_(False))
    if kind:
        statement = statement.where(Message.kind == kind)
    result = await db.execute(statement.values(read=True).execution_options(synchronize_session=False))
    await db.commit()
    return UpdatedOut(updated=int(result.rowcount or 0))


# ----------------------------------------------------------------------------- deletion
@router.delete("/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_message(
    message_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> Response:
    """Delete one message."""
    message = await _load_message(message_id, user, db)
    await db.delete(message)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/homes/{home_id}/messages", response_model=DeletedOut)
async def clear_messages(
    kind: Optional[str] = Query(default=None, pattern=KIND_PATTERN, description="Restrict to one kind"),
    access: HomeAccess = Depends(home_access),
    db: AsyncSession = Depends(get_db),
) -> DeletedOut:
    """Clear the message center of the home (optionally one kind only)."""
    statement = delete(Message).where(Message.home_id == access.home.id)
    if kind:
        statement = statement.where(Message.kind == kind)
    result = await db.execute(statement.execution_options(synchronize_session=False))
    await db.commit()
    logger.info("Cleared %s message(s) of home %s (kind=%s)", result.rowcount, access.home.id, kind or "*")
    return DeletedOut(deleted=int(result.rowcount or 0))
