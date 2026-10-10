"""Slice 3h: forecast and EOQ (FR-INV-018), production plan suggestion (FR-PRD-005) and the
best-vendor ranking (FR-PUR-007)."""

import uuid
from collections.abc import Iterator
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.settings.schemas import PlanningSettings
from app.modules.inventory.forecast import _trend, eoq
from app.modules.purchasing.vendor_rank import _effective
from tests.factories import add_member, add_outlet, drop_tenant, seed_tenant
from tests.test_auth_mfa import enroll_as
from tests.test_inventory import API, HASH, PW, login, make_item
from tests.test_planning import CAT, P
from tests.test_planning import stock as stock
from tests.test_purchasing import client as client

PRD = "/api/v1/production"


@pytest.fixture
def world() -> Iterator[dict[str, Any]]:
    a, roles = seed_tenant("Alpha", modules=("inventory", "purchasing", "production"))
    shop = add_outlet(a, "Shop")
    w: dict[str, Any] = {"a": a, "shop": shop}
    w["owner_a"] = add_member(a, roles["owner"], HASH)[1]
    w["manager_a"] = add_member(a, roles["manager"], HASH)[1]
    w["kitchen_a"] = add_member(a, roles["kitchen"], HASH)[1]
    yield w
    drop_tenant(a)


def test_fr_inv_018_eoq_and_trend_rules() -> None:
    conf = PlanningSettings(order_cost=50_000, holding_cost_pct=25)
    # sqrt(2 x 1000 g/day x 365 x 50.000 / (14 x 0.25)) ~ 102.120 g
    assert eoq(Decimal(1000), Decimal(14), conf, None) == Decimal("102120.3772")
    assert eoq(Decimal(1000), Decimal(14), conf, 30) == Decimal(30000)  # shelf life caps it
    assert eoq(Decimal(1000), Decimal(14), PlanningSettings(), None) is None  # no order cost
    week = [Decimal(10)] * 7
    assert _trend(Decimal(15), week) == Decimal("1.5")
    assert _trend(Decimal(100), week) == Decimal("1.5")  # one odd week cannot swing it
    assert _trend(Decimal(1), week) == Decimal("0.5")


def test_fr_pur_007_lateness_and_waiting_cost_more() -> None:
    conf = PlanningSettings(reliability_weight_pct=30, lead_day_cost_bp=100)
    on_time = _effective(Decimal(100), Decimal(1), Decimal(0), conf)
    late = _effective(Decimal(100), Decimal("0.5"), Decimal(0), conf)
    slow = _effective(Decimal(100), Decimal(1), Decimal(5), conf)
    assert on_time == 100 and late == 115 and slow == 105


def test_fr_inv_018_forecast_endpoint_and_eoq_setting(
    client: TestClient, world: dict[str, Any], stock: dict[str, Any]
) -> None:
    h = login(client, world["manager_a"])
    rows = {
        r["name"]: r
        for r in client.get(f"{API}/forecast?outlet_id={world['shop']}&days=7", headers=h).json()
    }
    [rice] = [r for r in rows.values() if r["unit_code"] == "g"]
    assert rice["enough_history"] is False  # used for one week only: plain averages
    assert Decimal(rice["daily"]) == 250 and len(rice["days"]) == 7 and rice["eoq"] is None

    csrf = enroll_as(client, world["owner_a"], PW)[2]
    o = {"X-CSRF-Token": csrf}
    put = client.put(
        "/api/v1/settings/planning", json={"order_cost": 50_000, "forecast_min_days": 7}, headers=o
    )
    assert put.status_code == 200, put.text
    [rice] = [
        r
        for r in client.get(f"{API}/forecast?outlet_id={world['shop']}", headers=o).json()
        if r["unit_code"] == "g"
    ]
    assert rice["enough_history"] is True and Decimal(rice["eoq"]) > 0


def test_fr_pur_007_vendor_ranking_by_price(
    client: TestClient, world: dict[str, Any], stock: dict[str, Any]
) -> None:
    h = login(client, world["manager_a"])
    u = stock["u"]
    pack = {
        "item_id": stock["rice"],
        "pack_qty": "25",
        "pack_unit_id": u["kg"],
        "valid_from": "2026-01-01",
    }
    for name, price in (("CV Beras", 340_000), ("Pasar Induk", 300_000)):
        v = client.post(f"{P}/vendors", json={"name": name}, headers=h).json()
        assert (
            client.post(
                f"{P}/vendors/{v['id']}/items", json={**pack, "price": price}, headers=h
            ).status_code
            == 201
        )
    ranked = client.get(f"{P}/vendor-ranking?item_id={stock['rice']}", headers=h).json()
    assert [r["vendor_name"] for r in ranked] == ["Pasar Induk", "CV Beras"]
    assert Decimal(ranked[0]["per_base"]) == 12 and ranked[0]["lead_days"] is None
    k = login(client, world["kitchen_a"])
    assert client.get(f"{P}/vendor-ranking?item_id={stock['rice']}", headers=k).status_code == 403


def test_fr_prd_005_plan_from_par_and_accept(
    client: TestClient, world: dict[str, Any], stock: dict[str, Any]
) -> None:
    h = login(client, world["manager_a"])
    shop = str(world["shop"])
    u = stock["u"]
    dry = {"shelf_life_days": None, "storage_type": "dry"}
    base = make_item(client, h, "BASE", "pcs", type="semi_finished", **dry)  # rice + 2 eggs
    lines = [
        {"component_item_id": stock["rice"], "qty": "200", "unit_id": u["g"], "waste_pct": "0"},
        {"component_item_id": stock["egg"], "qty": "2", "unit_id": u["pcs"], "waste_pct": "0"},
    ]
    recipe = {"lines": lines, "yield_qty": "1", "yield_unit_id": u["pcs"]}
    bom = client.post(f"{CAT}/items/{base}/boms", json=recipe, headers=h).json()
    on = {"valid_from": "2026-01-01"}
    assert client.post(f"{CAT}/boms/{bom['id']}/activate", json=on, headers=h).status_code == 200
    levels = {"outlet_id": shop, "levels": [{"item_id": base, "par_qty": "10"}]}
    assert client.put(f"{API}/levels", json=levels, headers=h).status_code == 200
    plan = client.get(f"{PRD}/plan?outlet_id={shop}", headers=h).json()
    assert plan["days"] == 3
    [row] = plan["rows"]
    assert row["item_id"] == base and Decimal(row["suggested"]) == 10
    assert Decimal(row["can_make"]) == 15  # eggs allow 15 plates

    body: dict[str, Any] = {
        "outlet_id": shop,
        "production_date": (date.today() + timedelta(days=1)).isoformat(),
        "lines": [{"item_id": base, "qty": "10"}],
    }
    key = {**h, "Idempotency-Key": str(uuid.uuid4())}
    made = client.post(f"{PRD}/plan/accept", json=body, headers=key)
    assert made.status_code == 201, made.text
    assert (
        client.post(f"{PRD}/plan/accept", json=body, headers=key).json()[0]["id"]
        == made.json()[0]["id"]
    )
    assert client.get(f"{PRD}/plan?outlet_id={shop}", headers=h).json()["rows"] == []  # planned
    dup = {**body, "lines": body["lines"] * 2}
    assert (
        client.post(
            f"{PRD}/plan/accept", json=dup, headers={**h, "Idempotency-Key": str(uuid.uuid4())}
        ).json()["code"]
        == "duplicate_item"
    )
