"""Platform admin application. Separate ASGI app, separate cookie, separate database role
(pos_admin): run it on its own port and, in production, restrict who can reach it (slice 0.8).

    uvicorn app.admin.main:create_admin_app --factory --port 8001
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine

import app.modules
from app.admin import announce_router, ops_router, router, security, usage
from app.core.access.permissions import build_registry
from app.core.access.policy import assert_all_routes_declared, include
from app.core.config import Settings, get_settings
from app.core.crypto import SecretBox
from app.core.db import create_sessionmaker
from app.core.errors import register_error_handlers
from app.core.health import router as health_router
from app.core.logging import configure_logging
from app.core.mailer import MemoryMailer
from app.core.middleware import RequestContextMiddleware
from app.core.modules import discover


def create_admin_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    if settings.admin_database_url is None:
        raise RuntimeError("ADMIN_DATABASE_URL must be set (connects as pos_admin)")

    @asynccontextmanager
    async def lifespan(api: FastAPI) -> AsyncIterator[None]:
        engine = create_async_engine(
            str(settings.admin_database_url), pool_size=2, max_overflow=2, pool_pre_ping=True
        )
        api.state.engine = engine
        api.state.sessionmaker = create_sessionmaker(engine)
        api.state.secret_box = SecretBox(settings.encryption_key)
        api.state.mailer = MemoryMailer(echo=settings.environment == "dev")
        yield
        await engine.dispose()

    api = FastAPI(
        title="Restaurant POS Admin API",
        lifespan=lifespan,
        docs_url=None if settings.environment == "production" else "/admin-api/docs",
        openapi_url="/admin-api/openapi.json",
        redoc_url=None,
    )
    api.state.settings = settings
    api.state.permission_registry = build_registry(discover(app.modules))
    register_error_handlers(api)
    api.add_middleware(RequestContextMiddleware)
    for r in (
        health_router,
        security.router,
        router.router,
        ops_router.router,
        announce_router.router,
        usage.router,
    ):
        include(api, r)
    assert_all_routes_declared(api, api.state.permission_registry)
    return api
