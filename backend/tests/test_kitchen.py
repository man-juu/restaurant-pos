"""Slice 2f: kitchen display (FR-KDS-001 to 004): sent lines become tickets at the default
station (or the station of their category), delivery orders are marked, start, ready, bump
and recall, voided lines struck through, paying unsent lines still reaches the kitchen,
outlet scope and isolation."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.factories import add_member, add_outlet, drop_tenant, seed_tenant
from tests.test_inventory import HASH, login
from tests.test_pos import POS, new_order, post
from tests.test_purchasing import client as client
from tests.test_sales_days import menu as menu

K = "/api/v1/kitchen"


@pytest.fixture
def world() -> Iterator[dict[str, Any]]:
    mods = ("inventory", "sales", "kitchen")
    a, roles = seed_tenant("Alpha", modules=mods)
    b, roles_b = seed_tenant("Beta", modules=mods)
    shop = add_outlet(a, "Shop")
    w: dict[str, Any] = {"a": a, "shop": shop}
    w["manager_a"] = add_member(a, roles["manager"], HASH)[1]
    w["cashier_a"] = add_member(a, roles["cashier"], HASH, outlets=(shop,))[1]
    w["cook_a"] = add_member(a, roles["kitchen"], HASH, outlets=(shop,))[1]
    w["manager_b"] = add_member(b, roles_b["manager"], HASH)[1]
    yield w
    drop_tenant(a)
    drop_tenant(b)


def tickets(
    client: TestClient, h: dict[str, str], world: dict[str, Any], **q: Any
) -> list[dict[str, Any]]:
    query = "&".join(f"{k}={v}" for k, v in q.items())
    out = client.get(f"{K}/tickets?outlet_id={world['shop']}&{query}", headers=h)
    assert out.status_code == 200, out.text
    return list(out.json())


def test_fr_kds_001_to_004_tickets_flow(
    client: TestClient, world: dict[str, Any], menu: dict[str, Any]
) -> None:
    m = login(client, world["manager_a"])
    hot = {"outlet_id": str(world["shop"]), "name": "Hot kitchen", "is_default": True}
    station = client.post(f"{K}/stations", json=hot, headers=m)
    assert station.status_code == 201, station.text
    bar = {"outlet_id": str(world["shop"]), "name": "Bar", "category_ids": []}
    assert client.post(f"{K}/stations", json=bar, headers=m).status_code == 201

    h = login(client, world["cashier_a"])
    order = new_order(client, h, world, menu)
    post(
        client,
        h,
        f"/orders/{order['id']}/lines",
        {"item_id": menu["nasi"], "qty": "2", "note": "no onion"},
    )
    out = post(client, h, f"/orders/{order['id']}/lines", {"item_id": menu["nasi"]}).json()
    client.post(f"{POS}/orders/{order['id']}/send", headers=h)

    c = login(client, world["cook_a"])
    [ticket] = tickets(client, c, world)
    assert ticket["station_id"] == station.json()["id"] and ticket["platform"] == "gofood"
    assert ticket["label"] == "Table 4" and not ticket["late"]
    assert [(i["qty"], i["note"]) for i in ticket["items"]] == [
        ("2.0000", "no onion"),
        ("1.0000", None),
    ]
    tid = ticket["id"]
    assert client.post(f"{K}/tickets/{tid}/start", headers=c).status_code == 204
    assert client.post(f"{K}/tickets/{tid}/start", headers=c).json()["code"] == "wrong_status"
    assert client.post(f"{K}/tickets/{tid}/ready", headers=c).status_code == 204
    assert client.post(f"{K}/tickets/{tid}/bump", headers=c).status_code == 204
    assert tickets(client, c, world) == []
    assert [t["id"] for t in tickets(client, c, world, bumped="true")] == [tid]
    assert client.post(f"{K}/tickets/{tid}/recall", headers=c).status_code == 204
    assert tickets(client, c, world)[0]["status"] == "ready"

    # A voided sent line is struck through on the display.
    h = login(client, world["cashier_a"])
    line_id = out["lines"][1]["id"]
    client.post(
        f"{POS}/orders/{order['id']}/lines/{line_id}/void",
        json={"reason": "Changed mind"},
        headers=h,
    )
    c = login(client, world["cook_a"])
    assert [i["status"] for i in tickets(client, c, world)[0]["items"]] == ["active", "void"]


def test_paid_before_sent_still_reaches_the_kitchen_and_scope(
    client: TestClient, world: dict[str, Any], menu: dict[str, Any]
) -> None:
    h = login(client, world["cashier_a"])
    client.post(
        f"{POS}/shifts", json={"outlet_id": str(world["shop"]), "opening_float": 0}, headers=h
    )
    order = new_order(client, h, world, menu)
    post(client, h, f"/orders/{order['id']}/lines", {"item_id": menu["nasi"]})
    assert (
        post(
            client,
            h,
            f"/orders/{order['id']}/pay",
            {"payments": [{"method": "cash", "amount": 27_500}]},
        ).status_code
        == 200
    )
    c = login(client, world["cook_a"])
    [ticket] = tickets(client, c, world)
    assert ticket["station_id"] is None  # no stations set up: one shared queue
    assert (
        client.post(
            f"{K}/stations", json={"outlet_id": str(world["shop"]), "name": "X"}, headers=c
        ).status_code
        == 403
    )
    b = login(client, world["manager_b"])
    assert client.get(f"{K}/tickets?outlet_id={world['shop']}", headers=b).status_code == 404
    assert client.post(f"{K}/tickets/{ticket['id']}/bump", headers=b).status_code == 404
