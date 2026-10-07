"""Slice 0.4b: TOTP 2FA (FR-IDN-002), password reset (FR-IDN-008), invitations (FR-IDN-006)."""

import asyncio
import base64
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
from app.core.crypto import SecretBox
from app.core.identity import totp
from app.core.identity.deps import COOKIE_NAME
from app.core.identity.passwords import WeakPassword, _hasher, validate_new_password
from app.core.ids import uuid7
from app.core.models import Membership, Role, Tenant, User
from app.main import create_app
from tests.conftest import TEST_OWNER_URL
from tests.test_auth import new_client, owner

PASSWORD = "a long and unusual owner passphrase"  # noqa: S105 - test fixture
STAFF_PASSWORD = "another staff passphrase"  # noqa: S105 - test fixture


@dataclass
class World:
    tenant: uuid.UUID
    owner_email: str
    owner_id: uuid.UUID
    staff_email: str
    staff_role: uuid.UUID


@pytest.fixture
def world() -> Iterator[World]:
    tenant, owner_id, staff_id, owner_role, staff_role = (uuid7() for _ in range(5))
    owner_email, staff_email = f"own-{owner_id}@example.test", f"staff-{staff_id}@example.test"
    owner(
        insert(Tenant).values(
            id=tenant,
            name="Kitchen",
            legal_name="Kitchen",
            country="ID",
            currency="IDR",
            language="id",
            timezone="Asia/Jakarta",
            profile="cloud_kitchen",
        )
    )
    owner(insert(Role).values(id=owner_role, tenant_id=tenant, name="Owner", requires_mfa=True))
    owner(insert(Role).values(id=staff_role, tenant_id=tenant, name="Cashier"))
    for uid, email, pw, role in (
        (owner_id, owner_email, PASSWORD, owner_role),
        (staff_id, staff_email, STAFF_PASSWORD, staff_role),
    ):
        owner(insert(User).values(id=uid, email=email, name="U", password_hash=_hasher.hash(pw)))
        owner(insert(Membership).values(tenant_id=tenant, user_id=uid, role_id=role))
    yield World(tenant, owner_email, owner_id, staff_email, staff_role)
    asyncio.run(_cleanup(tenant))


async def _cleanup(tenant: uuid.UUID) -> None:
    engine = create_async_engine(TEST_OWNER_URL)
    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL session_replication_role = replica"))
        users = "SELECT user_id FROM memberships WHERE tenant_id = :t"
        for sql in (
            f"DELETE FROM sessions WHERE user_id IN ({users})",
            f"DELETE FROM recovery_codes WHERE user_id IN ({users})",
            f"DELETE FROM password_resets WHERE user_id IN ({users})",
            "DELETE FROM auth_throttle",
            "DELETE FROM audit_log WHERE tenant_id = :t",
            "DELETE FROM invitations WHERE tenant_id = :t",
            "CREATE TEMP TABLE gone AS " + users,
            "DELETE FROM memberships WHERE tenant_id = :t",
            "DELETE FROM users WHERE id IN (SELECT user_id FROM gone)",
            "DELETE FROM roles WHERE tenant_id = :t",
            "DELETE FROM tenants WHERE id = :t",
        ):
            await conn.execute(text(sql), {"t": tenant})
    await engine.dispose()


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings.model_copy(update={"login_max_failures": 3}))


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with new_client(app) as c:
        yield c


def login(client: TestClient, email: str, password: str) -> dict[str, Any]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def enroll(client: TestClient, world: World) -> tuple[str, list[str], str]:
    """Sign in as the owner and complete 2FA setup; returns (secret, recovery codes, csrf)."""
    csrf = login(client, world.owner_email, PASSWORD)["csrf_token"]
    secret = client.post("/api/v1/auth/mfa/setup", headers={"X-CSRF-Token": csrf}).json()["secret"]
    response = client.post(
        "/api/v1/auth/mfa/confirm",
        json={"code": totp.code_at(secret, totp.current_step())},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200, response.text
    session = client.get("/api/v1/auth/session").json()
    return secret, response.json()["recovery_codes"], session["csrf_token"]


# --- TOTP and crypto units ---------------------------------------------------------------

RFC_SECRET = base64.b32encode(b"12345678901234567890").decode()


@pytest.mark.parametrize(
    ("unix_time", "expected"),
    [(59, "287082"), (1111111109, "081804"), (1234567890, "005924"), (2000000000, "279037")],
)
def test_totp_matches_rfc6238_vectors(unix_time: int, expected: str) -> None:
    assert totp.code_at(RFC_SECRET, totp.current_step(unix_time)) == expected


def test_totp_refuses_replay_and_old_codes() -> None:
    now = 1234567890.0
    step = totp.current_step(now)
    code = totp.code_at(RFC_SECRET, step)
    assert totp.verify(RFC_SECRET, code, last_used_step=None, now=now) == step
    assert totp.verify(RFC_SECRET, code, last_used_step=step, now=now) is None  # replay
    old = totp.code_at(RFC_SECRET, step - 3)
    assert totp.verify(RFC_SECRET, old, last_used_step=None, now=now) is None


def test_secret_box_rejects_tampering_and_wrong_owner() -> None:
    box = SecretBox(base64.b64encode(b"k" * 32).decode())
    blob = box.encrypt("JBSWY3DPEHPK3PXP", context=b"user-1")
    assert box.decrypt(blob, context=b"user-1") == "JBSWY3DPEHPK3PXP"
    with pytest.raises(Exception):  # noqa: B017 - any failure is correct
        box.decrypt(blob, context=b"user-2")
    with pytest.raises(Exception):  # noqa: B017
        box.decrypt(blob[:-1] + bytes([blob[-1] ^ 1]), context=b"user-1")


@pytest.mark.parametrize(
    ("password", "reason"),
    [("1234567890", "common"), ("qwertyuiop", "common"), ("rina.kitchen-2026", "contains_email")],
)
def test_password_policy_rejects_common_and_email_based(password: str, reason: str) -> None:
    with pytest.raises(WeakPassword) as exc:
        validate_new_password(password, privileged=False, email="rina.kitchen@example.test")
    assert exc.value.details["reason"] == reason


# --- 2FA flows ------------------------------------------------------------------------------


def test_fr_idn_002_owner_must_enroll_before_access(client: TestClient, world: World) -> None:
    body = login(client, world.owner_email, PASSWORD)
    assert body["mfa_state"] == "enroll"
    assert body["active_tenant_id"] is None
    blocked = client.get("/api/v1/auth/sessions")
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "mfa_required"

    before = client.cookies.get(COOKIE_NAME)
    csrf = body["csrf_token"]
    setup = client.post("/api/v1/auth/mfa/setup", headers={"X-CSRF-Token": csrf}).json()
    assert setup["otpauth_uri"].startswith("otpauth://totp/")
    confirm = client.post(
        "/api/v1/auth/mfa/confirm",
        json={"code": totp.code_at(setup["secret"], totp.current_step())},
        headers={"X-CSRF-Token": csrf},
    )
    assert confirm.status_code == 200
    assert len(confirm.json()["recovery_codes"]) == 10
    assert client.cookies.get(COOKIE_NAME) != before  # session rotated
    assert client.get("/api/v1/auth/sessions").status_code == 200
    session = client.get("/api/v1/auth/session").json()
    assert session["mfa_state"] == "ok"
    assert session["active_tenant_id"] == str(world.tenant)

    stored = owner("SELECT totp_secret_encrypted FROM users WHERE id = :u", {"u": world.owner_id})
    assert setup["secret"].encode() not in bytes(stored[0][0])  # encrypted at rest
    actions = [
        r[0]
        for r in owner("SELECT action FROM audit_log WHERE tenant_id = :t", {"t": world.tenant})
    ]
    assert "auth.mfa_enabled" in actions


def test_fr_idn_002_sign_in_needs_code_and_codes_cannot_be_replayed(
    client: TestClient, world: World
) -> None:
    secret, _, _ = enroll(client, world)
    client.cookies.clear()
    body = login(client, world.owner_email, PASSWORD)
    assert body["mfa_state"] == "verify"
    csrf = body["csrf_token"]
    wrong = client.post(
        "/api/v1/auth/mfa/verify", json={"code": "000000"}, headers={"X-CSRF-Token": csrf}
    )
    assert wrong.status_code == 400
    # The code used during enrolment is burned; wait-free test: use the next step's code.
    code = totp.code_at(secret, totp.current_step() + 1)
    ok = client.post("/api/v1/auth/mfa/verify", json={"code": code}, headers={"X-CSRF-Token": csrf})
    assert ok.status_code == 200, ok.text
    assert ok.json()["mfa_state"] == "ok"

    client.cookies.clear()
    csrf = login(client, world.owner_email, PASSWORD)["csrf_token"]
    replay = client.post(
        "/api/v1/auth/mfa/verify", json={"code": code}, headers={"X-CSRF-Token": csrf}
    )
    assert replay.status_code == 400


def test_fr_idn_002_recovery_code_works_once(client: TestClient, world: World) -> None:
    _, codes, _ = enroll(client, world)
    for expected in (200, 400):
        client.cookies.clear()
        csrf = login(client, world.owner_email, PASSWORD)["csrf_token"]
        response = client.post(
            "/api/v1/auth/mfa/verify",
            json={"code": codes[0].lower()},
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == expected


def test_fr_idn_003_mfa_codes_are_rate_limited(client: TestClient, world: World) -> None:
    secret, _, _ = enroll(client, world)
    client.cookies.clear()
    csrf = login(client, world.owner_email, PASSWORD)["csrf_token"]
    for _ in range(3):
        client.post(
            "/api/v1/auth/mfa/verify", json={"code": "000000"}, headers={"X-CSRF-Token": csrf}
        )
    good = totp.code_at(secret, totp.current_step() + 1)
    locked = client.post(
        "/api/v1/auth/mfa/verify", json={"code": good}, headers={"X-CSRF-Token": csrf}
    )
    assert locked.status_code == 429


def test_staff_without_mfa_role_signs_in_directly(client: TestClient, world: World) -> None:
    assert login(client, world.staff_email, STAFF_PASSWORD)["mfa_state"] == "ok"


# --- Password reset ----------------------------------------------------------------------


def _token(app: FastAPI) -> str:
    return app.state.mailer.sent[-1].link.split("#token=")[1]  # type: ignore[no-any-return]


def test_fr_idn_008_password_reset_flow(app: FastAPI, client: TestClient, world: World) -> None:
    csrf_staff_session = login(client, world.staff_email, STAFF_PASSWORD)["csrf_token"]
    assert csrf_staff_session
    assert (
        client.post(
            "/api/v1/auth/password-reset/request", json={"email": "nobody@example.test"}
        ).status_code
        == 202
    )
    assert app.state.mailer.sent == []  # unknown email: same answer, no mail
    assert (
        client.post(
            "/api/v1/auth/password-reset/request", json={"email": world.staff_email}
        ).status_code
        == 202
    )
    token = _token(app)
    assert app.state.mailer.sent[-1].link.startswith("http://localhost:5173/reset-password#token=")

    weak = client.post(
        "/api/v1/auth/password-reset/confirm", json={"token": token, "new_password": "short"}
    )
    assert weak.status_code == 422
    new_password = "a fresh staff passphrase"  # noqa: S105 - test value
    done = client.post(
        "/api/v1/auth/password-reset/confirm", json={"token": token, "new_password": new_password}
    )
    assert done.status_code == 204
    assert client.get("/api/v1/auth/session").status_code == 401  # signed out everywhere
    reuse = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": token, "new_password": new_password + "x"},
    )
    assert reuse.status_code == 400
    login(client, world.staff_email, new_password)


def test_fr_idn_008_expired_reset_token(app: FastAPI, client: TestClient, world: World) -> None:
    client.post("/api/v1/auth/password-reset/request", json={"email": world.staff_email})
    owner("UPDATE password_resets SET expires_at = now() - interval '1 second'")
    response = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": _token(app), "new_password": "a fresh staff passphrase"},
    )
    assert response.status_code == 400


# --- Invitations -------------------------------------------------------------------------


def test_fr_idn_006_invite_and_accept_new_user(
    app: FastAPI, client: TestClient, world: World
) -> None:
    _, _, csrf = enroll(client, world)
    email = f"new-{uuid.uuid4()}@example.test"
    created = client.post(
        "/api/v1/invitations",
        json={"email": email, "role_id": str(world.staff_role)},
        headers={"X-CSRF-Token": csrf},
    )
    assert created.status_code == 201, created.text
    token = _token(app)
    client.cookies.clear()
    accept = {"token": token, "name": "New Cook", "password": "new cook passphrase"}
    assert client.post("/api/v1/auth/invitations/accept", json=accept).status_code == 204
    assert (
        client.post("/api/v1/auth/invitations/accept", json=accept).status_code == 400
    )  # single use
    body = login(client, email, "new cook passphrase")
    assert body["active_tenant_id"] == str(world.tenant)
    owner(
        "DELETE FROM sessions WHERE user_id = (SELECT id FROM users WHERE email = :e)", {"e": email}
    )


def test_fr_idn_006_expired_invitation(app: FastAPI, client: TestClient, world: World) -> None:
    _, _, csrf = enroll(client, world)
    client.post(
        "/api/v1/invitations",
        json={"email": "late@example.test", "role_id": str(world.staff_role)},
        headers={"X-CSRF-Token": csrf},
    )
    owner("UPDATE invitations SET expires_at = now() - interval '1 second'")
    response = client.post(
        "/api/v1/auth/invitations/accept",
        json={"token": _token(app), "name": "Late", "password": "late cook passphrase"},
    )
    assert response.status_code == 400


def test_fr_idn_006_staff_cannot_invite(client: TestClient, world: World) -> None:
    csrf = login(client, world.staff_email, STAFF_PASSWORD)["csrf_token"]
    response = client.post(
        "/api/v1/invitations",
        json={"email": "x@example.test", "role_id": str(world.staff_role)},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 403
