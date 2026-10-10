"""Slice 3f: delivery-platform settlement (FR-FIN-007): sales stay gross, commission and
fees are an expense, the payout clears the platform receivable and is reconciled."""

import uuid
from typing import Any

from fastapi.testclient import TestClient

from tests.test_auto_journals import G, balance, books
from tests.test_auto_journals import world as world
from tests.test_inventory import login
from tests.test_purchasing import client as client
from tests.test_sales_days import enter, entry
from tests.test_sales_days import menu as menu

F = "/api/v1/finance"
SET = f"{F}/settlements"


def key(h: dict[str, str]) -> dict[str, str]:
    return {**h, "Idempotency-Key": str(uuid.uuid4())}


def test_fr_fin_007_payout_clears_receivable_and_reconciles(
    client: TestClient, world: dict[str, Any], menu: dict[str, Any]
) -> None:
    acc = login(client, world["acc"])
    client.post(f"{G}/setup", json={"start_date": "2026-01-01"}, headers=acc)
    client.post(f"{F}/accounts", json={"name": "BCA", "kind": "bank"}, headers=acc)
    bca = next(a for a in client.get(f"{F}/accounts", headers=acc).json() if a["name"] == "BCA")
    m = login(client, world["manager_a"])
    sold = enter(client, m, entry(world, menu, "4"))  # GoFood: 4 x 25.000
    assert sold.status_code == 201, sold.text
    acc = login(client, world["acc"])
    booked = balance(books(client, acc), "platform_receivable")
    assert booked >= 100_000

    body = {
        "channel_id": menu["gofood"],
        "outlet_id": str(world["shop"]),
        "account_id": bca["id"],
        "period_from": "2026-03-01",
        "period_to": "2026-03-07",
        "paid_on": "2026-03-10",
        "gross": booked,
        "commission": 20_000,
        "fees": 2_000,
        "adjustments": 0,
        "payout": booked - 22_000,
    }
    bad = client.post(SET, json={**body, "payout": 1}, headers=key(acc))
    assert bad.status_code == 422  # payout must add up
    h = key(acc)
    made = client.post(SET, json=body, headers=h)
    assert made.status_code == 201, made.text
    assert made.json()["number"].startswith("SET")
    assert client.post(SET, json=body, headers=h).json()["id"] == made.json()["id"]

    b = books(client, acc)
    assert balance(b, "platform_receivable") == 0
    assert balance(b, "platform_commission") == 22_000
    assert balance(b, "bank") == booked - 22_000
    assert sum(r["debit"] for r in b.values()) == sum(r["credit"] for r in b.values())
    accounts = {a["name"]: a["balance"] for a in client.get(f"{F}/accounts", headers=acc).json()}
    assert accounts["BCA"] == booked - 22_000

    q = f"channel_id={menu['gofood']}&outlet_id={world['shop']}&from=2026-03-01&to=2026-03-31"
    rec = client.get(f"{SET}/reconcile?{q}", headers=acc).json()
    assert rec["booked_gross"] == booked and rec["difference"] == 0
    assert rec["settlements"] == 1 and rec["commission_pct"] is not None

    rev = client.post(f"{SET}/{made.json()['id']}/reverse", headers=acc)
    assert rev.status_code == 200 and rev.json()["status"] == "reversed"
    assert balance(books(client, acc), "platform_receivable") == booked
    rec = client.get(f"{SET}/reconcile?{q}", headers=acc).json()
    assert rec["difference"] == booked  # nothing settled any more


def test_settlement_rules_and_permissions(
    client: TestClient, world: dict[str, Any], menu: dict[str, Any]
) -> None:
    acc = login(client, world["acc"])
    client.post(f"{F}/accounts", json={"name": "BCA", "kind": "bank"}, headers=acc)
    bca = client.get(f"{F}/accounts", headers=acc).json()[0]
    body = {
        "channel_id": menu["gofood"],
        "outlet_id": str(world["shop"]),
        "account_id": bca["id"],
        "period_from": "2026-03-01",
        "period_to": "2026-03-07",
        "paid_on": "2026-03-10",
        "gross": 10_000,
        "payout": 10_000,
    }
    m = login(client, world["manager_a"])
    assert client.post(SET, json=body, headers=key(m)).status_code == 403
    dine = client.post(
        "/api/v1/catalog/channels",
        json={"code": "dine", "name": "Dine in", "kind": "dine_in"},
        headers=m,
    ).json()["id"]
    acc = login(client, world["acc"])
    wrong = client.post(SET, json={**body, "channel_id": dine}, headers=key(acc))
    assert wrong.json()["code"] == "not_a_platform_channel"
    c = login(client, world["cashier_a"])
    assert client.get(f"{SET}?outlet_id={world['shop']}", headers=c).status_code == 403
