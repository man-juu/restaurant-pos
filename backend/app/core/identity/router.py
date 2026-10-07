"""Sign-in endpoints under /api/v1/auth (FR-IDN-001, 003, 005, 007; FR-AUD-001)."""

import uuid
from datetime import datetime
from typing import Any, NoReturn

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access.policy import public
from app.core.config import Settings
from app.core.errors import NotFoundError
from app.core.identity import service
from app.core.identity.deps import (
    COOKIE_NAME,
    CurrentAuth,
    PartialAuth,
)
from app.core.identity.passwords import (
    hash_password,
    needs_rehash,
    verify_password,
)
from app.core.identity.schemas import (
    LoginRequest,
    SessionInfo,
    SessionOut,
    SwitchTenantRequest,
)
from app.core.identity.web import (
    InvalidCredentials,
    TooManyAttempts,
    audit_auth,
    client_info,
    session_info,
    set_session_cookie,
)
from app.core.models import User, UserSession

# Sign-in endpoints are public by necessity; each one performs its own session checks.
router = APIRouter(prefix="/api/v1/auth", tags=["auth"], dependencies=[Depends(public())])

IP_FAILURE_FACTOR = 4  # outlets share one IP; don't let one typo-prone device lock everyone


async def _locked_or_user(sessions: Any, keys: list[str], email: str) -> User | None:
    async with sessions() as db, db.begin():
        until: datetime | None = await service.locked_until(db, keys)
        user = None if until is not None else await service.find_user(db, email)
    if until is not None:
        # Same answer whether or not the account exists: no account enumeration.
        raise TooManyAttempts(details={"retry_at": until.isoformat()})
    return user


async def _fail_login(
    request: Request, user: User | None, account_key: str, ip_keys: list[str]
) -> NoReturn:
    settings: Settings = request.app.state.settings
    async with request.app.state.sessionmaker() as db, db.begin():
        await service.record_failure(db, [account_key], settings.login_max_failures)
        await service.record_failure(db, ip_keys, settings.login_max_failures * IP_FAILURE_FACTOR)
        members = await service.active_memberships(db, user.id) if user else []
    for m in members:  # owners see attacks on their staff accounts (members implies user)
        await audit_auth(request, m.tenant_id, "auth.login_failed", user.id)  # type: ignore[union-attr]
    raise InvalidCredentials()


async def _mfa_state(db: AsyncSession, user: User) -> str:
    if user.totp_enabled_at is not None:
        return "verify"
    if await service.requires_mfa(db, user.id):
        return "enroll"  # FR-IDN-002: owners and co-owners must set up 2FA first
    return "ok"


@router.post("/login", response_model=SessionInfo)
async def login(body: LoginRequest, request: Request, response: Response) -> SessionInfo:
    settings: Settings = request.app.state.settings
    sessions = request.app.state.sessionmaker
    ip, user_agent = client_info(request)
    account_key = service.throttle_key("acct", body.email)
    ip_keys = [service.throttle_key("ip", ip)] if ip else []

    user = await _locked_or_user(sessions, [account_key, *ip_keys], body.email)
    ok = await verify_password(user.password_hash if user else None, body.password)
    if not ok or user is None or user.status != "active":
        await _fail_login(request, user, account_key, ip_keys)

    new_hash = (
        await hash_password(body.password) if needs_rehash(user.password_hash or "") else None
    )
    async with sessions() as db, db.begin():
        await service.clear_failures(db, [account_key])
        if new_hash:
            await db.execute(update(User).where(User.id == user.id).values(password_hash=new_hash))
        members = await service.active_memberships(db, user.id)
        tenant_id = members[0].tenant_id if members else None
        mfa_state = await _mfa_state(db, user)
        token, row = await service.create_session(
            db,
            user_id=user.id,
            tenant_id=tenant_id,
            ip=ip,
            user_agent=user_agent,
            settings=settings,
            mfa_state=mfa_state,
        )
        info = await session_info(db, user, row)
    if tenant_id:
        action = "auth.login" if mfa_state == "ok" else "auth.password_verified"
        await audit_auth(request, tenant_id, action, user.id, session_id=str(row.id))
    set_session_cookie(response, token, settings)
    return info


@router.post("/logout", status_code=204)
async def logout(auth: PartialAuth, request: Request, response: Response) -> None:
    async with request.app.state.sessionmaker() as db, db.begin():
        await service.revoke(db, session_id=auth.session_id, user_id=auth.user_id)
    if auth.tenant_id:
        await audit_auth(request, auth.tenant_id, "auth.logout", auth.user_id)
    response.delete_cookie(COOKIE_NAME, path="/", secure=True, httponly=True, samesite="lax")


@router.get("/session", response_model=SessionInfo)
async def current_session(auth: PartialAuth, request: Request) -> SessionInfo:
    async with request.app.state.sessionmaker() as db, db.begin():
        user = (await db.execute(select(User).where(User.id == auth.user_id))).scalar_one()
        row = (
            await db.execute(select(UserSession).where(UserSession.id == auth.session_id))
        ).scalar_one()
        return await session_info(db, user, row)


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
        await audit_auth(
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
    ip, user_agent = client_info(request)
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
        info = await session_info(db, user, row)
    await audit_auth(
        request,
        body.tenant_id,
        "auth.tenant_switched",
        auth.user_id,
        from_tenant=str(auth.tenant_id) if auth.tenant_id else None,
    )
    set_session_cookie(response, token, settings)
    return info


# --- Two-factor authentication (FR-IDN-002) -------------------------------------------
