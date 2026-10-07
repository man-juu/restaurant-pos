"""Password reset and invitations (FR-IDN-003, FR-TEN-002)."""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select, text, update

from app.core import audit
from app.core.access.policy import PermissionDenied, Principal, public, require
from app.core.config import Settings
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.identity import mfa, service
from app.core.identity.passwords import (
    hash_password,
    validate_new_password,
    verify_password,
)
from app.core.identity.schemas import (
    InvitationAccept,
    InvitationCreate,
    InvitationOut,
    PasswordResetConfirm,
    PasswordResetRequest,
)
from app.core.identity.web import (
    InvalidCredentials,
    audit_auth,
)
from app.core.mailer import Email
from app.core.models import Invitation, Membership, PasswordReset, Role, User
from app.core.tenancy import tenant_session

router = APIRouter(prefix="/api/v1/auth", tags=["auth"], dependencies=[Depends(public())])


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
        await audit_auth(request, m.tenant_id, "auth.password_reset", user.id)


# --- Invitations (FR-IDN-006) ----------------------------------------------------------

invitations_router = APIRouter(prefix="/api/v1/invitations", tags=["invitations"])


@invitations_router.post("", status_code=201, response_model=InvitationOut)
async def create_invitation(
    body: InvitationCreate,
    request: Request,
    p: Annotated[Principal, Depends(require("tenant.user.manage"))],
) -> InvitationOut:
    """FR-IDN-006: invite a person by email (single use, expiring link)."""
    settings: Settings = request.app.state.settings
    token = secrets.token_urlsafe(32)
    sessions = request.app.state.sessionmaker
    async with tenant_session(sessions, p.tenant_id, p.user_id) as db:
        role = (
            await db.execute(
                select(Role).where(Role.id == body.role_id, Role.tenant_id.is_not(None))
            )
        ).scalar_one_or_none()
        if role is None:  # RLS already hides other tenants' roles
            raise NotFoundError()
        # docs/03 rules 2 and 3: only the owner may hand out the owner role.
        if role.template_key == "owner" and not p.can("tenant.ownership.transfer"):
            raise PermissionDenied(details={"permission": "tenant.ownership.transfer"})
        invitation = Invitation(
            tenant_id=p.tenant_id,
            email=body.email.strip(),
            role_id=role.id,
            invited_by=p.user_id,
            token_hash=service.hash_token(token),
            expires_at=datetime.now(UTC) + timedelta(hours=settings.invitation_ttl_hours),
        )
        db.add(invitation)
        await db.flush()
        await audit.record(
            db,
            tenant_id=p.tenant_id,
            action="user.invited",
            user_id=p.user_id,
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
