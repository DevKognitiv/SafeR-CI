"""Alembic integration for the hub runtime: bring the database to ``head`` on startup.

The migrations live in ``backend/alembic`` (``alembic.ini`` next to it). They run through the runtime's own
engine (``AsyncConnection.run_sync``), which is also how an in-memory SQLite database can be migrated. Startup
logic (:func:`migrate_connection`):

- no hub table yet -> ``upgrade head`` creates everything;
- hub tables but no version table (a hub created with ``create_all`` before migrations existed) -> stamp
  the baseline revision, then ``upgrade head``; when the tables already match the models (``create_all`` with
  the current models) the database is stamped ``head`` instead, so no migration is replayed on them;
- otherwise -> ``upgrade head``.

``alembic_config()`` builds the same configuration the CLI uses, so tests and the runtime need no shell.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from sqlalchemy import Connection, inspect
from sqlalchemy.ext.asyncio import AsyncEngine

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from app.hub import models  # noqa: F401  pylint: disable=unused-import  # every table must be on Base.metadata
from app.hub.db import Base

logger = logging.getLogger("safer.hub.migrations")

__all__ = [
    "alembic_config", "migrate_connection", "migrate_async", "current_revision", "head_revision", "schema_diff",
    "BASELINE_REVISION", "VERSION_TABLE", "ALEMBIC_DIR", "ALEMBIC_INI",
]

BACKEND_DIR = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
ALEMBIC_DIR = BACKEND_DIR / "alembic"
BASELINE_REVISION = "0001_baseline"
# The hub shares DATABASE_URL with the main API by default: its own version table keeps the histories apart.
VERSION_TABLE = "hub_alembic_version"


def alembic_config(url: Optional[str] = None, connection: Optional[Connection] = None) -> Config:
    """Programmatic Alembic configuration (``alembic.ini`` + explicit script location, no logging takeover).

    Pass ``connection`` to migrate through an open connection, or ``url`` to let ``env.py`` open its own engine;
    with neither, ``env.py`` resolves the URL from the environment like the CLI does.
    """
    cfg = Config(str(ALEMBIC_INI)) if ALEMBIC_INI.exists() else Config()
    cfg.set_main_option("script_location", str(ALEMBIC_DIR))
    cfg.set_main_option("version_table", VERSION_TABLE)
    cfg.attributes["configure_logger"] = False
    if url:
        cfg.attributes["url"] = url
    if connection is not None:
        cfg.attributes["connection"] = connection
    return cfg


def head_revision() -> Optional[str]:
    """Revision id of ``head`` in the scripts directory."""
    return ScriptDirectory.from_config(alembic_config()).get_current_head()


def current_revision(connection: Connection) -> Optional[str]:
    """Revision stamped in the database (``None`` when it has no version row)."""
    return MigrationContext.configure(connection, opts={"version_table": VERSION_TABLE}).get_current_revision()


def schema_diff(connection: Connection) -> list:
    """Differences between the live schema and ``Base.metadata`` (empty when models and database agree)."""
    context = MigrationContext.configure(
        connection,
        opts={
            "compare_type": True, "compare_server_default": False, "version_table": VERSION_TABLE,
            "render_as_batch": connection.dialect.name == "sqlite",
        },
    )
    return compare_metadata(context, Base.metadata)


def migrate_connection(connection: Connection) -> str:
    """Bring the database behind ``connection`` to ``head`` (sync; call through ``AsyncConnection.run_sync``).

    Returns what happened: ``created``, ``stamped`` (legacy hub stamped at the baseline then upgraded),
    ``stamped_head`` (schema already current, only the version row was missing) or ``upgraded``.
    """
    names = set(inspect(connection).get_table_names())
    hub_tables = set(Base.metadata.tables) & names
    cfg = alembic_config(connection=connection)
    if not hub_tables:
        if VERSION_TABLE in names:
            command.stamp(cfg, "base")  # a stale version row without tables would make the upgrade a no-op
        action = "created"
    elif VERSION_TABLE not in names:
        if schema_diff(connection):
            command.stamp(cfg, BASELINE_REVISION)
            action = "stamped"
        else:
            command.stamp(cfg, "head")
            action = "stamped_head"
    else:
        action = "upgraded"
    command.upgrade(cfg, "head")
    return action


async def migrate_async(engine: AsyncEngine) -> str:
    """Async wrapper of :func:`migrate_connection` on the runtime's engine (one transaction)."""
    async with engine.begin() as connection:
        return await connection.run_sync(migrate_connection)
