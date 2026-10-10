"""Slice 2d: discounts within role limits (FR-SAL-007), voids with a waste write-off and
refunds with manager approval (FR-SAL-008); never approving one's own refund; cash refunds
lower the drawer's expected cash; isolation."""

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.factories import add_member, add_outlet, drop_tenant, seed_tenant
from tests.test_auth_mfa import enroll_as
from tests.test_inventory import HASH, PW, login
from tests.test_pos import POS, new_order, post
from tests.test_purchasing import client as client
from tests.test_purchasing import tenant_sql
from tests.test_sales_days import menu as menu
from tests.test_sales_days import on_hand


@pytest.fixture
def world() -> Iterator[dict[str, Any]]:
    mods = ("inventory", "sales")
    a, roles = seed_tenant("Alpha", modules=mods)
    b, roles_b = seed_tenant("Beta", modules=mods)
    shop = add_outlet(a, "Shop")
    w: dict[str, Any] = {"a": a, "shop": shop}
    for key in ("owner", "manager", "cashier", "waiter"):
        w[f"{key}_a"] = add_member(
            a, roles[key], HASH, outlets=(shop,) if key != "owner" else None
        )[1]
    w["manager_b"] = add_member(b, roles_b["manager"], HASH)[1]
    yield w
    drop_tenant(a)
    drop_tenant(b)


def line(
    client: TestClient,
    h: dict[str, str],
    order: dict[str, Any],
    menu: dict[str, Any],
    qty: str = "2",
) -> dict[str, Any]:
    out = post(client, h, f"/orders/{order['id']}/lines", {"item_id": menu["nasi"], "qty": qty})
    assert out.status_code == 200, out.text
    return dict(out.json())


def open_shift(
    client: TestClient, h: dict[str, str], world: dict[str, Any], float_: int = 100_000
) -> str:
    made = client.post(
        f"{POS}/shifts", json={"outlet_id": str(world["shop"]), "opening_float": float_}, headers=h
    )
    assert made.status_code == 201, made.text
    return str(made.json()["id"])


def test_fr_sal_007_discounts_follow_role_limits(
    client: TestClient, world: dict[str, Any], menu: dict[str, Any]
) -> None:
    h = login(client, world["cashier_a"])
    order = new_order(client, h, world, menu)
    out = line(client, h, order, menu)  # 2 x 25.000
    lid, oid = out["lines"][0]["id"], order["id"]
    too_much = {"kind": "percent", "value": 2000, "reason": "Regular"}
    big = client.put(f"{POS}/orders/{oid}/lines/{lid}/discount", json=too_much, headers=h)
    assert big.status_code == 403 and big.json()["details"]["limit"] == 1000  # cashier 10 %
    no_reason = client.put(
        f"{POS}/orders/{oid}/discount", json={"kind": "amount", "value": 1}, headers=h
    )
    assert no_reason.status_code == 422
    ten = {"kind": "percent", "value": 1000, "reason": "Regular"}
    assert (
        client.put(f"{POS}/orders/{oid}/lines/{lid}/discount", json=ten, headers=h).status_code
        == 200
    )
    # 3.000 off 45.000 is 6.7 %: within the limit. Tax is on what is left.
    body = client.put(
        f"{POS}/orders/{oid}/discount",
        json={"kind": "amount", "value": 3000, "reason": "Late food"},
        headers=h,
    ).json()
    assert body["lines"][0]["discount"] == 5000
    assert body["totals"] == {
        "subtotal": 50_000,
        "discount": 8_000,
        "service_charge": 0,
        "tax": 4_200,
        "total": 46_200,
    }
    # A manager's limit (50 %) covers what a cashier's does not.
    m = login(client, world["manager_a"])
    forty = {"kind": "percent", "value": 4000, "reason": "Owner's friend"}
    assert client.put(f"{POS}/orders/{oid}/discount", json=forty, headers=m).status_code == 200
    h = login(client, world["cashier_a"])
    assert (
        client.delete(f"{POS}/orders/{oid}/discount", headers=h).json()["totals"]["discount"]
        == 5000
    )
    open_shift(client, h, world)
    paid = post(
        client, h, f"/orders/{oid}/pay", {"payments": [{"method": "cash", "amount": 49_500}]}
    )
    assert paid.status_code == 200, paid.text


def test_fr_sal_008_void_sent_line_writes_off_waste(
    client: TestClient, world: dict[str, Any], menu: dict[str, Any]
) -> None:
    m = login(client, world["manager_a"])
    before = on_hand(client, m, world["shop"])
    h = login(client, world["cashier_a"])
    order = new_order(client, h, world, menu)
    lid = line(client, h, order, menu, "1")["lines"][0]["id"]
    client.post(f"{POS}/orders/{order['id']}/send", headers=h)
    no_reason = client.post(f"{POS}/orders/{order['id']}/lines/{lid}/void", json={}, headers=h)
    assert no_reason.status_code == 422
    voided = client.post(
        f"{POS}/orders/{order['id']}/lines/{lid}/void", json={"reason": "Dropped"}, headers=h
    ).json()
    assert voided["lines"][0]["status"] == "void" and voided["totals"]["total"] == 0
    w = login(client, world["waiter_a"])
    assert (
        client.post(f"{POS}/orders/{order['id']}/void", json={"reason": "x"}, headers=w).status_code
        == 403
    )
    h = login(client, world["cashier_a"])
    done = client.post(
        f"{POS}/orders/{order['id']}/void", json={"reason": "Customer left"}, headers=h
    ).json()
    assert done["status"] == "void"
    m = login(client, world["manager_a"])
    after = on_hand(client, m, world["shop"])
    # The cooked plate is waste (default setting): one egg, 200 g rice, 30 g sambal.
    assert before["EGG"] - after["EGG"] == 1 and before["RICE"] - after["RICE"] == 200


def test_fr_sal_008_refund_needs_another_persons_approval(
    client: TestClient, world: dict[str, Any], menu: dict[str, Any]
) -> None:
    m = login(client, world["manager_a"])
    before = on_hand(client, m, world["shop"])
    h = login(client, world["cashier_a"])
    sid = open_shift(client, h, world)
    order = new_order(client, h, world, menu)
    line(client, h, order, menu, "1")  # 25.000 + 10 % = 27.500
    post(
        client,
        h,
        f"/orders/{order['id']}/pay",
        {"payments": [{"method": "cash", "amount": 27_500}]},
    )
    # Money goes back the way it came: not by QRIS for a cash sale (security review 2l).
    other = {"reason": "Wrong dish", "stock_effect": "return", "method": "qris"}
    wrong = post(client, h, f"/orders/{order['id']}/refund", other)
    assert wrong.json()["code"] == "refund_method_mismatch"
    ask = {"reason": "Wrong dish", "stock_effect": "return", "method": "cash"}
    asked = post(client, h, f"/orders/{order['id']}/refund", ask).json()
    assert asked["status"] == "paid" and asked["refund"]["status"] == "requested"
    rid = asked["refund"]["id"]
    assert post(client, h, f"/orders/{order['id']}/refund", ask).json()["code"] == "refund_exists"
    own = client.post(f"{POS}/refunds/{rid}/approve", headers=h)
    assert own.status_code == 403 and own.json()["code"] == "cannot_approve_own_request"
    b = login(client, world["manager_b"])
    assert client.post(f"{POS}/refunds/{rid}/approve", headers=b).status_code == 404
    m = login(client, world["manager_a"])
    waiting = client.get(f"{POS}/refunds?outlet_id={world['shop']}", headers=m).json()
    assert [r["id"] for r in waiting] == [rid]
    done = client.post(f"{POS}/refunds/{rid}/approve", headers=m)
    assert done.status_code == 200 and done.json()["status"] == "done"
    assert client.get(f"{POS}/orders/{order['id']}", headers=m).json()["status"] == "refunded"
    assert on_hand(client, m, world["shop"]) == before  # "return": the stock came back
    h = login(client, world["cashier_a"])
    shift = client.get(f"{POS}/shifts/{sid}", headers=h).json()
    assert (shift["cash_refunds"], shift["expected"]) == (27_500, 100_000)


def test_owner_refunds_without_approval_and_waste_option(
    client: TestClient, world: dict[str, Any], menu: dict[str, Any]
) -> None:
    m = login(client, world["manager_a"])
    before = on_hand(client, m, world["shop"])
    o = {"X-CSRF-Token": enroll_as(client, world["owner_a"], PW)[2]}  # owners use 2FA
    open_shift(client, o, world, 0)
    order = new_order(client, o, world, menu)
    line(client, o, order, menu, "1")
    post(
        client,
        o,
        f"/orders/{order['id']}/pay",
        {"payments": [{"method": "qris", "amount": 27_500}]},
    )
    ask = {"reason": "Hair in food", "stock_effect": "waste", "method": "qris"}
    out = post(client, o, f"/orders/{order['id']}/refund", ask).json()
    assert out["status"] == "refunded" and out["refund"]["status"] == "done"
    after = on_hand(client, o, world["shop"])
    assert before["EGG"] - after["EGG"] == 1  # back from the sale, then written off as waste


def test_docs03_rule7_owner_sets_role_limits(client: TestClient, world: dict[str, Any]) -> None:
    o = {"X-CSRF-Token": enroll_as(client, world["owner_a"], PW)[2]}
    rows = client.get("/api/v1/role-limits", headers=o).json()
    cashier = next(r for r in rows if r["name"] == "Cashier")
    assert cashier["limits"] == [
        {"permission": "sales.discount.apply", "unit": "bp", "value": 1000}
    ]
    url = f"/api/v1/role-limits/{cashier['role_id']}"
    assert (
        client.put(url, json={"limits": {"sales.discount.apply": 1500}}, headers=o).status_code
        == 200
    )
    assert (
        client.put(url, json={"limits": {"sales.discount.apply": 20_000}}, headers=o).json()["code"]
        == "limit_above_100_percent"
    )
    assert (
        client.put(url, json={"limits": {"sales.order.pay": 1}}, headers=o).json()["code"]
        == "not_a_limited_permission"
    )
    m = login(client, world["manager_a"])
    assert (
        client.put(url, json={"limits": {"sales.discount.apply": 9000}}, headers=m).status_code
        == 403
    )


def test_discount_rechecked_at_payment_when_the_order_shrank(
    client: TestClient, world: dict[str, Any], menu: dict[str, Any]
) -> None:
    """Security review 2l: Rp 5.000 off Rp 50.000 is 10 % (the cashier's limit); lowering
    the order to Rp 25.000 afterwards makes it 20 %, which payment refuses."""
    h = login(client, world["cashier_a"])
    order = new_order(client, h, world, menu)
    out = line(client, h, order, menu)  # 2 x 25.000
    oid, lid = order["id"], out["lines"][0]["id"]
    off = {"kind": "amount", "value": 5000, "reason": "Regular"}
    assert client.put(f"{POS}/orders/{oid}/discount", json=off, headers=h).status_code == 200
    shrunk = client.put(f"{POS}/orders/{oid}/lines/{lid}", json={"qty": "1"}, headers=h)
    assert shrunk.status_code == 200, shrunk.text
    open_shift(client, h, world)
    total = shrunk.json()["totals"]["total"]
    paid = post(
        client, h, f"/orders/{oid}/pay", {"payments": [{"method": "cash", "amount": total}]}
    )
    assert paid.status_code == 403 and paid.json()["details"]["limit"] == 1000
    sql = "SELECT 1 FROM audit_log WHERE action = 'sales.order.line_qty'"
    changed = tenant_sql(world["a"], sql)
    assert len(changed) == 1  # the quantity change is on record


def test_an_idempotency_key_replays_only_for_the_same_user(
    client: TestClient, world: dict[str, Any], menu: dict[str, Any]
) -> None:
    """Security review 2l: someone else who learns a key gets no stored answer."""
    h = login(client, world["cashier_a"])
    order = new_order(client, h, world, menu)
    key = str(uuid.uuid4())
    body = {"item_id": menu["nasi"], "qty": "1"}
    first = post(client, h, f"/orders/{order['id']}/lines", body, key)
    assert post(client, h, f"/orders/{order['id']}/lines", body, key).json() == first.json()
    m = login(client, world["manager_a"])
    other = post(client, m, f"/orders/{order['id']}/lines", body, key)
    assert other.status_code == 409 and other.json()["code"] == "idempotency_key_reused"
