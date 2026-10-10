"""Sign in with Google (OpenID Connect, ADR 0.57): the parts that talk to Google.

Security choices, briefly:
- Authorization code flow with PKCE, a random `state` (stops login CSRF) and a `nonce`
  (stops a replayed ID token). All three live in a short-lived httpOnly cookie.
- The ID token is verified here, not trusted: Google's signature (keys from its JWKS), the
  issuer, our client id as audience, expiry and the nonce. Only a verified email counts.
- We ask only for `openid email profile`: Google learns that someone signed in to this app,
  nothing about the business. Google never creates an account; the owner invites people.
"""

import asyncio
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from authlib.oauth2.rfc7636 import create_s256_code_challenge
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import KeySet

from app.core.config import Settings

AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"  # noqa: S105 (a URL, not a secret)
JWKS = "https://www.googleapis.com/oauth2/v3/certs"
ISSUERS = ("https://accounts.google.com", "accounts.google.com")
TIMEOUT_SECONDS = 10
JWKS_TTL_SECONDS = 3600
CALLBACK = "/api/v1/auth/google/callback"


class GoogleError(Exception):
    """Anything wrong with Google's answer; the user just sees "could not sign in"."""


@dataclass(frozen=True)
class Attempt:
    state: str
    nonce: str
    verifier: str

    def cookie(self) -> str:
        return f"{self.state}.{self.nonce}.{self.verifier}"

    @classmethod
    def new(cls) -> "Attempt":
        return cls(secrets.token_urlsafe(32), secrets.token_urlsafe(32), secrets.token_urlsafe(64))

    @classmethod
    def parse(cls, value: str | None) -> "Attempt | None":
        parts = (value or "").split(".")
        return cls(*parts) if len(parts) == 3 and all(parts) else None


def redirect_uri(settings: Settings) -> str:
    return settings.app_base_url.rstrip("/") + CALLBACK


def authorize_url(settings: Settings, attempt: Attempt) -> str:
    query = {
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri(settings),
        "response_type": "code",
        "scope": "openid email profile",
        "state": attempt.state,
        "nonce": attempt.nonce,
        "code_challenge": create_s256_code_challenge(attempt.verifier),
        "code_challenge_method": "S256",
        "prompt": "select_account",
    }
    return f"{AUTHORIZE}?{urllib.parse.urlencode(query)}"


def _get_json(url: str, data: dict[str, str] | None = None) -> Any:
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    request = urllib.request.Request(url, data=body, headers={"Accept": "application/json"})  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
            return json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise GoogleError("google_unreachable") from exc


async def exchange_code(settings: Settings, code: str, verifier: str) -> str:
    """Trade the one-time code for Google's signed ID token."""
    form = {
        "code": code,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "redirect_uri": redirect_uri(settings),
        "grant_type": "authorization_code",
        "code_verifier": verifier,
    }
    answer = await asyncio.to_thread(_get_json, TOKEN, form)
    token = answer.get("id_token") if isinstance(answer, dict) else None
    if not isinstance(token, str):
        raise GoogleError("no_id_token")
    return token


_keys: dict[str, Any] = {"at": 0.0, "set": None}


async def google_keys() -> KeySet:
    if _keys["set"] is None or time.monotonic() - _keys["at"] > JWKS_TTL_SECONDS:
        _keys["set"] = KeySet.import_key_set(await asyncio.to_thread(_get_json, JWKS))
        _keys["at"] = time.monotonic()
    return _keys["set"]  # type: ignore[no-any-return]


def verified_email(id_token: str, keys: KeySet, client_id: str, nonce: str) -> str:
    """The email from a valid ID token for us, or GoogleError."""
    try:
        token = jwt.decode(id_token, keys, algorithms=["RS256"])
        jwt.JWTClaimsRegistry(
            iss={"essential": True, "values": list(ISSUERS)},
            aud={"essential": True, "value": client_id},
            exp={"essential": True},
            nonce={"essential": True, "value": nonce},
            email={"essential": True},
        ).validate(token.claims)
    except (JoseError, ValueError) as exc:
        raise GoogleError("bad_id_token") from exc
    if token.claims.get("email_verified") is not True:
        raise GoogleError("email_not_verified")
    return str(token.claims["email"]).strip().lower()
