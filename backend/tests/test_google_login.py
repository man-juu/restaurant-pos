"""ADR 0.57: Sign in with Google. Google is faked: a test key signs the ID tokens, so the
real checks run (signature, issuer, audience, expiry, nonce, verified email, state)."""

import time
from collections.abc import Iterator
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from joserfc import jwt
from joserfc.jwk import KeySet, RSAKey

from app.core.config import Settings
from app.core.identity import google
from app.core.identity.google_router import ATTEMPT_COOKIE
from app.main import create_app
from tests.test_auth import World, new_client
from tests.test_auth import world as world

CLIENT_ID = "test-client.apps.googleusercontent.com"
KEY = RSAKey.generate_key(2048, parameters={"kid": "k1"})
OTHER_KEY = RSAKey.generate_key(2048, parameters={"kid": "k1"})


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(
        settings.model_copy(
            update={"google_client_id": CLIENT_ID, "google_client_secret": "test-secret"}
        )
    )


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with new_client(app) as c:
        yield c


def id_token(nonce: str, email: str, key: RSAKey = KEY, **claims: Any) -> str:
    now = int(time.time())
    body = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "sub": "123",
        "iat": now,
        "exp": now + 300,
        "nonce": nonce,
        "email": email,
        "email_verified": True,
        **claims,
    }
    return jwt.encode({"alg": "RS256", "kid": "k1"}, body, key)


def sign_in(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, make: Any, state: str | None = None
) -> Any:
    """Run start, then the callback with whatever token `make(nonce)` returns."""
    start = client.get("/api/v1/auth/google/start", follow_redirects=False)
    assert start.status_code == 303
    query = parse_qs(urlparse(start.headers["location"]).query)
    assert query["code_challenge_method"] == ["S256"] and query["scope"] == ["openid email profile"]

    async def exchange(_s: Settings, code: str, verifier: str) -> str:
        assert code == "the-code" and len(verifier) > 40
        return str(make(query["nonce"][0]))

    async def keys() -> KeySet:
        return KeySet([KEY])

    monkeypatch.setattr(google, "exchange_code", exchange)
    monkeypatch.setattr(google, "google_keys", keys)
    sent_state = state or query["state"][0]
    return client.get(
        f"/api/v1/auth/google/callback?code=the-code&state={sent_state}", follow_redirects=False
    )


def test_adr_057_google_signs_in_an_invited_member(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert client.get("/api/v1/auth/providers").json() == {"google": True}
    done = sign_in(client, monkeypatch, lambda n: id_token(n, world.email.upper()))
    assert done.status_code == 303 and done.headers["location"].endswith("/login")
    session = client.get("/api/v1/auth/session").json()
    assert session["user"]["email"] == world.email and session["mfa_state"] == "ok"
    assert ATTEMPT_COOKIE not in client.cookies  # one use only


@pytest.mark.parametrize(
    "make",
    [
        lambda n: id_token(n, "nobody@example.test"),  # not invited: no account is created
        lambda n: id_token("other-nonce", "x@example.test"),
        lambda n: id_token(n, "x@example.test", aud="someone-else"),
        lambda n: id_token(n, "x@example.test", iss="https://evil.example"),
        lambda n: id_token(n, "x@example.test", exp=int(time.time()) - 60),
        lambda n: id_token(n, "x@example.test", email_verified=False),
        lambda n: id_token(n, "x@example.test", key=OTHER_KEY),  # forged signature
    ],
)
def test_adr_057_bad_tokens_are_refused(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch, make: Any
) -> None:
    done = sign_in(client, monkeypatch, make)
    assert done.status_code == 303 and "?google=" in done.headers["location"]
    assert client.get("/api/v1/auth/session").status_code == 401


def test_adr_057_state_must_match_and_unverified_email_of_member_refused(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    done = sign_in(client, monkeypatch, lambda n: id_token(n, world.email), state="forged")
    assert done.headers["location"].endswith("?google=failed")
    unverified = sign_in(
        client, monkeypatch, lambda n: id_token(n, world.email, email_verified=False)
    )
    assert unverified.headers["location"].endswith("?google=failed")
    assert client.get("/api/v1/auth/session").status_code == 401


def test_adr_057_off_without_credentials(settings: Settings) -> None:
    with new_client(create_app(settings)) as c:
        assert c.get("/api/v1/auth/providers").json() == {"google": False}
        assert c.get("/api/v1/auth/google/start", follow_redirects=False).status_code == 404
        callback = c.get("/api/v1/auth/google/callback?code=x&state=y", follow_redirects=False)
        assert callback.headers["location"].endswith("?google=failed")
