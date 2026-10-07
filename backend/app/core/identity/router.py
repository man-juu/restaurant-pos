"""Sign-in endpoints under /api/v1/auth (FR-IDN-001, 003, 005, 007; FR-AUD-001)."""

import ipaddress
import uuid
from datetime import datetime

from fastapi import APIRouter, Request, Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.config import Settings
from app.core.errors import AppError, NotFoundError
from app.core.identity import service
from app.core.identity.deps import COOKIE_NAME, CurrentAuth
from app.core.identity.passwords import hash_password, needs_rehash, verify_password
from app.core.identity.schemas import (
    LoginRequest,
    SessionInfo,
    SessionOut,
    SwitchTenantRequest,
    TenantOption,
    UserOut,
)
from app.core.models import User, UserSession
from app.core.tenancy import tenant_session

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

IP_FAILURE_FACTOR = 4  # outlets share one IP; don't let one typo-prone device lock everyone


class InvalidCredentials(AppError):
    status_code, code = 401, "invalid_credentials"


class TooManyAttempts(AppError):
    status_code, code = 429, "too_many_attempts"


def _client(request: Request) -> tuple[str | None, str | None]:
    # Behind Caddy and Cloudflare the real IP comes from trusted proxy headers (slice 0.8).
    host = request.client.host if request.client else None
    try:
        ip = str(ipaddress.ip_address(host)) if host else None
    except ValueError:  # e.g. a unix socket or test client name
        ip = None
    return ip, request.headers.get("user-agent")


def _set_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=settings.session_absolute_hours * 3600,
        path="/",
        secure=True,
        httponly=True,  # not readable from JavaScript, so XSS cannot steal it
        samesite="lax",  # not sent on cross-site POSTs (first CSRF layer)
    )


async def _session_info(db: AsyncSession, user: User, row: UserSession) -> SessionInfo:
    members = await service.active_memberships(db, user.id)
    return SessionInfo(
        user=UserOut(id=user.id, email=user.email, name=user.name, locale=user.locale),
        tenants=[TenantOption(id=m.tenant_id, name=m.tenant_name) for m in members],
        active_tenant_id=row.active_tenant_id,
        csrf_token=row.csrf_token,
    )


async def _audit(
    request: Request, tenant_id: uuid.UUID, action: str, user_id: uuid.UUID, **extra: object
) -> None:
    ip, _ = _client(request)
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


@router.post("/login", response_model=SessionInfo)
async def login(body: LoginRequest, request: Request, response: Response) -> SessionInfo:
    settings: Settings = request.app.state.settings
    sessions = request.app.state.sessionmaker
    ip, user_agent = _client(request)
    account_key = service.throttle_key("acct", body.email)
    ip_keys = [service.throttle_key("ip", ip)] if ip else []

    async with sessions() as db, db.begin():
        until: datetime | None = await service.locked_until(db, [account_key, *ip_keys])
        if until is None:
            user = await service.find_user(db, body.email)
    if until is not None:
        # Same answer whether or not the account exists: no account enumeration.
        raise TooManyAttempts(details={"retry_at": until.isoformat()})

    ok = await verify_password(user.password_hash if user else None, body.password)
    if not ok or user is None or user.status != "active":
        async with sessions() as db, db.begin():
            await service.record_failure(db, [account_key], settings.login_max_failures)
            await service.record_failure(
                db, ip_keys, settings.login_max_failures * IP_FAILURE_FACTOR
            )
            members = await service.active_memberships(db, user.id) if user else []
        for m in members:  # owners see attacks on their staff accounts
            await _audit(request, m.tenant_id, "auth.login_failed", user.id)  # type: ignore[union-attr]
        raise InvalidCredentials()

    new_hash = (
        await hash_password(body.password) if needs_rehash(user.password_hash or "") else None
    )
    async with sessions() as db, db.begin():
        await service.clear_failures(db, [account_key])
        if new_hash:
            await db.execute(update(User).where(User.id == user.id).values(password_hash=new_hash))
        members = await service.active_memberships(db, user.id)
        tenant_id = members[0].tenant_id if members else None
        token, row = await service.create_session(
            db,
            user_id=user.id,
            tenant_id=tenant_id,
            ip=ip,
            user_agent=user_agent,
            settings=settings,
        )
        info = await _session_info(db, user, row)
    if tenant_id:
        await _audit(request, tenant_id, "auth.login", user.id, session_id=str(row.id))
    _set_cookie(response, token, settings)
    return info


@router.post("/logout", status_code=204)
async def logout(auth: CurrentAuth, request: Request, response: Response) -> None:
    async with request.app.state.sessionmaker() as db, db.begin():
        await service.revoke(db, session_id=auth.session_id, user_id=auth.user_id)
    if auth.tenant_id:
        await _audit(request, auth.tenant_id, "auth.logout", auth.user_id)
    response.delete_cookie(COOKIE_NAME, path="/", secure=True, httponly=True, samesite="lax")


@router.get("/session", response_model=SessionInfo)
async def current_session(auth: CurrentAuth, request: Request) -> SessionInfo:
    async with request.app.state.sessionmaker() as db, db.begin():
        user = (await db.execute(select(User).where(User.id == auth.user_id))).scalar_one()
        row = (
            await db.execute(select(UserSession).where(UserSession.id == auth.session_id))
        ).scalar_one()
        row.active_tenant_id = auth.tenant_id  # reflects a membership removed since sign-in
        return await _session_info(db, user, row)


@router.get("/sessions", response_model=list[SessionOut])
async def my_sessions(auth: CurrentAuth, request: Request) -> list[SessionOut]:
    """FR-IDN-007: the user's active sessions, newest activity first."""
    async with request.app.state.sessionmaker() as db, db.begin():
        rows = await service.list_sessions(db, auth.user_id)
    return [
        SessionOut(
            id=r.id,
            created_at=r.created_at,
            last_seen_at=r.last_seen_at,
            ip=str(r.ip) if r.ip else None,
            user_agent=r.user_agent,
            current=r.id == auth.session_id,
        )
        for r in rows
    ]


@router.delete("/sessions/{session_id}", status_code=204)
async def revoke_session(session_id: uuid.UUID, auth: CurrentAuth, request: Request) -> None:
    """FR-IDN-007: revoke one of your own sessions (404 for anyone else's)."""
    async with request.app.state.sessionmaker() as db, db.begin():
        if not await service.revoke(db, session_id=session_id, user_id=auth.user_id):
            raise NotFoundError()
    if auth.tenant_id:
        await _audit(
            request,
            auth.tenant_id,
            "auth.session_revoked",
            auth.user_id,
            session_id=str(session_id),
        )


@router.post("/switch-tenant", response_model=SessionInfo)
async def switch_tenant(
    body: SwitchTenantRequest, auth: CurrentAuth, request: Request, response: Response
) -> SessionInfo:
    """FR-IDN-005. The requested tenant is only a choice: it is checked against the user's
    memberships. The session is rotated (new token and CSRF token) because the privileges
    change, which defeats session fixation."""
    settings: Settings = request.app.state.settings
    ip, user_agent = _client(request)
    async with request.app.state.sessionmaker() as db, db.begin():
        members = await service.active_memberships(db, auth.user_id)
        if body.tenant_id not in {m.tenant_id for m in members}:
            raise NotFoundError()  # 404, not 403: don't confirm that the tenant exists
        await service.revoke(db, session_id=auth.session_id, user_id=auth.user_id)
        token, row = await service.create_session(
            db,
            user_id=auth.user_id,
            tenant_id=body.tenant_id,
            ip=ip,
            user_agent=user_agent,
            settings=settings,
        )
        user = (await db.execute(select(User).where(User.id == auth.user_id))).scalar_one()
        info = await _session_info(db, user, row)
    await _audit(
        request,
        body.tenant_id,
        "auth.tenant_switched",
        auth.user_id,
        from_tenant=str(auth.tenant_id) if auth.tenant_id else None,
    )
    _set_cookie(response, token, settings)
    return info
