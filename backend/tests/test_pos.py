"""Slice 2b: POS orders, payments and cash shifts (FR-SAL-005, 006, 009): server-side
totals with modifiers and tax, stock out only on payment (recipe plus modifier ingredient
changes), split tenders and change, idempotent retries, shift expected cash and variance,
waiter without payment rights, outlet scope and tenant isolation."""

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.modules.sales.payments import cash_rounding
from tests.factories import add_member, add_outlet, drop_tenant, seed_tenant
from tests.test_inventory import HASH, login
from tests.test_purchasing import client as client
from tests.test_sales_days import menu as menu
from tests.test_sales_days import on_hand

POS = "/api/v1/pos"
CAT = "/api/v1/catalog"


@pytest.fixture
def world() -> Iterator[dict[str, Any]]:
    mods = ("inventory", "sales")
    a, roles = seed_tenant("Alpha", modules=mods)
    b, roles_b = seed_tenant("Beta", modules=mods)
    shop, other = add_outlet(a, "Shop"), add_outlet(a, "Other shop")
    w: dict[str, Any] = {"a": a, "shop": shop, "other": other}
    w["manager_a"] = add_member(a, roles["manager"], HASH)[1]
    w["cashier_a"] = add_member(a, roles["cashier"], HASH, outlets=(shop,))[1]
    w["waiter_a"] = add_member(a, roles["waiter"], HASH, outlets=(shop,))[1]
    w["manager_b"] = add_member(b, roles_b["manager"], HASH)[1]
    yield w
    drop_tenant(a)
    drop_tenant(b)


def post(
    client: TestClient, h: dict[str, str], path: str, body: Any, key: str | None = None
) -> Any:
    return client.post(
        f"{POS}{path}", json=body, headers={**h, "Idempotency-Key": key or str(uuid.uuid4())}
    )


@pytest.fixture
def extra_egg(client: TestClient, world: dict[str, Any], menu: dict[str, Any]) -> str:
    """Optional "Extra egg" (+Rp 5.000, one more egg) on nasi goreng."""
    h = login(client, world["manager_a"])
    group = {
        "name": "Add-ons",
        "min_select": 0,
        "max_select": 1,
        "options": [
            {
                "name": "Extra egg",
                "price_delta": 5000,
                "ingredient_item_id": menu["egg"],
                "ingredient_qty": "1",
            }
        ],
    }
    made = client.post(f"{CAT}/modifier-groups", json=group, headers=h).json()
    link = {"group_ids": [made["id"]]}
    assert (
        client.put(f"{CAT}/items/{menu['nasi']}/modifier-groups", json=link, headers=h).status_code
        == 200
    )
    return str(made["options"][0]["id"])


def new_order(
    client: TestClient,
    h: dict[str, str],
    world: dict[str, Any],
    menu: dict[str, Any],
    outlet: str = "shop",
) -> dict[str, Any]:
    made = post(
        client,
        h,
        "/orders",
        {"outlet_id": str(world[outlet]), "channel_id": menu["gofood"], "label": "Table 4"},
    )
    assert made.status_code == 201, made.text
    return dict(made.json())


def test_fr_sal_005_006_order_totals_payment_and_stock(
    client: TestClient, world: dict[str, Any], menu: dict[str, Any], extra_egg: str
) -> None:
    m = login(client, world["manager_a"])
    before = on_hand(client, m, world["shop"])
    h = login(client, world["cashier_a"])
    order = new_order(client, h, world, menu)
    assert order["number"].startswith("POS-") and order["status"] == "open"
    line = {"item_id": menu["nasi"], "qty": "2", "option_ids": [extra_egg], "note": "less spicy"}
    added = post(client, h, f"/orders/{order['id']}/lines", line)
    assert added.status_code == 200, added.text
    out = added.json()
    [ln] = out["lines"]
    assert (ln["unit_price"], ln["line_total"], ln["status"]) == (30_000, 60_000, "new")
    # PBJT 10 % from the Indonesian defaults; service charge is off by default.
    assert out["totals"] == {
        "subtotal": 60_000,
        "discount": 0,
        "service_charge": 0,
        "tax": 6_000,
        "total": 66_000,
    }

    pay = {
        "payments": [
            {"method": "cash", "amount": 50_000, "tendered": 100_000},
            {"method": "qris", "amount": 16_000},
        ]
    }
    no_shift = post(client, h, f"/orders/{order['id']}/pay", pay)
    assert no_shift.status_code == 409 and no_shift.json()["code"] == "shift_required"
    shift = client.post(
        f"{POS}/shifts", json={"outlet_id": str(world["shop"]), "opening_float": 100_000}, headers=h
    )
    assert shift.status_code == 201, shift.text
    again = client.post(
        f"{POS}/shifts", json={"outlet_id": str(world["shop"]), "opening_float": 0}, headers=h
    )
    assert again.json()["code"] == "shift_already_open"
    short = {"payments": [{"method": "cash", "amount": 60_000}]}
    assert (
        post(client, h, f"/orders/{order['id']}/pay", short).json()["code"]
        == "payment_total_mismatch"
    )
    card_change = {"payments": [{"method": "qris", "amount": 66_000, "tendered": 70_000}]}
    assert (
        post(client, h, f"/orders/{order['id']}/pay", card_change).json()["code"]
        == "tendered_mismatch"
    )

    key = str(uuid.uuid4())
    paid = post(client, h, f"/orders/{order['id']}/pay", pay, key)
    assert paid.status_code == 200, paid.text
    body = paid.json()
    assert body["status"] == "paid" and body["document_id"]
    assert [(p["method"], p["amount"], p["change"]) for p in body["payments"]] == [
        ("cash", 50_000, 50_000),
        ("qris", 16_000, 0),
    ]
    assert body["lines"][0]["status"] == "sent"  # paid before sending: the kitchen still gets it
    assert post(client, h, f"/orders/{order['id']}/pay", pay, key).json() == body  # retry
    late = post(client, h, f"/orders/{order['id']}/lines", line)
    assert late.status_code == 409 and late.json()["code"] == "wrong_status"
    sid = shift.json()["id"]
    m = login(client, world["manager_a"])
    after = on_hand(client, m, world["shop"])
    # 2 x (200 g rice + 1 egg + 30 g sambal) plus 2 extra eggs from the modifier.
    assert before["EGG"] - after["EGG"] == 4
    assert before["RICE"] - after["RICE"] == 400 and before["SAMBAL"] - after["SAMBAL"] == 60

    # FR-SAL-009: 100.000 float + 50.000 cash kept + 20.000 in; counted 1.000 short.
    h = login(client, world["cashier_a"])
    moved = client.post(
        f"{POS}/shifts/{sid}/movements",
        json={"kind": "in", "amount": 20_000, "reason": "Change from bank"},
        headers=h,
    )
    assert moved.status_code == 200 and moved.json()["expected"] == 170_000
    closed = client.post(f"{POS}/shifts/{sid}/close", json={"counted": 169_000}, headers=h).json()
    assert (closed["status"], closed["expected"], closed["variance"]) == ("closed", 170_000, -1_000)
    assert closed["by_method"] == {"cash": 50_000, "qris": 16_000} and closed["orders"] == 1
    m = login(client, world["manager_a"])
    listed = client.get(
        f"{POS}/shifts?outlet_id={world['shop']}&date_from=2020-01-01&date_to=2020-01-02", headers=m
    )
    assert listed.status_code == 200


def test_fr_sal_005_lines_send_cancel_and_rules(
    client: TestClient, world: dict[str, Any], menu: dict[str, Any], extra_egg: str
) -> None:
    h = login(client, world["waiter_a"])
    order = new_order(client, h, world, menu)
    oid = order["id"]
    two = {"item_id": menu["nasi"], "option_ids": [extra_egg, extra_egg]}
    assert post(client, h, f"/orders/{oid}/lines", two).json()["code"] == "duplicate_option"
    out = post(client, h, f"/orders/{oid}/lines", {"item_id": menu["nasi"]}).json()
    line_id = out["lines"][0]["id"]
    changed = client.put(f"{POS}/orders/{oid}/lines/{line_id}", json={"qty": "3"}, headers=h)
    assert changed.json()["lines"][0]["line_total"] == 75_000
    sent = client.post(f"{POS}/orders/{oid}/send", headers=h).json()
    assert sent["lines"][0]["status"] == "sent"
    # Sent lines are being cooked: removing them or cancelling the order needs a void (2d).
    assert (
        client.delete(f"{POS}/orders/{oid}/lines/{line_id}", headers=h).json()["code"]
        == "line_already_sent"
    )
    assert (
        client.post(f"{POS}/orders/{oid}/cancel", headers=h).json()["code"]
        == "order_has_sent_lines"
    )
    # Waiters take orders but do not take money.
    pay = {"payments": [{"method": "cash", "amount": 82_500}]}
    assert post(client, h, f"/orders/{oid}/pay", pay).status_code == 403
    fresh = new_order(client, h, world, menu)
    post(client, h, f"/orders/{fresh['id']}/lines", {"item_id": menu["nasi"]})
    assert (
        client.post(f"{POS}/orders/{fresh['id']}/cancel", headers=h).json()["status"] == "cancelled"
    )
    listed = client.get(f"{POS}/orders?outlet_id={world['shop']}", headers=h).json()
    assert [(o["id"], o["total"], o["lines"]) for o in listed] == [(oid, 75_000, 1)]
    # Sold out: the item cannot be added until it is back on sale.
    m = login(client, world["manager_a"])
    client.put(f"{CAT}/items/{menu['nasi']}/availability", json={"is_available": False}, headers=m)
    gone = post(client, m, f"/orders/{oid}/lines", {"item_id": menu["nasi"]})
    assert gone.json()["code"] == "item_sold_out"


def test_pos_outlet_scope_and_tenant_isolation(
    client: TestClient, world: dict[str, Any], menu: dict[str, Any]
) -> None:
    m = login(client, world["manager_a"])
    elsewhere = new_order(client, m, world, menu, outlet="other")
    shift = client.post(
        f"{POS}/shifts", json={"outlet_id": str(world["shop"]), "opening_float": 0}, headers=m
    ).json()
    h = login(client, world["cashier_a"])
    assert client.get(f"{POS}/orders/{elsewhere['id']}", headers=h).status_code == 404
    assert client.get(f"{POS}/orders?outlet_id={world['other']}", headers=h).status_code == 404
    assert client.get(f"{POS}/shifts/{shift['id']}", headers=h).status_code == 404  # not theirs
    body = {"outlet_id": str(world["other"]), "channel_id": menu["gofood"]}
    assert post(client, h, "/orders", body).status_code == 404
    b = login(client, world["manager_b"])
    assert client.get(f"{POS}/orders/{elsewhere['id']}", headers=b).status_code == 404
    assert (
        client.post(f"{POS}/shifts/{shift['id']}/close", json={"counted": 0}, headers=b).status_code
        == 404
    )


def test_cash_rounding_half_up_to_the_step() -> None:
    assert cash_rounding(27_550, 100) == 50
    assert cash_rounding(27_549, 100) == -49
    assert cash_rounding(27_549, 0) == 0


def test_fr_sal_004_menu_for_the_till_and_nav(
    client: TestClient, world: dict[str, Any], menu: dict[str, Any], extra_egg: str
) -> None:
    h = login(client, world["waiter_a"])
    found = client.get(f"{CAT}/menu?channel_id={menu['gofood']}", headers=h)
    assert found.status_code == 200, found.text
    [nasi] = found.json()  # only items priced on the channel
    assert (nasi["id"], nasi["price"], nasi["is_available"]) == (menu["nasi"], 25_000, True)
    assert [o["id"] for o in nasi["modifier_groups"][0]["options"]] == [extra_egg]
    # Waiters get the till but not the daily sales entry.
    nav = client.get("/api/v1/me/capabilities", headers=h).json()["nav"]
    assert "pos" in nav and "sales" not in nav


def test_fr_sal_010_receipt_json_and_pdf(
    client: TestClient, world: dict[str, Any], menu: dict[str, Any]
) -> None:
    h = login(client, world["cashier_a"])
    client.post(
        f"{POS}/shifts", json={"outlet_id": str(world["shop"]), "opening_float": 0}, headers=h
    )
    order = new_order(client, h, world, menu)
    post(client, h, f"/orders/{order['id']}/lines", {"item_id": menu["nasi"]})
    bill = client.get(f"{POS}/orders/{order['id']}/receipt", headers=h).json()
    assert bill["paid"] is False and bill["total"] == 27_500  # pre-bill to check
    pay = {"payments": [{"method": "cash", "amount": 27_500, "tendered": 50_000}]}
    assert post(client, h, f"/orders/{order['id']}/pay", pay).status_code == 200
    r = client.get(f"{POS}/orders/{order['id']}/receipt", headers=h).json()
    assert (r["paid"], r["number"], r["label"], r["footer"]) == (
        True,
        order["number"],
        "Table 4",
        "Terima kasih!",
    )
    assert r["payments"] == [
        {"method": "Tunai", "amount": 27_500, "tendered": 50_000, "change": 22_500}
    ]
    pdf = client.get(f"{POS}/orders/{order['id']}/receipt/pdf", headers=h)
    assert pdf.headers["content-type"] == "application/pdf" and pdf.content.startswith(b"%PDF")
    b = login(client, world["manager_b"])
    assert client.get(f"{POS}/orders/{order['id']}/receipt", headers=b).status_code == 404
