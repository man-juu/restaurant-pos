"""Slice 1d: item import and export (FR-IMP-001 to 003)."""

import io
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook

from app.core.tabular import InvalidTable, read_table, write_csv
from tests.test_catalog import client as client
from tests.test_catalog import signin
from tests.test_catalog import world as world

HEADER = "sku,type,name_en,name_id,base_unit,category,storage_type,shelf_life_days,is_stocked\n"
GOOD = (
    HEADER
    + "BEEF-150,ingredient,Beef pack,Daging,pcs,,frozen,90,yes\nRICE,bahan,Rice,Beras,kg,,dry,,ya\n"
)


def send(client: TestClient, h: dict[str, str], path: str, data: bytes, name: str) -> Any:
    return client.post(
        f"/api/v1/catalog/imports/items{path}?file_name={name}",
        content=data,
        headers={**h, "Content-Type": "application/octet-stream"},
    )


def test_formula_cells_are_neutralised_on_export() -> None:
    out = write_csv(["name"], [['=HYPERLINK("http://x")'], ["+1"], ["ok"]]).decode("utf-8-sig")
    assert "'=HYPERLINK" in out and "'+1" in out and "\nok" in out.replace("\r", "")


def test_xlsx_formulas_are_read_as_text_never_evaluated() -> None:
    book = Workbook()
    book.active.append(["sku", "name_en"])
    book.active.append(["A1", "=1+1"])
    buf = io.BytesIO()
    book.save(buf)
    rows = read_table(buf.getvalue(), "x.xlsx")
    assert rows[0]["sku"] == "A1"  # cached value missing: formula text, not "2"


def test_rejects_non_utf8_and_zip_bombs() -> None:
    with pytest.raises(InvalidTable):
        read_table("sku\n\xff".encode("latin-1"), "x.csv")
    with pytest.raises(InvalidTable):
        read_table(b"PK\x03\x04 not really a zip", "x.xlsx")


def test_fr_imp_001_002_check_commit_idempotent_and_revert(
    client: TestClient, world: dict[str, Any]
) -> None:
    h = signin(client, world["manager_a"])
    checked = send(client, h, "/check", GOOD.encode(), "items.csv")
    assert checked.json() == {"rows_ok": 2, "errors": [], "new_categories": []}
    batch = send(client, h, "", GOOD.encode(), "items.csv")
    assert batch.status_code == 201, batch.text
    skus = {i["sku"] for i in client.get("/api/v1/catalog/items").json()["items"]}
    assert skus == {"BEEF-150", "RICE"}
    again = send(client, h, "", GOOD.encode(), "items.csv")
    assert again.status_code == 409 and again.json()["code"] == "already_imported"
    reverted = client.post(f"/api/v1/catalog/imports/{batch.json()['id']}/revert", headers=h)
    assert reverted.json()["status"] == "reverted"
    assert client.get("/api/v1/catalog/items").json()["items"] == []  # archived, not deleted


def test_row_errors_block_the_whole_file(client: TestClient, world: dict[str, Any]) -> None:
    h = signin(client, world["manager_a"])
    bad = (
        HEADER
        + "A1,ingredient,A,A,pcs,,,,yes\n"
        + "A1,ingredient,B,B,pcs,,,,yes\n"
        + "B2,menu,C,C,parsec,,,,maybe\n"
    )
    checked = send(client, h, "/check", bad.encode(), "items.csv").json()
    assert {(e["row"], e["field"]) for e in checked["errors"]} == {
        (3, "sku_taken"),
        (4, "base_unit"),
        (4, "is_stocked"),
    }
    assert send(client, h, "", bad.encode(), "items.csv").status_code == 422
    assert client.get("/api/v1/catalog/items").json()["items"] == []


def test_export_round_trip_permissions_and_isolation(
    client: TestClient, world: dict[str, Any]
) -> None:
    h = signin(client, world["manager_a"])
    send(client, h, "", GOOD.encode(), "items.csv")
    xlsx = client.get("/api/v1/catalog/exports/items?format=xlsx")
    assert xlsx.status_code == 200, xlsx.text
    sheet = load_workbook(io.BytesIO(xlsx.content)).active
    assert [c.value for c in sheet[1]][:3] == ["sku", "type", "name_en"]
    assert sheet.max_row == 3
    template = client.get("/api/v1/catalog/imports/items/template?format=csv", headers=h)
    assert template.status_code == 200 and template.text.lstrip("﻿").startswith("sku,")
    hc = signin(client, world["cashier_a"])
    assert send(client, hc, "", GOOD.encode(), "other.csv").status_code == 403
    assert client.get("/api/v1/catalog/exports/items?format=csv").status_code == 200
    hb = signin(client, world["manager_b"])
    assert client.get("/api/v1/catalog/exports/items?format=csv").text.count("\n") == 1
    assert send(client, hb, "", b"x", "../evil.csv").status_code == 422  # path in name refused


def test_missing_categories_created_or_refused(client: TestClient, world: dict[str, Any]) -> None:
    h = signin(client, world["manager_a"])
    rows = HEADER + "K1,ingredient,Kimchi,Kimchi,kg,Sauces,chilled,30,yes\n"
    strict = send(client, h, "/check", rows.encode(), "c.csv&create_categories=false").json()
    assert strict["errors"] == [{"row": 2, "field": "category"}]
    checked = send(client, h, "/check", rows.encode(), "c.csv").json()
    assert checked["new_categories"] == ["Sauces"] and checked["errors"] == []
    assert send(client, h, "", rows.encode(), "c.csv").status_code == 201
    cats = {c["name"]: c["id"] for c in client.get("/api/v1/catalog/categories").json()}
    item = client.get("/api/v1/catalog/items").json()["items"][0]
    assert item["category_id"] == cats["Sauces"]
