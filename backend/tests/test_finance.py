"""Slice 2j: finance-lite (FR-FIN-001), tax report (FR-FIN-008), sales by staff (FR-RPT-012)."""

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.factories import add_member, add_outlet, drop_tenant, seed_tenant
from tests.test_inventory import HASH, login
from tests.test_pos import new_order, post
from tests.test_purchasing import client as client
from tests.test_sales_days import menu as menu

F = "/api/v1/finance"


@pytest.fixture
def world() -> Iterator[dict[str, Any]]:
    mods = ("inventory", "sales", "finance")
    a, roles = seed_tenant("Alpha", modules=mods)
    b, roles_b = seed_tenant("Beta", modules=mods)
    shop, other = add_outlet(a, "Shop"), add_outlet(a, "Other shop")
    w: dict[str, Any] = {"a": a, "shop": shop, "other": other}
    w["manager_a"] = add_member(a, roles["manager"], HASH)[1]
    w["cashier_a"] = add_member(a, roles["cashier"], HASH, outlets=(shop,))[1]
    w["accountant_a"] = add_member(a, roles["accountant"], HASH)[1]
    w["manager_b"] = add_member(b, roles_b["manager"], HASH)[1]
    w["accountant_b"] = add_member(b, roles_b["accountant"], HASH)[1]
    yield w
    drop_tenant(a)
    drop_tenant(b)


def test_fr_fin_001_expenses_transfers_and_profit_loss(
    client: TestClient, world: dict[str, Any], menu: dict[str, Any]
) -> None:
    c = login(client, world["cashier_a"])
    client.post(
        "/api/v1/pos/shifts", json={"outlet_id": str(world["shop"]), "opening_float": 0}, headers=c
    )
    order = new_order(client, c, world, menu)
    post(client, c, f"/orders/{order['id']}/lines", {"item_id": menu["nasi"], "qty": "2"})
    assert (
        post(
            client,
            c,
            f"/orders/{order['id']}/pay",
            {"payments": [{"method": "cash", "amount": 55_000}]},
        ).status_code
        == 200
    )
    assert client.get(f"{F}/accounts", headers=c).status_code == 403  # cashiers do not see finance

    h = login(client, world["accountant_a"])
    bank = client.post(
        f"{F}/accounts",
        json={"name": "BCA", "kind": "bank", "opening_balance": 1_000_000},
        headers=h,
    )
    assert bank.status_code == 201, bank.text
    client.post(
        f"{F}/accounts",
        json={"name": "Petty cash", "kind": "petty_cash", "outlet_id": str(world["shop"])},
        headers=h,
    )
    ids = {a["name"]: a["id"] for a in client.get(f"{F}/accounts", headers=h).json()}
    gas = client.post(f"{F}/categories", json={"name": "Gas"}, headers=h).json()["id"]
    moved = client.post(
        f"{F}/transfers",
        json={
            "from_account_id": ids["BCA"],
            "to_account_id": ids["Petty cash"],
            "amount": 200_000,
            "moved_on": "2026-03-05",
        },
        headers=h,
    )
    assert moved.status_code == 201
    body = {
        "outlet_id": str(world["shop"]),
        "account_id": ids["Petty cash"],
        "category_id": gas,
        "spent_on": "2026-10-09",
        "amount": 30_000,
        "payee": "Agen gas",
    }
    key = str(uuid.uuid4())
    made = client.post(f"{F}/expenses", json=body, headers={**h, "Idempotency-Key": key})
    assert made.status_code == 201 and made.json()["number"].startswith("EXP-")
    again = client.post(f"{F}/expenses", json=body, headers={**h, "Idempotency-Key": key})
    assert again.json()["id"] == made.json()["id"]
    wrong = client.post(
        f"{F}/expenses",
        json={**body, "amount": 99_000},
        headers={**h, "Idempotency-Key": str(uuid.uuid4())},
    ).json()
    assert (
        client.post(f"{F}/expenses/{wrong['id']}/reverse", headers=h).json()["status"] == "reversed"
    )
    balances = {a["name"]: a["balance"] for a in client.get(f"{F}/accounts", headers=h).json()}
    assert balances == {"BCA": 800_000, "Petty cash": 170_000}

    pl = client.get(
        f"{F}/profit-loss?from=2026-10-01&to=2026-12-31&outlet_id={world['shop']}", headers=h
    ).json()
    assert (pl["net_sales"], pl["expenses"], pl["tax_collected"]) == (
        50_000,
        {"Gas": 30_000},
        5_000,
    )
    assert pl["cost_of_sales"] > 0 and pl["net_profit"] == 50_000 - pl["cost_of_sales"] - 30_000

    tax = client.get("/api/v1/sales/reports/tax?from=2026-10-01&to=2026-12-31", headers=h).json()
    assert tax["totals"]["tax"] == 5_000
    staff = client.get(
        "/api/v1/sales/reports/staff?from=2026-10-01&to=2026-12-31", headers=h
    ).json()
    assert [(r["orders"], r["net_sales"], r["average_order"]) for r in staff["rows"]] == [
        (1, 50_000, 50_000)
    ]
    c = login(client, world["cashier_a"])
    assert (
        client.get(
            "/api/v1/sales/reports/staff?from=2026-10-01&to=2026-10-31", headers=c
        ).status_code
        == 403
    )


def test_finance_isolation(client: TestClient, world: dict[str, Any]) -> None:
    h = login(client, world["accountant_a"])
    client.post(f"{F}/accounts", json={"name": "BCA", "kind": "bank"}, headers=h)
    b = login(client, world["accountant_b"])
    assert client.get(f"{F}/accounts", headers=b).json() == []
