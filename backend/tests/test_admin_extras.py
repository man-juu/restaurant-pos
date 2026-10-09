"""Slice 1m: usage overview and feature flags (FR-ADM-004, 006), owner notices on
subscription changes (FR-SUB-006) and the tenant audit log viewer (FR-AUD-004)."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine

from app.admin.service import run_subscription_job
from app.core.db import create_sessionmaker
from tests.conftest import TEST_ADMIN_URL
from tests.factories import add_member, drop_tenant, seed_tenant
from tests.test_admin import admin_app as admin_app
from tests.test_admin import admin_login, create_tenant
from tests.test_admin import admins as admins
from tests.test_auth import new_client
from tests.test_inventory import HASH, login
from tests.test_purchasing import client as client
from tests.test_purchasing import tenant_sql


def test_fr_adm_004_006_usage_and_flags(admin_app: FastAPI, admins: dict[str, str]) -> None:
    with new_client(admin_app) as c:
        csrf = admin_login(c, admins["super_admin"])
        tenant = create_tenant(c, csrf)
        h = {"X-CSRF-Token": csrf}
        usage = c.get(f"/admin-api/tenants/{tenant}/usage", headers=h).json()
        assert usage["outlets"] >= 0 and usage["job_failures_7d"] == 0
        assert usage["flags"]["ai_images"] is True  # the registry default
        off = c.put(
            f"/admin-api/tenants/{tenant}/flags", json={"flags": {"ai_images": False}}, headers=h
        )
        assert off.status_code == 200 and off.json()["ai_images"] is False
        bad = c.put(f"/admin-api/tenants/{tenant}/flags", json={"flags": {"nope": True}}, headers=h)
        assert bad.status_code == 422 and bad.json()["code"] == "unknown_flag"
        assert c.get(f"/admin-api/tenants/{uuid.uuid4()}/usage", headers=h).status_code == 404
        csrf2 = admin_login(c, admins["support"])
        denied = c.put(
            f"/admin-api/tenants/{tenant}/flags",
            json={"flags": {"ai_images": True}},
            headers={"X-CSRF-Token": csrf2},
        )
        assert denied.status_code == 403


def test_fr_adm_006_flag_turns_a_feature_off_for_one_tenant(client: TestClient) -> None:
    a, roles = seed_tenant("Alpha")
    try:
        _, email = add_member(a, roles["manager"], HASH)
        tenant_sql(
            a,
            "INSERT INTO tenant_flags (tenant_id, flag, enabled) VALUES (:t, 'ai_images', false)",
            {"t": a},
        )
        h = login(client, email)
        caps = client.get("/api/v1/me/capabilities", headers=h).json()
        assert "ai_images" not in caps["flags"] and "reports_export" in caps["flags"]
        usage = client.get("/api/v1/catalog/ai-images/usage", headers=h).json()
        assert usage["enabled"] is False and usage["remaining"] == 0
        made = client.post("/api/v1/catalog/ai-images", json={"prompt": "nasi goreng"}, headers=h)
        assert made.status_code in (403, 409, 422, 503) and made.json()["code"] == "ai_disabled"
    finally:
        drop_tenant(a)


def test_fr_sub_006_owners_are_told_when_the_state_changes() -> None:
    ends = datetime.now(UTC) + timedelta(days=30)
    a, roles = seed_tenant("Alpha", plan_type="paid", ends_at=ends)
    try:
        owner_id, _ = add_member(a, roles["owner"], HASH)
        manager_id, _ = add_member(a, roles["manager"], HASH)

        async def run(now: datetime) -> None:
            engine = create_async_engine(TEST_ADMIN_URL)
            async with create_sessionmaker(engine)() as db, db.begin():
                await run_subscription_job(db, now)
            await engine.dispose()

        asyncio.run(run(ends - timedelta(days=40)))  # active
        asyncio.run(run(ends + timedelta(days=1)))  # grace
        rows = tenant_sql(
            a,
            "SELECT user_id, params->>'state' FROM notifications "
            "WHERE kind = 'subscription_state' ORDER BY created_at",
        )
        assert [(r[0], r[1]) for r in rows] == [(owner_id, "active"), (owner_id, "grace")]
        assert manager_id not in {r[0] for r in rows}
    finally:
        drop_tenant(a)


def test_fr_aud_004_audit_log_filters_and_export(client: TestClient) -> None:
    a, roles = seed_tenant("Alpha")
    b, roles_b = seed_tenant("Beta")
    try:
        _, manager = add_member(a, roles["manager"], HASH)
        _, cashier = add_member(a, roles["cashier"], HASH)
        _, other = add_member(b, roles_b["manager"], HASH)
        h = login(client, manager)
        made = client.post(
            "/api/v1/catalog/units",
            json={"code": "box", "name": "box", "dimension": "count"},
            headers=h,
        )
        assert made.status_code in (200, 201), made.text
        page = client.get("/api/v1/audit?action=catalog.", headers=h).json()
        assert page["items"] and all(r["action"].startswith("catalog.") for r in page["items"])
        assert page["items"][0]["user_name"] == "U"
        today = datetime.now(UTC).date()
        span = f"from={today - timedelta(days=1)}&to={today + timedelta(days=1)}"
        csv = client.get(f"/api/v1/audit/export?{span}&format=csv", headers=h)
        assert csv.status_code == 200 and b"catalog." in csv.content
        unbounded = client.get("/api/v1/audit/export", headers=h)
        assert unbounded.status_code == 422
        injected = client.get("/api/v1/audit?action=%25", headers=h)
        assert injected.status_code == 422  # only [a-z_.]: no LIKE wildcards
        c = login(client, cashier)
        assert client.get("/api/v1/audit", headers=c).status_code == 403
        o = login(client, other)
        assert client.get("/api/v1/audit?action=catalog.", headers=o).json()["items"] == []
    finally:
        drop_tenant(a)
        drop_tenant(b)


def test_sync_roles_adds_only_permissions_new_to_the_tenant() -> None:
    from app.admin.service import sync_roles

    a, roles = seed_tenant("Alpha")
    try:
        # As if the tenant predates sales reports, and its owner took stock reports
        # away from managers on purpose.
        tenant_sql(a, "DELETE FROM role_permissions WHERE permission_code = 'sales.report.view'")
        tenant_sql(
            a,
            "DELETE FROM role_permissions WHERE permission_code = 'inventory.report.view' "
            "AND role_id = :r",
            {"r": roles["manager"]},
        )

        async def run() -> int:
            engine = create_async_engine(TEST_ADMIN_URL)
            async with create_sessionmaker(engine)() as db, db.begin():
                added = await sync_roles(db)
            await engine.dispose()
            return added

        assert asyncio.run(run()) > 0
        held = {
            r[0]
            for r in tenant_sql(
                a,
                "SELECT permission_code FROM role_permissions WHERE role_id = :r",
                {"r": roles["manager"]},
            )
        }
        assert "sales.report.view" in held  # new to the tenant: granted per the template
        assert "inventory.report.view" not in held  # removed by the owner: stays removed
    finally:
        drop_tenant(a)
