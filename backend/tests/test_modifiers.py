"""Slice 2a: modifiers and availability (FR-CAT-003)."""
# ruff: noqa: F811  (pytest fixtures imported from test_catalog)

from typing import Any

from fastapi.testclient import TestClient

from tests.test_catalog import client, item_body, signin, units, world  # noqa: F401

CAT = "/api/v1/catalog"


def _items(client: TestClient, h: dict[str, str]) -> tuple[str, str]:
    g = units(client)["g"]
    egg = client.post(f"{CAT}/items", json=item_body(g, sku="EGG"), headers=h).json()["id"]
    menu = item_body(units(client)["pcs"], sku="NASGOR", type="menu", is_stocked=False)
    menu.pop("storage_type")
    made = client.post(f"{CAT}/items", json=menu, headers=h)
    assert made.status_code == 201, made.text
    return egg, made.json()["id"]


def _group(egg: str) -> dict[str, Any]:
    return {
        "name": "Add-ons",
        "min_select": 0,
        "max_select": 2,
        "options": [
            {
                "name": "Extra egg",
                "price_delta": 5000,
                "ingredient_item_id": egg,
                "ingredient_qty": "60",
            },
            {
                "name": "No egg",
                "price_delta": 0,
                "ingredient_item_id": egg,
                "ingredient_qty": "-60",
            },
        ],
    }


def test_fr_cat_003_modifier_groups_options_and_item_links(
    client: TestClient,
    world: dict[str, Any],
) -> None:
    h = signin(client, world["manager_a"])
    egg, nasgor = _items(client, h)
    made = client.post(f"{CAT}/modifier-groups", json=_group(egg), headers=h)
    assert made.status_code == 201, made.text
    group = made.json()
    assert [o["name"] for o in group["options"]] == ["Extra egg", "No egg"]
    # Saving again keeps option ids; an option left out is switched off, not deleted.
    keep = group["options"][0]
    body = {**_group(egg), "options": [{**keep, "price_delta": 6000}]}
    saved = client.put(f"{CAT}/modifier-groups/{group['id']}", json=body, headers=h).json()
    assert [(o["id"], o["price_delta"], o["is_active"]) for o in saved["options"]] == [
        (keep["id"], 6000, True),
        (group["options"][1]["id"], 0, False),
    ]
    linked = client.put(
        f"{CAT}/items/{nasgor}/modifier-groups", json={"group_ids": [group["id"]]}, headers=h
    )
    assert linked.status_code == 200 and linked.json()[0]["id"] == group["id"]
    # Only menu items take modifiers; ingredient changes must be stocked non-menu items.
    egg_link = client.put(f"{CAT}/items/{egg}/modifier-groups", json={"group_ids": []}, headers=h)
    assert egg_link.json()["code"] == "not_a_menu_item"
    bad = {**_group(nasgor), "name": "Bad"}
    assert client.post(f"{CAT}/modifier-groups", json=bad, headers=h).status_code == 404
    dup = client.post(f"{CAT}/modifier-groups", json=_group(egg), headers=h)
    assert dup.status_code == 409


def test_fr_cat_003_sold_out_switch_permissions_and_isolation(
    client: TestClient,
    world: dict[str, Any],
) -> None:
    h = signin(client, world["manager_a"])
    egg, nasgor = _items(client, h)
    group = client.post(f"{CAT}/modifier-groups", json=_group(egg), headers=h).json()
    hc = signin(client, world["cashier_a"])
    off = client.put(f"{CAT}/items/{nasgor}/availability", json={"is_available": False}, headers=hc)
    assert off.status_code == 204
    assert client.get(f"{CAT}/items/{nasgor}").json()["is_available"] is False
    assert client.post(f"{CAT}/modifier-groups", json=_group(egg), headers=hc).status_code == 403
    hb = signin(client, world["manager_b"])
    assert client.get(f"{CAT}/modifier-groups").json() == []
    other = client.put(f"{CAT}/modifier-groups/{group['id']}", json=_group(egg), headers=hb)
    assert other.status_code == 404
    gone = client.put(f"{CAT}/items/{nasgor}/availability", json={"is_available": True}, headers=hb)
    assert gone.status_code == 404
