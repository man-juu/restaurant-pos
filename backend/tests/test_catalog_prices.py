"""Slice 1b part 2: channels and channel list prices with start dates (FR-CAT-004)."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.core.config import Settings
from app.main import create_app
from tests.test_auth import new_client
from tests.test_catalog import item_body, signin, units
from tests.test_catalog import world as world

API = "/api/v1/catalog"
FUTURE = "2099-01-01"


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with new_client(app) as c:
        yield c


def channel(client: TestClient, h: dict[str, str], code: str = "dine_in", **extra: Any) -> str:
    body = {"code": code, "name": code.title(), "kind": "dine_in", **extra}
    res = client.post(f"{API}/channels", json=body, headers=h)
    assert res.status_code == 201, res.text
    return str(res.json()["id"])


def menu_item(client: TestClient, h: dict[str, str], sku: str = "NASI-01") -> str:
    body = item_body(units(client)["pcs"], sku=sku, type="menu", storage_type=None)
    res = client.post(f"{API}/items", json=body, headers=h)
    assert res.status_code == 201, res.text
    return str(res.json()["id"])


def set_price(
    client: TestClient, h: dict[str, str], item: str, ch: str, day: str, price: int
) -> Any:
    body = {"channel_id": ch, "valid_from": day, "price": price}
    return client.put(f"{API}/items/{item}/prices", json=body, headers=h)


def price_on(client: TestClient, ch: str, day: str | None = None) -> dict[str, int]:
    query = f"channel_id={ch}" + (f"&on={day}" if day else "")
    page = client.get(f"{API}/prices?{query}")
    assert page.status_code == 200, page.text
    return {p["item_id"]: p["price"] for p in page.json()["items"]}


def test_fr_cat_004_channels_kinds_and_locked_code(
    client: TestClient, world: dict[str, Any]
) -> None:
    h = signin(client, world["manager_a"])
    dine = channel(client, h)
    grab = channel(client, h, "grabfood", kind="platform", platform="grabfood")
    no_platform = {"code": "gofood", "name": "GoFood", "kind": "platform"}
    assert client.post(f"{API}/channels", json=no_platform, headers=h).status_code == 422
    dup = client.post(
        f"{API}/channels", json={"code": "dine_in", "name": "x", "kind": "dine_in"}, headers=h
    )
    assert dup.status_code == 409 and dup.json()["code"] == "channel_code_taken"
    renamed = client.put(
        f"{API}/channels/{dine}",
        json={"code": "dine_in", "name": "Makan di tempat", "kind": "dine_in"},
        headers=h,
    )
    assert renamed.status_code == 200 and renamed.json()["name"] == "Makan di tempat"
    recoded = client.put(
        f"{API}/channels/{grab}",
        json={"code": "grab", "name": "Grab", "kind": "platform", "platform": "grabfood"},
        headers=h,
    )
    assert recoded.status_code == 409 and recoded.json()["code"] == "channel_code_locked"
    hc = signin(client, world["cashier_a"])
    assert {c["code"] for c in client.get(f"{API}/channels").json()} == {"dine_in", "grabfood"}
    assert client.post(f"{API}/channels", json=no_platform, headers=hc).status_code == 403


def test_fr_cat_004_price_on_a_date_is_the_latest_start(
    client: TestClient, world: dict[str, Any]
) -> None:
    h = signin(client, world["manager_a"])
    ch, item = channel(client, h), menu_item(client, h)
    for day, price in (("2026-01-01", 25_000), ("2026-03-01", 27_000), (FUTURE, 30_000)):
        assert set_price(client, h, item, ch, day, price).status_code == 200
    assert price_on(client, ch, "2025-12-31") == {}  # not on sale before the first price
    assert price_on(client, ch, "2026-02-28") == {item: 25_000}
    assert price_on(client, ch, "2026-03-01") == {item: 27_000}
    assert price_on(client, ch) == {item: 27_000}  # today, in the tenant's time zone
    assert price_on(client, ch, FUTURE) == {item: 30_000}
    # Saving the same start date again corrects that price instead of adding a row.
    assert set_price(client, h, item, ch, "2026-03-01", 27_500).json()["price"] == 27_500
    history = client.get(f"{API}/items/{item}/prices").json()
    assert [(p["valid_from"], p["price"]) for p in history] == [
        (FUTURE, 30_000),
        ("2026-03-01", 27_500),
        ("2026-01-01", 25_000),
    ]


def test_only_prices_not_yet_started_can_be_deleted(
    client: TestClient, world: dict[str, Any]
) -> None:
    h = signin(client, world["manager_a"])
    ch, item = channel(client, h), menu_item(client, h)
    started = set_price(client, h, item, ch, "2026-01-01", 25_000).json()
    planned = set_price(client, h, item, ch, FUTURE, 30_000).json()
    refused = client.delete(f"{API}/prices/{started['id']}", headers=h)
    assert refused.status_code == 409 and refused.json()["code"] == "price_already_started"
    assert client.delete(f"{API}/prices/{planned['id']}", headers=h).status_code == 204
    assert price_on(client, ch, FUTURE) == {item: 25_000}


def test_price_validation_and_inactive_items(client: TestClient, world: dict[str, Any]) -> None:
    h = signin(client, world["manager_a"])
    ch, item = channel(client, h), menu_item(client, h)
    for bad in (-1, 1.5, 10**13, "25000"):
        assert set_price(client, h, item, ch, "2026-01-01", bad).status_code == 422  # type: ignore[arg-type]
    assert set_price(client, h, item, ch, "2026-01-01", 0).status_code == 200  # free item
    body = item_body(units(client)["pcs"], sku="NASI-01", type="menu", storage_type=None)
    archived = client.put(
        f"{API}/items/{item}", json={**body, "version": 1, "is_active": False}, headers=h
    )
    assert archived.status_code == 200
    assert price_on(client, ch, "2026-06-01") == {}  # archived items are not on the price list


def test_tenant_isolation_for_channels_and_prices(
    client: TestClient, world: dict[str, Any]
) -> None:
    h = signin(client, world["manager_a"])
    ch, item = channel(client, h), menu_item(client, h)
    price = set_price(client, h, item, ch, FUTURE, 30_000).json()
    hb = signin(client, world["manager_b"])
    own_ch, own_item = channel(client, hb), menu_item(client, hb)
    assert client.get(f"{API}/channels").json()[0]["id"] == own_ch  # only B's channel
    assert client.get(f"{API}/prices?channel_id={ch}").status_code == 422
    assert client.get(f"{API}/items/{item}/prices").status_code == 404
    # Foreign keys ignore RLS: the service must refuse A's channel and A's item for B.
    stolen = set_price(client, hb, own_item, ch, "2026-01-01", 1)
    assert stolen.status_code == 422 and stolen.json()["code"] == "invalid_reference"
    assert set_price(client, hb, item, own_ch, "2026-01-01", 1).status_code == 404
    assert client.delete(f"{API}/prices/{price['id']}", headers=hb).status_code == 404
    renamed = {"code": "dine_in", "name": "x", "kind": "dine_in"}
    assert client.put(f"{API}/channels/{ch}", json=renamed, headers=hb).status_code == 404


def test_price_list_query_count_does_not_grow_with_items(
    app: FastAPI, client: TestClient, world: dict[str, Any]
) -> None:
    h = signin(client, world["manager_a"])
    ch = channel(client, h)
    for i in range(30):  # enough rows that a per-row query would show up
        item = menu_item(client, h, sku=f"MENU-{i:02d}")
        set_price(client, h, item, ch, "2026-01-01", 10_000 + i)
    count = 0

    def on_execute(*_: object) -> None:
        nonlocal count
        count += 1

    engine = app.state.engine.sync_engine
    event.listen(engine, "before_cursor_execute", on_execute)
    try:
        assert len(price_on(client, ch, "2026-06-01")) == 30
    finally:
        event.remove(engine, "before_cursor_execute", on_execute)
    assert count <= 8
