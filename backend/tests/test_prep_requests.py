"""FR-PRD-008 with FR-TRF-001: open branch requests add to the central kitchen's prep list,
by their needed-by date, and only while the tenant counts them (production setting)."""

import uuid
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.factories import add_member, add_outlet, drop_tenant, seed_tenant
from tests.test_auth_mfa import enroll_as
from tests.test_inventory import HASH, PW, login
from tests.test_prep_labels import PREP, set_par
from tests.test_production import client as client
from tests.test_production import sambal as sambal

DAY = "2026-03-02"


@pytest.fixture
def world() -> Iterator[dict[str, Any]]:
    a, roles = seed_tenant("Alpha", modules=("inventory", "production", "transfers"))
    shop, kitchen = add_outlet(a, "Shop"), add_outlet(a, "Central kitchen")
    w: dict[str, Any] = {"a": a, "shop": shop, "kitchen": kitchen}
    w["manager_a"] = add_member(a, roles["manager"], HASH)[1]
    w["owner_a"] = add_member(a, roles["owner"], HASH)[1]
    yield w
    drop_tenant(a)


def request(client: TestClient, h: dict[str, str], w: dict[str, Any], **body: Any) -> None:
    body |= {"from_outlet_id": str(w["kitchen"]), "to_outlet_id": str(w["shop"])}
    headers = {**h, "Idempotency-Key": str(uuid.uuid4())}
    made = client.post("/api/v1/transfers", json=body, headers=headers)
    assert made.status_code == 201, made.text


def prep(client: TestClient, h: dict[str, str], w: dict[str, Any]) -> Any:
    return client.get(f"{PREP}?outlet_id={w['kitchen']}&on={DAY}", headers=h).json()


def test_fr_prd_008_branch_requests_add_to_prep_list(
    client: TestClient, world: dict[str, Any], sambal: dict[str, Any]
) -> None:
    m = login(client, world["manager_a"])
    line = {"item_id": sambal["sambal"], "qty": "1500"}
    # No par level: requested items still show, so the kitchen sees what branches need.
    request(client, m, world, lines=[line])
    [row] = prep(client, m, world)
    assert Decimal(row["requested"]) == 1500 and Decimal(row["suggested"]) == 1500
    # Par adds on top; a request needed later than the day does not count yet.
    assert set_par(client, m, world["kitchen"], sambal["sambal"], "2000").status_code == 200
    request(client, m, world, lines=[line], needed_by="2026-03-09")
    [row] = prep(client, m, world)
    assert Decimal(row["requested"]) == 1500 and Decimal(row["suggested"]) == 3500
    # The owner can switch it off: back to par only.
    csrf = enroll_as(client, world["owner_a"], PW)[2]
    off = client.put(
        "/api/v1/settings/production",
        json={"prep_includes_requests": False},
        headers={"X-CSRF-Token": csrf},
    )
    assert off.status_code == 200, off.text
    [row] = prep(client, {"X-CSRF-Token": csrf}, world)
    assert Decimal(row["requested"]) == 0 and Decimal(row["suggested"]) == 2000
