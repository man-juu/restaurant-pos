"""Helpers shared by the sign-in, 2FA and account routers."""

import ipaddress
import uuid

from fastapi import Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.config import Settings
from app.core.errors import AppError
from app.core.identity import service
from app.core.identity.deps import (
    COOKIE_NAME,
)
from app.core.identity.schemas import (
    SessionInfo,
    TenantOption,
    UserOut,
)
from app.core.models import User, UserSession
from app.core.tenancy import tenant_session


class InvalidCredentials(AppError):
    status_code, code = 401, "invalid_credentials"


class TooManyAttempts(AppError):
    status_code, code = 429, "too_many_attempts"


def client_info(request: Request) -> tuple[str | None, str | None]:
    # Behind Caddy and Cloudflare the real IP comes from trusted proxy headers (slice 0.8).
    host = request.client.host if request.client else None
    try:
        ip = str(ipaddress.ip_address(host)) if host else None
    except ValueError:  # e.g. a unix socket or test client name
        ip = None
    return ip, request.headers.get("user-agent")


def set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=settings.session_absolute_hours * 3600,
        path="/",
        secure=True,
        httponly=True,  # not readable from JavaScript, so XSS cannot steal it
        samesite="lax",  # not sent on cross-site POSTs (first CSRF layer)
    )


async def session_info(db: AsyncSession, user: User, row: UserSession) -> SessionInfo:
    members = await service.active_memberships(db, user.id)
    # Drop a tenant the user has since lost access to (computed, not saved to the row).
    active = row.active_tenant_id
    if active not in {m.tenant_id for m in members}:
        active = None
    return SessionInfo(
        user=UserOut(id=user.id, email=user.email, name=user.name, locale=user.locale),
        tenants=[TenantOption(id=m.tenant_id, name=m.tenant_name) for m in members],
        active_tenant_id=active if row.mfa_state == "ok" else None,
        csrf_token=row.csrf_token,
        mfa_state=row.mfa_state,
    )


async def audit_auth(
    request: Request, tenant_id: uuid.UUID, action: str, user_id: uuid.UUID, **extra: object
) -> None:
    ip, _ = client_info(request)
    async with tenant_session(request.app.state.sessionmaker, tenant_id, user_id) as db:
        await audit.record(
            db,
            tenant_id=tenant_id,
            action=action,
            user_id=user_id,
            target_type="user",
            target_id=user_id,
            summary=dict(extra),
            ip=ip,
        )
