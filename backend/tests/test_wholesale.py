"""Slice 3e: wholesale invoices (FR-SAL-011), accounts receivable and payables aging
(FR-FIN-006): stock leaves, the receivable is journaled, payments clear it, aging buckets."""

import uuid
from typing import Any

from fastapi.testclient import TestClient

from tests.test_auto_journals import G, balance, books
from tests.test_auto_journals import world as world
from tests.test_catalog import units
from tests.test_inventory import login
from tests.test_purchasing import client as client
from tests.test_sales_days import menu as menu

INV = "/api/v1/sales/invoices"
CAT = "/api/v1/catalog"


def key(h: dict[str, str]) -> dict[str, str]:
    return {**h, "Idempotency-Key": str(uuid.uuid4())}


def setup(client: TestClient, world: dict[str, Any], menu: dict[str, Any]) -> dict[str, Any]:
    acc = login(client, world["acc"])
    client.post(f"{G}/setup", json={"start_date": "2026-01-01"}, headers=acc)
    m = login(client, world["manager_a"])
    ch = client.post(
        f"{CAT}/channels",
        json={"code": "b2b", "name": "Wholesale", "kind": "wholesale"},
        headers=m,
    )
    assert ch.status_code == 201, ch.text
    cust = client.post("/api/v1/customers", json={"name": "Warung Bu Sri"}, headers=m)
    assert cust.status_code == 201, cust.text
    body = {
        "outlet_id": str(world["shop"]),
        "channel_id": ch.json()["id"],
        "customer_id": cust.json()["id"],
        "invoice_date": "2026-03-02",
        "lines": [{"item_id": menu["egg"], "qty": "5", "unit_price": 4_000}],
    }
    return {"m": m, "body": body, "gofood": menu["gofood"]}


def test_fr_sal_011_invoice_payment_and_aging(
    client: TestClient, world: dict[str, Any], menu: dict[str, Any]
) -> None:
    s = setup(client, world, menu)
    m, body = s["m"], s["body"]
    wrong = client.post(INV, json={**body, "channel_id": s["gofood"]}, headers=key(m))
    assert wrong.json()["code"] == "not_a_wholesale_channel"
    h = key(m)
    made = client.post(INV, json=body, headers=h)
    assert made.status_code == 201, made.text
    inv = made.json()
    assert inv["number"].startswith("INV") and inv["due_date"] == "2026-03-16"  # 14 days
    assert inv["status"] == "open" and inv["balance"] == inv["total"] >= 20_000
    assert client.post(INV, json=body, headers=h).json()["id"] == inv["id"]  # replay

    b = books(client, login(client, world["acc"]))
    assert balance(b, "receivable") == inv["total"] and balance(b, "cogs") > 0
    m = login(client, world["manager_a"])

    aged = client.get(f"{INV}/aging?as_of=2026-04-20", headers=m).json()
    assert [r["party_name"] for r in aged] == ["Warung Bu Sri"]
    assert aged[0]["total"] == inv["total"]

    too_much = {"paid_on": "2026-03-10", "amount": inv["total"] + 1, "method": "transfer"}
    assert (
        client.post(f"{INV}/{inv['id']}/payments", json=too_much, headers=key(m)).json()["code"]
        == "payment_exceeds_balance"
    )
    part = {"paid_on": "2026-03-10", "amount": 10_000, "method": "transfer"}
    paid = client.post(f"{INV}/{inv['id']}/payments", json=part, headers=key(m))
    assert paid.status_code == 201, paid.text
    assert paid.json()["status"] == "partially_paid" and paid.json()["paid"] == 10_000
    assert client.post(f"{INV}/{inv['id']}/void", headers=m).json()["code"] == (
        "invoice_has_payments"
    )
    rest = {**part, "amount": inv["total"] - 10_000}
    done = client.post(f"{INV}/{inv['id']}/payments", json=rest, headers=key(m)).json()
    assert done["status"] == "paid" and done["balance"] == 0
    b = books(client, login(client, world["acc"]))
    assert balance(b, "receivable") == 0 and balance(b, "bank") == inv["total"]
    assert sum(r["debit"] for r in b.values()) == sum(r["credit"] for r in b.values())
    m = login(client, world["manager_a"])
    assert client.get(f"{INV}/aging?as_of=2026-04-20", headers=m).json() == []
    assert client.get("/api/v1/purchasing/payables/aging", headers=m).status_code == 200


def test_void_returns_stock_and_reverses_journal(
    client: TestClient, world: dict[str, Any], menu: dict[str, Any]
) -> None:
    s = setup(client, world, menu)
    m = s["m"]
    inv = client.post(INV, json=s["body"], headers=key(m)).json()
    voided = client.post(f"{INV}/{inv['id']}/void", headers=m)
    assert voided.status_code == 200, voided.text
    assert voided.json()["status"] == "void"
    b = books(client, login(client, world["acc"]))
    for k in ("receivable", "cogs", "sales"):
        assert balance(b, k) == 0, k
    m = login(client, world["manager_a"])
    assert client.post(f"{INV}/{inv['id']}/void", headers=m).json()["code"] == "already_void"


def test_invoice_permissions_and_outlet_scope(
    client: TestClient, world: dict[str, Any], menu: dict[str, Any]
) -> None:
    s = setup(client, world, menu)
    c = login(client, world["cashier_a"])
    assert client.post(INV, json=s["body"], headers=key(c)).status_code == 403
    assert client.get(f"{INV}/aging", headers=c).status_code == 403
    m = login(client, world["manager_a"])
    listed = client.get(f"{INV}?outlet_id={world['shop']}", headers=m)
    assert listed.status_code == 200 and listed.json() == []
    assert units(client)  # catalog still reachable
