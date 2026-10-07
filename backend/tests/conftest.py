import os
from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import Settings
from app.core.db import create_engine
from app.main import create_app

# CI sets DATABASE_URL to its PostgreSQL service. Locally the default is the compose db
# (docker compose up -d db). Tests only use rolled-back transactions and temporary tables.
TEST_DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://pos_owner:dev-only-password@localhost:5432/pos"
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def settings() -> Settings:
    return Settings.model_validate({"environment": "test", "database_url": TEST_DATABASE_URL})


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    # The context manager runs the lifespan (engine setup and disposal).
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
async def engine(settings: Settings) -> AsyncIterator[AsyncEngine]:
    eng = create_engine(settings)
    yield eng
    await eng.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """A session inside a transaction that is always rolled back: tests leave no data behind."""
    async with engine.connect() as conn, conn.begin() as tx:
        yield AsyncSession(bind=conn)
        await tx.rollback()
