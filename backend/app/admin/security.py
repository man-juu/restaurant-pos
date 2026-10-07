"""Platform admin sign-in (FR-ADM-002): password plus mandatory TOTP for every admin.

Mirrors the tenant sign-in (app.core.identity) on separate tables, a separate cookie and a
separate database role, so a tenant session can never act as an admin.
"""

import secrets
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update

from app.admin.models import AdminSession, AdminUser
from app.core.access.policy import public
from app.core.errors import AppError, ConflictError
from app.core.identity import mfa, service
from app.core.identity.deps import CSRF_HEADER, SAFE_METHODS, CsrfFailed, MfaRequired
from app.core.identity.passwords import verify_password

COOKIE_NAME = "__Host-admin-session"
SESSION_HOURS = 8
IDLE_MINUTES = 30  # stricter than tenants: admin sessions are more powerful


class NotAuthenticated(AppError):
    status_code, code = 401, "not_authenticated"


class InvalidCredentials(AppError):
    status_code, code = 401, "invalid_credentials"


class InvalidCode(AppError):
    status_code, code = 400, "invalid_code"


class TooManyAttempts(AppError):
    status_code, code = 429, "too_many_attempts"


class AdminForbidden(AppError):
    status_code, code = 403, "admin_role_required"


@dataclass(frozen=True)
class AdminContext:
    session_id: uuid.UUID
    admin_id: uuid.UUID
    email: str
    role: str
    mfa_state: str


async def _resolve(request: Request) -> AdminContext:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise NotAuthenticated()
    async with request.app.state.sessionmaker() as db, db.begin():
        row = (
            await db.execute(
                select(AdminSession, AdminUser)
                .join(AdminUser, AdminUser.id == AdminSession.admin_id)
                .where(
                    AdminSession.token_hash == service.hash_token(token),
                    AdminSession.revoked_at.is_(None),
                    AdminSession.expires_at > func.now(),
                    AdminSession.last_seen_at > func.now() - timedelta(minutes=IDLE_MINUTES),
                    AdminUser.status == "active",
                )
            )
        ).one_or_none()
        if row is None:
            raise NotAuthenticated("session_expired")
        sess, admin = row
        await db.execute(
            update(AdminSession).where(AdminSession.id == sess.id).values(last_seen_at=func.now())
        )
    if request.method not in SAFE_METHODS and not secrets.compare_digest(
        request.headers.get(CSRF_HEADER, "").encode(), sess.csrf_token.encode()
    ):
        raise CsrfFailed()
    return AdminContext(sess.id, admin.id, admin.email, admin.role, sess.mfa_state)


def require_admin(*roles: str) -> Callable[[Request], Awaitable[AdminContext]]:
    """Full admin session (TOTP done) with one of `roles` (any admin role if empty)."""

    async def dependency(request: Request) -> AdminContext:
        ctx = await _resolve(request)
        if ctx.mfa_state != "ok":
            raise MfaRequired(details={"mfa_state": ctx.mfa_state})
        if roles and ctx.role not in roles:
            raise AdminForbidden(details={"required": list(roles)})
        return ctx

    dependency.access_rule = ("admin", roles)  # type: ignore[attr-defined]
    return dependency


# --- Endpoints ---------------------------------------------------------------------------

router = APIRouter(prefix="/admin-api/auth", tags=["admin-auth"], dependencies=[Depends(public())])


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class CodeIn(BaseModel):
    code: str = Field(min_length=6, max_length=20)


class AdminSessionOut(BaseModel):
    email: str
    role: str
    mfa_state: str
    csrf_token: str


class SetupOut(BaseModel):
    secret: str
    otpauth_uri: str


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=SESSION_HOURS * 3600,
        path="/",
        secure=True,
        httponly=True,
        samesite="strict",  # admin UI never needs cross-site navigation
    )


async def _new_session(
    request: Request, response: Response, admin: AdminUser, mfa_state: str
) -> AdminSessionOut:
    token = secrets.token_urlsafe(32)
    row = AdminSession(
        token_hash=service.hash_token(token),
        admin_id=admin.id,
        csrf_token=secrets.token_urlsafe(32),
        mfa_state=mfa_state,
        expires_at=datetime.now(UTC) + timedelta(hours=SESSION_HOURS),
    )
    async with request.app.state.sessionmaker() as db, db.begin():
        db.add(row)
    _set_cookie(response, token)
    return AdminSessionOut(
        email=admin.email, role=admin.role, mfa_state=mfa_state, csrf_token=row.csrf_token
    )


async def _load(request: Request, admin_id: uuid.UUID) -> AdminUser:
    async with request.app.state.sessionmaker() as db:
        admin: AdminUser = (
            await db.execute(select(AdminUser).where(AdminUser.id == admin_id))
        ).scalar_one()
        return admin


@router.post("/login", response_model=AdminSessionOut)
async def login(body: LoginIn, request: Request, response: Response) -> AdminSessionOut:
    key = service.throttle_key("admin", body.email)
    async with request.app.state.sessionmaker() as db, db.begin():
        if await service.locked_until(db, [key]) is not None:
            raise TooManyAttempts()
        admin = (
            await db.execute(select(AdminUser).where(AdminUser.email == body.email.strip()))
        ).scalar_one_or_none()
    ok = await verify_password(admin.password_hash if admin else None, body.password)
    if not ok or admin is None or admin.status != "active":
        async with request.app.state.sessionmaker() as db, db.begin():
            await service.record_failure(db, [key], 5)
        raise InvalidCredentials()
    async with request.app.state.sessionmaker() as db, db.begin():
        await service.clear_failures(db, [key])
    state = "verify" if admin.totp_enabled_at else "enroll"  # TOTP is never optional
    return await _new_session(request, response, admin, state)


@router.post("/mfa/setup", response_model=SetupOut)
async def mfa_setup(request: Request) -> SetupOut:
    ctx = await _resolve(request)
    if ctx.mfa_state != "enroll":
        raise ConflictError("mfa_already_enabled")
    admin = await _load(request, ctx.admin_id)
    async with request.app.state.sessionmaker() as db, db.begin():
        secret, uri = await mfa.start_setup(
            db,
            request.app.state.secret_box,
            admin,
            issuer=f"{request.app.state.settings.totp_issuer} Admin",
            model=AdminUser,
        )
    return SetupOut(secret=secret, otpauth_uri=uri)


@router.post("/mfa/confirm", response_model=AdminSessionOut)
async def mfa_confirm(body: CodeIn, request: Request, response: Response) -> AdminSessionOut:
    return await _complete(body, request, response, expected="enroll")


@router.post("/mfa/verify", response_model=AdminSessionOut)
async def mfa_verify(body: CodeIn, request: Request, response: Response) -> AdminSessionOut:
    return await _complete(body, request, response, expected="verify")


async def _complete(
    body: CodeIn, request: Request, response: Response, *, expected: str
) -> AdminSessionOut:
    ctx = await _resolve(request)
    if ctx.mfa_state != expected:
        raise InvalidCode(details={"reason": "not_expected"})
    key = service.throttle_key("admin-mfa", str(ctx.admin_id))
    admin = await _load(request, ctx.admin_id)
    async with request.app.state.sessionmaker() as db, db.begin():
        if await service.locked_until(db, [key]) is not None:
            raise TooManyAttempts()
        ok = await mfa.check_totp(
            db, request.app.state.secret_box, admin, body.code, model=AdminUser
        )
        if ok and expected == "enroll":
            await db.execute(
                update(AdminUser).where(AdminUser.id == admin.id).values(totp_enabled_at=func.now())
            )
        if ok:
            await service.clear_failures(db, [key])
            await db.execute(
                update(AdminSession)
                .where(AdminSession.id == ctx.session_id)
                .values(revoked_at=func.now())
            )
    if not ok:
        async with request.app.state.sessionmaker() as db, db.begin():
            await service.record_failure(db, [key], 5)
        raise InvalidCode()
    return await _new_session(request, response, admin, "ok")  # rotated, full privileges


@router.get("/session", response_model=AdminSessionOut)
async def current_session(request: Request) -> AdminSessionOut:
    """Lets the admin UI restore its CSRF token after a page reload."""
    ctx = await _resolve(request)
    async with request.app.state.sessionmaker() as db:
        csrf = (
            await db.execute(
                select(AdminSession.csrf_token).where(AdminSession.id == ctx.session_id)
            )
        ).scalar_one()
    return AdminSessionOut(email=ctx.email, role=ctx.role, mfa_state=ctx.mfa_state, csrf_token=csrf)


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response) -> None:
    ctx = await _resolve(request)
    async with request.app.state.sessionmaker() as db, db.begin():
        await db.execute(
            update(AdminSession)
            .where(AdminSession.id == ctx.session_id)
            .values(revoked_at=func.now())
        )
    response.delete_cookie(COOKIE_NAME, path="/", secure=True, httponly=True, samesite="strict")


CurrentAdmin = Annotated[AdminContext, Depends(require_admin())]
