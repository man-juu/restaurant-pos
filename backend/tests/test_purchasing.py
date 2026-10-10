"""Slice 1f part 1: vendors, vendor items, quick purchase (FR-PUR-001, 002, 004 to 006, 011)."""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.factories import _run, add_member, add_outlet, drop_tenant, seed_tenant
from tests.test_catalog import units
from tests.test_inventory import API, HASH, login, make_item
from tests.test_inventory import client as client

P = "/api/v1/purchasing"
DAY = date(2026, 3, 1)


@pytest.fixture
def world() -> Iterator[dict[str, Any]]:
    mods = ("inventory", "purchasing")
    a, roles_a = seed_tenant("Alpha", modules=mods)
    b, roles_b = seed_tenant("Beta", modules=mods)
    shop, kitchen = add_outlet(a, "Shop"), add_outlet(a, "Central kitchen")
    w: dict[str, Any] = {"a": a, "shop": shop, "kitchen": kitchen}
    w["manager_a"] = add_member(a, roles_a["manager"], HASH)[1]
    w["store_a"] = add_member(a, roles_a["warehouse"], HASH, outlets=(kitchen,))[1]
    w["cashier_a"] = add_member(a, roles_a["cashier"], HASH)[1]
    w["manager_b"] = add_member(b, roles_b["manager"], HASH)[1]
    yield w
    drop_tenant(a)
    drop_tenant(b)


def tenant_sql(tenant: Any, sql: str, params: dict[str, Any] | None = None) -> Any:
    """Owner query inside the tenant's RLS context (works with or without superuser)."""

    async def go(db: Any) -> Any:
        await db.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant)})
        result = await db.execute(text(sql), params or {})
        return result.all() if result.returns_rows else None

    return asyncio.run(_run(go))


def buy(client: TestClient, h: dict[str, str], body: dict[str, Any], key: str | None = None) -> Any:
    headers = {**h, "Idempotency-Key": key or str(uuid.uuid4())}
    return client.post(f"{P}/quick-purchases", json=body, headers=headers)


def purchase(
    world: dict[str, Any], items: dict[str, str], u: dict[str, str], **extra: Any
) -> dict[str, Any]:
    return {
        "outlet_id": str(world["shop"]),
        "vendor_name": "Pasar Senen",
        "business_date": DAY.isoformat(),
        "lines": [
            {"item_id": items["beef"], "qty": "2", "unit_id": u["kg"], "line_total": 240000},
            {"item_id": items["rice"], "qty": "10", "unit_id": u["kg"], "line_total": 140000},
        ],
        **extra,
    }


@pytest.fixture
def items(client: TestClient, world: dict[str, Any]) -> dict[str, str]:
    h = login(client, world["manager_a"])
    return {
        "beef": make_item(client, h, "BEEF", "g"),  # 90 days shelf life
        "rice": make_item(client, h, "RICE", "g", shelf_life_days=None, storage_type="dry"),
    }


def test_fr_pur_001_vendor_bank_details_are_encrypted_and_reveal_is_audited(
    client: TestClient, world: dict[str, Any]
) -> None:
    h = login(client, world["manager_a"])
    made = client.post(
        f"{P}/vendors",
        json={"name": "CV Daging Segar", "bank_details": "BCA 1234567890"},
        headers=h,
    )
    assert made.status_code == 201 and made.json()["has_bank_details"] is True
    assert "bank" not in str(made.json()).replace("has_bank_details", "")
    stored = tenant_sql(
        world["a"], "SELECT bank_details_enc FROM vendors WHERE name = 'CV Daging Segar'"
    )[0][0]
    assert b"1234567890" not in bytes(stored)  # encrypted at rest
    shown = client.post(f"{P}/vendors/{made.json()['id']}/bank-details", headers=h)
    assert shown.json() == {"bank_details": "BCA 1234567890"}
    actions = [
        r[0]
        for r in tenant_sql(
            world["a"],
            "SELECT action FROM audit_log WHERE target_id = :v",
            {"v": made.json()["id"]},
        )
    ]
    assert "purchasing.vendor.bank_details_viewed" in actions
    hs = login(client, world["store_a"])  # warehouse: can buy, not manage vendors
    assert (
        client.post(f"{P}/vendors/{made.json()['id']}/bank-details", headers=hs).status_code == 403
    )


def test_fr_pur_004_quick_purchase_receives_stock_prefills_expiry_and_records_prices(
    client: TestClient, world: dict[str, Any], items: dict[str, str]
) -> None:
    h = login(client, world["manager_a"])
    u = units(client)
    res = buy(client, h, purchase(world, items, u))
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["number"].startswith("GR-2026-") and body["total"] == 380000
    beef = next(ln for ln in body["lines"] if ln["item_id"] == items["beef"])
    assert beef["expiry_date"] == (DAY + timedelta(days=90)).isoformat()  # from shelf life
    rows = {
        r["sku"]: r for r in client.get(f"{API}/stock?outlet_id={world['shop']}").json()["items"]
    }
    assert Decimal(rows["BEEF"]["qty"]) == 2000 and Decimal(rows["BEEF"]["avg_cost"]) == 120
    prices = tenant_sql(world["a"], "SELECT unit_cost FROM vendor_price_history")
    assert sorted(Decimal(p[0]) for p in prices) == [Decimal(14), Decimal(120)]


def test_quick_purchase_is_idempotent_and_reversible(
    client: TestClient, world: dict[str, Any], items: dict[str, str]
) -> None:
    h = login(client, world["manager_a"])
    u = units(client)
    key = str(uuid.uuid4())
    first = buy(client, h, purchase(world, items, u), key)
    again = buy(client, h, purchase(world, items, u), key)
    assert first.json()["id"] == again.json()["id"]
    assert len(client.get(f"{P}/receipts?outlet_id={world['shop']}").json()) == 1
    back = client.post(f"{P}/receipts/{first.json()['id']}/reverse", headers=h)
    assert back.status_code == 200 and back.json()["status"] == "reversed"
    assert client.get(f"{API}/stock?outlet_id={world['shop']}").json()["items"] == []


def test_fr_pur_011_invoice_photo_optional_unless_required(
    client: TestClient, world: dict[str, Any], items: dict[str, str], settings: Any
) -> None:
    h = login(client, world["manager_a"])
    u = units(client)
    tenant_sql(
        world["a"],
        "INSERT INTO tenant_settings (tenant_id, key, value) VALUES (:t, 'purchasing', "
        "'{\"require_invoice_attachment\": true}')",
        {"t": world["a"]},
    )
    missing = buy(client, h, purchase(world, items, u))
    assert missing.status_code == 422 and missing.json()["code"] == "invoice_required"


def test_scope_permissions_and_isolation(
    client: TestClient, world: dict[str, Any], items: dict[str, str]
) -> None:
    h = login(client, world["manager_a"])
    u = units(client)
    hs = login(client, world["store_a"])  # Central kitchen only
    assert buy(client, hs, purchase(world, items, u)).status_code in (403, 404)  # not their outlet
    hc = login(client, world["cashier_a"])
    assert buy(client, hc, purchase(world, items, u)).status_code == 403
    login(client, world["manager_b"])
    assert client.get(f"{P}/vendors").json() == []
    hb = login(client, world["manager_b"])
    foreign = buy(client, hb, purchase(world, items, u))
    assert foreign.status_code in (403, 404, 422)  # another tenant's outlet and items
    assert h  # manager_a session was used above


def test_fr_rpt_005_purchase_reports(
    client: TestClient, world: dict[str, Any], items: dict[str, str]
) -> None:
    h = login(client, world["manager_a"])
    kg = units(client)["kg"]
    vendor = client.post(f"{P}/vendors", json={"name": "CV Segar"}, headers=h).json()
    for day, paid in (("2026-03-01", 140_000), ("2026-03-08", 150_000)):
        body = {
            "outlet_id": str(world["shop"]),
            "vendor_id": vendor["id"],
            "business_date": day,
            "lines": [{"item_id": items["rice"], "qty": "10", "unit_id": kg, "line_total": paid}],
        }
        assert buy(client, h, body).status_code == 201
    span = "from=2026-03-01&to=2026-03-31"
    by_vendor = client.get(f"{P}/reports/purchases?{span}&by=vendor", headers=h).json()
    assert by_vendor["rows"] == [{"name": "CV Segar", "receipts": 2, "total": 290_000}]
    trend = client.get(f"{P}/reports/price-trend?{span}&item_id={items['rice']}", headers=h).json()
    assert [r["unit_cost"] for r in trend["rows"]] == ["14", "15"]
    store = login(client, world["store_a"])  # kitchen-only storekeeper: shop is out of scope
    assert (
        client.get(
            f"{P}/reports/purchases?{span}&outlet_id={world['shop']}", headers=store
        ).status_code
        == 404
    )
    cashier = login(client, world["cashier_a"])
    assert client.get(f"{P}/reports/purchases?{span}", headers=cashier).status_code == 403
