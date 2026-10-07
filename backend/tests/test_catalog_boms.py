"""Slice 1c: recipes with versions, nesting, cycle check and theoretical cost
(FR-CAT-005, FR-CAT-006, FR-CAT-007)."""

import uuid
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.core.config import Settings
from app.core.tenancy import tenant_session
from app.main import create_app
from app.modules.catalog import costing
from tests.test_auth import new_client
from tests.test_catalog import item_body, signin, units
from tests.test_catalog import world as world

API = "/api/v1/catalog"


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with new_client(app) as c:
        yield c


def make_item(client: TestClient, h: dict[str, str], sku: str, kind: str, unit: str) -> str:
    body = item_body(units(client)[unit], sku=sku, type=kind, storage_type=None)
    body["translations"] = [{"language": "en", "name": sku.title()}]
    res = client.post(f"{API}/items", json=body, headers=h)
    assert res.status_code == 201, res.text
    return str(res.json()["id"])


def line(item: str, qty: str, unit: str, waste: str = "0") -> dict[str, str]:
    return {"component_item_id": item, "qty": qty, "unit_id": unit, "waste_pct": waste}


def draft(client: TestClient, h: dict[str, str], item: str, lines: list[Any], **extra: Any) -> Any:
    return client.post(f"{API}/items/{item}/boms", json={"lines": lines, **extra}, headers=h)


def activate(client: TestClient, h: dict[str, str], bom: str, day: str) -> Any:
    return client.post(f"{API}/boms/{bom}/activate", json={"valid_from": day}, headers=h)


@pytest.fixture
def kitchen(client: TestClient, world: dict[str, Any]) -> dict[str, Any]:
    """Nasi goreng = 200 g rice + 1 egg + 30 g sambal; sambal (semi-finished, makes 500 g) =
    400 g chili with 20 % waste + 100 ml oil."""
    h = signin(client, world["manager_a"])
    u = units(client)
    k: dict[str, Any] = {"h": h, "u": u}
    for sku, kind, unit in (
        ("rice", "ingredient", "g"),
        ("egg", "ingredient", "pcs"),
        ("chili", "ingredient", "g"),
        ("oil", "ingredient", "ml"),
        ("sambal", "semi_finished", "g"),
        ("nasi", "menu", "pcs"),
    ):
        k[sku] = make_item(client, h, sku, kind, unit)
    sambal = draft(
        client,
        h,
        k["sambal"],
        [line(k["chili"], "400", u["g"], "20"), line(k["oil"], "0.1", u["l"])],
        yield_qty="0.5",
        yield_unit_id=u["kg"],
    )
    assert sambal.status_code == 201, sambal.text
    nasi = draft(
        client,
        h,
        k["nasi"],
        [
            line(k["rice"], "200", u["g"]),
            line(k["egg"], "1", u["pcs"]),
            line(k["sambal"], "30", u["g"]),
        ],
    )
    assert nasi.status_code == 201, nasi.text
    k["sambal_bom"], k["nasi_bom"] = sambal.json()["id"], nasi.json()["id"]
    for bom in (k["sambal_bom"], k["nasi_bom"]):
        assert activate(client, h, bom, "2026-01-01").status_code == 200
    return k


def test_fr_cat_005_nested_recipe_expands_to_ingredients(
    client: TestClient, kitchen: dict[str, Any]
) -> None:
    res = client.get(f"{API}/items/{kitchen['nasi']}/costing?on=2026-02-01")
    assert res.status_code == 200, res.text
    body = res.json()
    got = {ln["sku"]: (int(Decimal(ln["base_qty"])), ln["unit_code"]) for ln in body["lines"]}
    # 30 g sambal: chili 400 g / 0.8 = 500 g per 500 g batch -> 30 g; oil 100 ml/500 g -> 6 ml.
    assert got == {"rice": (200, "g"), "egg": (1, "pcs"), "chili": (30, "g"), "oil": (6, "ml")}
    assert body["bom_id"] == kitchen["nasi_bom"]
    # No cost source until the inventory ledger exists (slice 1e): cost is unknown, not 0.
    assert body["cost"] is None and len(body["missing_costs"]) == 4
    assert client.get(f"{API}/items/{kitchen['nasi']}/costing?on=2025-12-31").json()["lines"] == []


def test_fr_cat_006_versions_draft_then_fixed(client: TestClient, kitchen: dict[str, Any]) -> None:
    h, u = kitchen["h"], kitchen["u"]
    fixed = client.put(
        f"{API}/boms/{kitchen['nasi_bom']}",
        json={"lines": [line(kitchen["rice"], "1", u["g"])]},
        headers=h,
    )
    assert fixed.status_code == 409 and fixed.json()["code"] == "bom_not_draft"
    v2 = draft(client, h, kitchen["nasi"], [line(kitchen["rice"], "250", u["g"])]).json()
    assert v2["version"] == 2 and v2["status"] == "draft"
    early = activate(client, h, v2["id"], "2026-01-01")
    assert early.status_code == 409 and early.json()["code"] == "bom_start_too_early"
    assert activate(client, h, v2["id"], "2026-06-01").status_code == 200
    versions = {b["version"]: b for b in client.get(f"{API}/items/{kitchen['nasi']}/boms").json()}
    assert versions[1]["valid_to"] == "2026-05-31" and versions[2]["valid_to"] is None

    def rice(day: str) -> Decimal:
        lines = client.get(f"{API}/items/{kitchen['nasi']}/costing?on={day}").json()["lines"]
        return Decimal(next(ln["base_qty"] for ln in lines if ln["sku"] == "rice"))

    assert rice("2026-05-31") == Decimal(200) and rice("2026-06-01") == Decimal(250)
    v3 = draft(client, h, kitchen["nasi"], [line(kitchen["egg"], "2", u["pcs"])]).json()
    assert client.delete(f"{API}/boms/{v3['id']}", headers=h).status_code == 204
    gone = client.delete(f"{API}/boms/{kitchen['nasi_bom']}", headers=h)
    assert gone.status_code == 409  # active versions are kept


def test_recipes_refuse_cycles_and_wrong_components(
    client: TestClient, kitchen: dict[str, Any]
) -> None:
    h, u = kitchen["h"], kitchen["u"]
    base = make_item(client, h, "base", "semi_finished", "g")
    yields = {"yield_qty": "1", "yield_unit_id": u["kg"]}
    assert (
        draft(client, h, base, [line(kitchen["sambal"], "1", u["g"])], **yields).status_code == 201
    )
    # sambal -> base -> sambal (through base's draft): refused even before anything is active.
    loop = draft(client, h, kitchen["sambal"], [line(base, "1", u["g"])], **yields)
    assert loop.status_code == 422 and loop.json()["code"] == "bom_cycle"
    itself = draft(client, h, base, [line(base, "1", u["g"])], **yields)
    assert itself.json()["code"] == "bom_cycle"
    cases = [
        (kitchen["rice"], [line(kitchen["egg"], "1", u["pcs"])], {}, "ingredient_has_no_recipe"),
        (base, [line(kitchen["nasi"], "1", u["pcs"])], yields, "component_not_stock_item"),
        (base, [line(kitchen["rice"], "1", u["g"])], {}, "yield_required"),
        (kitchen["nasi"], [line(kitchen["egg"], "1", u["g"])], {}, "no_unit_conversion"),
    ]
    for item, lines, extra, code in cases:
        res = draft(client, h, item, lines, **extra)
        assert res.status_code == 422 and res.json()["code"] == code, (code, res.text)
    bad_waste = draft(client, h, kitchen["nasi"], [line(kitchen["rice"], "1", u["g"], "100")])
    assert bad_waste.status_code == 422


def test_cost_needs_permission_and_tenants_are_isolated(
    client: TestClient, world: dict[str, Any], kitchen: dict[str, Any]
) -> None:
    signin(client, world["cashier_a"])  # can see recipes, not costs (docs/03)
    seen = client.get(f"{API}/items/{kitchen['nasi']}/costing").json()
    assert seen["cost_visible"] is False and seen["missing_costs"] == [] and seen["lines"]
    assert all(ln["unit_cost"] is None for ln in seen["lines"])
    hc = signin(client, world["cashier_a"])
    assert draft(client, hc, kitchen["nasi"], []).status_code == 403
    hb = signin(client, world["manager_b"])
    own = make_item(client, hb, "dish", "menu", "pcs")
    stolen = draft(client, hb, own, [line(kitchen["rice"], "1", units(client)["g"])])
    assert stolen.status_code == 422 and stolen.json()["code"] == "invalid_reference"
    assert client.get(f"{API}/boms/{kitchen['nasi_bom']}").status_code == 404
    assert client.get(f"{API}/items/{kitchen['nasi']}/costing").status_code == 404


@pytest.mark.anyio
async def test_fr_cat_007_cost_and_margin_from_cost_source(
    engine: AsyncEngine, client: TestClient, world: dict[str, Any], kitchen: dict[str, Any]
) -> None:
    h = kitchen["h"]
    ch = client.post(
        f"{API}/channels", json={"code": "dine_in", "name": "Dine-in", "kind": "dine_in"}, headers=h
    ).json()["id"]
    price = {"channel_id": ch, "valid_from": "2026-01-01", "price": 25_000}
    assert (
        client.put(f"{API}/items/{kitchen['nasi']}/prices", json=price, headers=h).status_code
        == 200
    )
    unit_costs = {
        uuid.UUID(kitchen["rice"]): Decimal("15"),  # Rp 15 per g
        uuid.UUID(kitchen["egg"]): Decimal("2500"),
        uuid.UUID(kitchen["chili"]): Decimal("60"),
        uuid.UUID(kitchen["oil"]): Decimal("20"),
    }

    async def source(_db: object, ids: set[uuid.UUID]) -> dict[uuid.UUID, Decimal]:
        return {i: unit_costs[i] for i in ids if i in unit_costs}

    registered = costing._cost_source  # the inventory module's, restored afterwards
    costing.set_cost_source(source)
    try:
        async with tenant_session(async_sessionmaker(engine), world["a"]) as db:
            result = await costing.costing(
                db,
                tenant_id=world["a"],
                item_id=uuid.UUID(kitchen["nasi"]),
                on=date(2026, 2, 1),
                language="en",
                show_cost=True,
            )
    finally:
        costing.set_cost_source(registered)
    # 200*15 + 1*2500 + 30*60 + 6*20 = 3000 + 2500 + 1800 + 120
    assert result.cost == Decimal("7420.00") and result.missing_costs == []
    [m] = result.margins
    assert m.price == 25_000 and m.margin == Decimal(m.net_price) - Decimal("7420.00")
    assert m.cost_pct == (Decimal("742000") / m.net_price).quantize(Decimal("0.01"))


@pytest.mark.anyio
async def test_active_recipe_lines_are_fixed_in_the_database(
    engine: AsyncEngine, kitchen: dict[str, Any], world: dict[str, Any]
) -> None:
    async with tenant_session(async_sessionmaker(engine), world["a"]) as db:
        with pytest.raises(DBAPIError, match="fixed"):
            await db.execute(
                text("DELETE FROM bom_lines WHERE bom_id = :b"), {"b": kitchen["nasi_bom"]}
            )


def test_costing_query_count_does_not_grow_with_lines(
    app: FastAPI, client: TestClient, kitchen: dict[str, Any]
) -> None:
    h, u = kitchen["h"], kitchen["u"]
    parts = [make_item(client, h, f"part{i:02d}", "ingredient", "g") for i in range(20)]

    def dish(sku: str, size: int) -> str:
        item = make_item(client, h, sku, "menu", "pcs")
        bom = draft(client, h, item, [line(p, "10", u["g"]) for p in parts[:size]]).json()["id"]
        assert activate(client, h, bom, "2026-01-01").status_code == 200
        return item

    def queries(item: str, expected_lines: int) -> int:
        count = 0

        def on_execute(*_: object) -> None:
            nonlocal count
            count += 1

        sync_engine = app.state.engine.sync_engine
        event.listen(sync_engine, "before_cursor_execute", on_execute)
        try:
            res = client.get(f"{API}/items/{item}/costing?on=2026-02-01").json()
            assert len(res["lines"]) == expected_lines
        finally:
            event.remove(sync_engine, "before_cursor_execute", on_execute)
        return count

    small, large = queries(dish("snack", 1), 1), queries(dish("feast", 20), 20)
    assert small == large <= 20  # batched per nesting level, never per line
