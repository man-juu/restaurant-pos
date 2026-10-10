"""Slice 0.6: platform admin (FR-ADM-001 to 003, FR-SUB-001 to 003 and 005, FR-AUD-003)."""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import insert, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from app.admin.main import create_admin_app
from app.admin.models import AdminUser
from app.admin.router import ImpersonationExpired, _read_only_view
from app.admin.security import AdminContext
from app.admin.service import run_subscription_job
from app.core.config import Settings
from app.core.db import create_sessionmaker
from app.core.identity import totp
from app.core.identity.passwords import _hasher
from app.core.ids import uuid7
from app.main import create_app
from tests.conftest import TEST_ADMIN_URL
from tests.factories import drop_tenant
from tests.test_auth import new_client, owner

PW = "platform admin passphrase"
TENANT = {
    "name": "Dapur Sehat",
    "legal_name": "PT Dapur Sehat",
    "profile": "cloud_kitchen",
    "owner_email": "",
    "plan_type": "paid",
}


@pytest.fixture
def admins() -> Iterator[dict[str, str]]:
    emails = {}
    for role in ("super_admin", "support"):
        email = f"{role}-{uuid.uuid4()}@platform.test"
        owner(
            insert(AdminUser).values(
                id=uuid7(), email=email, name=role, role=role, password_hash=_hasher.hash(PW)
            )
        )
        emails[role] = email
    yield emails
    owner("DELETE FROM admin_sessions")
    owner("DELETE FROM auth_throttle")
    created = owner("SELECT id FROM tenants WHERE name = 'Dapur Sehat'")
    owner("DELETE FROM impersonation_sessions")
    for (tenant_id,) in created:
        drop_tenant(tenant_id)
    owner("DELETE FROM admin_users WHERE email LIKE '%@platform.test'")


@pytest.fixture
def admin_app(settings: Settings) -> FastAPI:
    return create_admin_app(settings)


def admin_login(client: TestClient, email: str) -> str:
    """Full admin sign-in including mandatory TOTP enrolment; returns the CSRF token."""
    client.cookies.clear()
    body = client.post("/admin-api/auth/login", json={"email": email, "password": PW}).json()
    assert body["mfa_state"] == "enroll", body
    headers = {"X-CSRF-Token": body["csrf_token"]}
    secret = client.post("/admin-api/auth/mfa/setup", headers=headers).json()["secret"]
    done = client.post(
        "/admin-api/auth/mfa/confirm",
        json={"code": totp.code_at(secret, totp.current_step())},
        headers=headers,
    )
    assert done.status_code == 200, done.text
    return str(done.json()["csrf_token"])


def create_tenant(client: TestClient, csrf: str, **overrides: Any) -> uuid.UUID:
    payload = {**TENANT, "owner_email": f"owner-{uuid.uuid4()}@example.test", **overrides}
    response = client.post("/admin-api/tenants", json=payload, headers={"X-CSRF-Token": csrf})
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["id"])


def actions(tenant_id: uuid.UUID) -> list[tuple[str, str]]:
    rows = owner(
        "SELECT action, actor_type FROM audit_log WHERE tenant_id = :t ORDER BY at",
        {"t": tenant_id},
    )
    return [(r[0], r[1]) for r in rows]


def test_fr_adm_002_totp_is_mandatory_for_admins(
    admin_app: FastAPI, admins: dict[str, str]
) -> None:
    with new_client(admin_app) as client:
        body = client.post(
            "/admin-api/auth/login", json={"email": admins["support"], "password": PW}
        ).json()
        assert body["mfa_state"] == "enroll"
        blocked = client.get("/admin-api/tenants")
        assert blocked.status_code == 403
        assert blocked.json()["code"] == "mfa_required"
        admin_login(client, admins["support"])
        assert client.get("/admin-api/tenants").status_code == 200


def test_tenant_session_cannot_reach_admin_api(admin_app: FastAPI, settings: Settings) -> None:
    with new_client(admin_app) as client:
        client.cookies.set("__Host-session", "a-tenant-session-token")
        assert client.get("/admin-api/tenants").status_code == 401


def test_fr_adm_001_create_tenant_with_defaults(admin_app: FastAPI, admins: dict[str, str]) -> None:
    with new_client(admin_app) as client:
        csrf = admin_login(client, admins["super_admin"])
        tenant_id = create_tenant(client, csrf, ends_at="2027-01-01T00:00:00Z")
        mail = admin_app.state.mailer.sent[-1]
        assert "/accept-invitation#token=" in mail.link
        listed = {t["id"]: t for t in client.get("/admin-api/tenants").json()}[str(tenant_id)]
    assert listed["modules"] == sorted(
        ["sales", "inventory", "purchasing", "production", "finance", "reports"]
    )
    roles = owner("SELECT template_key FROM roles WHERE tenant_id = :t", {"t": tenant_id})
    assert {r[0] for r in roles} >= {"owner", "co_owner", "manager", "viewer"}
    assert ("admin.tenant_created", "admin") in actions(tenant_id)  # FR-AUD-003


def test_support_admin_cannot_create_tenants(admin_app: FastAPI, admins: dict[str, str]) -> None:
    with new_client(admin_app) as client:
        csrf = admin_login(client, admins["support"])
        response = client.post(
            "/admin-api/tenants",
            json={**TENANT, "owner_email": "x@example.test"},
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 403
        assert response.json()["code"] == "admin_role_required"


def test_module_dependencies_are_enforced(admin_app: FastAPI, admins: dict[str, str]) -> None:
    with new_client(admin_app) as client:
        csrf = admin_login(client, admins["super_admin"])
        tenant_id = create_tenant(client, csrf)
        bad = client.put(
            f"/admin-api/tenants/{tenant_id}/modules",
            json={"modules": ["purchasing"]},  # needs inventory
            headers={"X-CSRF-Token": csrf},
        )
        assert bad.status_code == 422
        assert bad.json()["code"] == "module_dependency_missing"
        ok = client.put(
            f"/admin-api/tenants/{tenant_id}/modules",
            json={"modules": ["inventory", "purchasing"]},
            headers={"X-CSRF-Token": csrf},
        )
        assert ok.status_code == 204
    enabled = owner(
        "SELECT module FROM tenant_modules WHERE tenant_id = :t AND enabled", {"t": tenant_id}
    )
    assert {r[0] for r in enabled} == {"inventory", "purchasing"}


def test_suspend_blocks_tenant_users(
    admin_app: FastAPI, admins: dict[str, str], settings: Settings
) -> None:
    from tests.factories import add_member

    with new_client(admin_app) as admin:
        csrf = admin_login(admin, admins["super_admin"])
        tenant_id = create_tenant(admin, csrf)
        viewer_role = owner(
            "SELECT id FROM roles WHERE tenant_id = :t AND template_key = 'viewer'",
            {"t": tenant_id},
        )[0][0]
        _, email = add_member(tenant_id, viewer_role, _hasher.hash(PW))
        with new_client(create_app(settings)) as user:
            user.post("/api/v1/auth/login", json={"email": email, "password": PW})
            assert user.get("/api/v1/outlets").status_code == 200
            response = admin.put(
                f"/admin-api/tenants/{tenant_id}/status",
                json={"status": "suspended"},
                headers={"X-CSRF-Token": csrf},
            )
            assert response.status_code == 204
            assert user.get("/api/v1/outlets").json()["code"] in (
                "tenant_suspended",
                "no_active_tenant",
            )
    assert ("admin.tenant_suspended", "admin") in actions(tenant_id)


def test_fr_sub_002_003_daily_job_records_transitions(
    admin_app: FastAPI, admins: dict[str, str]
) -> None:
    ends = datetime(2026, 11, 1, tzinfo=UTC)
    with new_client(admin_app) as client:
        csrf = admin_login(client, admins["super_admin"])
        tenant_id = create_tenant(client, csrf)
        response = client.put(
            f"/admin-api/tenants/{tenant_id}/subscription",
            json={
                "plan_type": "paid",
                "starts_at": "2026-10-01T00:00:00Z",
                "ends_at": ends.isoformat(),
                "grace_days": 7,
                "reminders_enabled": True,
                "reminder_days": [14, 7],
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 204

    async def run(now: datetime) -> list[tuple[uuid.UUID, str, str]]:
        engine = create_async_engine(TEST_ADMIN_URL)
        async with create_sessionmaker(engine)() as db, db.begin():
            changes = await run_subscription_job(db, now)
        await engine.dispose()
        return [c for c in changes if c[0] == tenant_id]

    states = []
    for days in (-30, -10, -10, 1, 8):  # controllable clock; the repeat must not log again
        changes = asyncio.run(run(ends + timedelta(days=days)))
        states.append(changes[0][2] if changes else None)
    assert states == ["active", "expiring", None, "grace", "read_only"]
    logged = [a for a in actions(tenant_id) if a[0] == "subscription.state_changed"]
    assert len(logged) == 4
    assert ("admin.subscription_changed", "admin") in actions(tenant_id)


def test_fr_adm_003_impersonation_is_read_only_and_expires(
    admin_app: FastAPI, admins: dict[str, str]
) -> None:
    with new_client(admin_app) as client:
        super_csrf = admin_login(client, admins["super_admin"])
        tenant_id = create_tenant(client, super_csrf)
        csrf = admin_login(client, admins["support"])
        too_short = client.post(
            f"/admin-api/tenants/{tenant_id}/impersonations",
            json={"reason": "help"},
            headers={"X-CSRF-Token": csrf},
        )
        assert too_short.status_code == 422, too_short.text  # a real reason is required
        started = client.post(
            f"/admin-api/tenants/{tenant_id}/impersonations",
            json={"reason": "Owner reported missing outlet", "minutes": 15},
            headers={"X-CSRF-Token": csrf},
        )
        assert started.status_code == 201
        imp_id = started.json()["id"]
        assert client.get(f"/admin-api/impersonations/{imp_id}/summary").status_code == 200

        support_id = owner("SELECT id FROM admin_users WHERE email = :e", {"e": admins["support"]})[
            0
        ][0]

        async def try_write() -> None:
            engine = create_async_engine(TEST_ADMIN_URL)
            request: Any = SimpleNamespace(
                app=SimpleNamespace(state=SimpleNamespace(sessionmaker=create_sessionmaker(engine)))
            )
            ctx = AdminContext(uuid.uuid4(), support_id, admins["support"], "support", "ok")
            try:
                async with _read_only_view(request, ctx, uuid.UUID(imp_id)) as (db, tid):
                    await db.execute(
                        text("UPDATE tenants SET name = 'hacked' WHERE id = :t"), {"t": tid}
                    )
            finally:
                await engine.dispose()

        with pytest.raises(DBAPIError, match="read-only transaction"):
            asyncio.run(try_write())

        owner("UPDATE impersonation_sessions SET expires_at = now() - interval '1 second'")
        expired = client.get(f"/admin-api/impersonations/{imp_id}/summary")
        assert expired.status_code == 403
        assert expired.json()["code"] == ImpersonationExpired.code
    assert ("admin.impersonation_started", "admin") in actions(tenant_id)


def test_tenant_api_role_cannot_touch_platform_tables() -> None:
    rows = owner(
        "SELECT has_table_privilege('pos_app', t, 'SELECT') FROM unnest(ARRAY["
        "'admin_users', 'admin_sessions', 'impersonation_sessions']) t"
    )
    assert [r[0] for r in rows] == [False, False, False]
