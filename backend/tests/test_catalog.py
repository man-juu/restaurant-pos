"""Slice 1b: catalog units, categories and items (FR-CAT-001, 002, 008, 009)."""

import uuid
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.core.config import Settings
from app.core.identity.passwords import _hasher
from app.core.tenancy import tenant_session
from app.main import create_app
from app.modules.catalog import service
from app.modules.catalog.schemas import ItemIn, UnitIn
from tests.factories import add_member, drop_tenant, seed_tenant
from tests.test_auth import new_client

PW = "catalog test passphrase"
HASH = _hasher.hash(PW)


@pytest.fixture
def world() -> Iterator[dict[str, Any]]:
    a, roles_a = seed_tenant("Alpha")
    b, roles_b = seed_tenant("Beta")
    _, manager_a = add_member(a, roles_a["manager"], HASH)
    _, cashier_a = add_member(a, roles_a["cashier"], HASH)
    _, manager_b = add_member(b, roles_b["manager"], HASH)
    yield {"a": a, "b": b, "manager_a": manager_a, "cashier_a": cashier_a, "manager_b": manager_b}
    drop_tenant(a)
    drop_tenant(b)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with new_client(create_app(settings)) as c:
        yield c


def signin(client: TestClient, email: str) -> dict[str, str]:
    client.cookies.clear()
    body = client.post("/api/v1/auth/login", json={"email": email, "password": PW}).json()
    return {"X-CSRF-Token": body["csrf_token"]}


def units(client: TestClient) -> dict[str, str]:
    return {u["code"]: u["id"] for u in client.get("/api/v1/catalog/units").json()}


def item_body(base_unit_id: str, sku: str = "BEEF-01", **extra: Any) -> dict[str, Any]:
    return {
        "sku": sku,
        "type": "ingredient",
        "base_unit_id": base_unit_id,
        "storage_type": "frozen",
        "shelf_life_days": 90,
        "allergens": [],
        "translations": [
            {"language": "en", "name": "Beef slices"},
            {"language": "id", "name": "Irisan daging sapi"},
        ],
        **extra,
    }


def test_fr_cat_002_platform_units_and_custom_unit(
    client: TestClient, world: dict[str, Any]
) -> None:
    h = signin(client, world["manager_a"])
    assert {"g", "kg", "ml", "l", "pcs"} <= units(client).keys()
    box = client.post(
        "/api/v1/catalog/units",
        json={"code": "box", "name": "Box", "dimension": "count"},
        headers=h,
    )
    assert box.status_code == 201 and box.json()["is_platform"] is False
    dup = client.post(
        "/api/v1/catalog/units", json={"code": "KG", "name": "x", "dimension": "mass"}, headers=h
    )
    assert dup.status_code == 409
    signin(client, world["manager_b"])
    assert "box" not in units(client)  # another tenant's unit is invisible


def test_fr_cat_001_009_item_create_names_fallback_and_search(
    client: TestClient, world: dict[str, Any]
) -> None:
    h = signin(client, world["manager_a"])
    g = units(client)["g"]
    created = client.post("/api/v1/catalog/items", json=item_body(g), headers=h)
    assert created.status_code == 201, created.text
    item = created.json()
    assert item["name"] == "Beef slices" and item["version"] == 1
    in_id = client.get(f"/api/v1/catalog/items/{item['id']}?lang=id").json()
    assert in_id["name"] == "Irisan daging sapi"
    # No Korean name: falls back to the tenant default language, never empty.
    assert client.get(f"/api/v1/catalog/items/{item['id']}?lang=ko").json()["name"]
    found = client.get("/api/v1/catalog/items?q=sapi&lang=id").json()["items"]
    assert [i["sku"] for i in found] == ["BEEF-01"]
    assert client.get("/api/v1/catalog/items?q=%25").json()["items"] == []  # % is literal
    again = client.post("/api/v1/catalog/items", json=item_body(g), headers=h)
    assert again.status_code == 409 and again.json()["code"] == "sku_taken"


def test_cashier_can_view_but_not_edit(client: TestClient, world: dict[str, Any]) -> None:
    h = signin(client, world["cashier_a"])
    assert client.get("/api/v1/catalog/items").status_code == 200
    g = units(client)["g"]
    assert client.post("/api/v1/catalog/items", json=item_body(g), headers=h).status_code == 403


def test_update_uses_versions_and_locks_base_unit(
    client: TestClient, world: dict[str, Any]
) -> None:
    h = signin(client, world["manager_a"])
    u = units(client)
    item = client.post("/api/v1/catalog/items", json=item_body(u["g"]), headers=h).json()
    url = f"/api/v1/catalog/items/{item['id']}"
    ok = client.put(url, json={**item_body(u["g"], sku="BEEF-02"), "version": 1}, headers=h)
    assert ok.status_code == 200 and ok.json()["version"] == 2
    stale = client.put(url, json={**item_body(u["g"]), "version": 1}, headers=h)
    assert stale.status_code == 409 and stale.json()["code"] == "stale_version"
    moved = client.put(url, json={**item_body(u["kg"]), "version": 2}, headers=h)
    assert moved.json()["code"] == "base_unit_locked"


def test_tenant_isolation_for_items_and_references(
    client: TestClient, world: dict[str, Any]
) -> None:
    h = signin(client, world["manager_a"])
    box = client.post(
        "/api/v1/catalog/units",
        json={"code": "box", "name": "Box", "dimension": "count"},
        headers=h,
    ).json()
    item = client.post(
        "/api/v1/catalog/items", json=item_body(units(client)["g"]), headers=h
    ).json()
    hb = signin(client, world["manager_b"])
    assert client.get(f"/api/v1/catalog/items/{item['id']}").status_code == 404
    assert client.get("/api/v1/catalog/items").json()["items"] == []
    # Foreign keys ignore RLS, so the service must refuse another tenant's unit id.
    stolen = client.post("/api/v1/catalog/items", json=item_body(box["id"]), headers=hb)
    assert stolen.status_code == 422 and stolen.json()["code"] == "invalid_reference"


def test_category_tree_rejects_cycles(client: TestClient, world: dict[str, Any]) -> None:
    h = signin(client, world["manager_a"])
    top = client.post("/api/v1/catalog/categories", json={"name": "Meat"}, headers=h).json()
    child = client.post(
        "/api/v1/catalog/categories", json={"name": "Beef", "parent_id": top["id"]}, headers=h
    ).json()
    loop = client.put(
        f"/api/v1/catalog/categories/{top['id']}",
        json={"name": "Meat", "parent_id": child["id"]},
        headers=h,
    )
    assert loop.status_code == 422


def test_fr_x_003_item_create_is_idempotent(client: TestClient, world: dict[str, Any]) -> None:
    h = signin(client, world["manager_a"])
    key = {**h, "Idempotency-Key": str(uuid.uuid4())}
    body = item_body(units(client)["g"])
    first = client.post("/api/v1/catalog/items", json=body, headers=key)
    second = client.post("/api/v1/catalog/items", json=body, headers=key)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


@pytest.mark.anyio
async def test_fr_cat_002_conversions_are_exact(engine: AsyncEngine, world: dict[str, Any]) -> None:
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with tenant_session(maker, world["a"]) as db:
        u = {x.code: x.id for x in await service.list_units(db)}
        box = await service.create_unit(
            db,
            tenant_id=world["a"],
            user_id=uuid.uuid4(),
            data=UnitIn(code="box", name="Box", dimension="count"),
        )
        body = item_body(
            str(u["g"]), conversions=[{"unit_id": str(box.id), "factor_to_base": "2500.5"}]
        )
        iid = await service.create_item(
            db, tenant_id=world["a"], user_id=uuid.uuid4(), data=ItemIn.model_validate(body)
        )
        got = [await service.factor_to_base(db, iid, x) for x in (u["kg"], box.id, u["g"])]
    assert got == [Decimal(1000), Decimal("2500.5"), Decimal(1)]
