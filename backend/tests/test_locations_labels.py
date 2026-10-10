"""Slice 3g: storage locations with counts per location (FR-INV-017); barcodes, batch QR
labels and scanning (FR-INV-019)."""

from typing import Any

from fastapi.testclient import TestClient

from tests.test_catalog import item_body, units
from tests.test_inventory_documents import INV, client, login, world

__all__ = ["client", "world"]

CAT = "/api/v1/catalog/items"


def stock(client: TestClient, w: dict[str, Any]) -> dict[str, Any]:
    h = login(client, w["manager"])
    u = units(client)
    ids = {}
    for sku, barcode in (("RICE", "8991234567890"), ("BEEF", None)):
        body = item_body(u["g"], sku=sku, shelf_life_days=None, barcode=barcode)
        made = client.post(CAT, json=body, headers=h)
        assert made.status_code == 201, made.text
        ids[sku] = made.json()["id"]
    lines = [
        {"item_id": i, "qty": "1", "unit_id": u["kg"], "unit_cost": "100000", "lot_code": f"L-{s}"}
        for s, i in ids.items()
    ]
    body = {"outlet_id": str(w["shop"]), "business_date": "2026-01-01", "lines": lines}
    assert client.post(f"{INV}/opening", json=body, headers=h).status_code == 201
    return {"h": h, "u": u, **ids}


def test_fr_inv_017_location_count_covers_items_kept_there(
    client: TestClient, world: dict[str, Any]
) -> None:
    s = stock(client, world)
    h, shop = s["h"], str(world["shop"])
    freezer = client.post(
        f"{INV}/locations", json={"outlet_id": shop, "name": "Freezer"}, headers=h
    )
    assert freezer.status_code == 201, freezer.text
    fid = freezer.json()["id"]
    dup = client.post(f"{INV}/locations", json={"outlet_id": shop, "name": "Freezer"}, headers=h)
    assert dup.json()["code"] == "location_name_taken"
    put = client.put(f"{INV}/locations/{fid}/items", json={"item_ids": [s["BEEF"]]}, headers=h)
    assert put.status_code == 204
    homes = client.get(f"{INV}/locations/homes?outlet_id={shop}", headers=h).json()
    assert [(x["item_id"], x["location_id"], x["sku"]) for x in homes] == [(s["BEEF"], fid, "BEEF")]

    body = {
        "outlet_id": shop,
        "business_date": "2026-01-02",
        "count_type": "full",
        "location_id": fid,
    }
    count = client.post(f"{INV}/counts", json=body, headers=h)
    assert count.status_code == 201, count.text
    assert [ln["item_id"] for ln in count.json()["lines"]] == [s["BEEF"]]  # rice is not kept there
    assert count.json()["location_id"] == fid

    cook = login(client, world["cook"])
    denied = client.post(f"{INV}/locations", json={"outlet_id": shop, "name": "Dry"}, headers=cook)
    assert denied.status_code == 403
    other = login(client, world["manager_b"])  # another tenant sees nothing (RLS)
    assert client.get(f"{INV}/locations/homes?outlet_id={shop}", headers=other).json() == []


def test_fr_inv_019_scan_codes_and_print_labels(client: TestClient, world: dict[str, Any]) -> None:
    s = stock(client, world)
    h, shop = s["h"], world["shop"]
    by_barcode = client.get(f"{INV}/scan?outlet_id={shop}&code=8991234567890", headers=h).json()
    assert by_barcode["kind"] == "item" and by_barcode["item_id"] == s["RICE"]
    by_sku = client.get(f"{INV}/scan?outlet_id={shop}&code=BEEF", headers=h).json()
    assert by_sku["item_id"] == s["BEEF"]
    lot = client.get(f"{INV}/scan?outlet_id={shop}&code=L-BEEF", headers=h).json()
    assert lot["kind"] == "batch" and lot["lot_code"] == "L-BEEF"
    by_label = client.get(f"{INV}/scan?outlet_id={shop}&code=B:{lot['batch_id']}", headers=h).json()
    assert by_label["batch_id"] == lot["batch_id"]
    missing = client.get(f"{INV}/scan?outlet_id={shop}&code=NOPE", headers=h)
    assert missing.status_code == 404 and missing.json()["code"] == "code_not_found"

    taken = item_body(s["u"]["g"], sku="RICE2", barcode="8991234567890")
    assert client.post(CAT, json=taken, headers=h).json()["code"] == "barcode_taken"

    pdf = client.get(
        f"{INV}/labels?outlet_id={shop}&batch_id={lot['batch_id']}&item_id={s['RICE']}&copies=2",
        headers=h,
    )
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert pdf.headers["content-type"] == "application/pdf"
