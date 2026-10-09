"""Slice 1j part 1: stock alerts and the notification center (FR-INV-012, FR-NTF-001):
conditions open alerts once, recipients follow outlet scope, alerts resolve when the
condition clears, users only see their own notifications, tenants never mix."""

import asyncio
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.admin.alerts_job import run_alerts
from app.core.config import Settings
from tests.test_inventory import login
from tests.test_purchasing import tenant_sql
from tests.test_transfers import client as client
from tests.test_transfers import items as items
from tests.test_transfers import world as world

N = "/api/v1/notifications"
LEVELS = "/api/v1/inventory/levels"


def scan(settings: Settings, *tenants: Any) -> int:
    async def go() -> int:
        engine = create_async_engine(str(settings.database_url))
        try:
            return await run_alerts(
                list(tenants), async_sessionmaker(engine, expire_on_commit=False)
            )
        finally:
            await engine.dispose()

    return asyncio.run(go())


def reorder_at(client: TestClient, h: dict[str, str], outlet: Any, item: str, point: str) -> None:
    body = {"outlet_id": str(outlet), "levels": [{"item_id": item, "reorder_point": point}]}
    assert client.put(LEVELS, json=body, headers=h).status_code == 200


def kinds(client: TestClient, h: dict[str, str]) -> list[str]:
    return sorted(n["kind"] for n in client.get(N, headers=h).json())


def test_fr_inv_012_alerts_open_once_notify_and_resolve(
    client: TestClient, world: dict[str, Any], items: dict[str, str], settings: Settings
) -> None:
    m = login(client, world["manager_a"])
    # The kitchen holds beef that expired on 1 April and 20 kg rice; reorder rice at 30 kg.
    reorder_at(client, m, world["kitchen"], items["rice"], "30000")
    assert scan(settings, world["a"]) == 0
    assert kinds(client, m) == ["below_reorder_point", "expired_stock"]
    [low] = [n for n in client.get(N, headers=m).json() if n["kind"] == "below_reorder_point"]
    assert low["params"]["item"] and low["params"]["qty"] == "20000" and low["link"] == "/inventory"
    assert client.get(f"{N}/unread-count", headers=m).json() == {"unread": 2}

    scan(settings, world["a"])  # runs again: no duplicate alerts or notifications
    assert len(kinds(client, m)) == 2
    assert client.post(f"{N}/{low['id']}/read", headers=m).status_code == 204
    assert client.get(f"{N}/unread-count", headers=m).json() == {"unread": 1}

    # The condition clears: the alert is resolved, and a new low raises a new one later.
    reorder_at(client, m, world["kitchen"], items["rice"], "1000")
    scan(settings, world["a"])
    states = tenant_sql(world["a"], "SELECT type, state FROM alerts ORDER BY type")
    assert [tuple(r) for r in states] == [
        ("below_reorder_point", "resolved"),
        ("expired_stock", "open"),
    ]
    assert client.post(f"{N}/read-all", headers=m).status_code == 204
    assert client.get(f"{N}/unread-count", headers=m).json() == {"unread": 0}


def test_fr_ntf_001_notifications_are_per_user_and_tenant(
    client: TestClient, world: dict[str, Any], items: dict[str, str], settings: Settings
) -> None:
    scan(settings, world["a"])
    m = login(client, world["manager_a"])
    mine = client.get(N, headers=m).json()
    assert [n["kind"] for n in mine] == ["expired_stock"]
    # The shop storekeeper is not a default recipient and cannot see the kitchen anyway.
    shop = login(client, world["store_shop"])
    assert client.get(N, headers=shop).json() == []
    assert client.post(f"{N}/{mine[0]['id']}/read", headers=shop).status_code == 204  # no effect
    other = login(client, world["manager_b"])
    assert client.get(N, headers=other).json() == []
    m = login(client, world["manager_a"])
    assert client.get(f"{N}/unread-count", headers=m).json() == {"unread": 1}
