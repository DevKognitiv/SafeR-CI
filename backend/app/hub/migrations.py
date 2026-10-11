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
from sqlalchemy.exc import OperationalError
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
    "BASELINE_REVISION", "VERSION_TABLE", "ALEMBIC_DIR", "ALEMBIC_INI", "SQLITE_BUSY_TIMEOUT_MS",
    "POSTGRES_ADVISORY_LOCK",
]

BACKEND_DIR = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
ALEMBIC_DIR = BACKEND_DIR / "alembic"
BASELINE_REVISION = "0001_baseline"
# The hub shares DATABASE_URL with the main API by default: its own version table keeps the histories apart.
VERSION_TABLE = "hub_alembic_version"
# Two hub processes (or the hub and a manual ``alembic upgrade``) starting together must not race the schema:
# SQLite takes the write lock up front and waits this long for it, PostgreSQL takes one advisory lock.
SQLITE_BUSY_TIMEOUT_MS = 30_000
POSTGRES_ADVISORY_LOCK = 0x5AFE0001


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


def _hub_tables_only(name: Optional[str], type_: str, _parent_names: dict) -> bool:
    """Autogenerate filter: only the hub's own tables count (the main API's tables share DATABASE_URL by default)."""
    return type_ != "table" or name in Base.metadata.tables


def schema_diff(connection: Connection) -> list:
    """Differences between the live schema and ``Base.metadata`` (empty when models and database agree).

    Foreign tables (the main API, PostGIS, anything else on a shared database) are ignored: they are not drift.
    """
    context = MigrationContext.configure(
        connection,
        opts={
            "compare_type": True, "compare_server_default": False, "version_table": VERSION_TABLE,
            "render_as_batch": connection.dialect.name == "sqlite", "include_name": _hub_tables_only,
        },
    )
    return compare_metadata(context, Base.metadata)


def serialise(connection: Connection) -> None:
    """Make the migration exclusive before the schema is inspected: a second process waits instead of racing.

    SQLite: ``BEGIN IMMEDIATE`` takes the write lock now (SQLAlchemy's SQLite driver would only begin at the first
    write, after the inspection), with ``busy_timeout`` so the loser waits for the winner to commit and then sees
    the finished schema. PostgreSQL: a transaction-scoped advisory lock shared by every hub process.
    """
    if connection.dialect.name == "sqlite":
        connection.exec_driver_sql(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
        try:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
        except OperationalError as exc:  # already inside a driver transaction: the caller serialised us
            if "within a transaction" not in str(exc):
                raise
    elif connection.dialect.name == "postgresql":
        connection.exec_driver_sql(f"SELECT pg_advisory_xact_lock({POSTGRES_ADVISORY_LOCK})")


def migrate_connection(connection: Connection) -> str:
    """Bring the database behind ``connection`` to ``head`` (sync; call through ``AsyncConnection.run_sync``).

    Returns what happened: ``created``, ``stamped`` (legacy hub stamped at the baseline then upgraded),
    ``stamped_head`` (schema already current, only the version row was missing) or ``upgraded``.
    """
    serialise(connection)
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
    """Async wrapper of :func:`migrate_connection` on the runtime's engine (one transaction).

    The runtime enables ``PRAGMA foreign_keys`` on every SQLite connection; during a migration that would turn a
    batch table recreate (``DROP TABLE`` + rename) into a cascade delete of every child row, so the pragma is off
    for the migration and back on before the connection returns to the pool. Both pragmas run outside the
    transaction, where SQLite honours them.
    """
    async with engine.connect() as connection:
        sqlite = connection.dialect.name == "sqlite"
        if sqlite:
            await connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        try:
            action = await connection.run_sync(migrate_connection)
            await connection.commit()
        except BaseException:
            await connection.rollback()
            raise
        finally:
            if sqlite:
                await connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    return action
