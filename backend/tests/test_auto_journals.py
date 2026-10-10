"""Slice 3d: automatic journals from operations (FR-FIN-003): POS sales and refunds, stock
used, expenses, purchases and vendor payments; nothing before the books' start; posting
rules follow the account that holds a role; every entry balanced (I-5)."""

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.factories import add_member, add_outlet, drop_tenant, seed_tenant
from tests.test_auth_mfa import enroll_as
from tests.test_catalog import units
from tests.test_inventory import HASH, PW, login
from tests.test_pos import new_order, post
from tests.test_pos_adjustments import line, open_shift
from tests.test_purchasing import P, buy
from tests.test_purchasing import client as client
from tests.test_sales_days import menu as menu

G = "/api/v1/finance/gl"
F = "/api/v1/finance"


@pytest.fixture
def world() -> Iterator[dict[str, Any]]:
    a, roles = seed_tenant("Alpha", modules=("inventory", "sales", "finance", "purchasing"))
    shop = add_outlet(a, "Shop")
    w: dict[str, Any] = {"a": a, "shop": shop, "other": add_outlet(a, "Other")}
    w["owner_a"] = add_member(a, roles["owner"], HASH)[1]
    w["manager_a"] = add_member(a, roles["manager"], HASH)[1]
    w["cashier_a"] = add_member(a, roles["cashier"], HASH, outlets=(shop,))[1]
    w["acc"] = add_member(a, roles["accountant"], HASH)[1]
    yield w
    drop_tenant(a)


def books(client: TestClient, h: dict[str, str]) -> dict[str, dict[str, Any]]:
    """Trial balance by account role (or code), as of far in the future."""
    keys = {
        a["id"]: a["system_key"] or a["code"] for a in client.get(f"{G}/accounts", headers=h).json()
    }
    rows = client.get(f"{G}/trial-balance?until=2099-12-31", headers=h).json()
    return {keys[r["account_id"]]: r for r in rows}


def balance(b: dict[str, dict[str, Any]], key: str) -> int:
    return int(b[key]["balance"]) if key in b else 0


def test_fr_fin_003_pos_sale_and_refund_are_journaled(
    client: TestClient, world: dict[str, Any], menu: dict[str, Any]
) -> None:
    acc = login(client, world["acc"])
    assert (
        client.post(f"{G}/setup", json={"start_date": "2026-01-01"}, headers=acc).status_code == 201
    )
    o = {"X-CSRF-Token": enroll_as(client, world["owner_a"], PW)[2]}  # owners refund at once
    open_shift(client, o, world, 0)
    order = new_order(client, o, world, menu)
    line(client, o, order, menu, "1")  # 25.000 + 10 % tax
    paid = post(
        client,
        o,
        f"/orders/{order['id']}/pay",
        {"payments": [{"method": "cash", "amount": 27_500}]},
    )
    assert paid.status_code == 200, paid.text
    b = books(client, o)  # owners see the books too
    assert balance(b, "cash") == 27_500 and balance(b, "sales") == 25_000
    assert balance(b, "tax_payable") == 2_500
    assert balance(b, "cogs") > 0 and balance(b, "inventory") == -balance(b, "cogs")  # stock used
    assert sum(r["debit"] for r in b.values()) == sum(r["credit"] for r in b.values())

    refund = {"reason": "Wrong dish", "stock_effect": "return", "method": "cash"}
    assert post(client, o, f"/orders/{order['id']}/refund", refund).json()["status"] == "refunded"
    b = books(client, o)
    for key in ("cash", "sales", "tax_payable", "cogs", "inventory"):
        assert balance(b, key) == 0, key  # every journal reversed


def test_fr_fin_003_expenses_purchases_and_vendor_payments(
    client: TestClient, world: dict[str, Any], menu: dict[str, Any]
) -> None:
    acc = login(client, world["acc"])
    client.post(f"{G}/setup", json={"start_date": "2026-01-01"}, headers=acc)
    till = {"name": "Till", "kind": "cash", "outlet_id": str(world["shop"])}
    client.post(f"{F}/accounts", json=till, headers=acc)
    cash = next(a for a in client.get(f"{F}/accounts", headers=acc).json() if a["name"] == "Till")
    gas = client.post(f"{F}/categories", json={"name": "Gas"}, headers=acc).json()
    spent = {
        "outlet_id": str(world["shop"]),
        "account_id": cash["id"],
        "category_id": gas["id"],
        "spent_on": "2026-03-02",
        "amount": 50_000,
    }
    made = client.post(
        f"{F}/expenses", json=spent, headers={**acc, "Idempotency-Key": str(uuid.uuid4())}
    )
    assert made.status_code == 201, made.text
    b = books(client, acc)
    assert balance(b, "other_expense") == 50_000 and balance(b, "cash") == -50_000

    m = login(client, world["manager_a"])
    u = units(client)
    egg_line = [{"item_id": menu["egg"], "qty": "10", "unit_id": u["pcs"], "line_total": 30_000}]
    market = {
        "outlet_id": str(world["shop"]),
        "vendor_name": "Pasar",
        "business_date": "2026-03-02",
        "lines": egg_line,
    }
    assert buy(client, m, market).status_code == 201  # paid on the spot: from cash
    vendor = client.post(f"{P}/vendors", json={"name": "CV Telur"}, headers=m).json()["id"]
    billed = buy(
        client, m, {**market, "vendor_name": None, "vendor_id": vendor}
    ).json()  # on account
    acc = login(client, world["acc"])
    b = books(client, acc)
    assert balance(b, "inventory") >= 60_000 and balance(b, "payable") == 30_000
    assert balance(b, "cash") == -80_000

    m = login(client, world["manager_a"])
    bill = {
        "vendor_id": vendor,
        "vendor_invoice_no": "T-1",
        "outlet_id": str(world["shop"]),
        "bill_date": "2026-03-03",
        "receipt_ids": [billed["id"]],
        "lines": [{"item_id": menu["egg"], "qty": "10", "amount": 30_000}],
    }
    bid = client.post(
        f"{P}/bills", json=bill, headers={**m, "Idempotency-Key": str(uuid.uuid4())}
    ).json()["id"]
    acc = login(client, world["acc"])
    pay = {"paid_on": "2026-03-04", "amount": 30_000, "method": "transfer"}
    assert (
        client.post(
            f"{P}/bills/{bid}/payments",
            json=pay,
            headers={**acc, "Idempotency-Key": str(uuid.uuid4())},
        ).status_code
        == 201
    )
    b = books(client, acc)
    assert balance(b, "payable") == 0 and balance(b, "bank") == -30_000
    assert sum(r["debit"] for r in b.values()) == sum(r["credit"] for r in b.values())


def test_posting_rules_follow_the_role_and_nothing_before_the_start(
    client: TestClient, world: dict[str, Any], menu: dict[str, Any]
) -> None:
    acc = login(client, world["acc"])
    client.post(f"{G}/setup", json={"start_date": "2030-01-01"}, headers=acc)  # books start later
    client.post(f"{F}/accounts", json={"name": "Till", "kind": "cash"}, headers=acc)
    cash = next(a for a in client.get(f"{F}/accounts", headers=acc).json() if a["name"] == "Till")
    cat = client.post(f"{F}/categories", json={"name": "Gas"}, headers=acc).json()
    spent = {
        "outlet_id": str(world["shop"]),
        "account_id": cash["id"],
        "category_id": cat["id"],
        "spent_on": "2026-03-02",
        "amount": 10_000,
    }
    client.post(f"{F}/expenses", json=spent, headers={**acc, "Idempotency-Key": str(uuid.uuid4())})
    assert client.get(f"{G}/trial-balance?until=2099-12-31", headers=acc).json() == []
    # "cash" moves to a new petty cash account: the role says where journals go.
    petty = client.post(
        f"{G}/accounts", json={"code": "1-1110", "name": "Petty cash", "type": "asset"}, headers=acc
    ).json()
    moved = client.put(f"{G}/accounts/{petty['id']}/role", json={"system_key": "cash"}, headers=acc)
    assert moved.status_code == 200 and moved.json()["system_key"] == "cash"
    wrong = client.post(
        f"{G}/accounts", json={"code": "4-1001", "name": "Drinks", "type": "revenue"}, headers=acc
    ).json()
    assert (
        client.put(
            f"{G}/accounts/{wrong['id']}/role", json={"system_key": "cash"}, headers=acc
        ).json()["code"]
        == "role_needs_same_type"
    )
