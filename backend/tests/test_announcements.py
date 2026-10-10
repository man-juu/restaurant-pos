"""Slice 3k: platform announcements shown in-app to all or chosen tenants (FR-ADM-005)."""

from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.factories import add_member, drop_tenant, seed_tenant
from tests.test_admin import admin_app as admin_app
from tests.test_admin import admin_login
from tests.test_admin import admins as admins
from tests.test_auth import new_client
from tests.test_inventory import HASH, login
from tests.test_purchasing import client as client

A = "/api/v1/announcements"


def body(**extra: object) -> dict[str, object]:
    now = datetime.now(UTC)
    return {
        "title_en": "Maintenance tonight",
        "title_id": "Pemeliharaan malam ini",
        "body_en": "The app is down 23:00-23:15 WIB.",
        "body_id": "Aplikasi berhenti 23:00-23:15 WIB.",
        "level": "warning",
        "starts_at": (now - timedelta(minutes=5)).isoformat(),
        "ends_at": (now + timedelta(hours=2)).isoformat(),
        **extra,
    }


def test_fr_adm_005_targeted_announcement_and_dismissal(
    admin_app: FastAPI, admins: dict[str, str], client: TestClient
) -> None:
    a, roles = seed_tenant("Alpha")
    b, roles_b = seed_tenant("Beta")
    try:
        cashier_a = add_member(a, roles["cashier"], HASH)[1]
        manager_b = add_member(b, roles_b["manager"], HASH)[1]
        with new_client(admin_app) as ac:
            h = {"X-CSRF-Token": admin_login(ac, admins["super_admin"])}
            only_a = ac.post("/admin-api/announcements", json=body(tenant_ids=[str(a)]), headers=h)
            assert only_a.status_code == 201, only_a.text
            everyone = ac.post(
                "/admin-api/announcements", json=body(title_en="New: menu engineering"), headers=h
            )
            assert everyone.status_code == 201
            bad = ac.post(
                "/admin-api/announcements", json=body(ends_at="2020-01-01T00:00:00Z"), headers=h
            )
            assert bad.status_code == 422
            s = {"X-CSRF-Token": admin_login(ac, admins["support"])}
            assert ac.post("/admin-api/announcements", json=body(), headers=s).status_code == 403

        ha = login(client, cashier_a)
        mine = client.get(f"{A}?lang=id", headers=ha).json()
        assert len(mine) == 2 and "Pemeliharaan malam ini" in {m["title"] for m in mine}
        first = only_a.json()["id"]
        assert client.post(f"{A}/{first}/dismiss", headers=ha).status_code == 204
        assert [m["id"] for m in client.get(A, headers=ha).json()] == [everyone.json()["id"]]

        hb = login(client, manager_b)
        assert [m["title"] for m in client.get(A, headers=hb).json()] == ["New: menu engineering"]
        assert client.post(f"{A}/{first}/dismiss", headers=hb).status_code == 404  # not for B
    finally:
        drop_tenant(a)
        drop_tenant(b)
