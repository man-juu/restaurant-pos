"""Two-factor endpoints under /api/v1/auth/mfa (FR-IDN-002)."""

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select

from app.core.access.policy import public
from app.core.config import Settings
from app.core.errors import AppError, ConflictError
from app.core.identity import mfa, service
from app.core.identity.deps import (
    AuthContext,
    MfaRequired,
    PartialAuth,
)
from app.core.identity.schemas import (
    CodeRequest,
    MfaSetupOut,
    RecoveryCodesOut,
    SessionInfo,
)
from app.core.identity.web import (
    TooManyAttempts,
    audit_auth,
    client_info,
    session_info,
    set_session_cookie,
)
from app.core.models import User, UserSession

router = APIRouter(prefix="/api/v1/auth", tags=["auth"], dependencies=[Depends(public())])


class InvalidCode(AppError):
    status_code, code = 400, "invalid_code"


async def _rotate(
    request: Request, response: Response, auth: AuthContext, user: User, mfa_state: str
) -> SessionInfo:
    """Replace the session with a new token at the new privilege level (no fixation)."""
    settings: Settings = request.app.state.settings
    ip, user_agent = client_info(request)
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
        info = await session_info(db, user, row)
    set_session_cookie(response, token, settings)
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
        await audit_auth(
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
        await audit_auth(request, info.active_tenant_id, "auth.mfa_enabled", user.id)
    return RecoveryCodesOut(recovery_codes=codes)


# --- Password reset (FR-IDN-008) -------------------------------------------------------
