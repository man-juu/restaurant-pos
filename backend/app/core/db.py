"""Async database engine. Tenant-scoped sessions (set_config per transaction) come in 0.3."""

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        str(settings.database_url),
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_pool_size,
        pool_pre_ping=True,
        pool_recycle=1800,
    )


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def ping(engine: AsyncEngine, timeout_s: float = 2.0) -> bool:
    try:
        async with asyncio.timeout(timeout_s), engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
