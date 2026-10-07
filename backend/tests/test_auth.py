"""Slice 0.4a: sign-in, sessions, CSRF, lockout (FR-IDN-001, 003, 005, 007, 009; FR-AUD-001)."""

import asyncio
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import Settings
from app.core.identity.deps import COOKIE_NAME
from app.core.identity.passwords import (
    WeakPassword,
    _hasher,
    validate_new_password,
    verify_password,
)
from app.core.ids import uuid7
from app.core.models import Membership, Role, Tenant, User
from app.main import create_app
from tests.conftest import TEST_OWNER_URL

PASSWORD = "correct horse battery staple"  # noqa: S105 - test fixture
HASH = _hasher.hash(PASSWORD)


@dataclass
class World:
    a: uuid.UUID
    b: uuid.UUID
    outsider_tenant: uuid.UUID
    email: str
    user_id: uuid.UUID


async def _owner(sql_or_stmt: Any, params: dict[str, Any] | None = None) -> Any:
    engine = create_async_engine(TEST_OWNER_URL)
    try:
        async with engine.begin() as conn:
            stmt = text(sql_or_stmt) if isinstance(sql_or_stmt, str) else sql_or_stmt
            result = await conn.execute(stmt, params or {})
            return result.all() if result.returns_rows else None
    finally:
        await engine.dispose()


def owner(sql: Any, params: dict[str, Any] | None = None) -> Any:
    return asyncio.run(_owner(sql, params))


@pytest.fixture
def world() -> Iterator[World]:
    a, b, c, user = uuid7(), uuid7(), uuid7(), uuid7()
    email = f"owner-{user}@example.test"
    tenants = [
        {
            "id": t,
            "name": n,
            "legal_name": n,
            "country": "ID",
            "currency": "IDR",
            "language": "id",
            "timezone": "Asia/Jakarta",
            "profile": "cloud_kitchen",
        }
        for t, n in ((a, "Alpha"), (b, "Beta"), (c, "Gamma"))
    ]
    owner(insert(Tenant), tenants)  # type: ignore[arg-type]
    owner(insert(User).values(id=user, email=email, name="Owner", password_hash=HASH))
    for t in (a, b):  # member of Alpha and Beta, not Gamma
        role = uuid7()
        owner(insert(Role).values(id=role, tenant_id=t, name="Owner"))
        owner(insert(Membership).values(tenant_id=t, user_id=user, role_id=role))
    yield World(a=a, b=b, outsider_tenant=c, email=email, user_id=user)
    ids = {"ids": [a, b, c]}
    for sql in (
        "DELETE FROM sessions WHERE user_id = :u",
        "DELETE FROM auth_throttle",
        "DELETE FROM memberships WHERE tenant_id = ANY(:ids)",
        "DELETE FROM roles WHERE tenant_id = ANY(:ids)",
        "DELETE FROM users WHERE id = :u",
    ):
        owner(sql, {**ids, "u": user})
    asyncio.run(_cleanup_audit_and_tenants([a, b, c]))


async def _cleanup_audit_and_tenants(ids: list[uuid.UUID]) -> None:
    engine = create_async_engine(TEST_OWNER_URL)
    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL session_replication_role = replica"))
        await conn.execute(text("DELETE FROM audit_log WHERE tenant_id = ANY(:ids)"), {"ids": ids})
        await conn.execute(text("DELETE FROM tenants WHERE id = ANY(:ids)"), {"ids": ids})
    await engine.dispose()


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings.model_copy(update={"login_max_failures": 3}))


def new_client(app: FastAPI) -> TestClient:
    # https base URL: the session cookie is Secure and is only sent over HTTPS.
    return TestClient(app, base_url="https://testserver", raise_server_exceptions=False)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with new_client(app) as c:
        yield c


def login(client: TestClient, email: str, password: str = PASSWORD) -> Any:
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def audit_actions(tenant: uuid.UUID) -> list[str]:
    rows = owner("SELECT action FROM audit_log WHERE tenant_id = :t ORDER BY at", {"t": tenant})
    return [r[0] for r in rows]


def test_fr_idn_001_login_sets_hardened_cookie(client: TestClient, world: World) -> None:
    response = login(client, world.email)
    assert response.status_code == 200, response.text
    body = response.json()
    assert {t["name"] for t in body["tenants"]} == {"Alpha", "Beta"}
    assert body["active_tenant_id"] in {str(world.a), str(world.b)}
    assert body["csrf_token"]
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{COOKIE_NAME}=")
    for attribute in ("HttpOnly", "Secure", "SameSite=lax", "Path=/"):
        assert attribute in cookie
    assert "Domain" not in cookie
    assert "auth.login" in audit_actions(uuid.UUID(body["active_tenant_id"]))
    stored = owner("SELECT token_hash FROM sessions WHERE user_id = :u", {"u": world.user_id})
    token = client.cookies.get(COOKIE_NAME)
    assert token and token.encode() not in bytes(stored[0][0])  # only the hash is stored


def test_fr_idn_001_wrong_password_and_unknown_email_look_the_same(
    client: TestClient, world: World
) -> None:
    wrong = login(client, world.email, "not the password at all")
    unknown = login(client, "nobody@example.test", "not the password at all")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["code"] == unknown.json()["code"] == "invalid_credentials"
    assert "auth.login_failed" in audit_actions(world.a)


def test_fr_idn_001_login_requires_json(client: TestClient, world: World) -> None:
    # Cross-site HTML forms can only send form encoding; requiring JSON blocks login CSRF.
    response = client.post("/api/v1/auth/login", data={"email": world.email, "password": PASSWORD})
    assert response.status_code == 422


def test_fr_idn_003_lockout_after_repeated_failures(client: TestClient, world: World) -> None:
    for _ in range(3):
        assert login(client, world.email, "wrong-password-123").status_code == 401
    locked = login(client, world.email)  # even the right password is refused while locked
    assert locked.status_code == 429
    assert locked.json()["code"] == "too_many_attempts"
    owner("UPDATE auth_throttle SET locked_until = now() - interval '1 second'")
    assert login(client, world.email).status_code == 200


def test_session_required(client: TestClient) -> None:
    response = client.get("/api/v1/auth/session")
    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"


def test_csrf_token_required_for_state_changes(client: TestClient, world: World) -> None:
    csrf = login(client, world.email).json()["csrf_token"]
    rejected = client.post("/api/v1/auth/logout")
    assert rejected.status_code == 403
    assert rejected.json()["code"] == "csrf_failed"
    assert client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 204
    assert client.get("/api/v1/auth/session").status_code == 401
    assert "auth.logout" in audit_actions(world.a) + audit_actions(world.b)


def test_fr_idn_007_revoked_session_fails_on_next_request(client: TestClient, world: World) -> None:
    # Two devices = two cookies on one client (one app instance, one event loop).
    login(client, world.email)
    phone = client.cookies.get(COOKIE_NAME)
    client.cookies.clear()
    csrf = login(client, world.email).json()["csrf_token"]
    laptop = client.cookies.get(COOKIE_NAME)

    sessions = client.get("/api/v1/auth/sessions").json()
    assert len(sessions) == 2
    phone_session = next(s for s in sessions if not s["current"])
    response = client.delete(
        f"/api/v1/auth/sessions/{phone_session['id']}", headers={"X-CSRF-Token": csrf}
    )
    assert response.status_code == 204
    unknown = client.delete(f"/api/v1/auth/sessions/{uuid.uuid4()}", headers={"X-CSRF-Token": csrf})
    assert unknown.status_code == 404
    assert client.get("/api/v1/auth/session").status_code == 200  # laptop still signed in
    client.cookies.clear()
    client.cookies.set(COOKIE_NAME, phone or "")
    assert client.get("/api/v1/auth/session").status_code == 401  # phone signed out at once
    client.cookies.clear()
    client.cookies.set(COOKIE_NAME, laptop or "")  # control: a manually set cookie does work
    assert client.get("/api/v1/auth/session").status_code == 200


@pytest.mark.parametrize(
    "expire",
    [
        "UPDATE sessions SET last_seen_at = now() - interval '2 hours'",  # idle timeout
        "UPDATE sessions SET expires_at = now() - interval '1 second'",  # absolute timeout
    ],
)
def test_fr_idn_009_session_timeouts(client: TestClient, world: World, expire: str) -> None:
    login(client, world.email)
    owner(expire + " WHERE user_id = :u", {"u": world.user_id})
    assert client.get("/api/v1/auth/session").json()["code"] == "session_expired"


def test_fr_idn_005_switch_tenant_rotates_session(app: FastAPI, world: World) -> None:
    with new_client(app) as client:
        body = login(client, world.email).json()
        old_cookie = client.cookies.get(COOKIE_NAME)
        target = world.b if body["active_tenant_id"] == str(world.a) else world.a
        switched = client.post(
            "/api/v1/auth/switch-tenant",
            json={"tenant_id": str(target)},
            headers={"X-CSRF-Token": body["csrf_token"]},
        )
        assert switched.status_code == 200, switched.text
        assert switched.json()["active_tenant_id"] == str(target)
        assert switched.json()["csrf_token"] != body["csrf_token"]
        assert client.cookies.get(COOKIE_NAME) != old_cookie
        assert "auth.tenant_switched" in audit_actions(target)

        refused = client.post(
            "/api/v1/auth/switch-tenant",
            json={"tenant_id": str(world.outsider_tenant)},
            headers={"X-CSRF-Token": switched.json()["csrf_token"]},
        )
        assert refused.status_code == 404
    with new_client(app) as stale:
        stale.cookies.clear()
        stale.cookies.set(COOKIE_NAME, old_cookie or "")
        assert stale.get("/api/v1/auth/session").status_code == 401


def test_removed_membership_drops_active_tenant(client: TestClient, world: World) -> None:
    active = login(client, world.email).json()["active_tenant_id"]
    owner("UPDATE memberships SET status = 'disabled' WHERE tenant_id = :t", {"t": active})
    body = client.get("/api/v1/auth/session").json()
    assert body["active_tenant_id"] is None
    assert active not in {t["id"] for t in body["tenants"]}


@pytest.mark.anyio
async def test_password_hashing_and_policy() -> None:
    assert HASH.startswith("$argon2id$")
    assert await verify_password(HASH, PASSWORD)
    assert not await verify_password(HASH, "wrong")
    assert not await verify_password(None, PASSWORD)  # unknown user never verifies
    validate_new_password("a" * 12, privileged=True)
    validate_new_password("a" * 10, privileged=False)
    for password, privileged in (("a" * 11, True), ("a" * 9, False), ("a" * 257, False)):
        with pytest.raises(WeakPassword):
            validate_new_password(password, privileged=privileged)
