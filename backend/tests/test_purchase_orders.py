"""Slice 1f part 2: purchase orders, approval, receiving, PDF (FR-PUR-003, 005, 006, 010)."""

import uuid
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient

from tests.factories import add_member
from tests.test_catalog import units
from tests.test_inventory import API, HASH, login
from tests.test_purchasing import DAY, P, tenant_sql
from tests.test_purchasing import client as client
from tests.test_purchasing import items as items
from tests.test_purchasing import world as world


def order(
    client: TestClient, h: dict[str, str], world: dict[str, Any], items: dict[str, str]
) -> dict[str, Any]:
    u = units(client)
    vendor = client.post(f"{P}/vendors", json={"name": "CV Segar"}, headers=h).json()
    body = {
        "outlet_id": str(world["shop"]),
        "vendor_id": vendor["id"],
        "order_date": DAY.isoformat(),
        "lines": [
            {"item_id": items["beef"], "qty": "10", "unit_id": u["kg"], "unit_price": 120000},
            {"item_id": items["rice"], "qty": "25", "unit_id": u["kg"], "unit_price": 14000},
        ],
    }
    made = client.post(f"{P}/orders", json=body, headers=h)
    assert made.status_code == 201, made.text
    result: dict[str, Any] = made.json()
    return result


def receive(
    client: TestClient, h: dict[str, str], po: dict[str, Any], lines: list[dict[str, Any]]
) -> Any:
    headers = {**h, "Idempotency-Key": str(uuid.uuid4())}
    body = {"business_date": "2026-03-04", "lines": lines}
    return client.post(f"{P}/orders/{po['id']}/receipts", json=body, headers=headers)


def test_fr_pur_003_submit_without_rule_approves_and_receives_in_parts(
    client: TestClient, world: dict[str, Any], items: dict[str, str]
) -> None:
    h = login(client, world["manager_a"])
    po = order(client, h, world, items)
    assert po["status"] == "draft" and po["total"] == 1_550_000
    po = client.post(f"{P}/orders/{po['id']}/submit", headers=h).json()
    assert po["status"] == "approved" and po["number"].startswith("PO-2026-")
    beef, rice = po["lines"]
    part = receive(client, h, po, [{"po_line_id": beef["id"], "qty": "6"}])
    assert part.status_code == 201, part.text
    assert client.get(f"{P}/orders/{po['id']}").json()["status"] == "partially_received"
    over = receive(client, h, po, [{"po_line_id": beef["id"], "qty": "5"}])
    assert over.status_code == 409 and over.json()["code"] == "more_than_ordered"
    # The rest arrives; rice came 1.000 per kg dearer than ordered (FR-PUR-005 discrepancy).
    rest = receive(
        client,
        h,
        po,
        [
            {"po_line_id": beef["id"], "qty": "4"},
            {"po_line_id": rice["id"], "qty": "25", "unit_price": 15000},
        ],
    )
    assert rest.json()["total"] == 4 * 120000 + 25 * 15000
    done = client.get(f"{P}/orders/{po['id']}").json()
    assert done["status"] == "received"
    stock = {
        r["sku"]: r for r in client.get(f"{API}/stock?outlet_id={world['shop']}").json()["items"]
    }
    assert Decimal(stock["RICE"]["avg_cost"]) == Decimal(15)  # per g, the price actually paid
    lead = tenant_sql(world["a"], "SELECT ordered_at, received_at FROM vendor_lead_history")
    assert len(lead) == 3 and all(str(r[1]) == "2026-03-04" for r in lead)
    # Undo the first receipt: the order is partly open again.
    back = client.post(f"{P}/receipts/{part.json()['id']}/reverse", headers=h)
    assert back.status_code == 200, back.text
    assert client.get(f"{P}/orders/{po['id']}").json()["status"] == "partially_received"


def test_fr_ten_007_order_above_threshold_needs_another_approver(
    client: TestClient, world: dict[str, Any], items: dict[str, str]
) -> None:
    # Platform template roles are readable too: pick this tenant's own manager role.
    roles = tenant_sql(
        world["a"],
        "SELECT id FROM roles WHERE template_key = 'manager' AND tenant_id = :t",
        {"t": world["a"]},
    )
    tenant_sql(
        world["a"],
        "INSERT INTO approval_rules (id, tenant_id, document_type, min_amount, approver_role_id) "
        "VALUES (gen_random_uuid(), :t, 'purchase_order', 1000000, :r)",
        {"t": world["a"], "r": roles[0][0]},
    )
    _, other = add_member(world["a"], roles[0][0], HASH)  # a second manager can approve
    h = login(client, world["manager_a"])
    po = order(client, h, world, items)
    po = client.post(f"{P}/orders/{po['id']}/submit", headers=h).json()
    assert po["status"] == "submitted"
    own = client.post(f"{P}/orders/{po['id']}/decide", json={"approve": True}, headers=h)
    assert own.status_code == 403  # never your own request (docs/03 rule 1)
    early = receive(client, h, po, [{"po_line_id": po["lines"][0]["id"], "qty": "1"}])
    assert early.status_code == 409  # not approved yet
    h2 = login(client, other)
    # FR-NTF-002: the other manager was told; the requester was not.
    [note] = client.get("/api/v1/notifications", headers=h2).json()
    assert note["kind"] == "approval_requested" and note["params"]["number"] == po["number"]
    ok = client.post(f"{P}/orders/{po['id']}/decide", json={"approve": True}, headers=h2)
    assert ok.status_code == 200 and ok.json()["status"] == "approved"
    h = login(client, world["manager_a"])
    assert client.get("/api/v1/notifications", headers=h).json() == []


def test_fr_pur_010_pdf_and_scope(
    client: TestClient, world: dict[str, Any], items: dict[str, str]
) -> None:
    h = login(client, world["manager_a"])
    po = order(client, h, world, items)
    client.post(f"{P}/orders/{po['id']}/submit", headers=h)
    pdf = client.get(f"{P}/orders/{po['id']}/pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert pdf.headers["content-type"] == "application/pdf"
    login(client, world["store_a"])  # Central kitchen only; the order is for Shop
    assert client.get(f"{P}/orders/{po['id']}").status_code == 404
    login(client, world["manager_b"])
    assert client.get(f"{P}/orders/{po['id']}/pdf").status_code == 404
