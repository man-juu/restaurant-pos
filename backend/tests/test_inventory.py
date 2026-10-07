"""Slice 1e: inventory ledger (FR-INV-001 to 006, FR-INV-014, FR-X-005, docs/05 section 3).

Engine tests post directly through the service (as purchasing, production and sales will);
API tests cover opening balances, scope, permissions and isolation. After every scenario the
ledger invariants are checked: balances equal the sum of movements (I-1) and the average
cost is never negative (I-2).
"""

import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.identity.passwords import _hasher
from app.core.tenancy import tenant_session
from app.main import create_app
from app.modules.inventory import policy
from app.modules.inventory.service import (
    InLine,
    InsufficientStock,
    OutLine,
    Posting,
    StockError,
    consume,
    receive,
    reverse,
)
from tests.factories import add_member, add_outlet, drop_tenant, seed_tenant
from tests.test_auth import new_client
from tests.test_catalog import item_body, units

PW = "inventory test passphrase"
HASH = _hasher.hash(PW)
API = "/api/v1/inventory"
DAY = date(2026, 3, 1)


@pytest.fixture
def world() -> Iterator[dict[str, Any]]:
    a, roles_a = seed_tenant("Alpha", modules=("inventory",))
    b, roles_b = seed_tenant("Beta", modules=("inventory",))
    shop, kitchen = add_outlet(a, "Shop"), add_outlet(a, "Central kitchen")
    w: dict[str, Any] = {"a": a, "b": b, "shop": shop, "kitchen": kitchen}
    w["manager_a"] = add_member(a, roles_a["manager"], HASH)[1]
    w["cashier_a"] = add_member(a, roles_a["cashier"], HASH)[1]
    w["store_a"] = add_member(a, roles_a["warehouse"], HASH, outlets=(kitchen,))[1]
    w["manager_b"] = add_member(b, roles_b["manager"], HASH)[1]
    w["outlet_b"] = add_outlet(b, "Beta shop")
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


def make_item(client: TestClient, h: dict[str, str], sku: str, unit: str, **extra: Any) -> str:
    body = item_body(units(client)[unit], sku=sku, **extra)
    res = client.post("/api/v1/catalog/items", json=body, headers=h)
    assert res.status_code == 201, res.text
    return str(res.json()["id"])


@pytest.fixture
def items(client: TestClient, world: dict[str, Any]) -> dict[str, str]:
    h = login(client, world["manager_a"])
    return {
        "beef": make_item(client, h, "BEEF", "g"),  # perishable: 90 days shelf life
        "rice": make_item(client, h, "RICE", "g", shelf_life_days=None, storage_type="dry"),
    }


@pytest.fixture
async def db(engine: AsyncEngine, world: dict[str, Any]) -> AsyncIterator[AsyncSession]:
    """A tenant session that is rolled back: engine scenarios leave nothing behind."""
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with tenant_session(maker, world["a"]) as session:
        yield session
        await session.rollback()


def posting(world: dict[str, Any], doc_type: str = "test", day: date = DAY) -> Posting:
    return Posting(world["a"], world["shop"], None, doc_type, uuid.uuid4(), day)


async def on_hand(db: AsyncSession, outlet: uuid.UUID, item: str) -> Decimal:
    q = "SELECT COALESCE(SUM(qty), 0) FROM stock_balances WHERE outlet_id = :o AND item_id = :i"
    return Decimal(await db.scalar(text(q), {"o": outlet, "i": item}))


async def avg_cost(db: AsyncSession, outlet: uuid.UUID, item: str) -> Decimal:
    q = "SELECT avg_cost FROM item_costs WHERE outlet_id = :o AND item_id = :i"
    return Decimal(await db.scalar(text(q), {"o": outlet, "i": item}))


async def assert_invariants(db: AsyncSession) -> None:
    drift = await db.scalar(
        text(
            "SELECT count(*) FROM (SELECT outlet_id, item_id, batch_id, SUM(qty) q "
            "FROM stock_movements GROUP BY 1, 2, 3) m FULL JOIN stock_balances b "
            "ON b.outlet_id = m.outlet_id AND b.item_id = m.item_id "
            "AND b.batch_id IS NOT DISTINCT FROM m.batch_id "
            "WHERE COALESCE(m.q, 0) <> COALESCE(b.qty, 0)"
        )
    )
    assert drift == 0, "I-1: balances must equal the sum of movements"
    assert await db.scalar(text("SELECT count(*) FROM item_costs WHERE avg_cost < 0")) == 0


def beef_in(item: str, qty: str, cost: str, expiry: date) -> InLine:
    return InLine(uuid.UUID(item), Decimal(qty), Decimal(cost), lot_code="L", expiry_date=expiry)


@pytest.mark.anyio
async def test_fr_inv_005_moving_average_and_fefo(
    db: AsyncSession, world: dict[str, Any], items: dict[str, str]
) -> None:
    beef = items["beef"]
    late, early = date(2026, 6, 1), date(2026, 4, 1)
    await receive(db, posting(world), "purchase_receipt", [beef_in(beef, "1000", "100", late)])
    await receive(db, posting(world), "purchase_receipt", [beef_in(beef, "1000", "130", early)])
    assert await avg_cost(db, world["shop"], beef) == Decimal(115)  # (1000*100+1000*130)/2000
    used = await consume(
        db,
        posting(world),
        "sale_consumption",
        [OutLine(uuid.UUID(beef), Decimal(1500))],
        allow_negative=False,
    )
    # FEFO: the batch expiring first (April) goes first, then 500 from June.
    picked = [(m.qty, m.batch_id) for m in used.movements]
    assert [q for q, _ in picked] == [Decimal(-1000), Decimal(-500)]
    assert all(m.unit_cost == Decimal(115) for m in used.movements)  # valued at average
    assert sum(m.value for m in used.movements) == -172_500
    assert await avg_cost(db, world["shop"], beef) == Decimal(115)  # consumption keeps it
    await assert_invariants(db)


@pytest.mark.anyio
async def test_fr_inv_003_006_expiry_and_negative_stock(
    db: AsyncSession, world: dict[str, Any], items: dict[str, str]
) -> None:
    beef, rice = uuid.UUID(items["beef"]), uuid.UUID(items["rice"])
    with pytest.raises(StockError, match="expiry_required"):
        await receive(
            db, posting(world), "purchase_receipt", [InLine(beef, Decimal(1), Decimal(1))]
        )
    await receive(db, posting(world), "purchase_receipt", [InLine(rice, Decimal(100), Decimal(12))])
    with pytest.raises(InsufficientStock):
        await consume(
            db, posting(world), "waste", [OutLine(rice, Decimal(150))], allow_negative=False
        )
    sold = await consume(
        db, posting(world), "sale_consumption", [OutLine(rice, Decimal(150))], allow_negative=True
    )
    assert sold.short == {rice: Decimal(50)}
    assert await on_hand(db, world["shop"], str(rice)) == Decimal(-50)
    # Nothing on hand: the next receipt sets the average to its own cost (ledger rule 5).
    await receive(db, posting(world), "purchase_receipt", [InLine(rice, Decimal(100), Decimal(20))])
    assert await avg_cost(db, world["shop"], str(rice)) == Decimal(20)
    # Default policy: sales may go negative, production must confirm, waste never.
    tenant = world["a"]
    assert await policy.negative_allowed(db, tenant, "sale", confirmed=False)
    assert not await policy.negative_allowed(db, tenant, "production", confirmed=False)
    assert await policy.negative_allowed(db, tenant, "production", confirmed=True)
    assert not await policy.negative_allowed(db, tenant, "other", confirmed=True)
    await assert_invariants(db)


@pytest.mark.anyio
async def test_fr_x_005_reversal_restores_stock_value_and_average(
    db: AsyncSession, world: dict[str, Any], items: dict[str, str]
) -> None:
    rice = uuid.UUID(items["rice"])
    first, second = posting(world, "receipt"), posting(world, "receipt")
    await receive(db, first, "purchase_receipt", [InLine(rice, Decimal(100), Decimal(10))])
    await receive(db, second, "purchase_receipt", [InLine(rice, Decimal(100), Decimal(30))])
    assert await avg_cost(db, world["shop"], str(rice)) == Decimal(20)
    undo = await reverse(db, posting(world), "receipt", second.doc_id)
    assert [m.qty for m in undo] == [Decimal(-100)] and undo[0].reverses_id is not None
    assert await avg_cost(db, world["shop"], str(rice)) == Decimal(10)
    assert await on_hand(db, world["shop"], str(rice)) == Decimal(100)
    with pytest.raises(Exception, match="nothing_to_reverse"):
        await reverse(db, posting(world), "receipt", second.doc_id)
    sale = posting(world, "sale")
    await consume(db, sale, "sale_consumption", [OutLine(rice, Decimal(80))], allow_negative=False)
    with pytest.raises(Exception, match="batch_already_used"):
        await reverse(db, posting(world), "receipt", first.doc_id)
    await reverse(db, posting(world), "sale", sale.doc_id)  # a void puts stock back
    assert await on_hand(db, world["shop"], str(rice)) == Decimal(100)
    await assert_invariants(db)


@pytest.mark.anyio
async def test_ledger_is_append_only_for_the_app_role(
    db: AsyncSession, world: dict[str, Any], items: dict[str, str]
) -> None:
    rice = uuid.UUID(items["rice"])
    await receive(db, posting(world), "purchase_receipt", [InLine(rice, Decimal(5), Decimal(1))])
    with pytest.raises(DBAPIError):
        await db.execute(text("UPDATE stock_movements SET qty = 1"))


def opening(outlet: uuid.UUID, item: str, unit: str, **extra: Any) -> dict[str, Any]:
    line = {"item_id": item, "qty": "2.5", "unit_id": unit, "unit_cost": "120000", **extra}
    return {"outlet_id": str(outlet), "business_date": "2026-01-01", "lines": [line]}


def test_opening_balance_api_with_units_cost_and_reversal(
    client: TestClient, world: dict[str, Any], items: dict[str, str]
) -> None:
    h = login(client, world["manager_a"])
    kg = units(client)["kg"]
    missing = client.post(
        f"{API}/opening", json=opening(world["shop"], items["beef"], kg), headers=h
    )
    assert missing.status_code == 422 and missing.json()["code"] == "expiry_required"
    body = opening(world["shop"], items["beef"], kg, expiry_date="2026-02-01", lot_code="A1")
    posted = client.post(f"{API}/opening", json=body, headers=h)
    assert posted.status_code == 201, posted.text
    [row] = client.get(f"{API}/stock?outlet_id={world['shop']}").json()["items"]
    # 2.5 kg = 2500 g at Rp 120.000 per kg = Rp 120 per g.
    assert Decimal(row["qty"]) == Decimal(2500) and Decimal(row["avg_cost"]) == Decimal(120)
    assert row["value"] == 300_000
    [batch] = client.get(f"{API}/stock/{items['beef']}/batches?outlet_id={world['shop']}").json()
    assert batch["lot_code"] == "A1" and batch["expiry_date"] == "2026-02-01"
    again = client.post(f"{API}/opening", json=body, headers=h)
    assert again.status_code == 409 and again.json()["code"] == "opening_after_movements"
    valued = client.get(f"{API}/valuation?outlet_id={world['shop']}&on=2026-01-01").json()
    assert [v["value"] for v in valued["items"]] == [300_000]
    doc = posted.json()["doc_id"]
    assert client.post(f"{API}/opening/{doc}/reverse", headers=h).status_code == 200
    assert client.get(f"{API}/stock?outlet_id={world['shop']}").json()["items"] == []
    history = client.get(f"{API}/movements?outlet_id={world['shop']}").json()["items"]
    assert [Decimal(m["qty"]) for m in history] == [-2500, 2500]  # newest first, kept forever
    # The past is reproducible: on 1 January the stock was still there (FR-INV-014).
    assert client.get(f"{API}/valuation?outlet_id={world['shop']}&on=2026-01-01").json()["items"]


def test_scope_permissions_and_tenant_isolation(
    client: TestClient, world: dict[str, Any], items: dict[str, str]
) -> None:
    h = login(client, world["manager_a"])
    g = units(client)["g"]
    body = opening(world["kitchen"], items["rice"], g)
    assert client.post(f"{API}/opening", json=body, headers=h).status_code == 201
    hs = login(client, world["store_a"])  # storekeeper of the central kitchen only
    assert client.get(f"{API}/stock?outlet_id={world['kitchen']}").status_code == 200
    assert client.get(f"{API}/stock?outlet_id={world['shop']}").status_code == 404
    shop_body = opening(world["shop"], items["rice"], g)
    assert client.post(f"{API}/opening", json=shop_body, headers=hs).status_code == 404
    login(client, world["cashier_a"])  # no stock permission (docs/03)
    assert client.get(f"{API}/stock?outlet_id={world['kitchen']}").status_code == 403
    hb = login(client, world["manager_b"])
    assert client.get(f"{API}/stock?outlet_id={world['kitchen']}").json()["items"] == []
    stolen = opening(world["outlet_b"], items["rice"], g)  # A's item into B's outlet
    res = client.post(f"{API}/opening", json=stolen, headers=hb)
    assert res.status_code == 422, res.text
    foreign_outlet = opening(world["kitchen"], items["rice"], g)
    assert client.post(f"{API}/opening", json=foreign_outlet, headers=hb).status_code == 404


def test_recipe_costing_uses_ledger_average(
    client: TestClient, world: dict[str, Any], items: dict[str, str]
) -> None:
    h = login(client, world["manager_a"])
    u = units(client)
    body = opening(world["kitchen"], items["rice"], u["kg"])  # Rp 120 per g
    assert client.post(f"{API}/opening", json=body, headers=h).status_code == 201
    dish = make_item(client, h, "NASI", "pcs", type="menu", storage_type=None, shelf_life_days=None)
    line = {"component_item_id": items["rice"], "qty": "200", "unit_id": u["g"]}
    bom = client.post(f"/api/v1/catalog/items/{dish}/boms", json={"lines": [line]}, headers=h)
    act = {"valid_from": "2026-01-01"}
    assert client.post(f"/api/v1/catalog/boms/{bom.json()['id']}/activate", json=act, headers=h)
    costing = client.get(f"/api/v1/catalog/items/{dish}/costing?on=2026-02-01").json()
    assert Decimal(costing["cost"]) == Decimal(24_000)  # 200 g x Rp 120
