"""Slice 3k: tenant data export (FR-TEN-010) and admin export and restore requests
(FR-ADM-007). The export holds only the tenant's own rows and never secrets."""

import asyncio
import io
import json
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.admin.alerts_job import run_alerts
from app.core.config import Settings
from app.main import create_app
from tests.factories import add_member, drop_tenant, seed_tenant
from tests.test_admin import admin_app as admin_app
from tests.test_admin import admin_login, create_tenant
from tests.test_admin import admins as admins
from tests.test_auth import new_client
from tests.test_auth_mfa import enroll_as
from tests.test_inventory import HASH, PW, login

E = "/api/v1/tenant/exports"


def build(settings: Settings, *tenants: Any) -> None:
    async def go() -> None:
        engine = create_async_engine(str(settings.database_url))
        try:
            await run_alerts(
                list(tenants), async_sessionmaker(engine, expire_on_commit=False), settings
            )
        finally:
            await engine.dispose()

    asyncio.run(go())


def test_fr_ten_010_owner_exports_own_data_without_secrets(
    settings: Settings, tmp_path: Path
) -> None:
    conf = settings.model_copy(update={"upload_dir": str(tmp_path)})
    a, roles = seed_tenant("Alpha")
    b, roles_b = seed_tenant("Beta")
    try:
        add_member(a, roles["owner"], HASH)
        owner_email = add_member(a, roles["owner"], HASH)[1]
        cashier = add_member(a, roles["cashier"], HASH)[1]
        other_owner = add_member(b, roles_b["owner"], HASH)[1]
        with new_client(create_app(conf)) as c:
            o = {"X-CSRF-Token": enroll_as(c, owner_email, PW)[2]}
            asked = c.post(E, headers=o)
            assert asked.status_code == 202 and asked.json()["status"] == "queued"
            assert c.post(E, headers=o).json()["code"] == "export_already_queued"
            build(conf, a)
            [ready] = c.get(E, headers=o).json()
            assert ready["status"] == "ready" and ready["byte_size"] > 0
            got = c.get(f"{E}/{ready['id']}/download", headers=o)
            assert got.status_code == 200 and got.headers["content-type"] == "application/zip"
            z = zipfile.ZipFile(io.BytesIO(got.content))
            manifest = json.loads(z.read("manifest.json"))
            assert manifest["tenant_id"] == str(a) and "memberships" in manifest["tables"]
            assert "idempotency_keys" not in manifest["tables"]
            text = b"".join(z.read(n) for n in z.namelist() if n != "manifest.json").decode()
            assert str(b) not in text  # nothing of the other tenant
            keys = {k for line in text.splitlines() if line for k in json.loads(line)}
            assert not {k for k in keys if "hash" in k or "secret" in k or "token" in k}
            assert "outlets.jsonl" in z.namelist()

            k = login(c, cashier)
            assert c.post(E, headers=k).status_code == 403
            ob = {"X-CSRF-Token": enroll_as(c, other_owner, PW)[2]}
            assert c.get(f"{E}/{ready['id']}/download", headers=ob).status_code == 404
    finally:
        drop_tenant(a)
        drop_tenant(b)


def test_fr_adm_007_admin_starts_export_and_records_restore(
    admin_app: FastAPI, admins: dict[str, str]
) -> None:
    with new_client(admin_app) as c:
        csrf = admin_login(c, admins["super_admin"])
        tenant = create_tenant(c, csrf)
        h = {"X-CSRF-Token": csrf}
        started = c.post(f"/admin-api/tenants/{tenant}/exports", headers=h)
        assert started.status_code == 202 and started.json()["status"] == "queued"
        assert c.post(f"/admin-api/tenants/{tenant}/exports", headers=h).json()["code"] == (
            "export_already_queued"
        )
        when = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        restore = {"restore_to": when, "reason": "Owner deleted a day of sales by mistake"}
        made = c.post(f"/admin-api/tenants/{tenant}/restore-requests", json=restore, headers=h)
        assert made.status_code == 201 and made.json()["status"] == "requested"
        future = {**restore, "restore_to": (datetime.now(UTC) + timedelta(days=1)).isoformat()}
        assert (
            c.post(f"/admin-api/tenants/{tenant}/restore-requests", json=future, headers=h).json()[
                "code"
            ]
            == "restore_point_in_future"
        )
        s = {"X-CSRF-Token": admin_login(c, admins["support"])}
        assert c.get(f"/admin-api/tenants/{tenant}/restore-requests", headers=s).status_code == 200
        assert c.post(f"/admin-api/tenants/{tenant}/exports", headers=s).status_code == 403
