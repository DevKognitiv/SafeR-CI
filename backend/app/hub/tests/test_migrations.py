"""Alembic migration tests, run programmatically (no CLI): fresh upgrade, legacy hub stamping, models in sync."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from alembic import command
from app.hub.db import Base
from app.hub.migrations import (
    BASELINE_REVISION, VERSION_TABLE, alembic_config, current_revision, head_revision, migrate_connection, schema_diff,
)
from app.hub.runtime import HubRuntime, set_runtime
from app.hub.tests.conftest import make_settings

HEAD = "0002_sos_address"


def sqlite_url(path: Path) -> str:
    """Sync SQLAlchemy URL of a SQLite file."""
    return f"sqlite:///{path}"


def columns(connection, table: str) -> set:
    """Column names of ``table`` as the database reports them."""
    return {column["name"] for column in inspect(connection).get_columns(table)}


async def start_hub(path: Path) -> str:
    """Start (and stop) a runtime with auto-migrate on the SQLite file; returns what ``prepare_schema`` did."""
    runtime = HubRuntime(settings=make_settings(HUB_AUTO_MIGRATE=True), database_url=f"sqlite+aiosqlite:///{path}", start_services=False)
    set_runtime(runtime)
    try:
        await runtime.start()
        assert runtime.started
    finally:
        await runtime.stop()
        set_runtime(None)
    return "started"


def test_upgrade_head_creates_every_table(tmp_path):
    db = tmp_path / "fresh.db"
    command.upgrade(alembic_config(url=sqlite_url(db)), "head")
    engine = create_engine(sqlite_url(db))
    with engine.connect() as conn:
        names = set(inspect(conn).get_table_names())
        assert set(Base.metadata.tables) <= names
        assert VERSION_TABLE in names
        assert current_revision(conn) == head_revision() == HEAD
        assert "address" in columns(conn, "hub_sos_alerts")
    engine.dispose()


def test_models_and_migrations_are_in_sync(tmp_path):
    db = tmp_path / "sync.db"
    command.upgrade(alembic_config(url=sqlite_url(db)), "head")
    engine = create_engine(sqlite_url(db))
    with engine.connect() as conn:
        assert schema_diff(conn) == []
    engine.dispose()


def test_baseline_alone_is_the_pre_migration_schema(tmp_path):
    """0001 reproduces the create_all schema of the last release: every table, minus the columns added since."""
    db = tmp_path / "baseline.db"
    command.upgrade(alembic_config(url=sqlite_url(db)), BASELINE_REVISION)
    engine = create_engine(sqlite_url(db))
    with engine.connect() as conn:
        assert set(Base.metadata.tables) <= set(inspect(conn).get_table_names())
        assert "address" not in columns(conn, "hub_sos_alerts")
        diff_kinds = {item[0] for item in schema_diff(conn)}
        assert diff_kinds == {"add_column"}
    engine.dispose()


async def test_legacy_hub_is_stamped_then_upgraded_on_start(tmp_path):
    """A hub created with ``create_all`` before migrations existed has tables but no alembic_version."""
    db = tmp_path / "legacy.db"
    command.upgrade(alembic_config(url=sqlite_url(db)), BASELINE_REVISION)
    engine = create_engine(sqlite_url(db))
    with engine.begin() as conn:
        conn.execute(text(f"DROP TABLE {VERSION_TABLE}"))
    with engine.connect() as conn:
        assert VERSION_TABLE not in inspect(conn).get_table_names()
        assert "address" not in columns(conn, "hub_sos_alerts")
    engine.dispose()

    await start_hub(db)

    engine = create_engine(sqlite_url(db))
    with engine.connect() as conn:
        assert current_revision(conn) == HEAD
        assert "address" in columns(conn, "hub_sos_alerts")
        assert schema_diff(conn) == []
    engine.dispose()
    # a second start is a no-op upgrade
    await start_hub(db)


async def test_create_all_with_current_models_is_stamped_head(tmp_path):
    """Tables created by ``create_all`` with the current models must not get 0002 replayed on them."""
    db = tmp_path / "current.db"
    runtime = HubRuntime(settings=make_settings(HUB_AUTO_MIGRATE=False), database_url=f"sqlite+aiosqlite:///{db}", start_services=False)
    set_runtime(runtime)
    try:
        await runtime.start()
    finally:
        await runtime.stop()
        set_runtime(None)
    engine = create_engine(sqlite_url(db))
    with engine.connect() as conn:
        assert VERSION_TABLE not in inspect(conn).get_table_names()
    with engine.begin() as conn:
        assert migrate_connection(conn) == "stamped_head"
    with engine.connect() as conn:
        assert current_revision(conn) == HEAD and schema_diff(conn) == []
    engine.dispose()


async def test_auto_migrate_on_in_memory_database():
    """The runtime migrates through its own engine, so even ``sqlite+aiosqlite://`` (one shared connection) works."""
    runtime = HubRuntime(settings=make_settings(HUB_AUTO_MIGRATE=True), database_url="sqlite+aiosqlite://", start_services=False)
    set_runtime(runtime)
    try:
        await runtime.start()
        async with runtime.db.engine.connect() as conn:
            assert await conn.run_sync(current_revision) == HEAD
            assert await conn.run_sync(schema_diff) == []
    finally:
        await runtime.stop()
        set_runtime(None)


def test_downgrade_rehearsal(tmp_path):
    """Rollback to the baseline and back to head (what an operator rehearses before a hub release)."""
    db = tmp_path / "rollback.db"
    cfg = alembic_config(url=sqlite_url(db))
    command.upgrade(cfg, "head")
    command.downgrade(cfg, BASELINE_REVISION)
    engine = create_engine(sqlite_url(db))
    with engine.connect() as conn:
        assert current_revision(conn) == BASELINE_REVISION
        assert "address" not in columns(conn, "hub_sos_alerts")
    engine.dispose()
    command.upgrade(cfg, "head")
    engine = create_engine(sqlite_url(db))
    with engine.connect() as conn:
        assert current_revision(conn) == HEAD and "address" in columns(conn, "hub_sos_alerts")
    engine.dispose()


def test_migration_env_needs_no_hub_settings(tmp_path, monkeypatch):
    """env.py reads only the URL (argument or environment), never the hub settings / ``.env`` secrets."""
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("HUB_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'from-env.db'}")  # async URL -> sync driver
    cfg = alembic_config()
    command.upgrade(cfg, "head")
    engine = create_engine(sqlite_url(tmp_path / "from-env.db"))
    with engine.connect() as conn:
        assert current_revision(conn) == HEAD
    engine.dispose()
