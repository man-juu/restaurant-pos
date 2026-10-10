"""Slice 4d: loyalty points and vouchers (FR-SAL-016)."""

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.factories import add_member, add_outlet, drop_tenant, seed_tenant
from tests.test_auth_mfa import enroll_as
from tests.test_inventory import HASH, PW, login
from tests.test_pos import POS, new_order, post
from tests.test_pos_adjustments import line, open_shift
from tests.test_purchasing import client as client
from tests.test_sales_days import menu as menu

L = "/api/v1/loyalty"


@pytest.fixture
def world() -> Iterator[dict[str, Any]]:
    mods = ("inventory", "sales", "loyalty")
    a, roles = seed_tenant("Alpha", modules=mods)
    b, roles_b = seed_tenant("Beta", modules=mods)
    shop, other = add_outlet(a, "Shop"), add_outlet(a, "Other shop")
    w: dict[str, Any] = {"a": a, "shop": shop, "other": other}
    w["manager_a"] = add_member(a, roles["manager"], HASH)[1]
    w["owner_a"] = add_member(a, roles["owner"], HASH)[1]
    w["cashier_a"] = add_member(a, roles["cashier"], HASH, outlets=(shop,))[1]
    w["cashier_other"] = add_member(a, roles["cashier"], HASH, outlets=(other,))[1]
    w["manager_b"] = add_member(b, roles_b["manager"], HASH)[1]
    yield w
    drop_tenant(a)
    drop_tenant(b)


def _key(h: dict[str, str]) -> dict[str, str]:
    return {**h, "Idempotency-Key": str(uuid.uuid4())}


def _setup(client: TestClient, w: dict[str, Any]) -> str:
    o = {"X-CSRF-Token": enroll_as(client, w["owner_a"], PW)[2]}  # owners use 2FA
    methods = client.get("/api/v1/settings", headers=o).json()["payment_methods"]["methods"]
    methods.append({"code": "voucher", "name": "Voucher", "kind": "voucher"})
    put = client.put("/api/v1/settings/payment_methods", json={"methods": methods}, headers=o)
    assert put.status_code in (200, 204), put.text
    guest = client.post(
        "/api/v1/customers",
        json={"name": "Sari", "phone": "0812111222", "consent": True},
        headers=o,
    )
    assert guest.status_code == 201, guest.text
    return str(guest.json()["id"])


def _sale(
    client: TestClient,
    h: dict[str, str],
    w: dict[str, Any],
    menu: dict[str, Any],
    pay: list[Any] | None = None,
) -> dict[str, Any]:
    order = new_order(client, h, w, menu)
    line(client, h, order, menu, "4")  # 100.000 + 10 % = 110.000
    paid = post(
        client,
        h,
        f"/orders/{order['id']}/pay",
        {"payments": pay or [{"method": "cash", "amount": 110_000}]},
    )
    return {"order": order, "res": paid}


def test_fr_sal_016_earn_redeem_pay_and_refund(
    client: TestClient, world: dict[str, Any], menu: dict[str, Any]
) -> None:
    guest = _setup(client, world)
    h = login(client, world["cashier_a"])
    open_shift(client, h, world)
    sale = _sale(client, h, world, menu)
    assert sale["res"].status_code == 200, sale["res"].text
    doc = sale["res"].json()["document_id"]
    earn = {"document_id": doc, "customer_id": guest}
    got = client.post(f"{L}/earn", json=earn, headers=h)
    assert got.status_code == 200, got.text
    assert got.json() == {"points": 10, "balance": 10}  # 100.000 net / 10.000 per point
    assert client.post(f"{L}/earn", json=earn, headers=h).json()["balance"] == 10  # once

    # Another outlet's cashier cannot give points for this receipt.
    x = login(client, world["cashier_other"])
    assert client.post(f"{L}/earn", json=earn, headers=x).status_code == 404

    # Points below the minimum (default 100) cannot be redeemed; enough points can.
    h = login(client, world["cashier_a"])
    low = client.post(f"{L}/redeem", json={"customer_id": guest, "points": 10}, headers=_key(h))
    assert low.json()["code"] == "points_below_minimum"
    m = login(client, world["manager_a"])
    gift = client.post(
        f"{L}/vouchers", json={"amount": 20_000, "customer_id": guest}, headers=_key(m)
    )
    assert gift.status_code == 201, gift.text
    code = gift.json()["code"]

    # Paying with the voucher uses it up; the same code cannot pay twice.
    h = login(client, world["cashier_a"])
    pay = [
        {"method": "voucher", "amount": 20_000, "reference": code.lower()},
        {"method": "cash", "amount": 90_000},
    ]
    used = _sale(client, h, world, menu, pay)
    assert used["res"].status_code == 200, used["res"].text
    assert client.get(f"{L}/vouchers/by-code/{code}", headers=h).json()["status"] == "used"
    again = _sale(client, h, world, menu, pay)["res"]
    assert again.status_code == 409 and again.json()["code"] == "voucher_not_active"
    bad = [{"method": "voucher", "amount": 110_000, "reference": "NOPE-NOPE"}]
    assert _sale(client, h, world, menu, bad)["res"].json()["code"] == "voucher_not_found"

    # Refunding the first receipt takes its points back.
    ask = {"reason": "Wrong dish", "stock_effect": "return", "method": "cash"}
    rid = post(client, h, f"/orders/{sale['order']['id']}/refund", ask).json()["refund"]["id"]
    m = login(client, world["manager_a"])
    assert client.post(f"{POS}/refunds/{rid}/approve", headers=m).status_code == 200
    bal = client.get(f"{L}/customers/{guest}", headers=m).json()
    assert bal["balance"] == 0 and [e["kind"] for e in bal["entries"]][:2] == ["reverse", "earn"]

    # Tenant isolation: another business sees neither the guest nor the voucher.
    b = login(client, world["manager_b"])
    assert client.get(f"{L}/customers/{guest}", headers=b).status_code == 404
    assert client.get(f"{L}/vouchers/by-code/{code}", headers=b).status_code == 404
    # Server decides: a cashier cannot issue vouchers by hand.
    h = login(client, world["cashier_a"])
    assert client.post(f"{L}/vouchers", json={"amount": 1}, headers=_key(h)).status_code == 403
