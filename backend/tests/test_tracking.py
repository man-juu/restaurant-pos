"""Tracking modes and standard cost (owner decisions docs/09 0.26, 0.27)."""

from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient

from tests.test_catalog import units
from tests.test_imports_more import send
from tests.test_inventory import API, login, make_item
from tests.test_inventory import client as client
from tests.test_inventory import world as world

DAY = "2026-03-01"


def on_hand(client: TestClient, outlet: str, sku: str) -> Decimal:
    rows = client.get(f"{API}/stock?outlet_id={outlet}").json()["items"]
    return sum((Decimal(r["qty"]) for r in rows if r["sku"] == sku), Decimal(0))


def setup(client: TestClient, world: dict[str, Any]) -> dict[str, Any]:
    h = login(client, world["manager_a"])
    dry = {"shelf_life_days": None, "storage_type": "dry"}
    ids = {
        "rice": make_item(client, h, "RICE", "kg", tracking_mode="estimated", **dry),
        "egg": make_item(client, h, "EGG", "pcs", **dry),
    }
    rows = "outlet,sku,qty,unit,unit_cost\nShop,RICE,5,kg,14000\nShop,EGG,10,pcs,2000\n"
    assert send(client, h, f"{API}/imports/opening?business_date={DAY}", rows).status_code == 201
    return {**ids, "h": h}


def waste(
    client: TestClient, h: dict[str, str], world: dict[str, Any], item: str, unit: str, qty: str
) -> Any:
    body = {
        "outlet_id": str(world["shop"]),
        "business_date": DAY,
        "reason_code": "spoilage",
        "lines": [{"item_id": item, "qty": qty, "unit_id": unit}],
    }
    return client.post(f"{API}/waste", json=body, headers=h)


def test_estimated_items_never_block_but_exact_items_do(
    client: TestClient, world: dict[str, Any]
) -> None:
    s = setup(client, world)
    u = units(client)
    # Default policy for waste is "block": an exact item cannot go below zero ...
    assert waste(client, s["h"], world, s["egg"], u["pcs"], "11").status_code == 409
    # ... an estimated item can (the real amount was never known exactly).
    assert waste(client, s["h"], world, s["rice"], u["kg"], "7").status_code == 201
    assert on_hand(client, world["shop"], "RICE") == Decimal(-2)  # base unit kg


def test_set_on_hand_corrects_estimated_items_only(
    client: TestClient, world: dict[str, Any]
) -> None:
    s = setup(client, world)
    u = units(client)
    url = f"{API}/stock/set-on-hand"
    body = {"outlet_id": str(world["shop"]), "unit_id": u["kg"], "business_date": DAY}
    fixed = client.post(url, json={**body, "item_id": s["rice"], "qty": "3"}, headers=s["h"])
    assert fixed.status_code == 200 and fixed.json()["status"] == "posted"
    assert on_hand(client, world["shop"], "RICE") == Decimal(3)
    same = client.post(url, json={**body, "item_id": s["rice"], "qty": "3"}, headers=s["h"])
    assert same.status_code == 200 and same.json() is None
    egg = {**body, "unit_id": u["pcs"], "item_id": s["egg"], "qty": "4"}
    assert client.post(url, json=egg, headers=s["h"]).json()["code"] == "not_estimated"
    hc = login(client, world["cashier_a"])
    assert (
        client.post(url, json={**body, "item_id": s["rice"], "qty": "1"}, headers=hc).status_code
        == 403
    )


def test_standard_cost_fills_recipe_cost_and_is_hidden_without_permission(
    client: TestClient, world: dict[str, Any]
) -> None:
    h = login(client, world["manager_a"])
    gas = make_item(
        client, h, "GAS", "kg", tracking_mode="untracked", standard_cost="22", shelf_life_days=None
    )
    dish = make_item(client, h, "SOUP", "pcs", type="menu", is_stocked=False)
    u = units(client)
    bom = client.post(
        f"/api/v1/catalog/items/{dish}/boms",
        json={"lines": [{"component_item_id": gas, "qty": "50", "unit_id": u["g"]}]},
        headers=h,
    )
    assert bom.status_code == 201, bom.text
    client.post(
        f"/api/v1/catalog/boms/{bom.json()['id']}/activate", json={"valid_from": DAY}, headers=h
    )
    costing = client.get(f"/api/v1/catalog/items/{dish}/costing?on={DAY}").json()
    assert costing["missing_costs"] == [] and Decimal(costing["cost"]) == Decimal("1.1")
    item = client.get(f"/api/v1/catalog/items/{gas}").json()
    assert item["tracking_mode"] == "untracked" and item["is_stocked"] is False
    assert Decimal(item["standard_cost"]) == Decimal(22)
    login(client, world["cashier_a"])
    assert client.get(f"/api/v1/catalog/items/{gas}").json()["standard_cost"] is None
