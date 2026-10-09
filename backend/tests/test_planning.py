"""Slice 1j part 2: days of inventory (FR-INV-011), producible quantity (FR-INV-020),
reorder suggestions by vendor (FR-INV-013) and the low-days alert (FR-INV-012)."""

from collections.abc import Iterator
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from tests.factories import add_member, add_outlet, drop_tenant, seed_tenant
from tests.test_alerts import scan
from tests.test_catalog import units
from tests.test_inventory import API, HASH, login, make_item
from tests.test_purchasing import client as client
from tests.test_purchasing import tenant_sql

P = "/api/v1/purchasing"
CAT = "/api/v1/catalog"


@pytest.fixture
def world() -> Iterator[dict[str, Any]]:
    mods = ("inventory", "purchasing")
    a, roles = seed_tenant("Alpha", modules=mods)
    b, roles_b = seed_tenant("Beta", modules=mods)
    shop = add_outlet(a, "Shop")
    w: dict[str, Any] = {"a": a, "shop": shop}
    w["manager_a"] = add_member(a, roles["manager"], HASH)[1]
    w["kitchen_a"] = add_member(a, roles["kitchen"], HASH)[1]
    w["manager_b"] = add_member(b, roles_b["manager"], HASH)[1]
    yield w
    drop_tenant(a)
    drop_tenant(b)


@pytest.fixture
def stock(client: TestClient, world: dict[str, Any]) -> dict[str, Any]:
    """Shop: 10 kg rice, 30 eggs. Fried rice (1 pcs) = 200 g rice + 2 eggs. Over the last
    four weeks 7 kg rice was wasted, so the shop uses 250 g a day on average."""
    h = login(client, world["manager_a"])
    u = units(client)
    dry = {"shelf_life_days": None, "storage_type": "dry"}
    k: dict[str, Any] = {
        "rice": make_item(client, h, "RICE", "g", **dry),
        "egg": make_item(client, h, "EGG", "pcs", **dry),
        "nasi": make_item(client, h, "NASI", "pcs", type="menu", **dry),
        "u": u,
    }
    lines = [
        {"component_item_id": k["rice"], "qty": "200", "unit_id": u["g"], "waste_pct": "0"},
        {"component_item_id": k["egg"], "qty": "2", "unit_id": u["pcs"], "waste_pct": "0"},
    ]
    bom = client.post(f"{CAT}/items/{k['nasi']}/boms", json={"lines": lines}, headers=h).json()
    client.post(f"{CAT}/boms/{bom['id']}/activate", json={"valid_from": "2026-01-01"}, headers=h)
    start = (date.today() - timedelta(days=60)).isoformat()
    opening = [
        {"item_id": k["rice"], "qty": "17", "unit_id": u["kg"], "unit_cost": "14000"},
        {"item_id": k["egg"], "qty": "30", "unit_id": u["pcs"], "unit_cost": "2200"},
    ]
    body = {"outlet_id": str(world["shop"]), "business_date": start, "lines": opening}
    assert client.post(f"{API}/opening", json=body, headers=h).status_code == 201
    for days_ago in range(1, 8):
        waste = {
            "outlet_id": str(world["shop"]),
            "business_date": (date.today() - timedelta(days=days_ago)).isoformat(),
            "reason_code": "spoilage",
            "lines": [{"item_id": k["rice"], "qty": "1000", "unit_id": u["g"]}],
        }
        assert client.post(f"{API}/waste", json=waste, headers=h).status_code == 201
    return k


def test_fr_inv_011_days_left_on_the_stock_screen(
    client: TestClient, world: dict[str, Any], stock: dict[str, Any]
) -> None:
    h = login(client, world["manager_a"])
    rows = {
        r["sku"]: r
        for r in client.get(f"{API}/stock?outlet_id={world['shop']}", headers=h).json()["items"]
    }
    assert Decimal(rows["RICE"]["qty"]) == 10000
    assert Decimal(rows["RICE"]["avg_daily_use"]) == 250  # 7 kg over 28 days
    assert Decimal(rows["RICE"]["days_left"]) > 0
    assert rows["EGG"]["days_left"] is None  # not used lately: no estimate


def test_fr_inv_020_producible_with_limiting_ingredient(
    client: TestClient, world: dict[str, Any], stock: dict[str, Any]
) -> None:
    h = login(client, world["kitchen_a"])
    [row] = client.get(f"{API}/producible?outlet_id={world['shop']}", headers=h).json()
    # Rice allows 50 plates, eggs only 15: eggs limit.
    assert row["name"] and Decimal(row["can_make"]) == 15 and row["limiting_name"]


def test_fr_inv_013_reorder_suggestions_by_vendor_to_draft_po(
    client: TestClient, world: dict[str, Any], stock: dict[str, Any]
) -> None:
    h = login(client, world["manager_a"])
    u = stock["u"]
    cheap = client.post(f"{P}/vendors", json={"name": "Pasar Induk"}, headers=h).json()
    usual = client.post(f"{P}/vendors", json={"name": "CV Beras"}, headers=h).json()
    day = "2026-01-01"
    rice_25 = {
        "item_id": stock["rice"],
        "pack_qty": "25",
        "pack_unit_id": u["kg"],
        "valid_from": day,
    }
    client.post(f"{P}/vendors/{cheap['id']}/items", json={**rice_25, "price": 300000}, headers=h)
    preferred = {**rice_25, "price": 340000, "is_preferred": True}
    assert (
        client.post(f"{P}/vendors/{usual['id']}/items", json=preferred, headers=h).status_code
        == 201
    )
    levels = {
        "outlet_id": str(world["shop"]),
        "levels": [
            {"item_id": stock["rice"], "reorder_point": "12000", "max_qty": "40000"},
            {"item_id": stock["egg"], "reorder_point": "40"},
        ],
    }
    assert client.put(f"{API}/levels", json=levels, headers=h).status_code == 200
    groups = client.get(f"{P}/reorder-suggestions?outlet_id={world['shop']}", headers=h).json()
    by_vendor = {g["vendor_name"]: g for g in groups}
    [rice] = by_vendor["CV Beras"]["lines"]  # preferred beats cheaper
    assert Decimal(rice["suggested"]) == 30000  # up to the 40 kg maximum
    assert Decimal(rice["order_qty"]) == 50 and rice["unit_price"] == 13600  # two 25 kg sacks
    [egg] = by_vendor[None]["lines"]  # no vendor price: listed last, no pack
    assert egg["order_qty"] is None and groups[-1]["vendor_id"] is None
    po = {
        "outlet_id": str(world["shop"]),
        "vendor_id": usual["id"],
        "order_date": day,
        "lines": [
            {
                "item_id": rice["item_id"],
                "qty": rice["order_qty"],
                "unit_id": rice["order_unit_id"],
                "unit_price": rice["unit_price"],
            }
        ],
    }
    assert client.post(f"{P}/orders", json=po, headers=h).status_code == 201
    kitchen = login(client, world["kitchen_a"])  # cannot create orders: no suggestions either
    assert (
        client.get(
            f"{P}/reorder-suggestions?outlet_id={world['shop']}", headers=kitchen
        ).status_code
        == 403
    )


def test_fr_inv_012_low_days_alert(
    client: TestClient, world: dict[str, Any], stock: dict[str, Any], settings: Settings
) -> None:
    h = login(client, world["manager_a"])
    # Owners change settings in the UI; here the stored setting is written directly.
    tenant_sql(
        world["a"],
        "INSERT INTO tenant_settings (tenant_id, key, value) VALUES (:t, 'stock', :v) "
        "ON CONFLICT (tenant_id, key) DO UPDATE SET value = EXCLUDED.value",
        {"t": world["a"], "v": '{"low_days_alert": 60}'},
    )
    scan(settings, world["a"])
    kinds = [n["kind"] for n in client.get("/api/v1/notifications", headers=h).json()]
    assert "low_days_of_inventory" in kinds
