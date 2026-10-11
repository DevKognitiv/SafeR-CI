"""Alembic migration tests, run programmatically (no CLI): fresh upgrade, legacy hub stamping, models in sync."""
from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from app.hub import migrations
from app.hub.db import Base, Database
from app.hub.migrations import (
    BASELINE_REVISION, VERSION_TABLE, alembic_config, current_revision, head_revision, migrate_async, migrate_connection,
    schema_diff,
)
from app.hub.models import Home, Room
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


def test_foreign_tables_on_a_shared_database_are_not_drift(tmp_path):
    """The main API's tables share DATABASE_URL: a current hub schema next to them is stamped head, not replayed."""
    engine = create_engine(sqlite_url(tmp_path / "shared.db"))
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE incidents (id INTEGER PRIMARY KEY, kind VARCHAR(20))"))
        connection.execute(text("CREATE TABLE spatial_ref_sys (srid INTEGER PRIMARY KEY)"))
    with engine.begin() as connection:
        assert schema_diff(connection) == []
        assert migrate_connection(connection) == "stamped_head"
    with engine.connect() as connection:
        assert current_revision(connection) == HEAD
        assert {"incidents", "spatial_ref_sys"} <= set(inspect(connection).get_table_names())
    with engine.begin() as connection:
        assert migrate_connection(connection) == "upgraded"  # a second start is a no-op


async def test_batch_recreate_during_a_migration_keeps_child_rows(monkeypatch):
    """SQLite batch mode drops and recreates the table; with foreign keys on that would cascade-delete every child."""
    db = Database("sqlite+aiosqlite://")
    try:
        assert await migrate_async(db.engine) == "created"
        async with AsyncSession(db.engine, expire_on_commit=False) as session:
            home = Home(name="Maison")
            session.add(home)
            await session.flush()
            session.add(Room(home_id=home.id, name="Salon"))
            await session.commit()

        def recreate(connection) -> str:
            context = MigrationContext.configure(connection, opts={"version_table": VERSION_TABLE, "render_as_batch": True})
            with Operations.context(context) as op:
                with op.batch_alter_table("hub_homes", recreate="always") as batch:
                    batch.alter_column("name", existing_type=Base.metadata.tables["hub_homes"].c.name.type)
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 0
            return "recreated"

        monkeypatch.setattr(migrations, "migrate_connection", recreate)
        assert await migrate_async(db.engine) == "recreated"
        async with AsyncSession(db.engine) as session:
            assert len((await session.execute(select(Room))).scalars().all()) == 1
            # enforcement is back on for the runtime: deleting the home cascades to the room again
            await session.delete((await session.execute(select(Home))).scalar_one())
            await session.commit()
            assert (await session.execute(select(Room))).scalars().all() == []
        async with db.engine.connect() as connection:
            assert (await connection.exec_driver_sql("PRAGMA foreign_keys")).scalar() == 1
    finally:
        await db.engine.dispose()


def test_concurrent_startups_serialise_on_sqlite(tmp_path):
    """Two hub processes starting on the same fresh file: one creates, the other waits and finds the schema."""
    url = f"sqlite+aiosqlite:///{tmp_path / 'race.db'}"
    barrier = threading.Barrier(2)

    def start(worker: int) -> str:
        async def run() -> str:
            engine = create_async_engine(url)
            try:
                barrier.wait(timeout=10)
                return await migrate_async(engine)
            finally:
                await engine.dispose()
        return asyncio.run(run())

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = sorted(pool.map(start, [0, 1]))
    assert results == ["created", "upgraded"] or results == ["created", "stamped_head"], results
    engine = create_engine(sqlite_url(tmp_path / "race.db"))
    with engine.connect() as connection:
        assert current_revision(connection) == HEAD
        assert "hub_sos_alerts" in inspect(connection).get_table_names()
