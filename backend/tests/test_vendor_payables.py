"""Slice 2k: returns to vendors with credit notes (FR-PUR-008), vendor bills with three-way
match, payments and payables (FR-PUR-009)."""

import uuid
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.factories import add_member, add_outlet, drop_tenant, seed_tenant
from tests.test_catalog import units
from tests.test_inventory import API, HASH, login
from tests.test_purchase_orders import order, receive
from tests.test_purchasing import DAY, P, buy
from tests.test_purchasing import client as client
from tests.test_purchasing import items as items


@pytest.fixture
def world() -> Iterator[dict[str, Any]]:
    mods = ("inventory", "purchasing")
    a, roles = seed_tenant("Alpha", modules=mods)
    b, roles_b = seed_tenant("Beta", modules=mods)
    shop, kitchen = add_outlet(a, "Shop"), add_outlet(a, "Central kitchen")
    w: dict[str, Any] = {"a": a, "shop": shop, "kitchen": kitchen}
    w["manager_a"] = add_member(a, roles["manager"], HASH)[1]
    w["accountant_a"] = add_member(a, roles["accountant"], HASH)[1]
    w["cashier_a"] = add_member(a, roles["cashier"], HASH)[1]
    w["manager_b"] = add_member(b, roles_b["manager"], HASH)[1]
    yield w
    drop_tenant(a)
    drop_tenant(b)


def post(client: TestClient, h: dict[str, str], path: str, body: dict[str, Any]) -> Any:
    return client.post(f"{P}{path}", json=body, headers={**h, "Idempotency-Key": str(uuid.uuid4())})


def bill_body(world: dict[str, Any], vendor: str, no: str, lines: list[Any], **extra: Any) -> Any:
    return {
        "vendor_id": vendor,
        "vendor_invoice_no": no,
        "outlet_id": str(world["shop"]),
        "bill_date": "2026-03-05",
        "lines": lines,
        **extra,
    }


def test_fr_pur_009_three_way_match_payments_and_payables(
    client: TestClient, world: dict[str, Any], items: dict[str, str]
) -> None:
    m = login(client, world["manager_a"])
    po = order(client, m, world, items)
    client.post(f"{P}/orders/{po['id']}/submit", headers=m)
    beef, rice = client.get(f"{P}/orders/{po['id']}", headers=m).json()["lines"]
    got = receive(
        client,
        m,
        po,
        [
            {"po_line_id": beef["id"], "qty": "10"},
            {"po_line_id": rice["id"], "qty": "25", "unit_price": 15000},
        ],
    )
    assert got.status_code == 201, got.text
    lines = [
        {"item_id": items["beef"], "qty": "10000", "amount": 1_200_000},
        {"item_id": items["rice"], "qty": "25000", "amount": 375_000},  # 15/g, PO said 14/g
    ]
    body = bill_body(world, po["vendor_id"], "INV-77", lines, po_id=po["id"])
    made = post(client, m, "/bills", body)
    assert made.status_code == 201, made.text
    bill = made.json()
    assert bill["receipt_ids"] == [got.json()["id"]]  # the PO's unbilled receipt
    assert bill["match_status"] == "mismatch" and bill["due_date"] == "2026-03-05"
    [note] = bill["match_notes"]
    assert note["item_id"] == items["rice"] and note["issue"] == "price_over_po"
    assert post(client, m, "/bills", body).json()["code"] == "duplicate_vendor_invoice"
    again = bill_body(world, po["vendor_id"], "INV-78", lines, receipt_ids=bill["receipt_ids"])
    assert post(client, m, "/bills", again).json()["code"] == "receipt_already_billed"

    # Managers enter bills; paying is the accountant's (docs/03 finance rows).
    pay = {"paid_on": "2026-03-10", "amount": 500_000, "method": "transfer"}
    assert post(client, m, f"/bills/{bill['id']}/payments", pay).status_code == 403
    acc = login(client, world["accountant_a"])
    paid = post(client, acc, f"/bills/{bill['id']}/payments", pay).json()
    assert paid["status"] == "partially_paid" and paid["balance"] == 1_075_000
    owed = client.get(f"{P}/payables", headers=acc).json()
    assert [(r["number"], r["balance"]) for r in owed] == [(bill["number"], 1_075_000)]
    too_much = post(client, acc, f"/bills/{bill['id']}/payments", {**pay, "amount": 2_000_000})
    assert too_much.json()["code"] == "payment_exceeds_balance"
    first = paid["payments"][0]["id"]
    undo = client.post(f"{P}/bills/{bill['id']}/payments/{first}/reverse", headers=acc).json()
    assert undo["status"] == "open" and undo["balance"] == 1_575_000
    rest = post(client, acc, f"/bills/{bill['id']}/payments", {**pay, "amount": 1_575_000})
    assert rest.json()["status"] == "paid" and client.get(f"{P}/payables", headers=acc).json() == []
    m = login(client, world["manager_a"])  # one session per test client
    assert client.post(f"{P}/bills/{bill['id']}/void", headers=m).json()["code"] == (
        "bill_has_settlements"
    )
    # Isolation: another tenant and a cashier see nothing.
    assert (
        client.get(f"{P}/bills/{bill['id']}", headers=login(client, world["manager_b"])).status_code
        == 404
    )
    assert client.get(f"{P}/payables", headers=login(client, world["cashier_a"])).status_code == 403


def test_fr_pur_008_return_credit_note_applied_to_a_bill(
    client: TestClient, world: dict[str, Any], items: dict[str, str]
) -> None:
    m = login(client, world["manager_a"])
    u = units(client)
    vendor = client.post(f"{P}/vendors", json={"name": "CV Segar"}, headers=m).json()["id"]
    body = {
        "outlet_id": str(world["shop"]),
        "vendor_id": vendor,
        "business_date": DAY.isoformat(),
        "lines": [{"item_id": items["beef"], "qty": "2", "unit_id": u["kg"], "line_total": 240000}],
    }
    receipt = buy(client, m, body).json()
    [base] = client.get(f"{P}/returns/receipt-lines/{receipt['id']}", headers=m).json()
    assert (base["sku"], Decimal(base["qty"]), base["amount"]) == ("BEEF", 2000, 240000)
    back = {
        "outlet_id": str(world["shop"]),
        "vendor_id": vendor,
        "receipt_id": receipt["id"],
        "business_date": "2026-03-02",
        "reason": "damaged",
        "lines": [{"item_id": items["beef"], "qty": "500"}],
    }
    made = post(client, m, "/returns", back)
    assert made.status_code == 201, made.text
    ret = made.json()
    assert ret["number"].startswith("RTN-2026-")
    assert ret["credit_amount"] == 60000 and ret["stock_value"] == 60000  # 120 per g paid
    stock = client.get(f"{API}/stock?outlet_id={world['shop']}", headers=m).json()["items"]
    assert Decimal(stock[0]["qty"]) == 1500
    huge = {**back, "lines": [{"item_id": items["beef"], "qty": "5000"}]}
    assert post(client, m, "/returns", huge).status_code == 409  # never below zero

    second = buy(client, m, body).json()
    lines = [{"item_id": items["beef"], "qty": "2000", "amount": 240000}]
    bill = post(
        client, m, "/bills", bill_body(world, vendor, "INV-9", lines, receipt_ids=[second["id"]])
    ).json()
    assert bill["match_status"] == "no_po" and bill["match_notes"] == []
    early = client.post(f"{P}/bills/{bill['id']}/credits", json={"return_id": ret["id"]}, headers=m)
    assert early.json()["code"] == "credit_note_missing"
    note = {"credit_note_number": "CN-12", "credited_on": "2026-03-06"}
    client.post(f"{P}/returns/{ret['id']}/credit-note", json=note, headers=m)
    used = client.post(f"{P}/bills/{bill['id']}/credits", json={"return_id": ret["id"]}, headers=m)
    assert used.json()["credited"] == 60000 and used.json()["balance"] == 180000
    twice = client.post(f"{P}/bills/{bill['id']}/credits", json={"return_id": ret["id"]}, headers=m)
    assert twice.json()["code"] == "credit_already_applied"
    # A credited return can no longer be undone.
    assert client.post(f"{P}/returns/{ret['id']}/reverse", headers=m).json()["code"] == (
        "already_credited"
    )
