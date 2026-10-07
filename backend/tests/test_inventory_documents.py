"""Slice 1i: waste logs, adjustments and stock counts (FR-INV-007 to 009, FR-TEN-007,
docs/03 rules 1 and 7)."""

import asyncio
import uuid
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import Settings
from app.core.identity.passwords import _hasher
from app.main import create_app
from tests.conftest import TEST_OWNER_URL
from tests.factories import add_member, add_outlet, drop_tenant, seed_tenant
from tests.test_auth import new_client
from tests.test_catalog import item_body, units

PW = "stock documents passphrase"
HASH = _hasher.hash(PW)
INV = "/api/v1/inventory"


def owner_sql(sql: str, params: dict[str, Any]) -> None:
    async def go() -> None:
        engine = create_async_engine(TEST_OWNER_URL)
        async with engine.begin() as conn:
            await conn.execute(text(sql), params)
        await engine.dispose()

    asyncio.run(go())


@pytest.fixture
def world() -> Iterator[dict[str, Any]]:
    a, roles = seed_tenant("Alpha", modules=("inventory",))
    b, roles_b = seed_tenant("Beta", modules=("inventory",))
    shop = add_outlet(a, "Shop")
    w: dict[str, Any] = {"a": a, "shop": shop, "roles": roles}
    for name, role, outlets in (
        ("manager", "manager", None),
        ("manager2", "manager", None),
        ("cook", "kitchen", (shop,)),
        ("cashier", "cashier", None),
    ):
        w[name] = add_member(a, roles[role], HASH, outlets=outlets)[1]
    w["manager_b"] = add_member(b, roles_b["manager"], HASH)[1]
    yield w
    drop_tenant(a)
    drop_tenant(b)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with new_client(create_app(settings)) as c:
        yield c


def login(client: TestClient, email: str) -> dict[str, str]:
    client.cookies.clear()
    body = client.post("/api/v1/auth/login", json={"email": email, "password": PW}).json()
    return {"X-CSRF-Token": body["csrf_token"]}


@pytest.fixture
def stock(client: TestClient, world: dict[str, Any]) -> dict[str, Any]:
    """2.5 kg of rice at Rp 120 per g at the shop."""
    h = login(client, world["manager"])
    u = units(client)
    body = item_body(u["g"], sku="RICE", shelf_life_days=None, storage_type="dry")
    rice = client.post("/api/v1/catalog/items", json=body, headers=h).json()["id"]
    line = {"item_id": rice, "qty": "2.5", "unit_id": u["kg"], "unit_cost": "120000"}
    opening = {"outlet_id": str(world["shop"]), "business_date": "2026-01-01", "lines": [line]}
    assert client.post(f"{INV}/opening", json=opening, headers=h).status_code == 201
    return {"rice": rice, "g": u["g"], "kg": u["kg"]}


def on_hand(client: TestClient, world: dict[str, Any]) -> Decimal:
    rows = client.get(f"{INV}/stock?outlet_id={world['shop']}").json()["items"]
    return Decimal(rows[0]["qty"]) if rows else Decimal(0)


def doc(world: dict[str, Any], stock: dict[str, Any], qty: str, **extra: Any) -> dict[str, Any]:
    line = {"item_id": stock["rice"], "qty": qty, "unit_id": stock["g"]}
    return {
        "outlet_id": str(world["shop"]),
        "business_date": "2026-02-01",
        "lines": [line],
        **extra,
    }


def test_fr_inv_008_waste_posts_at_once_and_can_be_reversed(
    client: TestClient, world: dict[str, Any], stock: dict[str, Any]
) -> None:
    hc = login(client, world["cook"])  # kitchen staff log waste (docs/03)
    res = client.post(
        f"{INV}/waste", json=doc(world, stock, "500", reason_code="spoilage"), headers=hc
    )
    assert res.status_code == 201, res.text
    waste = res.json()
    assert waste["status"] == "posted" and waste["number"].startswith("WASTE-2026-")
    assert on_hand(client, world) == Decimal(2000)
    too_much = client.post(
        f"{INV}/waste", json=doc(world, stock, "9000", reason_code="damaged"), headers=hc
    )
    assert too_much.status_code == 409  # policy "other": never below zero
    assert client.post(f"{INV}/waste/{waste['id']}/reverse", headers=hc).status_code == 403
    hm = login(client, world["manager"])
    assert (
        client.post(f"{INV}/waste/{waste['id']}/reverse", headers=hm).json()["status"] == "reversed"
    )
    assert on_hand(client, world) == Decimal(2500)
    listed = client.get(f"{INV}/documents/waste?outlet_id={world['shop']}").json()
    assert [d["number"] for d in listed] == [waste["number"]]


def test_fr_inv_009_adjustment_without_rule_posts_on_submit(
    client: TestClient, world: dict[str, Any], stock: dict[str, Any]
) -> None:
    h = login(client, world["manager"])
    draft = client.post(
        f"{INV}/adjustments", json=doc(world, stock, "-300", reason_code="theft"), headers=h
    ).json()
    assert draft["status"] == "draft" and on_hand(client, world) == Decimal(2500)
    posted = client.post(f"{INV}/adjustments/{draft['id']}/submit", headers=h).json()
    assert posted["status"] == "posted" and on_hand(client, world) == Decimal(2200)
    again = client.post(f"{INV}/adjustments/{draft['id']}/submit", headers=h)
    assert again.status_code == 409 and again.json()["code"] == "wrong_status"


def test_fr_ten_007_adjustment_rule_needs_another_approver(
    client: TestClient, world: dict[str, Any], stock: dict[str, Any]
) -> None:
    owner_sql(
        "INSERT INTO approval_rules (id, tenant_id, document_type, min_amount, approver_role_id) "
        "VALUES (:i, :t, 'adjustment', 10000, :r)",
        {"i": uuid.uuid4(), "t": world["a"], "r": world["roles"]["manager"]},
    )
    h = login(client, world["manager"])
    small = client.post(
        f"{INV}/adjustments", json=doc(world, stock, "50", reason_code="found"), headers=h
    ).json()  # 50 g x Rp 120 = Rp 6.000, below the rule
    assert (
        client.post(f"{INV}/adjustments/{small['id']}/submit", headers=h).json()["status"]
        == "posted"
    )
    big = client.post(
        f"{INV}/adjustments", json=doc(world, stock, "-200", reason_code="damaged"), headers=h
    ).json()  # Rp 24.000: needs a manager
    assert (
        client.post(f"{INV}/adjustments/{big['id']}/submit", headers=h).json()["status"]
        == "submitted"
    )
    assert on_hand(client, world) == Decimal(2550)
    own = client.post(f"{INV}/adjustments/{big['id']}/approve", headers=h)
    assert own.status_code == 403 and own.json()["code"] == "cannot_approve_own_request"
    h2 = login(client, world["manager2"])
    assert client.post(f"{INV}/adjustments/{big['id']}/maybe", headers=h2).status_code == 422
    done = client.post(f"{INV}/adjustments/{big['id']}/approve", headers=h2).json()
    assert done["status"] == "posted" and on_hand(client, world) == Decimal(2350)


def test_fr_inv_007_blind_count_posts_the_difference(
    client: TestClient, world: dict[str, Any], stock: dict[str, Any]
) -> None:
    hc = login(client, world["cook"])
    body = {
        "outlet_id": str(world["shop"]),
        "business_date": "2026-02-01",
        "count_type": "full",
        "blind": True,
    }
    count = client.post(f"{INV}/counts", json=body, headers=hc).json()
    [line] = count["lines"]
    assert line["item_id"] == stock["rice"] and line["system_qty"] is None  # blind
    early = client.post(f"{INV}/counts/{count['id']}/submit", headers=hc)
    assert early.status_code == 422 and early.json()["code"] == "count_incomplete"
    counted = {"lines": [{"item_id": stock["rice"], "counted_qty": "2400"}]}
    assert (
        client.put(f"{INV}/counts/{count['id']}/lines", json=counted, headers=hc).status_code == 200
    )
    posted = client.post(f"{INV}/counts/{count['id']}/submit", headers=hc).json()
    assert posted["status"] == "posted" and Decimal(posted["lines"][0]["system_qty"]) == 2500
    assert on_hand(client, world) == Decimal(2400)
    history = client.get(f"{INV}/movements?outlet_id={world['shop']}").json()["items"]
    assert history[0]["movement_type"] == "count_correction" and Decimal(history[0]["qty"]) == -100


def test_documents_respect_permissions_and_tenants(
    client: TestClient, world: dict[str, Any], stock: dict[str, Any]
) -> None:
    h = login(client, world["manager"])
    adj = client.post(
        f"{INV}/adjustments", json=doc(world, stock, "10", reason_code="found"), headers=h
    ).json()
    hk = login(client, world["cashier"])
    assert (
        client.post(
            f"{INV}/waste", json=doc(world, stock, "1", reason_code="other"), headers=hk
        ).status_code
        == 403
    )
    hb = login(client, world["manager_b"])
    assert client.get(f"{INV}/documents/adjustments/{adj['id']}").status_code == 404
    assert client.post(f"{INV}/adjustments/{adj['id']}/submit", headers=hb).status_code == 404
    stolen = doc(world, stock, "1", reason_code="other")  # A's outlet and item
    assert client.post(f"{INV}/waste", json=stolen, headers=hb).status_code == 404
