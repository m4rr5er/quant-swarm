"""Async engine + session helpers for the SQLite operational store."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from quant_swarm.core.db.models import Base


def engine_for(db_path: str) -> AsyncEngine:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return create_async_engine(f"sqlite+aiosqlite:///{db_path}")


def session_factory(db_path: str) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine_for(db_path), expire_on_commit=False)


async def init_db(db_path: str) -> None:
    """Create all tables + enable WAL (used by ``qs init-db`` and tests).

    Alembic owns incremental migrations going forward; create_all is the
    bootstrap path and stays schema-identical to the initial revision.
    """
    engine = engine_for(db_path)
    try:
        async with engine.begin() as conn:
            await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
            await conn.run_sync(Base.metadata.create_all)
            await conn.exec_driver_sql(
                "CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5("
                "content, session_id UNINDEXED, expert UNINDEXED)"
            )
    finally:
        await engine.dispose()
