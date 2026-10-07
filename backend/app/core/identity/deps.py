"""Request authentication (docs/06 section 3).

`require_session` resolves the session cookie on every request (so revocation is immediate),
enforces CSRF on state-changing methods and re-checks that the active tenant membership is
still valid. Permission, module and subscription checks are layered on top in slice 0.5.
"""

import secrets
import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request

from app.core.errors import AppError
from app.core.identity import service

COOKIE_NAME = "__Host-session"  # __Host-: Secure, path=/, no Domain, so subdomains can't set it
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class NotAuthenticated(AppError):
    status_code, code = 401, "not_authenticated"


class CsrfFailed(AppError):
    status_code, code = 403, "csrf_failed"


@dataclass(frozen=True)
class AuthContext:
    session_id: uuid.UUID
    user_id: uuid.UUID
    tenant_id: uuid.UUID | None
    csrf_token: str


async def require_session(request: Request) -> AuthContext:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise NotAuthenticated()
    sessions = request.app.state.sessionmaker
    async with sessions() as db, db.begin():
        row = await service.resolve_session(db, token, request.app.state.settings)
        if row is None:
            raise NotAuthenticated("session_expired")
        tenant_id = row.active_tenant_id
        if tenant_id is not None:
            allowed = {m.tenant_id for m in await service.active_memberships(db, row.user_id)}
            if tenant_id not in allowed:  # removed from the tenant or tenant suspended
                tenant_id = None

    if request.method not in SAFE_METHODS:
        sent = request.headers.get(CSRF_HEADER, "")
        # Constant-time compare: no timing hints about the expected token.
        if not secrets.compare_digest(sent.encode(), row.csrf_token.encode()):
            raise CsrfFailed()
    return AuthContext(row.id, row.user_id, tenant_id, row.csrf_token)


CurrentAuth = Annotated[AuthContext, Depends(require_session)]
