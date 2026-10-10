"""Slice 3l, Gate 3 reconciliation drill: a month of operations (opening stock carried into
the books, a POS sale, a market purchase, an on-account purchase billed and partly paid, a
wholesale invoice partly paid), after which every sub-ledger agrees with the books and every
journal balances. A hand journal against a control account then shows as a difference."""

import uuid
from typing import Any

from fastapi.testclient import TestClient

from tests.test_auth_mfa import enroll_as
from tests.test_auto_journals import G, world
from tests.test_catalog import units
from tests.test_inventory import API, PW, login
from tests.test_pos import new_order, post
from tests.test_pos_adjustments import line, open_shift
from tests.test_purchasing import P, buy
from tests.test_purchasing import client as client
from tests.test_sales_days import menu as menu

__all__ = ["world"]


def key(h: dict[str, str]) -> dict[str, str]:
    return {**h, "Idempotency-Key": str(uuid.uuid4())}


def stock_value(client: TestClient, h: dict[str, str], shop: Any) -> int:
    rows = client.get(f"{API}/valuation?outlet_id={shop}&on=2026-12-31&limit=200", headers=h)
    return sum(r["value"] for r in rows.json()["items"])


def test_gate3_month_reconciles(
    client: TestClient, world: dict[str, Any], menu: dict[str, Any]
) -> None:
    shop = str(world["shop"])
    m = login(client, world["manager_a"])
    opening_stock = stock_value(client, m, shop)  # posted before the books started
    acc = login(client, world["acc"])
    setup = {
        "start_date": "2026-03-02",
        "opening": [{"account_code": "1-1400", "debit": opening_stock}],
    }
    assert client.post(f"{G}/setup", json=setup, headers=acc).status_code == 201

    o = {"X-CSRF-Token": enroll_as(client, world["owner_a"], PW)[2]}
    open_shift(client, o, world, 0)
    order = new_order(client, o, world, menu)
    line(client, o, order, menu, "2")
    pay = {"payments": [{"method": "cash", "amount": 55_000}]}
    assert post(client, o, f"/orders/{order['id']}/pay", pay).status_code == 200

    m = login(client, world["manager_a"])
    u = units(client)
    eggs = [{"item_id": menu["egg"], "qty": "10", "unit_id": u["pcs"], "line_total": 30_000}]
    market = {
        "outlet_id": shop,
        "vendor_name": "Pasar",
        "business_date": "2026-03-03",
        "lines": eggs,
    }
    assert buy(client, m, market).status_code == 201
    vendor = client.post(f"{P}/vendors", json={"name": "CV Telur"}, headers=m).json()["id"]
    on_account = buy(client, m, {**market, "vendor_name": None, "vendor_id": vendor}).json()
    unbilled = buy(client, m, {**market, "vendor_name": None, "vendor_id": vendor})
    assert unbilled.status_code == 201  # received, no bill yet: still owed
    bill = {
        "vendor_id": vendor,
        "vendor_invoice_no": "T-9",
        "outlet_id": shop,
        "bill_date": "2026-03-04",
        "receipt_ids": [on_account["id"]],
        "lines": [{"item_id": menu["egg"], "qty": "10", "amount": 30_000}],
    }
    bid = client.post(f"{P}/bills", json=bill, headers=key(m)).json()["id"]

    ch = client.post(
        "/api/v1/catalog/channels",
        json={"code": "b2b", "name": "Wholesale", "kind": "wholesale"},
        headers=m,
    ).json()["id"]
    cust = client.post("/api/v1/customers", json={"name": "Warung Sri"}, headers=m).json()["id"]
    inv = {
        "outlet_id": shop,
        "channel_id": ch,
        "customer_id": cust,
        "invoice_date": "2026-03-05",
        "lines": [{"item_id": menu["egg"], "qty": "4", "unit_price": 4_000}],
    }
    made = client.post("/api/v1/sales/invoices", json=inv, headers=key(m)).json()
    receipt = {"paid_on": "2026-03-06", "amount": 6_000, "method": "transfer"}
    assert (
        client.post(
            f"/api/v1/sales/invoices/{made['id']}/payments", json=receipt, headers=key(m)
        ).status_code
        == 201
    )

    acc = login(client, world["acc"])
    paid = {"paid_on": "2026-03-07", "amount": 10_000, "method": "transfer"}
    assert client.post(f"{P}/bills/{bid}/payments", json=paid, headers=key(acc)).status_code == 201

    rows = {r["name"]: r for r in client.get(f"{G}/reconcile", headers=acc).json()}
    assert set(rows) == {"stock_value", "open_invoices", "owed_to_vendors"}
    for name, r in rows.items():
        assert r["difference"] == 0, (name, r)
    assert rows["owed_to_vendors"]["subledger"] == 20_000 + 30_000  # bill rest + unbilled
    assert rows["open_invoices"]["subledger"] == made["total"] - 6_000

    hand = {
        "entry_date": "2026-03-08",
        "memo": "Typed straight into payables",
        "lines": [
            {"account_id": _account(client, acc, "payable"), "debit": 1_000, "credit": 0},
            {"account_id": _account(client, acc, "bank"), "debit": 0, "credit": 1_000},
        ],
    }
    posted = client.post(f"{G}/journals", json=hand, headers=key(acc))
    assert posted.status_code == 201, posted.text
    rows = {r["name"]: r for r in client.get(f"{G}/reconcile", headers=acc).json()}
    assert rows["owed_to_vendors"]["difference"] == 1_000  # the accountant sees it
    c = login(client, world["cashier_a"])
    assert client.get(f"{G}/reconcile", headers=c).status_code == 403


def _account(client: TestClient, h: dict[str, str], role: str) -> str:
    accounts = client.get(f"{G}/accounts", headers=h).json()
    return str(next(a["id"] for a in accounts if a["system_key"] == role))
