"""Slice 2i: combos (FR-CAT-011) and per-outlet price and availability (FR-TEN-011)."""

from typing import Any

from fastapi.testclient import TestClient

from tests.test_inventory import login, make_item
from tests.test_pos import CAT, POS, new_order, post, world
from tests.test_purchasing import client as client
from tests.test_sales_days import menu as menu
from tests.test_sales_days import on_hand

__all__ = ["world"]


def test_fr_cat_011_combo_takes_its_parts_stock(
    client: TestClient, world: dict[str, Any], menu: dict[str, Any]
) -> None:
    m = login(client, world["manager_a"])
    combo = make_item(
        client,
        m,
        "PAKET",
        "pcs",
        type="menu",
        is_stocked=False,
        shelf_life_days=None,
        storage_type="dry",
    )
    bad = client.put(
        f"{CAT}/items/{combo}/combo", json={"parts": [{"item_id": menu["egg"]}]}, headers=m
    )
    assert bad.status_code == 404  # only menu items go in a combo
    done = client.put(
        f"{CAT}/items/{combo}/combo",
        json={"parts": [{"item_id": menu["nasi"], "qty": "2"}]},
        headers=m,
    )
    assert done.status_code == 200, done.text
    nested = client.put(
        f"{CAT}/items/{menu['nasi']}/combo", json={"parts": [{"item_id": combo}]}, headers=m
    )
    assert nested.json()["code"] == "combo_in_combo"
    price = {"channel_id": menu["gofood"], "valid_from": "2026-01-01", "price": 45_000}
    client.put(f"{CAT}/items/{combo}/prices", json=price, headers=m)
    listed = {
        i["id"]: i for i in client.get(f"{CAT}/menu?channel_id={menu['gofood']}", headers=m).json()
    }
    assert [c["qty"] for c in listed[combo]["combo"]] == ["2.0000"]
    before = on_hand(client, m, world["shop"])
    client.post(
        f"{POS}/shifts", json={"outlet_id": str(world["shop"]), "opening_float": 0}, headers=m
    )
    order = new_order(client, m, world, menu)
    post(client, m, f"/orders/{order['id']}/lines", {"item_id": combo})
    paid = post(
        client,
        m,
        f"/orders/{order['id']}/pay",
        {"payments": [{"method": "cash", "amount": 49_500}]},
    )
    assert paid.status_code == 200, paid.text
    after = on_hand(client, m, world["shop"])
    assert before["EGG"] - after["EGG"] == 2 and before["RICE"] - after["RICE"] == 400


def test_fr_ten_011_outlet_price_and_sold_out(
    client: TestClient, world: dict[str, Any], menu: dict[str, Any]
) -> None:
    m = login(client, world["manager_a"])
    own = {
        "channel_id": menu["gofood"],
        "valid_from": "2026-01-01",
        "price": 27_000,
        "outlet_id": str(world["shop"]),
    }
    assert client.put(f"{CAT}/items/{menu['nasi']}/prices", json=own, headers=m).status_code == 200
    shop = client.get(
        f"{CAT}/menu?channel_id={menu['gofood']}&outlet_id={world['shop']}", headers=m
    ).json()
    other = client.get(
        f"{CAT}/menu?channel_id={menu['gofood']}&outlet_id={world['other']}", headers=m
    ).json()
    assert (shop[0]["price"], other[0]["price"]) == (27_000, 25_000)
    order = new_order(client, m, world, menu)
    line = post(client, m, f"/orders/{order['id']}/lines", {"item_id": menu["nasi"]}).json()
    assert line["lines"][0]["unit_price"] == 27_000
    off = client.put(
        f"{CAT}/items/{menu['nasi']}/outlets/{world['shop']}/availability",
        json={"is_available": False},
        headers=m,
    )
    assert off.status_code == 204
    assert (
        post(client, m, f"/orders/{order['id']}/lines", {"item_id": menu["nasi"]}).json()["code"]
        == "item_sold_out"
    )
    elsewhere = new_order(client, m, world, menu, outlet="other")
    assert (
        post(client, m, f"/orders/{elsewhere['id']}/lines", {"item_id": menu["nasi"]}).status_code
        == 200
    )
    h = login(client, world["cashier_a"])  # scoped to the shop only
    url = f"{CAT}/items/{menu['nasi']}/outlets/{world['other']}/availability"
    assert client.put(url, json={"is_available": False}, headers=h).status_code == 404
