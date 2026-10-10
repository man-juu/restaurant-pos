"""Slice 1d part 2: recipe and opening-stock imports (FR-IMP-001, 002)."""

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from tests.factories import add_outlet
from tests.test_inventory import API, login, make_item
from tests.test_inventory import client as client
from tests.test_inventory import world as world


def send(client: TestClient, h: dict[str, str], url: str, text: str, name: str = "f.csv") -> Any:
    sep = "&" if "?" in url else "?"
    return client.post(
        f"{url}{sep}file_name={name}",
        content=text.encode(),
        headers={**h, "Content-Type": "application/octet-stream"},
    )


def setup_items(client: TestClient, h: dict[str, str]) -> None:
    make_item(client, h, "BEEF", "pcs")
    make_item(client, h, "RICE", "kg", shelf_life_days=None, storage_type="dry")
    make_item(client, h, "BIBIMBAP", "pcs", type="menu", is_stocked=False)


RECIPE = "item_sku,component_sku,qty,unit\nBIBIMBAP,BEEF,1,pcs\nBIBIMBAP,RICE,200,g\n"


def test_recipe_import_creates_drafts_and_undo_deletes_them(
    client: TestClient, world: dict[str, Any]
) -> None:
    h = login(client, world["manager_a"])
    setup_items(client, h)
    base = "/api/v1/catalog/imports/recipes"
    bad = send(client, h, f"{base}/check", RECIPE + "BIBIMBAP,NOPE,1,pcs\n").json()
    assert bad["errors"] == [{"row": 2, "field": "component_sku"}]
    loop = "item_sku,component_sku,qty,unit\nBEEF,RICE,1,kg\n"  # ingredients have no recipe
    assert send(client, h, f"{base}/check", loop).json()["errors"][0]["field"] == (
        "ingredient_has_no_recipe"
    )
    batch = send(client, h, base, RECIPE)
    assert batch.status_code == 201, batch.text
    items = client.get("/api/v1/catalog/items?q=BIBIMBAP").json()["items"]
    versions = client.get(f"/api/v1/catalog/items/{items[0]['id']}/boms").json()
    assert [v["status"] for v in versions] == ["draft"]
    undone = client.post(f"/api/v1/catalog/imports/{batch.json()['id']}/revert", headers=h)
    assert undone.json()["status"] == "reverted"
    assert client.get(f"/api/v1/catalog/items/{items[0]['id']}/boms").json() == []


def test_opening_import_posts_per_outlet_and_undo_reverses(
    client: TestClient, world: dict[str, Any]
) -> None:
    h = login(client, world["manager_a"])
    setup_items(client, h)
    url = f"{API}/imports/opening"
    rows = (
        "outlet,sku,qty,unit,unit_cost,expiry_date\n"
        "Shop,BEEF,10,pcs,18000,31/12/2026\nShop,RICE,5,kg,14000,\n"
        "Central kitchen,RICE,20000,g,14,\n"
    )
    checked = send(client, h, f"{url}/check?business_date=2026-03-01", rows).json()
    assert checked == {"rows_ok": 3, "errors": [], "new_categories": []}
    batch = send(client, h, f"{url}?business_date=2026-03-01", rows)
    assert batch.status_code == 201, batch.text
    assert send(client, h, url, rows).json()["code"] == "already_imported"
    undone = client.post(f"{url.rsplit('/', 1)[0]}/{batch.json()['id']}/revert", headers=h)
    assert undone.status_code == 200 and undone.json()["status"] == "reverted"


def test_opening_import_respects_outlet_scope_and_permissions(
    client: TestClient, world: dict[str, Any]
) -> None:
    h = login(client, world["manager_a"])
    setup_items(client, h)
    rows = "outlet,sku,qty,unit,unit_cost\nShop,RICE,5,kg,14000\n"
    hs = login(client, world["store_a"])  # warehouse, Central kitchen only
    checked = send(client, hs, f"{API}/imports/opening/check", rows).json()
    assert checked["errors"] == [{"row": 2, "field": "outlet"}]
    hc = login(client, world["cashier_a"])
    assert send(client, hc, f"{API}/imports/opening/check", rows).status_code == 403


def test_demo_kitchen_files_import_cleanly(client: TestClient, world: dict[str, Any]) -> None:
    """docs/demo must keep working as the product changes."""
    demo = Path(__file__).resolve().parents[2] / "docs" / "demo"
    add_outlet(world["a"], "Demo kitchen")
    h = login(client, world["manager_a"])
    for url, name in (
        ("/api/v1/catalog/imports/items", "items.csv"),
        ("/api/v1/catalog/imports/recipes", "recipes.csv"),
        (f"{API}/imports/opening?business_date=2026-10-08", "opening-stock.csv"),
    ):
        res = send(client, h, url, (demo / name).read_text(), name)
        assert res.status_code == 201, (name, res.text)
