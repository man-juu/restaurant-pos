"""Phase 1 security review regressions (docs/security-review-phase1.md)."""

from typing import Any

from fastapi.testclient import TestClient

from tests.test_catalog import units
from tests.test_inventory import API as INV
from tests.test_inventory import client, items, login, opening, world  # noqa: F401


def test_audit_log_is_limited_to_own_outlets(
    client: TestClient,  # noqa: F811
    world: dict[str, Any],  # noqa: F811
    items: dict[str, str],  # noqa: F811
) -> None:
    h = login(client, world["manager_a"])
    kg = units(client)["kg"]
    for outlet in (world["shop"], world["kitchen"]):
        body = opening(outlet, items["beef"], kg, expiry_date="2026-02-01")
        assert client.post(f"{INV}/opening", json=body, headers=h).status_code == 201
    everyone = {r["outlet_id"] for r in client.get("/api/v1/audit").json()["items"]}
    assert {str(world["shop"]), str(world["kitchen"])} <= everyone
    login(client, world["kitchen_manager_a"])
    seen = {r["outlet_id"] for r in client.get("/api/v1/audit").json()["items"]}
    assert str(world["shop"]) not in seen and str(world["kitchen"]) in seen
