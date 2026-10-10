"""FR-INV-016: lot traceability. Chili is cooked into sambal at the central kitchen, and the
sambal is sent to the shop: tracing works both ways and respects outlet scope."""

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.factories import add_member, add_outlet, drop_tenant, seed_tenant
from tests.test_inventory import API, HASH, login
from tests.test_production import PRD, plan
from tests.test_production import client as client
from tests.test_production import sambal as sambal


@pytest.fixture
def world() -> Iterator[dict[str, Any]]:
    a, roles = seed_tenant("Alpha", modules=("inventory", "production", "transfers"))
    b, roles_b = seed_tenant("Beta", modules=("inventory",))
    shop, kitchen = add_outlet(a, "Shop"), add_outlet(a, "Central kitchen")
    w: dict[str, Any] = {"a": a, "shop": shop, "kitchen": kitchen}
    w["manager_a"] = add_member(a, roles["manager"], HASH)[1]
    w["store_shop"] = add_member(a, roles["warehouse"], HASH, outlets=(shop,))[1]
    w["manager_b"] = add_member(b, roles_b["manager"], HASH)[1]
    yield w
    drop_tenant(a)
    drop_tenant(b)


def batch_of(client: TestClient, h: dict[str, str], outlet: Any, item: str) -> str:
    rows = client.get(f"{API}/stock/{item}/batches?outlet_id={outlet}", headers=h).json()
    return str(rows[0]["id"])


def cook_and_send(client: TestClient, w: dict[str, Any], k: dict[str, Any]) -> None:
    m = login(client, w["manager_a"])
    order = plan(client, m, w["kitchen"], k["sambal"], "500").json()
    done = client.post(f"{PRD}/{order['id']}/complete", json={"actual_qty": "500"}, headers=m)
    assert done.status_code == 200, done.text
    body = {
        "from_outlet_id": str(w["kitchen"]),
        "to_outlet_id": str(w["shop"]),
        "lines": [{"item_id": k["sambal"], "qty": "300"}],
    }
    t = client.post(
        "/api/v1/transfers", json=body, headers={**m, "Idempotency-Key": str(uuid.uuid4())}
    ).json()
    day = {"business_date": "2026-03-02"}
    for step, payload in (("approve", {}), ("ship", day), ("receive", {**day, "lines": []})):
        res = client.post(f"/api/v1/transfers/{t['id']}/{step}", json=payload, headers=m)
        assert res.status_code == 200, (step, res.text)


def test_fr_inv_016_trace_forward_and_back(
    client: TestClient, world: dict[str, Any], sambal: dict[str, Any]
) -> None:
    cook_and_send(client, world, sambal)
    m = login(client, world["manager_a"])
    chili = batch_of(client, m, world["kitchen"], sambal["chili"])
    down = client.get(f"{API}/batches/{chili}/trace", headers=m).json()
    assert [(d["sku"], d["depth"]) for d in down["descendants"]] == [("SAMBAL", 1), ("SAMBAL", 2)]
    assert {d["outlet_id"] for d in down["descendants"]} == {
        str(world["kitchen"]),
        str(world["shop"]),
    }
    assert down["sources"] == [] and down["uses"][0]["made"]

    at_shop = batch_of(client, m, world["shop"], sambal["sambal"])
    up = client.get(f"{API}/batches/{at_shop}/trace", headers=m).json()
    assert (up["sources"][0]["sku"], up["sources"][0]["depth"]) == ("SAMBAL", 1)
    assert {s["sku"] for s in up["sources"] if s["depth"] == 2} == {"CHILI", "OIL"}

    # A shop storekeeper sees only the shop: the kitchen batches are counted, not shown.
    shop = login(client, world["store_shop"])
    mine = client.get(f"{API}/batches/{at_shop}/trace", headers=shop).json()
    assert mine["sources"] == [] and mine["hidden"] == 3
    assert client.get(f"{API}/batches/{chili}/trace", headers=shop).status_code == 404
    # Another tenant cannot see the batch at all.
    other = login(client, world["manager_b"])
    assert client.get(f"{API}/batches/{chili}/trace", headers=other).status_code == 404


def test_fr_inv_016_find_by_lot_code(
    client: TestClient, world: dict[str, Any], sambal: dict[str, Any]
) -> None:
    cook_and_send(client, world, sambal)
    m = login(client, world["manager_a"])
    lot = client.get(f"{PRD}?outlet_id={world['kitchen']}", headers=m).json()
    code = (lot["items"] if isinstance(lot, dict) else lot)[0]["lot_code"] or ""
    found = client.get(f"{API}/lots?lot={code[:4]}", headers=m).json()
    assert {f["sku"] for f in found} == {"SAMBAL"} and len(found) == 2  # kitchen and shop
    assert client.get(f"{API}/lots?lot=%25", headers=m).json() == []  # % is literal
