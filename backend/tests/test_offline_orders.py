"""Slice 4a: offline order taking (FR-SAL-013). An order taken without a connection is
uploaded later with the till's own id: a repeat upload changes nothing, stock and the
shift are posted as online, a payment that no longer fits leaves the order open with the
reason, and outlet scope and the pay permission still hold."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient

from tests.test_inventory import login
from tests.test_pos import POS
from tests.test_pos import world as world
from tests.test_purchasing import client as client
from tests.test_sales_days import menu as menu
from tests.test_sales_days import on_hand

OFF = f"{POS}/offline"


def offline_order(world: dict[str, Any], menu: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {
        "client_id": str(uuid.uuid4()),
        "outlet_id": str(world["shop"]),
        "channel_id": menu["gofood"],
        "taken_at": (datetime.now(UTC) - timedelta(minutes=30)).isoformat(),
        "label": "Table 2",
        "lines": [{"item_id": menu["nasi"], "qty": "2"}],
        **extra,
    }


def test_fr_sal_013_pack_has_the_rules_for_totals(
    client: TestClient, world: dict[str, Any], menu: dict[str, Any]
) -> None:
    h = login(client, world["cashier_a"])
    pack = client.get(f"{OFF}/pack?channel_id={menu['gofood']}", headers=h)
    assert pack.status_code == 200, pack.text
    body = pack.json()
    assert body["enabled"] is True and body["tax"]["rules"]
    assert {m["code"] for m in body["methods"]} >= {"cash", "qris"}


def test_fr_sal_013_sync_is_idempotent_and_posts_stock(
    client: TestClient, world: dict[str, Any], menu: dict[str, Any]
) -> None:
    m = login(client, world["manager_a"])
    before = on_hand(client, m, world["shop"])
    h = login(client, world["cashier_a"])
    shift = {"outlet_id": str(world["shop"]), "opening_float": 0}
    assert client.post(f"{POS}/shifts", json=shift, headers=h).status_code == 201
    # 2 x 25.000 + PBJT 10 % = 55.000, worked out on the till.
    pay = {"payments": [{"method": "cash", "amount": 55_000, "tendered": 60_000}]}
    body = offline_order(world, menu, payment=pay)
    first = client.post(f"{OFF}/orders", json=body, headers=h)
    assert first.status_code == 200, first.text
    out = first.json()
    assert (out["status"], out["problem"], out["skipped_lines"]) == ("paid", None, 0)
    again = client.post(f"{OFF}/orders", json=body, headers=h).json()
    assert again["order_id"] == out["order_id"] and again["status"] == "paid"
    m = login(client, world["manager_a"])
    after = on_hand(client, m, world["shop"])
    assert before["RICE"] - after["RICE"] == 400  # posted once, not twice

    h = login(client, world["cashier_a"])
    wrong = {"payments": [{"method": "cash", "amount": 50_000}]}  # prices changed meanwhile
    left = client.post(f"{OFF}/orders", json=offline_order(world, menu, payment=wrong), headers=h)
    assert left.status_code == 200, left.text
    assert (left.json()["status"], left.json()["problem"]) == ("open", "payment_total_mismatch")
    order = client.get(f"{POS}/orders/{left.json()['order_id']}", headers=h).json()
    assert order["status"] == "open" and order["lines"][0]["status"] == "sent"

    gone = offline_order(world, menu)
    gone["lines"].append({"item_id": str(uuid.uuid4()), "qty": "1"})
    part = client.post(f"{OFF}/orders", json=gone, headers=h).json()
    assert (part["status"], part["problem"], part["skipped_lines"]) == (
        "open",
        "lines_skipped",
        1,
    )


def test_fr_sal_013_scope_permission_and_clock(
    client: TestClient, world: dict[str, Any], menu: dict[str, Any]
) -> None:
    h = login(client, world["cashier_a"])
    other = offline_order(world, menu, outlet_id=str(world["other"]))
    assert client.post(f"{OFF}/orders", json=other, headers=h).status_code == 404
    old = offline_order(world, menu, taken_at=(datetime.now(UTC) - timedelta(days=9)).isoformat())
    assert client.post(f"{OFF}/orders", json=old, headers=h).json()["code"] == "offline_taken_at"
    w = login(client, world["waiter_a"])
    pay = {"payments": [{"method": "cash", "amount": 66_000}]}
    denied = client.post(f"{OFF}/orders", json=offline_order(world, menu, payment=pay), headers=w)
    assert denied.status_code == 403
    served = client.post(f"{OFF}/orders", json=offline_order(world, menu), headers=w)
    assert served.status_code == 200 and served.json()["status"] == "open"
    b = login(client, world["manager_b"])
    assert client.post(f"{OFF}/orders", json=offline_order(world, menu), headers=b).status_code in (
        403,
        404,
    )
