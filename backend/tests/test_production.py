"""Slice 1g: production orders (FR-PRD-001 to 004): plan from the recipe, complete with a
different output and usage, cost per unit of output, expiry from shelf life, reversal,
outlet scope, permissions and tenant isolation."""

import uuid
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.factories import add_member, add_outlet, drop_tenant, seed_tenant
from tests.test_catalog import item_body, units
from tests.test_inventory import API, HASH, login
from tests.test_purchasing import client as client

PRD = "/api/v1/production/orders"
CAT = "/api/v1/catalog"


@pytest.fixture
def world() -> Iterator[dict[str, Any]]:
    mods = ("inventory", "production")
    a, roles_a = seed_tenant("Alpha", modules=mods)
    b, roles_b = seed_tenant("Beta", modules=mods)
    shop, kitchen = add_outlet(a, "Shop"), add_outlet(a, "Central kitchen")
    w: dict[str, Any] = {"a": a, "shop": shop, "kitchen": kitchen}
    w["manager_a"] = add_member(a, roles_a["manager"], HASH)[1]
    w["cook_a"] = add_member(a, roles_a["kitchen"], HASH, outlets=(kitchen,))[1]
    w["cashier_a"] = add_member(a, roles_a["cashier"], HASH)[1]
    w["manager_b"] = add_member(b, roles_b["manager"], HASH)[1]
    yield w
    drop_tenant(a)
    drop_tenant(b)


def _item(client: TestClient, h: dict[str, str], sku: str, kind: str, unit: str, **x: Any) -> str:
    body = item_body(units(client)[unit], sku=sku, type=kind, **x)
    res = client.post(f"{CAT}/items", json=body, headers=h)
    assert res.status_code == 201, res.text
    return str(res.json()["id"])


@pytest.fixture
def sambal(client: TestClient, world: dict[str, Any]) -> dict[str, Any]:
    """Sambal (makes 500 g, 3 days) = 400 g chili with 20 % waste + 100 ml oil; the kitchen
    holds 2 kg chili at Rp 30 per g and 1 l oil at Rp 20 per ml."""
    h = login(client, world["manager_a"])
    u = units(client)
    dry = {"shelf_life_days": None, "storage_type": "dry"}
    k = {
        "chili": _item(client, h, "CHILI", "ingredient", "g", **dry),
        "oil": _item(client, h, "OIL", "ingredient", "ml", **dry),
        "sambal": _item(
            client, h, "SAMBAL", "semi_finished", "g", shelf_life_days=3, storage_type="chilled"
        ),
    }
    lines = [
        {"component_item_id": k["chili"], "qty": "400", "unit_id": u["g"], "waste_pct": "20"},
        {"component_item_id": k["oil"], "qty": "100", "unit_id": u["ml"], "waste_pct": "0"},
    ]
    bom = client.post(
        f"{CAT}/items/{k['sambal']}/boms",
        json={"lines": lines, "yield_qty": "500", "yield_unit_id": u["g"]},
        headers=h,
    )
    assert bom.status_code == 201, bom.text
    on = client.post(
        f"{CAT}/boms/{bom.json()['id']}/activate", json={"valid_from": "2026-01-01"}, headers=h
    )
    assert on.status_code == 200, on.text
    stock = [
        {"item_id": k["chili"], "qty": "2", "unit_id": u["kg"], "unit_cost": "30000"},
        {"item_id": k["oil"], "qty": "1", "unit_id": u["l"], "unit_cost": "20000"},
    ]
    body = {"outlet_id": str(world["kitchen"]), "business_date": "2026-03-01", "lines": stock}
    assert client.post(f"{API}/opening", json=body, headers=h).status_code == 201
    k["bom"] = bom.json()["id"]
    return k


def plan(
    client: TestClient, h: dict[str, str], outlet: Any, item: str, qty: str, key: str | None = None
) -> Any:
    body = {
        "outlet_id": str(outlet),
        "item_id": item,
        "planned_qty": qty,
        "production_date": "2026-03-02",
    }
    return client.post(PRD, json=body, headers={**h, "Idempotency-Key": key or str(uuid.uuid4())})


def on_hand(client: TestClient, outlet: Any) -> dict[str, Decimal]:
    rows = client.get(f"{API}/stock?outlet_id={outlet}").json()["items"]
    return {r["sku"]: Decimal(r["qty"]) for r in rows}


def test_fr_prd_001_to_004_plan_complete_cost_and_reverse(
    client: TestClient, world: dict[str, Any], sambal: dict[str, Any]
) -> None:
    h = login(client, world["cook_a"])
    key = str(uuid.uuid4())
    made = plan(client, h, world["kitchen"], sambal["sambal"], "1000", key)
    assert made.status_code == 201, made.text
    order = made.json()
    assert plan(client, h, world["kitchen"], sambal["sambal"], "1000", key).json() == order
    assert order["status"] == "planned" and order["number"].startswith("PRD-")
    assert order["bom_id"] == sambal["bom"]
    needs = {ln["item_id"]: Decimal(ln["planned_qty"]) for ln in order["lines"]}
    assert needs == {sambal["chili"]: Decimal(1000), sambal["oil"]: Decimal(200)}
    # FR-PRD-002: planning reserves nothing.
    assert on_hand(client, world["kitchen"])["CHILI"] == Decimal(2000)

    body = {"actual_qty": "900", "used": [{"item_id": sambal["oil"], "qty": "250"}]}
    done = client.post(f"{PRD}/{order['id']}/complete", json=body, headers=h)
    assert done.status_code == 200, done.text
    out = done.json()
    assert out["status"] == "completed"
    assert Decimal(out["yield_variance"]) == Decimal(-100)  # FR-PRD-003
    assert out["input_value"] == 1000 * 30 + 250 * 20  # FR-PRD-004
    assert Decimal(out["unit_cost"]) == Decimal("38.888889")
    assert out["expiry_date"] == "2026-03-05"  # production date + 3 days shelf life
    stock = on_hand(client, world["kitchen"])
    assert stock == {"CHILI": Decimal(1000), "OIL": Decimal(750), "SAMBAL": Decimal(900)}
    again = client.post(f"{PRD}/{order['id']}/complete", json=body, headers=h)
    assert again.status_code == 409

    # Cooks may not undo; a manager can, while the output is still all there.
    assert client.post(f"{PRD}/{order['id']}/reverse", headers=h).status_code == 403
    m = login(client, world["manager_a"])
    back = client.post(f"{PRD}/{order['id']}/reverse", headers=m)
    assert back.status_code == 200 and back.json()["status"] == "reversed"
    stock = on_hand(client, world["kitchen"])
    assert stock["CHILI"] == Decimal(2000) and stock.get("SAMBAL", Decimal(0)) == 0


def test_fr_prd_002_shortage_needs_confirmation_and_cancel(
    client: TestClient, world: dict[str, Any], sambal: dict[str, Any]
) -> None:
    h = login(client, world["manager_a"])
    order = plan(client, h, world["kitchen"], sambal["sambal"], "5000").json()
    short = client.post(f"{PRD}/{order['id']}/complete", json={"actual_qty": "5000"}, headers=h)
    assert short.status_code == 409 and short.json()["code"] == "insufficient_stock"
    body = {"actual_qty": "5000", "confirm_negative": True}  # default policy: warn
    assert client.post(f"{PRD}/{order['id']}/complete", json=body, headers=h).status_code == 200
    other = plan(client, h, world["kitchen"], sambal["sambal"], "10").json()
    gone = client.post(f"{PRD}/{other['id']}/cancel", headers=h)
    assert gone.json()["status"] == "cancelled"
    raw = plan(client, h, world["kitchen"], sambal["chili"], "10")
    assert raw.status_code == 409 and raw.json()["code"] == "not_producible"


def test_production_scope_permissions_and_isolation(
    client: TestClient, world: dict[str, Any], sambal: dict[str, Any]
) -> None:
    m = login(client, world["manager_a"])
    order = plan(client, m, world["shop"], sambal["sambal"], "100").json()
    cook = login(client, world["cook_a"])
    assert plan(client, cook, world["shop"], sambal["sambal"], "100").status_code == 404
    assert client.get(f"{PRD}/{order['id']}", headers=cook).status_code == 404
    cashier = login(client, world["cashier_a"])
    assert client.get(f"{PRD}?outlet_id={world['shop']}", headers=cashier).status_code == 403
    other = login(client, world["manager_b"])
    assert client.get(f"{PRD}/{order['id']}", headers=other).status_code == 404
