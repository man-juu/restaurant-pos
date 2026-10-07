"""Test database setup.

A dedicated database (`pos_test` by default) is recreated once per test run and migrated from
empty with Alembic, so every run also proves "upgrade from an empty database" (CLAUDE.md rule
11). Tests then connect as the restricted app role, exactly like production, so row-level
security is really exercised.

Environment: OWNER_DATABASE_URL points at any database on the server as a role that may create
databases (CI: the service superuser; locally: the compose owner via `docker compose up -d db`).
"""

import asyncio
import os
from collections.abc import AsyncIterator, Iterator

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.core.config import Settings
from app.core.db import create_engine
from app.main import create_app

OWNER_URL = make_url(
    os.environ.get(
        "OWNER_DATABASE_URL",
        "postgresql+asyncpg://pos_owner:dev-only-password@localhost:5432/pos",
    )
)
TEST_DB = os.environ.get("TEST_DATABASE_NAME", "pos_test")
APP_PASSWORD = "test-only-app-password"  # noqa: S105 - local test database only

TEST_OWNER_URL = OWNER_URL.set(database=TEST_DB)
TEST_APP_URL = OWNER_URL.set(database=TEST_DB, username="pos_app", password=APP_PASSWORD)


async def _recreate_database(name: str) -> None:
    engine = create_async_engine(OWNER_URL.set(database="postgres"), isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        await conn.execute(text(f'CREATE DATABASE "{name}"'))
    await engine.dispose()


async def _enable_app_login() -> None:
    # Roles are cluster-wide; migrations create them NOLOGIN, tests give the app role a password.
    engine = create_async_engine(TEST_OWNER_URL, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        await conn.execute(text(f"ALTER ROLE pos_app LOGIN PASSWORD '{APP_PASSWORD}'"))
    await engine.dispose()


def alembic_config(url: str) -> Config:
    config = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    config.set_main_option(
        "script_location", os.path.join(os.path.dirname(__file__), "..", "migrations")
    )
    config.attributes["url"] = url
    return config


def migrate_fresh(name: str) -> str:
    """Create an empty database, upgrade it to head and return its owner URL."""
    asyncio.run(_recreate_database(name))
    url = OWNER_URL.set(database=name).render_as_string(hide_password=False)
    command.upgrade(alembic_config(url), "head")
    return url


@pytest.fixture(scope="session", autouse=True)
def database() -> None:
    migrate_fresh(TEST_DB)
    asyncio.run(_enable_app_login())


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def settings() -> Settings:
    return Settings.model_validate(
        {"environment": "test", "database_url": TEST_APP_URL.render_as_string(hide_password=False)}
    )


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
    """Engine connected as the restricted app role (RLS applies)."""
    eng = create_engine(settings)
    yield eng
    await eng.dispose()


@pytest.fixture
async def owner_engine() -> AsyncIterator[AsyncEngine]:
    """Owner connection for seeding test data (bypasses RLS as superuser in dev and CI)."""
    eng = create_async_engine(TEST_OWNER_URL)
    yield eng
    await eng.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """A session inside a transaction that is always rolled back: tests leave no data behind."""
    async with engine.connect() as conn, conn.begin() as tx:
        yield AsyncSession(bind=conn)
        await tx.rollback()
