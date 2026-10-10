"""Slice 3i: standing transfer orders by weekday (FR-TRF-005) and optional internal transfer
pricing (FR-TRF-006)."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient

from app.modules.transfers.standing import days_of, due_days, mask
from app.modules.transfers.standing_models import StandingTransfer
from tests.test_inventory import login
from tests.test_purchasing import client as client
from tests.test_purchasing import tenant_sql
from tests.test_transfers import T, ask, items, world

__all__ = ["client", "items", "world"]


def test_fr_trf_005_due_days_follow_weekdays_and_lead() -> None:
    s = StandingTransfer(weekdays=mask([0, 3]), lead_days=2)  # Monday and Thursday
    monday = date(2026, 10, 12)
    assert days_of(s.weekdays) == [0, 3]
    assert due_days(s, monday - timedelta(days=2)) == [monday]  # Saturday: Monday is due
    assert due_days(s, monday + timedelta(days=1)) == [monday + timedelta(days=3)]
    assert due_days(s, monday + timedelta(days=4)) == []  # Friday: nothing within two days


def test_fr_trf_005_standing_order_makes_requests_once(
    client: TestClient, world: dict[str, Any], items: dict[str, str]
) -> None:
    shop = login(client, world["store_shop"])
    every_day = {
        "from_outlet_id": str(world["kitchen"]),
        "to_outlet_id": str(world["shop"]),
        "weekdays": [0, 1, 2, 3, 4, 5, 6],
        "lead_days": 1,
        "lines": [{"item_id": items["rice"], "qty": "2000"}],
    }
    made = client.post(f"{T}/standing", json=every_day, headers=shop)
    assert made.status_code == 201, made.text
    sid = made.json()["id"]
    assert made.json()["weekdays"] == [0, 1, 2, 3, 4, 5, 6] and made.json()["next_delivery"]

    assert client.post(f"{T}/standing/run", headers=shop).json() == {"made": 2}  # today, tomorrow
    assert client.post(f"{T}/standing/run", headers=shop).json() == {"made": 0}  # never twice
    asked = client.get(f"{T}?outlet_id={world['shop']}", headers=shop).json()
    from_standing = [t for t in asked if t["standing_id"] == sid]
    assert len(from_standing) == 2 and {t["status"] for t in from_standing} == {"requested"}

    off = client.put(f"{T}/standing/{sid}", json={**every_day, "is_active": False}, headers=shop)
    assert off.status_code == 200 and off.json()["next_delivery"] is None
    kitchen_only = login(client, world["store_kitchen"])  # not the receiving outlet: unseen
    assert client.post(f"{T}/standing", json=every_day, headers=kitchen_only).status_code == 404
    cashier = login(client, world["cashier_a"])
    assert client.get(f"{T}/standing?outlet_id={world['shop']}", headers=cashier).status_code == 403


def test_fr_trf_006_cost_plus_charges_on_shipping(
    client: TestClient, world: dict[str, Any], items: dict[str, str]
) -> None:
    tenant_sql(
        world["a"],
        "INSERT INTO tenant_settings (tenant_id, key, value) VALUES (:t, 'transfers',"
        ' \'{"price_mode": "cost_plus", "markup_bp": 1000}\')',
        {"t": str(world["a"])},
    )
    m = login(client, world["manager_a"])
    t = ask(client, m, world, [{"item_id": items["rice"], "qty": "1000"}]).json()
    client.post(f"{T}/{t['id']}/approve", json={"lines": []}, headers=m)
    sent = client.post(f"{T}/{t['id']}/ship", json={"business_date": "2026-03-02"}, headers=m)
    assert sent.status_code == 200, sent.text
    body = sent.json()
    assert body["shipped_value"] == 14_000 and body["charge_total"] == 15_400  # +10 %
    rows = client.get(f"{T}/reports/charges?from=2026-03-01&to=2026-03-31", headers=m).json()
    assert [(r["cost"], r["charge"], r["transfers"]) for r in rows] == [(14_000, 15_400, 1)]
    assert Decimal(body["lines"][0]["shipped_qty"]) == 1000
