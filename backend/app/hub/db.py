"""Async SQLAlchemy database wrapper for the hub (SQLite for dev/tests, PostgreSQL in prod)."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

logger = logging.getLogger("safer.hub.db")

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    """Declarative base for all hub models."""


class Database:
    """Owns the engine and session factory for one hub runtime."""

    def __init__(self, url: str, echo: bool = False):
        self.url = url
        kwargs = {"echo": echo, "future": True}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
            if ":memory:" in url or url.endswith("sqlite+aiosqlite://"):
                kwargs["poolclass"] = StaticPool
        self.engine: AsyncEngine = create_async_engine(url, **kwargs)
        if url.startswith("sqlite"):
            # SQLite ignores ON DELETE CASCADE / SET NULL unless foreign keys are enabled per connection.
            @event.listens_for(self.engine.sync_engine, "connect")
            def _enable_foreign_keys(dbapi_connection, _record):  # pragma: no cover - trivial
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False, class_=AsyncSession)

    async def create_all(self) -> None:
        """Create all tables (idempotent)."""
        from app.hub import models  # noqa: F401  pylint: disable=import-outside-toplevel,unused-import

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def drop_all(self) -> None:
        """Drop all tables (tests)."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Context-managed session."""
        async with self.session_factory() as session:
            yield session

    async def dispose(self) -> None:
        """Dispose the engine."""
        await self.engine.dispose()


async def rollback_and_restore(session: AsyncSession) -> None:
    """Roll back, then re-load every persistent instance the session still holds.

    ``Session.rollback()`` expires every object in the identity map (whatever ``expire_on_commit`` says), and an
    expired attribute accessed outside a greenlet raises ``MissingGreenlet``. Request handlers keep using the
    ``Home``/``Scene``/``User``/``Device`` rows they loaded before a failed adapter call, so restore them here.
    """
    instances = list(session.identity_map.values())
    await session.rollback()
    for instance in instances:
        try:
            await session.refresh(instance)
        except Exception:  # pylint: disable=broad-except  # row deleted meanwhile: detach it instead
            logger.debug("Could not restore %r after rollback", instance, exc_info=True)
            try:
                session.expunge(instance)
            except Exception:  # pylint: disable=broad-except
                pass
