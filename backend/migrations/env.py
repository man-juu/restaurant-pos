"""Alembic environment. Migrations run as the owner role (MIGRATION_DATABASE_URL), never as
the restricted app role, because only the owner may create tables and policies."""

import asyncio

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

import app.admin.models
import app.core.ai.models
import app.core.settings.models
import app.core.uploads.models
import app.modules.catalog.models
import app.modules.inventory.doc_models
import app.modules.inventory.models  # noqa: F401 - module tables
from app.core.config import get_settings
from app.core.models import Base

target_metadata = Base.metadata


def _run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def _run_async() -> None:
    url = context.config.attributes.get("url") or str(get_settings().migration_url)
    engine = create_async_engine(url)
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    raise SystemExit("Offline (--sql) migrations are not supported.")
asyncio.run(_run_async())
