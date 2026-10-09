"""Slice 1k: manual daily sales (FR-SAL-002, 003) and platform item codes (FR-CAT-010):
recipe consumption that stops at stocked prepared items, promos as discount, replacing an
entry, day lock and reopen, idempotency, cost visibility, outlet scope and isolation."""

import uuid
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.factories import add_member, add_outlet, drop_tenant, seed_tenant
from tests.test_catalog import units
from tests.test_inventory import API, HASH, login, make_item
from tests.test_purchasing import client as client

S = "/api/v1/sales/days"
CAT = "/api/v1/catalog"
DAY = "2026-03-05"


@pytest.fixture
def world() -> Iterator[dict[str, Any]]:
    mods = ("inventory", "sales")
    a, roles = seed_tenant("Alpha", modules=mods)
    b, roles_b = seed_tenant("Beta", modules=mods)
    shop, other = add_outlet(a, "Shop"), add_outlet(a, "Other shop")
    w: dict[str, Any] = {"a": a, "shop": shop, "other": other}
    w["manager_a"] = add_member(a, roles["manager"], HASH)[1]
    w["cashier_a"] = add_member(a, roles["cashier"], HASH, outlets=(shop,))[1]
    w["manager_b"] = add_member(b, roles_b["manager"], HASH)[1]
    yield w
    drop_tenant(a)
    drop_tenant(b)


@pytest.fixture
def menu(client: TestClient, world: dict[str, Any]) -> dict[str, Any]:
    """Nasi goreng = 200 g rice + 1 egg + 30 g sambal. Sambal is made in the kitchen and
    stocked (its own recipe must not be expanded again). GoFood lists it at Rp 25.000,
    platform code NG-01."""
    h = login(client, world["manager_a"])
    u = units(client)
    dry = {"shelf_life_days": None, "storage_type": "dry"}
    k: dict[str, Any] = {
        "rice": make_item(client, h, "RICE", "g", **dry),
        "egg": make_item(client, h, "EGG", "pcs", **dry),
        "chili": make_item(client, h, "CHILI", "g", **dry),
        "sambal": make_item(client, h, "SAMBAL", "g", type="semi_finished", **dry),
        "nasi": make_item(client, h, "NASI", "pcs", type="menu", is_stocked=False, **dry),
    }

    def recipe(item: str, lines: list[tuple[str, str, str]], **extra: Any) -> None:
        body = {
            "lines": [
                {"component_item_id": k[c], "qty": q, "unit_id": u[un], "waste_pct": "0"}
                for c, q, un in lines
            ],
            **extra,
        }
        bom = client.post(f"{CAT}/items/{k[item]}/boms", json=body, headers=h)
        assert bom.status_code == 201, bom.text
        on = client.post(
            f"{CAT}/boms/{bom.json()['id']}/activate", json={"valid_from": "2026-01-01"}, headers=h
        )
        assert on.status_code == 200, on.text

    recipe("sambal", [("chili", "1000", "g")], yield_qty="1000", yield_unit_id=u["g"])
    recipe("nasi", [("rice", "200", "g"), ("egg", "1", "pcs"), ("sambal", "30", "g")])
    opening = [
        {"item_id": k["rice"], "qty": "10", "unit_id": u["kg"], "unit_cost": "14000"},
        {"item_id": k["egg"], "qty": "30", "unit_id": u["pcs"], "unit_cost": "2200"},
        {"item_id": k["sambal"], "qty": "1", "unit_id": u["kg"], "unit_cost": "60000"},
        {"item_id": k["chili"], "qty": "1", "unit_id": u["kg"], "unit_cost": "40000"},
    ]
    body = {"outlet_id": str(world["shop"]), "business_date": "2026-03-01", "lines": opening}
    assert client.post(f"{API}/opening", json=body, headers=h).status_code == 201
    channel = {"code": "gofood", "name": "GoFood", "kind": "platform", "platform": "gofood"}
    ch = client.post(f"{CAT}/channels", json=channel, headers=h)
    assert ch.status_code == 201, ch.text
    k["gofood"] = ch.json()["id"]
    price = {"channel_id": k["gofood"], "valid_from": "2026-01-01", "price": 25_000}
    assert client.put(f"{CAT}/items/{k['nasi']}/prices", json=price, headers=h).status_code == 200
    mapping = {"mappings": [{"platform_code": "NG-01", "item_id": k["nasi"]}]}
    assert (
        client.put(f"{CAT}/channels/{k['gofood']}/mappings", json=mapping, headers=h).status_code
        == 200
    )
    return k


def enter(
    client: TestClient, h: dict[str, str], body: dict[str, Any], key: str | None = None
) -> Any:
    return client.post(
        f"{S}/entries", json=body, headers={**h, "Idempotency-Key": key or str(uuid.uuid4())}
    )


def on_hand(client: TestClient, h: dict[str, str], outlet: Any) -> dict[str, Decimal]:
    rows = client.get(f"{API}/stock?outlet_id={outlet}", headers=h).json()["items"]
    return {r["sku"]: Decimal(r["qty"]) for r in rows}


def entry(world: dict[str, Any], menu: dict[str, Any], qty: str, **extra: Any) -> dict[str, Any]:
    return {
        "outlet_id": str(world["shop"]),
        "business_date": DAY,
        "channel_id": menu["gofood"],
        "lines": [{"platform_code": "NG-01", "qty": qty}],
        **extra,
    }


def test_fr_sal_002_entry_consumes_recipes_and_replaces(
    client: TestClient, world: dict[str, Any], menu: dict[str, Any]
) -> None:
    h = login(client, world["cashier_a"])
    key = str(uuid.uuid4())
    made = enter(client, h, entry(world, menu, "10", reported_total=225_000), key)
    assert made.status_code == 201, made.text
    assert (
        enter(client, h, entry(world, menu, "10", reported_total=225_000), key).json()
        == made.json()
    )
    [doc] = made.json()["documents"]
    assert doc["subtotal"] == 250_000 and doc["discount"] == 25_000  # promo = discount line
    assert doc["total"] == doc["subtotal"] - doc["discount"] + doc["service_charge"] + doc["tax"]
    assert doc["cost"] is None  # cashiers do not see costs
    assert doc["lines"][0]["platform_code"] == "NG-01"
    m = login(client, world["manager_a"])
    stock = on_hand(client, m, world["shop"])
    # Sambal is taken as made; its chili is not taken again.
    assert stock == {"RICE": 8000, "EGG": 20, "SAMBAL": 700, "CHILI": 1000}
    # Saving the channel again replaces the entry: the stock of the first comes back.
    h = login(client, world["cashier_a"])
    again = enter(client, h, entry(world, menu, "8"))
    assert again.status_code == 201 and len(again.json()["documents"]) == 1
    m = login(client, world["manager_a"])
    assert on_hand(client, m, world["shop"])["RICE"] == 8400
    day = client.get(f"{S}/{world['shop']}/{DAY}", headers=m).json()
    assert day["documents"][0]["cost"] == 8 * (200 * 14 + 2200 + 30 * 60)


def test_fr_sal_003_lock_blocks_entries_until_reopened(
    client: TestClient, world: dict[str, Any], menu: dict[str, Any]
) -> None:
    h = login(client, world["cashier_a"])
    assert enter(client, h, entry(world, menu, "1")).status_code == 201
    assert client.post(f"{S}/{world['shop']}/{DAY}/lock", headers=h).status_code == 403
    m = login(client, world["manager_a"])
    locked = client.post(f"{S}/{world['shop']}/{DAY}/lock", headers=m)
    assert locked.status_code == 200 and locked.json()["status"] == "locked"
    h = login(client, world["cashier_a"])
    blocked = enter(client, h, entry(world, menu, "2"))
    assert blocked.status_code == 409 and blocked.json()["code"] == "day_locked"
    m = login(client, world["manager_a"])
    assert client.post(f"{S}/{world['shop']}/{DAY}/reopen", headers=m).json()["status"] == "open"
    h = login(client, world["cashier_a"])
    assert enter(client, h, entry(world, menu, "2")).status_code == 201


def test_sales_entry_errors_scope_and_isolation(
    client: TestClient, world: dict[str, Any], menu: dict[str, Any]
) -> None:
    h = login(client, world["cashier_a"])
    body = entry(world, menu, "1")
    body["lines"] = [{"platform_code": "XX-99", "qty": "1"}]
    unknown = enter(client, h, body)
    assert unknown.status_code == 404 and unknown.json()["code"] == "unknown_platform_code"
    above = enter(client, h, entry(world, menu, "1", reported_total=30_000))
    assert above.status_code == 409 and above.json()["code"] == "reported_above_list"
    elsewhere = entry(world, menu, "1")
    elsewhere["outlet_id"] = str(world["other"])
    assert enter(client, h, elsewhere).status_code == 404  # not this cashier's outlet
    other = login(client, world["manager_b"])
    assert client.get(f"{S}/{world['shop']}/{DAY}", headers=other).status_code == 404
