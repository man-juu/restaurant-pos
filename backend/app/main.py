from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

import app.modules
from app.core import health, tenant_router
from app.core.access.permissions import build_registry
from app.core.access.policy import assert_all_routes_declared, include
from app.core.config import Settings, get_settings
from app.core.crypto import SecretBox
from app.core.db import create_engine, create_sessionmaker
from app.core.errors import register_error_handlers
from app.core.identity import account_router, mfa_router
from app.core.identity import router as identity
from app.core.logging import configure_logging
from app.core.mailer import MemoryMailer
from app.core.middleware import RequestContextMiddleware
from app.core.modules import ModuleManifest, discover, mount
from app.core.settings import router as settings_router


def create_app(
    settings: Settings | None = None, manifests: list[ModuleManifest] | None = None
) -> FastAPI:
    """App factory: tests build an app with their own settings; no import-time side effects."""
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(api: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings)
        api.state.engine = engine
        api.state.sessionmaker = create_sessionmaker(engine)
        api.state.secret_box = SecretBox(settings.encryption_key)
        # Real SMTP comes in slice 0.8; until then mail is kept in memory (printed in dev).
        api.state.mailer = MemoryMailer(echo=settings.environment == "dev")
        yield
        await engine.dispose()

    is_prod = settings.environment == "production"
    api = FastAPI(
        title="Restaurant POS API",
        lifespan=lifespan,
        # API docs are useful in dev and staging; hide them in production.
        docs_url=None if is_prod else "/docs",
        redoc_url=None,
    )
    api.state.settings = settings
    api.state.modules = manifests if manifests is not None else discover(app.modules)
    api.state.permission_registry = build_registry(api.state.modules)
    register_error_handlers(api)
    api.add_middleware(RequestContextMiddleware)
    for router in (
        health.router,
        identity.router,
        mfa_router.router,
        account_router.router,
        account_router.invitations_router,
        tenant_router.router,
        settings_router.router,
    ):
        include(api, router)
    mount(api, api.state.modules, include)
    # Deny by default: refuse to start if any route lacks require(...) or public().
    assert_all_routes_declared(api, api.state.permission_registry)
    return api
