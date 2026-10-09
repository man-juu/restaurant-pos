"""Sign in with Google (ADR 0.57): start and callback, both full-page redirects.

Google only proves who the person is. They must already be an active member of a business
(the owner invited them); otherwise nothing is created. Roles that require 2FA still get the
code step afterwards: Google sign-in replaces the password, not the second factor."""

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.core.access.policy import public
from app.core.config import Settings
from app.core.errors import NotFoundError
from app.core.identity import google, service
from app.core.identity.router import _mfa_state
from app.core.identity.web import audit_auth, client_info, set_session_cookie

router = APIRouter(prefix="/api/v1/auth", tags=["auth"], dependencies=[Depends(public())])

ATTEMPT_COOKIE = "__Host-pos_google"
ATTEMPT_MINUTES = 10
Text = Annotated[str | None, Query(max_length=2048)]


class Providers(BaseModel):
    google: bool


def _settings(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


def _to_login(request: Request, problem: str | None = None) -> RedirectResponse:
    base = _settings(request).app_base_url.rstrip("/")
    url = f"{base}/login" + (f"?google={problem}" if problem else "")
    response = RedirectResponse(url, status_code=303)
    response.delete_cookie(ATTEMPT_COOKIE, path="/", secure=True, httponly=True, samesite="lax")
    return response


@router.get("/providers", response_model=Providers)
async def providers(request: Request) -> Providers:
    """Which extra sign-in buttons the login page shows."""
    return Providers(google=_settings(request).google_enabled)


@router.get("/google/start")
async def google_start(request: Request) -> RedirectResponse:
    settings = _settings(request)
    if not settings.google_enabled:
        raise NotFoundError("google_disabled")
    attempt = google.Attempt.new()
    response = RedirectResponse(google.authorize_url(settings, attempt), status_code=303)
    # Lax, not Strict: Google sends the browser back with a cross-site top-level GET.
    response.set_cookie(
        ATTEMPT_COOKIE,
        attempt.cookie(),
        max_age=ATTEMPT_MINUTES * 60,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )
    return response


async def _email(request: Request, code: str | None, state: str | None) -> str:
    settings = _settings(request)
    attempt = google.Attempt.parse(request.cookies.get(ATTEMPT_COOKIE))
    if not (settings.google_enabled and attempt and code and state):
        raise google.GoogleError("no_attempt")
    if not secrets.compare_digest(state.encode(), attempt.state.encode()):
        raise google.GoogleError("state_mismatch")  # login CSRF or a stale tab
    id_token = await google.exchange_code(settings, code, attempt.verifier)
    keys = await google.google_keys()
    return google.verified_email(id_token, keys, settings.google_client_id, attempt.nonce)


@router.get("/google/callback")
async def google_callback(
    request: Request, code: Text = None, state: Text = None
) -> RedirectResponse:
    try:
        email = await _email(request, code, state)
    except google.GoogleError:
        return _to_login(request, "failed")
    settings = _settings(request)
    ip, user_agent = client_info(request)
    async with request.app.state.sessionmaker() as db, db.begin():
        user = await service.find_user(db, email)
        members = await service.active_memberships(db, user.id) if user else []
        if user is None or user.status != "active" or not members:
            return _to_login(request, "no_account")  # Google never creates accounts
        mfa_state = await _mfa_state(db, user)
        token, row = await service.create_session(
            db,
            user_id=user.id,
            tenant_id=members[0].tenant_id,
            ip=ip,
            user_agent=user_agent,
            settings=settings,
            mfa_state=mfa_state,
        )
    action = "auth.login" if mfa_state == "ok" else "auth.password_verified"
    await audit_auth(
        request, members[0].tenant_id, action, user.id, session_id=str(row.id), method="google"
    )
    response = _to_login(request)
    set_session_cookie(response, token, settings)
    return response
