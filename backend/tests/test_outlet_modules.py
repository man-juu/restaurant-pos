"""Modules per outlet (FR-TEN-003, owner 2026-10-10): the owner switches modules per outlet,
dependencies hold per outlet, and the server hides an outlet from a module switched off
there (not just the UI)."""

from typing import Any

from fastapi.testclient import TestClient

from tests.factories import add_member
from tests.test_auth_mfa import enroll_as
from tests.test_inventory import HASH, PW, login
from tests.test_pos import POS
from tests.test_pos import world as world
from tests.test_purchasing import client as client
from tests.test_sales_days import menu as menu

OM = "/api/v1/outlet-modules"


def test_fr_ten_003_modules_per_outlet(
    client: TestClient, world: dict[str, Any], menu: dict[str, Any]
) -> None:
    owner = add_member(world["a"], _role(world["a"], "owner"), HASH)[1]
    m = {"X-CSRF-Token": enroll_as(client, owner, PW)[2]}
    got = client.get(OM, headers=m)
    assert got.status_code == 200, got.text
    assert {"inventory", "sales"} <= set(got.json()["modules"])
    other = str(world["other"])
    # Sales needs inventory at the same outlet.
    bad = client.put(OM, json={"off": {other: ["inventory"]}}, headers=m)
    assert bad.status_code == 422 and bad.json()["code"] == "module_dependency_missing"
    assert client.put(OM, json={"off": {other: ["sales"]}}, headers=m).status_code == 204

    m = login(client, world["manager_a"])
    outlets = {o["id"]: o for o in client.get("/api/v1/outlets", headers=m).json()}
    assert outlets[other]["modules_off"] == ["sales"]
    order = {"outlet_id": other, "channel_id": menu["gofood"]}
    headers = {**m, "Idempotency-Key": "4b1d5f0e-0000-4000-8000-000000000001"}
    assert client.post(f"{POS}/orders", json=order, headers=headers).status_code == 404
    shop = {"outlet_id": str(world["shop"]), "channel_id": menu["gofood"]}
    headers["Idempotency-Key"] = "4b1d5f0e-0000-4000-8000-000000000002"
    assert client.post(f"{POS}/orders", json=shop, headers=headers).status_code == 201
    # Inventory is still on there.
    assert client.get(f"/api/v1/inventory/stock?outlet_id={other}", headers=m).status_code == 200

    c = login(client, world["cashier_a"])
    assert client.get(OM, headers=c).status_code == 403


def _role(tenant: Any, key: str) -> Any:
    from tests.test_purchasing import tenant_sql

    [(rid,)] = tenant_sql(
        tenant,
        "SELECT id FROM roles WHERE template_key = :k AND tenant_id = :t",
        {"k": key, "t": tenant},
    )
    return rid
