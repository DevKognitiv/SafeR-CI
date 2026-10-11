"""Alembic environment for the SafeR Hub schema.

The target metadata is ``app.hub.db.Base`` with every model of ``app.hub.models`` imported. The database URL is
resolved in this order and is never read from a ``.env`` file (so no secret ever reaches the logs):

1. ``config.attributes["connection"]`` -- an already open SQLAlchemy connection (the hub runtime migrates through
   its own engine, which is also how in-memory SQLite databases can be migrated);
2. ``config.attributes["url"]`` or ``-x url=<url>`` on the command line;
3. ``HUB_DATABASE_URL``, then ``DATABASE_URL`` from the process environment;
4. ``sqlite:///./safer_hub.db``.

Async URLs are converted to their sync drivers (``sqlite+aiosqlite`` -> ``sqlite``, ``postgresql+asyncpg`` ->
``postgresql+psycopg2``). SQLite migrations run in batch mode (``render_as_batch``) because SQLite cannot ALTER
columns in place.
"""
from __future__ import annotations

import logging
import os
from logging.config import fileConfig
from typing import Optional

from alembic import context
from sqlalchemy import Connection, create_engine, pool
from sqlalchemy.engine import make_url

from app.hub import models  # noqa: F401  pylint: disable=unused-import  # registers every table on Base.metadata
from app.hub.db import Base

config = context.config

if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

logger = logging.getLogger("alembic.env")

target_metadata = Base.metadata

DEFAULT_URL = "sqlite:///./safer_hub.db"
# The hub can share a PostgreSQL database with the main API: its own version table keeps the histories apart.
VERSION_TABLE = config.get_main_option("version_table") or "hub_alembic_version"
ASYNC_DRIVERS = {
    "sqlite+aiosqlite": "sqlite",
    "postgresql+asyncpg": "postgresql+psycopg2",
}


def sync_url(url: str) -> str:
    """Rewrite an async SQLAlchemy URL to its sync driver (other URLs are returned unchanged)."""
    parsed = make_url(url)
    replacement = ASYNC_DRIVERS.get(parsed.drivername)
    if replacement is None:
        return url
    return parsed.set(drivername=replacement).render_as_string(hide_password=False)


def resolve_url() -> str:
    """Database URL from ``-x url=``/attributes, the environment, or the local SQLite default."""
    explicit: Optional[str] = config.attributes.get("url")
    if not explicit:
        explicit = context.get_x_argument(as_dictionary=True).get("url")
    url = explicit or os.environ.get("HUB_DATABASE_URL") or os.environ.get("DATABASE_URL") or DEFAULT_URL
    return sync_url(url.strip())


def _configure_and_run(connection: Connection) -> None:
    dialect = connection.dialect.name
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table=VERSION_TABLE,
        render_as_batch=dialect == "sqlite",
        compare_type=True,
        compare_server_default=False,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it (``alembic upgrade head --sql``)."""
    url = resolve_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        version_table=VERSION_TABLE,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=url.startswith("sqlite"),
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations on the injected connection, or on a throw-away engine built from the resolved URL."""
    connection: Optional[Connection] = config.attributes.get("connection")
    if connection is not None:
        _configure_and_run(connection)
        return
    url = resolve_url()
    engine = create_engine(url, poolclass=pool.NullPool)
    # Only the dialect and the password-less URL are logged: credentials never reach the logs.
    logger.info("Migrating %s database %s", engine.dialect.name, engine.url.render_as_string(hide_password=True))
    try:
        with engine.connect() as conn:
            _configure_and_run(conn)
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
