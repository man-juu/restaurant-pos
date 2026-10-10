"""Slice 4c: delivery-platform sales files with a saved column mapping (FR-IMP-004):
mapping per channel, check before saving, rows summed per day, codes then SKUs, the file's
amount kept exactly, stock out by recipe, no double import, undo, scope and isolation."""

from typing import Any

from fastapi.testclient import TestClient

from tests.test_imports_more import send
from tests.test_inventory import login
from tests.test_purchasing import client as client
from tests.test_sales_days import S, on_hand
from tests.test_sales_days import menu as menu
from tests.test_sales_days import world as world

P = "/api/v1/sales/platform-imports"
MAP = {
    "date_column": "Order Date",
    "code_column": "Item Code",
    "qty_column": "Qty",
    "amount_column": "Net Sales",
    "date_format": "dmy",
}
FILE = (
    "Order Date,Item Code,Qty,Net Sales\n"
    '05/03/2026 12:01,NG-01,2,"45.000"\n'
    "05/03/2026 18:40,NG-01,1,22500\n"
    '06/03/2026 09:15,nasi,1,"Rp 25.000"\n'
)


def where(world: dict[str, Any], menu: dict[str, Any]) -> str:
    return f"outlet_id={world['shop']}&channel_id={menu['gofood']}"


def test_fr_imp_004_mapping_check_import_and_undo(
    client: TestClient, world: dict[str, Any], menu: dict[str, Any]
) -> None:
    h = login(client, world["manager_a"])
    q = where(world, menu)
    assert send(client, h, f"{P}/check?{q}", FILE).json()["code"] == "mapping_not_found"
    saved = client.put(f"{P}/mappings/{menu['gofood']}", json=MAP, headers=h)
    assert saved.status_code == 200 and saved.json()["date_column"] == "order date"
    assert send(client, h, f"{P}/columns", FILE).json() == [
        "order date",
        "item code",
        "qty",
        "net sales",
    ]
    bad = send(client, h, f"{P}/check?{q}", FILE + "31/02/2026,NG-01,1,1\n,XX,0,1\n").json()
    assert bad["rows_ok"] == 0
    assert bad["errors"] == [
        {"row": 5, "field": "date"},
        {"row": 6, "field": "date"},
    ]
    ok = send(client, h, f"{P}/check?{q}", FILE).json()
    assert ok["errors"] == [] and ok["rows_ok"] == 3
    assert [(d["business_date"], d["total"], d["replaces"]) for d in ok["days"]] == [
        ("2026-03-05", 67_500, False),
        ("2026-03-06", 25_000, False),
    ]
    assert on_hand(client, h, world["shop"])["RICE"] == 10_000  # the check saved nothing

    batch = send(client, h, f"{P}?{q}", FILE)
    assert batch.status_code == 201, batch.text
    assert send(client, h, f"{P}?{q}", FILE).json()["code"] == "already_imported"
    assert on_hand(client, h, world["shop"])["RICE"] == 10_000 - 4 * 200
    [doc] = client.get(f"{S}/{world['shop']}/2026-03-05", headers=h).json()["documents"]
    assert doc["subtotal"] - doc["discount"] == 67_500  # exactly the platform's amount

    undone = client.post(f"{P}/{batch.json()['id']}/revert", headers=h)
    assert undone.status_code == 200 and undone.json()["status"] == "reverted"
    assert on_hand(client, h, world["shop"])["RICE"] == 10_000
    assert client.get(f"{S}/{world['shop']}/2026-03-05", headers=h).json()["documents"] == []


def test_platform_import_scope_permissions_and_isolation(
    client: TestClient, world: dict[str, Any], menu: dict[str, Any]
) -> None:
    h = login(client, world["manager_a"])
    assert client.put(f"{P}/mappings/{menu['gofood']}", json=MAP, headers=h).status_code == 200
    c = login(client, world["cashier_a"])  # Shop only
    other = f"outlet_id={world['other']}&channel_id={menu['gofood']}"
    assert send(client, c, f"{P}/check?{other}", FILE).status_code == 404  # out of scope
    b = login(client, world["manager_b"])
    assert client.get(f"{P}/mappings/{menu['gofood']}", headers=b).status_code == 404
    # Another tenant's channel is unknown here: refused before anything is saved.
    assert client.put(f"{P}/mappings/{menu['gofood']}", json=MAP, headers=b).status_code == 422
