"""Slice 2e: floors and tables (FR-TBL-001), sessions with orders (FR-TBL-002), move, merge
and split by item (FR-TBL-003), occupancy with open amount (FR-TBL-004); paying the last
bill frees the tables to "needs cleaning" through the sales event; scope and isolation."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.factories import add_member, add_outlet, drop_tenant, seed_tenant
from tests.test_inventory import HASH, login
from tests.test_pos import POS, post
from tests.test_purchasing import client as client
from tests.test_sales_days import menu as menu

T = "/api/v1/tables"


@pytest.fixture
def world() -> Iterator[dict[str, Any]]:
    mods = ("inventory", "sales", "tables")
    a, roles = seed_tenant("Alpha", modules=mods)
    b, roles_b = seed_tenant("Beta", modules=mods)
    shop = add_outlet(a, "Shop")
    w: dict[str, Any] = {"a": a, "shop": shop}
    w["manager_a"] = add_member(a, roles["manager"], HASH)[1]
    w["cashier_a"] = add_member(a, roles["cashier"], HASH, outlets=(shop,))[1]
    w["waiter_a"] = add_member(a, roles["waiter"], HASH, outlets=(shop,))[1]
    w["manager_b"] = add_member(b, roles_b["manager"], HASH)[1]
    yield w
    drop_tenant(a)
    drop_tenant(b)


@pytest.fixture
def floor(client: TestClient, world: dict[str, Any]) -> dict[str, str]:
    h = login(client, world["manager_a"])
    made = client.post(
        f"{T}/floors", json={"outlet_id": str(world["shop"]), "name": "Main"}, headers=h
    )
    assert made.status_code == 201, made.text
    fid = made.json()["id"]
    ids = {}
    for name in ("T1", "T2", "T3"):
        rows = client.post(T, json={"floor_id": fid, "name": name, "capacity": 4}, headers=h).json()
        ids[name] = next(r["id"] for r in rows if r["name"] == name)
    dup = client.post(T, json={"floor_id": fid, "name": "T1"}, headers=h)
    assert dup.status_code == 409
    return ids


def tables(client: TestClient, h: dict[str, str], world: dict[str, Any]) -> dict[str, Any]:
    return {t["name"]: t for t in client.get(f"{T}?outlet_id={world['shop']}", headers=h).json()}


def test_fr_tbl_001_to_004_seat_move_merge_split_and_free(
    client: TestClient, world: dict[str, Any], menu: dict[str, Any], floor: dict[str, str]
) -> None:
    h = login(client, world["waiter_a"])
    seat = {"channel_id": menu["gofood"], "party_size": 3}
    s1 = client.post(f"{T}/{floor['T1']}/seat", json=seat, headers=h)
    assert s1.status_code == 201, s1.text
    session = s1.json()
    assert (
        client.post(f"{T}/{floor['T1']}/seat", json=seat, headers=h).json()["code"]
        == "table_not_free"
    )
    first = session["orders"][0]["id"]
    for _ in range(2):
        post(client, h, f"/orders/{first}/lines", {"item_id": menu["nasi"]})
    view = tables(client, h, world)
    assert view["T1"]["status"] == "occupied" and view["T1"]["session"]["open_amount"] == 50_000

    moved = client.post(
        f"{T}/sessions/{session['id']}/move", json={"to_table_id": floor["T2"]}, headers=h
    )
    assert moved.json()["table_ids"] == [floor["T2"]]
    view = tables(client, h, world)
    assert (view["T1"]["status"], view["T2"]["status"]) == ("available", "occupied")

    other = client.post(f"{T}/{floor['T3']}/seat", json={**seat, "party_size": 2}, headers=h).json()
    merged = client.post(
        f"{T}/sessions/{session['id']}/merge", json={"session_id": other["id"]}, headers=h
    ).json()
    assert merged["party_size"] == 5 and sorted(merged["table_ids"]) == sorted(
        [floor["T2"], floor["T3"]]
    )
    assert len(merged["orders"]) == 2

    order = client.get(f"{POS}/orders/{first}", headers=h).json()
    split = {"from_order_id": first, "line_ids": [order["lines"][0]["id"]]}
    after = client.post(f"{T}/sessions/{session['id']}/split", json=split, headers=h).json()
    assert sorted(o["subtotal"] for o in after["orders"]) == [0, 25_000, 25_000]

    # Paying and closing every bill frees both tables for cleaning (sales event).
    c = login(client, world["cashier_a"])
    client.post(
        f"{POS}/shifts", json={"outlet_id": str(world["shop"]), "opening_float": 0}, headers=c
    )
    for bill in after["orders"]:
        if bill["subtotal"]:
            paid = post(
                client,
                c,
                f"/orders/{bill['id']}/pay",
                {"payments": [{"method": "cash", "amount": 27_500}]},
            )
            assert paid.status_code == 200, paid.text
        else:
            assert client.post(f"{POS}/orders/{bill['id']}/cancel", headers=c).status_code == 200
    view = tables(client, c, world)
    assert (view["T2"]["status"], view["T3"]["status"]) == ("needs_cleaning", "needs_cleaning")
    assert view["T2"]["session"] is None
    clean = client.put(f"{T}/{floor['T2']}/status", json={"status": "available"}, headers=c)
    assert {t["name"]: t["status"] for t in clean.json()}["T2"] == "available"


def test_tables_setup_permission_scope_and_isolation(
    client: TestClient, world: dict[str, Any], menu: dict[str, Any], floor: dict[str, str]
) -> None:
    h = login(client, world["waiter_a"])
    assert client.post(T, json={"floor_id": floor["T1"], "name": "X"}, headers=h).status_code == 403
    b = login(client, world["manager_b"])
    assert client.get(f"{T}?outlet_id={world['shop']}", headers=b).status_code == 404
    seat = {"channel_id": menu["gofood"], "party_size": 2}
    assert client.post(f"{T}/{floor['T1']}/seat", json=seat, headers=b).status_code == 404
