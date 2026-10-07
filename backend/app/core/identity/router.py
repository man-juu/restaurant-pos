"""Sign-in endpoints under /api/v1/auth (FR-IDN-001, 003, 005, 007; FR-AUD-001)."""

import ipaddress
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Request, Response
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.config import Settings
from app.core.errors import AppError, ConflictError, ForbiddenError, NotFoundError
from app.core.identity import mfa, service
from app.core.identity.deps import (
    COOKIE_NAME,
    AuthContext,
    CurrentAuth,
    MfaRequired,
    PartialAuth,
)
from app.core.identity.passwords import (
    hash_password,
    needs_rehash,
    validate_new_password,
    verify_password,
)
from app.core.identity.schemas import (
    CodeRequest,
    InvitationAccept,
    InvitationCreate,
    InvitationOut,
    LoginRequest,
    MfaSetupOut,
    PasswordResetConfirm,
    PasswordResetRequest,
    RecoveryCodesOut,
    SessionInfo,
    SessionOut,
    SwitchTenantRequest,
    TenantOption,
    UserOut,
)
from app.core.mailer import Email
from app.core.models import Invitation, Membership, PasswordReset, Role, User, UserSession
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
        if user.totp_enabled_at is not None:
            mfa_state = "verify"
        elif await service.requires_mfa(db, user.id):
            mfa_state = "enroll"  # FR-IDN-002: owners and co-owners must set up 2FA first
        else:
            mfa_state = "ok"
        token, row = await service.create_session(
            db,
            user_id=user.id,
            tenant_id=tenant_id,
            ip=ip,
            user_agent=user_agent,
            settings=settings,
            mfa_state=mfa_state,
        )
        info = await _session_info(db, user, row)
    if tenant_id:
        action = "auth.login" if mfa_state == "ok" else "auth.password_verified"
        await _audit(request, tenant_id, action, user.id, session_id=str(row.id))
    _set_cookie(response, token, settings)
    return info


@router.post("/logout", status_code=204)
async def logout(auth: PartialAuth, request: Request, response: Response) -> None:
    async with request.app.state.sessionmaker() as db, db.begin():
        await service.revoke(db, session_id=auth.session_id, user_id=auth.user_id)
    if auth.tenant_id:
        await _audit(request, auth.tenant_id, "auth.logout", auth.user_id)
    response.delete_cookie(COOKIE_NAME, path="/", secure=True, httponly=True, samesite="lax")


@router.get("/session", response_model=SessionInfo)
async def current_session(auth: PartialAuth, request: Request) -> SessionInfo:
    async with request.app.state.sessionmaker() as db, db.begin():
        user = (await db.execute(select(User).where(User.id == auth.user_id))).scalar_one()
        row = (
            await db.execute(select(UserSession).where(UserSession.id == auth.session_id))
        ).scalar_one()
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


# --- Two-factor authentication (FR-IDN-002) -------------------------------------------


class InvalidCode(AppError):
    status_code, code = 400, "invalid_code"


async def _rotate(
    request: Request, response: Response, auth: AuthContext, user: User, mfa_state: str
) -> SessionInfo:
    """Replace the session with a new token at the new privilege level (no fixation)."""
    settings: Settings = request.app.state.settings
    ip, user_agent = _client(request)
    async with request.app.state.sessionmaker() as db, db.begin():
        old = (
            await db.execute(select(UserSession).where(UserSession.id == auth.session_id))
        ).scalar_one()
        await service.revoke(db, session_id=auth.session_id, user_id=auth.user_id)
        token, row = await service.create_session(
            db,
            user_id=user.id,
            tenant_id=old.active_tenant_id,
            ip=ip,
            user_agent=user_agent,
            settings=settings,
            mfa_state=mfa_state,
        )
        info = await _session_info(db, user, row)
    _set_cookie(response, token, settings)
    return info


@router.post("/mfa/verify", response_model=SessionInfo)
async def mfa_verify(
    body: CodeRequest, auth: PartialAuth, request: Request, response: Response
) -> SessionInfo:
    """Second sign-in step: a TOTP code, or a one-time recovery code."""
    if auth.mfa_state != "verify":
        raise InvalidCode(details={"reason": "not_expected"})
    settings: Settings = request.app.state.settings
    key = service.throttle_key("mfa", str(auth.user_id))
    async with request.app.state.sessionmaker() as db, db.begin():
        until = await service.locked_until(db, [key])
        if until is not None:
            raise TooManyAttempts(details={"retry_at": until.isoformat()})
        user = await mfa.load_user(db, auth.user_id)
        box = request.app.state.secret_box
        ok = await mfa.check_totp(db, box, user, body.code)
        used_recovery = False
        if not ok:
            ok = used_recovery = await mfa.use_recovery_code(db, user.id, body.code)
        if ok:
            await service.clear_failures(db, [key])
    if not ok:
        async with request.app.state.sessionmaker() as db, db.begin():
            await service.record_failure(db, [key], settings.login_max_failures)
        raise InvalidCode()
    info = await _rotate(request, response, auth, user, "ok")
    if info.active_tenant_id:
        await _audit(
            request,
            info.active_tenant_id,
            "auth.login",
            user.id,
            second_factor="recovery_code" if used_recovery else "totp",
        )
    return info


@router.post("/mfa/setup", response_model=MfaSetupOut)
async def mfa_setup(auth: PartialAuth, request: Request) -> MfaSetupOut:
    """Start (or restart) enrolment. Allowed when fully signed in or when enrolment is
    required; not while a code is still owed for an existing setup."""
    if auth.mfa_state == "verify":
        raise MfaRequired(details={"mfa_state": "verify"})
    settings: Settings = request.app.state.settings
    async with request.app.state.sessionmaker() as db, db.begin():
        user = await mfa.load_user(db, auth.user_id)
        if user.totp_enabled_at is not None:
            raise ConflictError("mfa_already_enabled")
        secret, uri = await mfa.start_setup(
            db, request.app.state.secret_box, user, issuer=settings.totp_issuer
        )
    return MfaSetupOut(secret=secret, otpauth_uri=uri)


@router.post("/mfa/confirm", response_model=RecoveryCodesOut)
async def mfa_confirm(
    body: CodeRequest, auth: PartialAuth, request: Request, response: Response
) -> RecoveryCodesOut:
    """Finish enrolment with a first code from the app; returns recovery codes once."""
    if auth.mfa_state == "verify":
        raise MfaRequired(details={"mfa_state": "verify"})
    async with request.app.state.sessionmaker() as db, db.begin():
        user = await mfa.load_user(db, auth.user_id)
        if user.totp_enabled_at is not None:
            raise ConflictError("mfa_already_enabled")
        if not await mfa.check_totp(db, request.app.state.secret_box, user, body.code):
            raise InvalidCode()
        codes = await mfa.enable(db, user.id)
    info = await _rotate(request, response, auth, user, "ok")
    if info.active_tenant_id:
        await _audit(request, info.active_tenant_id, "auth.mfa_enabled", user.id)
    return RecoveryCodesOut(recovery_codes=codes)


# --- Password reset (FR-IDN-008) -------------------------------------------------------


class InvalidToken(AppError):
    status_code, code = 400, "invalid_or_expired_token"


def _link(settings: Settings, path: str, token: str) -> str:
    # Token in the URL fragment (#): browsers never send fragments to servers or in Referer
    # headers, so it cannot leak into proxy or access logs.
    return f"{settings.app_base_url.rstrip('/')}{path}#token={token}"


@router.post("/password-reset/request", status_code=202)
async def request_password_reset(body: PasswordResetRequest, request: Request) -> None:
    """Always 202, whether or not the email has an account (no account enumeration)."""
    settings: Settings = request.app.state.settings
    key = service.throttle_key("reset", body.email)
    async with request.app.state.sessionmaker() as db, db.begin():
        if await service.locked_until(db, [key]) is not None:
            return  # silently drop: limits email flooding of one address
        await service.record_failure(db, [key], 3)  # at most a few mails per window
        user = await service.find_user(db, body.email)
        if user is None or user.status != "active":
            return
        token = secrets.token_urlsafe(32)
        db.add(
            PasswordReset(
                user_id=user.id,
                token_hash=service.hash_token(token),
                expires_at=datetime.now(UTC)
                + timedelta(minutes=settings.password_reset_ttl_minutes),
            )
        )
    await request.app.state.mailer.send(
        Email(
            to=user.email,
            subject_key="email.password_reset.subject",
            link=_link(settings, "/reset-password", token),
        )
    )


@router.post("/password-reset/confirm", status_code=204)
async def confirm_password_reset(body: PasswordResetConfirm, request: Request) -> None:
    """Single use; sets the new password and signs the user out everywhere. 2FA still
    applies at the next sign-in, so a stolen mailbox alone cannot take over an owner."""
    async with request.app.state.sessionmaker() as db, db.begin():
        reset = (
            await db.execute(
                select(PasswordReset)
                .where(
                    PasswordReset.token_hash == service.hash_token(body.token),
                    PasswordReset.used_at.is_(None),
                    PasswordReset.expires_at > func.now(),
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if reset is None:
            raise InvalidToken()
        user = await mfa.load_user(db, reset.user_id)
        privileged = await service.requires_mfa(db, user.id)
    validate_new_password(body.new_password, privileged=privileged, email=user.email)
    new_hash = await hash_password(body.new_password)
    async with request.app.state.sessionmaker() as db, db.begin():
        used = await db.execute(
            update(PasswordReset)
            .where(PasswordReset.id == reset.id, PasswordReset.used_at.is_(None))
            .values(used_at=func.now())
        )
        if not used.rowcount:
            raise InvalidToken()  # a parallel request used it first
        await db.execute(update(User).where(User.id == user.id).values(password_hash=new_hash))
        await service.revoke_all(db, user.id)
        await service.clear_failures(db, [service.throttle_key("acct", user.email)])
        members = await service.active_memberships(db, user.id)
    for m in members:
        await _audit(request, m.tenant_id, "auth.password_reset", user.id)


# --- Invitations (FR-IDN-006) ----------------------------------------------------------

invitations_router = APIRouter(prefix="/api/v1/invitations", tags=["invitations"])


class NoActiveTenant(AppError):
    status_code, code = 409, "no_active_tenant"


@invitations_router.post("", status_code=201, response_model=InvitationOut)
async def create_invitation(
    body: InvitationCreate, auth: CurrentAuth, request: Request
) -> InvitationOut:
    """Owners and co-owners invite staff by email (single use, expiring link).

    Interim check until the permission framework (slice 0.5): the inviter's role in this
    tenant must be one that requires 2FA, i.e. owner or co-owner."""
    if auth.tenant_id is None:
        raise NoActiveTenant()
    settings: Settings = request.app.state.settings
    token = secrets.token_urlsafe(32)
    sessions = request.app.state.sessionmaker
    async with tenant_session(sessions, auth.tenant_id, auth.user_id) as db:
        inviter_is_owner = (
            await db.execute(
                select(Role.requires_mfa)
                .join(Membership, Membership.role_id == Role.id)
                .where(Membership.user_id == auth.user_id, Membership.status == "active")
            )
        ).scalar_one_or_none()
        if not inviter_is_owner:
            raise ForbiddenError()
        role = (
            await db.execute(
                select(Role).where(Role.id == body.role_id, Role.tenant_id.is_not(None))
            )
        ).scalar_one_or_none()
        if role is None:  # RLS already hides other tenants' roles
            raise NotFoundError()
        invitation = Invitation(
            tenant_id=auth.tenant_id,
            email=body.email.strip(),
            role_id=role.id,
            invited_by=auth.user_id,
            token_hash=service.hash_token(token),
            expires_at=datetime.now(UTC) + timedelta(hours=settings.invitation_ttl_hours),
        )
        db.add(invitation)
        await db.flush()
        await audit.record(
            db,
            tenant_id=auth.tenant_id,
            action="user.invited",
            user_id=auth.user_id,
            target_type="invitation",
            target_id=invitation.id,
            summary={"role_id": str(role.id)},
        )
    await request.app.state.mailer.send(
        Email(
            to=invitation.email,
            subject_key="email.invitation.subject",
            link=_link(settings, "/accept-invitation", token),
        )
    )
    return InvitationOut(id=invitation.id, email=invitation.email, expires_at=invitation.expires_at)


@router.post("/invitations/accept", status_code=204)
async def accept_invitation(body: InvitationAccept, request: Request) -> None:
    """New email: creates the account with the given password. Existing account: the
    password must match it (proves the invitee owns that account). Then sign in normally."""
    sessions = request.app.state.sessionmaker
    async with sessions() as db, db.begin():
        inv = (
            await db.execute(
                text("SELECT * FROM auth_invitation_by_token(:h)"),
                {"h": service.hash_token(body.token)},
            )
        ).one_or_none()
        if inv is None or inv.used_at is not None or inv.expires_at <= datetime.now(UTC):
            raise InvalidToken()
        user = await service.find_user(db, inv.email)

    async with tenant_session(sessions, inv.tenant_id) as db:
        privileged = bool(
            (await db.execute(select(Role.requires_mfa).where(Role.id == inv.role_id))).scalar()
        )
    if user is not None:
        if not await verify_password(user.password_hash, body.password):
            raise InvalidCredentials()
        user_id = user.id
    else:
        if not body.name:
            raise InvalidToken(details={"reason": "name_required"})
        validate_new_password(body.password, privileged=privileged, email=inv.email)
        password_hash = await hash_password(body.password)
        async with sessions() as db, db.begin():
            new_user = User(email=inv.email, name=body.name.strip(), password_hash=password_hash)
            db.add(new_user)
            await db.flush()
            user_id = new_user.id

    async with tenant_session(sessions, inv.tenant_id, user_id) as db:
        used = await db.execute(
            update(Invitation)
            .where(Invitation.id == inv.id, Invitation.used_at.is_(None))
            .values(used_at=func.now())
        )
        if not used.rowcount:  # type: ignore[attr-defined]
            raise InvalidToken()
        exists = (
            await db.execute(select(Membership.id).where(Membership.user_id == user_id))
        ).scalar_one_or_none()
        if exists is not None:
            raise ConflictError("already_member")
        db.add(Membership(tenant_id=inv.tenant_id, user_id=user_id, role_id=inv.role_id))
        await audit.record(
            db,
            tenant_id=inv.tenant_id,
            action="user.invitation_accepted",
            user_id=user_id,
            target_type="invitation",
            target_id=inv.id,
        )
