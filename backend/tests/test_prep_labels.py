"""Slice 1g part 2: stock levels (docs/05 2.3), daily prep list (FR-PRD-008) and
shelf-life labels (FR-PRD-007): suggestions, outlet scope, permissions, PDFs."""

import uuid
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient

from tests.test_inventory import login
from tests.test_production import PRD, plan
from tests.test_production import client as client
from tests.test_production import sambal as sambal
from tests.test_production import world as world

LEVELS = "/api/v1/inventory/levels"
PREP = "/api/v1/production/prep-list"


def set_par(client: TestClient, h: dict[str, str], outlet: Any, item: str, par: str | None) -> Any:
    body = {"outlet_id": str(outlet), "levels": [{"item_id": item, "par_qty": par}]}
    return client.put(LEVELS, json=body, headers=h)


def test_fr_prd_008_prep_list_suggests_par_minus_stock_minus_planned(
    client: TestClient, world: dict[str, Any], sambal: dict[str, Any]
) -> None:
    m = login(client, world["manager_a"])
    kitchen = world["kitchen"]
    saved = set_par(client, m, kitchen, sambal["sambal"], "2000")
    assert saved.status_code == 200, saved.text
    assert Decimal(saved.json()[0]["par_qty"]) == Decimal(2000)
    # Ingredients with a par do not belong on the prep list.
    assert set_par(client, m, kitchen, sambal["chili"], "5000").status_code == 200
    day = "2026-03-02"
    [row] = client.get(f"{PREP}?outlet_id={kitchen}&on={day}", headers=m).json()
    assert row["sku"] == "SAMBAL" and Decimal(row["suggested"]) == Decimal(2000)
    plan(client, m, kitchen, sambal["sambal"], "500")
    [row] = client.get(f"{PREP}?outlet_id={kitchen}&on={day}", headers=m).json()
    assert Decimal(row["planned"]) == Decimal(500) and Decimal(row["suggested"]) == Decimal(1500)
    sheet = client.get(f"{PREP}/pdf?outlet_id={kitchen}&on={day}&lang=id", headers=m)
    assert sheet.status_code == 200 and sheet.content.startswith(b"%PDF")
    # Clearing every target removes the row.
    assert set_par(client, m, kitchen, sambal["sambal"], None).json()[0]["sku"] == "CHILI"


def test_fr_prd_007_labels_for_completed_production_only(
    client: TestClient, world: dict[str, Any], sambal: dict[str, Any]
) -> None:
    cook = login(client, world["cook_a"])
    order = plan(client, cook, world["kitchen"], sambal["sambal"], "1000").json()
    early = client.get(f"{PRD}/{order['id']}/labels", headers=cook)
    assert early.status_code == 409
    client.post(f"{PRD}/{order['id']}/complete", json={"actual_qty": "1000"}, headers=cook)
    labels = client.get(f"{PRD}/{order['id']}/labels?copies=3&lang=id", headers=cook)
    assert labels.status_code == 200 and labels.content.startswith(b"%PDF")
    assert labels.headers["x-content-type-options"] == "nosniff"
    assert labels.content.count(b"/Type /Page\n") + labels.content.count(b"/Type /Page ") >= 3
    too_many = client.get(f"{PRD}/{order['id']}/labels?copies=500", headers=cook)
    assert too_many.status_code == 422
    # FR-PRD-006: the cook's prep sheet with the scaled recipe.
    sheet = client.get(f"{PRD}/{order['id']}/sheet?lang=id", headers=cook)
    assert sheet.status_code == 200 and sheet.content.startswith(b"%PDF")


def test_levels_scope_and_permissions(
    client: TestClient, world: dict[str, Any], sambal: dict[str, Any]
) -> None:
    cook = login(client, world["cook_a"])  # kitchen role: view only, kitchen outlet only
    assert set_par(client, cook, world["kitchen"], sambal["sambal"], "1").status_code == 403
    assert client.get(f"{LEVELS}?outlet_id={world['shop']}", headers=cook).status_code == 404
    assert (
        client.get(f"{PREP}?outlet_id={world['shop']}&on=2026-03-02", headers=cook).status_code
        == 404
    )
    other = login(client, world["manager_b"])
    foreign = set_par(client, other, world["kitchen"], sambal["sambal"], "1")
    assert foreign.status_code == 404
    m = login(client, world["manager_a"])
    unknown = set_par(client, m, world["kitchen"], str(uuid.uuid4()), "1")
    assert unknown.status_code == 404
