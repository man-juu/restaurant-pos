"""Slice 1h: transfers (FR-TRF-001 to 004): request, approve with changed quantities, ship
by FEFO, delivery note, receive with damage (adjustment), cost and expiry carried over,
outlet scope, permissions and tenant isolation."""

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

T = "/api/v1/transfers"


@pytest.fixture
def world() -> Iterator[dict[str, Any]]:
    mods = ("inventory", "transfers")
    a, roles_a = seed_tenant("Alpha", modules=mods)
    b, roles_b = seed_tenant("Beta", modules=mods)
    shop, kitchen = add_outlet(a, "Shop"), add_outlet(a, "Central kitchen")
    w: dict[str, Any] = {"a": a, "shop": shop, "kitchen": kitchen}
    w["manager_a"] = add_member(a, roles_a["manager"], HASH)[1]
    w["store_kitchen"] = add_member(a, roles_a["warehouse"], HASH, outlets=(kitchen,))[1]
    w["store_shop"] = add_member(a, roles_a["warehouse"], HASH, outlets=(shop,))[1]
    w["cashier_a"] = add_member(a, roles_a["cashier"], HASH)[1]
    w["manager_b"] = add_member(b, roles_b["manager"], HASH)[1]
    yield w
    drop_tenant(a)
    drop_tenant(b)


@pytest.fixture
def items(client: TestClient, world: dict[str, Any]) -> dict[str, str]:
    """The central kitchen holds 5 kg beef (Rp 120 per g, expires 1 April) and 20 kg rice."""
    h = login(client, world["manager_a"])
    it = {
        "beef": make_item(client, h, "BEEF", "g"),
        "rice": make_item(client, h, "RICE", "g", shelf_life_days=None, storage_type="dry"),
    }
    kg = units(client)["kg"]
    lines = [
        {
            "item_id": it["beef"],
            "qty": "5",
            "unit_id": kg,
            "unit_cost": "120000",
            "expiry_date": "2026-04-01",
            "lot_code": "B1",
        },
        {"item_id": it["rice"], "qty": "20", "unit_id": kg, "unit_cost": "14000"},
    ]
    body = {"outlet_id": str(world["kitchen"]), "business_date": "2026-03-01", "lines": lines}
    assert client.post(f"{API}/opening", json=body, headers=h).status_code == 201
    return it


def ask(
    client: TestClient,
    h: dict[str, str],
    world: dict[str, Any],
    lines: list[Any],
    key: str | None = None,
) -> Any:
    body = {
        "from_outlet_id": str(world["kitchen"]),
        "to_outlet_id": str(world["shop"]),
        "lines": lines,
    }
    return client.post(T, json=body, headers={**h, "Idempotency-Key": key or str(uuid.uuid4())})


def _items(page: Any) -> list[dict[str, Any]]:
    return list(page["items"] if isinstance(page, dict) else page)


def stock(client: TestClient, h: dict[str, str], outlet: Any) -> dict[str, dict[str, Any]]:
    return {
        r["sku"]: r
        for r in client.get(f"{API}/stock?outlet_id={outlet}", headers=h).json()["items"]
    }


def test_fr_trf_001_to_004_request_approve_ship_receive_with_damage(
    client: TestClient, world: dict[str, Any], items: dict[str, str]
) -> None:
    shop = login(client, world["store_shop"])
    key = str(uuid.uuid4())
    lines = [{"item_id": items["beef"], "qty": "3000"}, {"item_id": items["rice"], "qty": "5000"}]
    made = ask(client, shop, world, lines, key)
    assert made.status_code == 201, made.text
    t = made.json()
    assert ask(client, shop, world, lines, key).json() == t  # retry: same transfer
    assert t["status"] == "requested" and t["number"].startswith("TRF-")
    # The shop cannot approve its own request: it has no access to the source outlet.
    assert client.post(f"{T}/{t['id']}/approve", json={}, headers=shop).status_code == 404

    kitchen = login(client, world["store_kitchen"])
    # The central kitchen is told of the request; the shop hears back when it is handled.
    told = client.get("/api/v1/notifications", headers=kitchen).json()
    assert any(n["kind"] == "transfer_requested" for n in _items(told))
    body = {"lines": [{"item_id": items["rice"], "qty": "4000"}]}
    ok = client.post(f"{T}/{t['id']}/approve", json=body, headers=kitchen)
    assert ok.status_code == 200 and ok.json()["status"] == "approved"
    sent = client.post(f"{T}/{t['id']}/ship", json={"business_date": "2026-03-02"}, headers=kitchen)
    assert sent.status_code == 200, sent.text
    assert sent.json()["shipped_value"] == 3000 * 120 + 4000 * 14
    have = stock(client, kitchen, world["kitchen"])
    assert Decimal(have["BEEF"]["qty"]) == 2000 and Decimal(have["RICE"]["qty"]) == 16000
    note = client.get(f"{T}/{t['id']}/delivery-note?lang=id", headers=shop)
    assert note.status_code == 200 and note.content.startswith(b"%PDF")

    shop = login(client, world["store_shop"])
    back = _items(client.get("/api/v1/notifications", headers=shop).json())
    assert {n["params"]["action"] for n in back if n["kind"] == "transfer_updated"} == {
        "approve",
        "ship",
    }
    kitchen = login(client, world["store_kitchen"])
    # FR-TRF-003: 200 g of beef arrived damaged; a reason is required.
    shop = login(client, world["store_shop"])  # one session per client: sign in again
    beef: dict[str, str] = {"item_id": items["beef"], "qty": "2800"}
    damaged: dict[str, Any] = {"business_date": "2026-03-02", "lines": [beef]}
    missing = client.post(f"{T}/{t['id']}/receive", json=damaged, headers=shop)
    assert missing.status_code == 409 and missing.json()["code"] == "reason_required"
    beef["reason"] = "damaged"
    got = client.post(f"{T}/{t['id']}/receive", json=damaged, headers=shop)
    assert got.status_code == 200, got.text
    assert got.json()["status"] == "received" and got.json()["adjustment_id"]
    # No approval rule in this tenant: the loss adjustment posted at once.
    m = login(client, world["manager_a"])
    here = stock(client, m, world["shop"])
    assert Decimal(here["BEEF"]["qty"]) == 2800 and Decimal(here["RICE"]["qty"]) == 4000
    assert Decimal(here["BEEF"]["avg_cost"]) == 120  # FR-TRF-004: source cost carried over
    batches = client.get(
        f"{API}/stock/{items['beef']}/batches?outlet_id={world['shop']}", headers=m
    ).json()
    assert {b["expiry_date"] for b in batches} == {"2026-04-01"}  # same batch, same expiry


def test_transfer_cancel_and_status_guards(
    client: TestClient, world: dict[str, Any], items: dict[str, str]
) -> None:
    m = login(client, world["manager_a"])
    t = ask(client, m, world, [{"item_id": items["rice"], "qty": "1000"}]).json()
    early = client.post(f"{T}/{t['id']}/ship", json={"business_date": "2026-03-02"}, headers=m)
    assert early.status_code == 409
    gone = client.post(f"{T}/{t['id']}/cancel", headers=m)
    assert gone.json()["status"] == "cancelled"
    same = {
        "from_outlet_id": str(world["shop"]),
        "to_outlet_id": str(world["shop"]),
        "lines": [{"item_id": items["rice"], "qty": "1"}],
    }
    bad = client.post(T, json=same, headers={**m, "Idempotency-Key": str(uuid.uuid4())})
    assert bad.status_code == 409 and bad.json()["code"] == "same_outlet"


def test_transfer_permissions_and_isolation(
    client: TestClient, world: dict[str, Any], items: dict[str, str]
) -> None:
    m = login(client, world["manager_a"])
    t = ask(client, m, world, [{"item_id": items["rice"], "qty": "1000"}]).json()
    cashier = login(client, world["cashier_a"])
    assert client.get(f"{T}?outlet_id={world['shop']}", headers=cashier).status_code == 403
    other = login(client, world["manager_b"])
    assert client.get(f"{T}/{t['id']}", headers=other).status_code == 404
    kitchen = login(client, world["store_kitchen"])
    # The source may read but not receive (receiving belongs to the destination outlet).
    assert client.get(f"{T}/{t['id']}", headers=kitchen).status_code == 200
    rec = client.post(
        f"{T}/{t['id']}/receive", json={"business_date": "2026-03-02"}, headers=kitchen
    )
    assert rec.status_code == 404


def test_docs05_ledger_invariants_hold_and_catch_a_broken_balance(
    client: TestClient, world: dict[str, Any], items: dict[str, str], settings: Any
) -> None:
    import asyncio

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.admin.alerts_job import run_invariants
    from tests.test_purchasing import tenant_sql

    shop, kitchen = login(client, world["store_shop"]), None
    t = ask(client, shop, world, [{"item_id": items["rice"], "qty": "1000"}]).json()
    kitchen = login(client, world["store_kitchen"])
    client.post(f"{T}/{t['id']}/approve", json={}, headers=kitchen)
    client.post(f"{T}/{t['id']}/ship", json={"business_date": "2026-03-02"}, headers=kitchen)
    shop = login(client, world["store_shop"])
    client.post(f"{T}/{t['id']}/receive", json={"business_date": "2026-03-02"}, headers=shop)

    def check() -> Any:
        async def go() -> Any:
            engine = create_async_engine(str(settings.database_url))
            try:
                return await run_invariants([world["a"]], async_sessionmaker(engine))
            finally:
                await engine.dispose()

        return asyncio.run(go())

    assert check() == {}
    # Corrupt one cached balance (only possible with the owner role): I-1 must notice.
    tenant_sql(
        world["a"],
        "UPDATE stock_balances SET qty = qty + 1 WHERE item_id = :i",
        {"i": items["rice"]},
    )
    assert "I-1 balances = movements" in check()[world["a"]]
