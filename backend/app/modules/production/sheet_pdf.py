"""Production prep sheet (FR-PRD-006): one page per production order for the cook, with the
ingredients scaled to the planned quantity, tick boxes, and lines to sign. Plain strings only
(no markup is parsed), like the other PDFs."""

import asyncio
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Spacer, Table, TableStyle

from app.modules.production.pdf import _cut, _qty
from app.modules.production.schemas import ProductionOut

WORDS = {
    "en": {
        "title": "Prep sheet",
        "make": "Make",
        "date": "Date",
        "lot": "Lot",
        "use_by": "Use by",
        "head": ["Ingredient", "Quantity", "Weighed"],
        "actual": "Actual yield",
        "made": "Made by",
        "checked": "Checked by",
    },
    "id": {
        "title": "Lembar persiapan",
        "make": "Buat",
        "date": "Tanggal",
        "lot": "Lot",
        "use_by": "Gunakan sebelum",
        "head": ["Bahan", "Jumlah", "Ditimbang"],
        "actual": "Hasil aktual",
        "made": "Dibuat oleh",
        "checked": "Diperiksa oleh",
    },
}
GRID = TableStyle(
    [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1d2833")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c3cfda")),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
    ]
)


def _sheet(order: ProductionOut, language: str) -> bytes:
    w = WORDS.get(language[:2], WORDS["en"])
    out = io.BytesIO()
    title = f"{w['title']} {order.number}"
    doc = SimpleDocTemplate(out, pagesize=A4, title=title)
    head = [
        [title, ""],
        [w["make"], f"{_qty(order.planned_qty)} {order.unit_code} {_cut(order.item_name, 50)}"],
        [w["date"], order.production_date.strftime("%d/%m/%Y")],
        [w["lot"], order.lot_code or order.number],
        [w["use_by"], order.expiry_date.strftime("%d/%m/%Y") if order.expiry_date else "-"],
    ]
    ingredients = [list(w["head"])] + [
        [_cut(ln.item_name, 50), f"{_qty(ln.planned_qty)} {ln.unit_code}", "[  ]"]
        for ln in order.lines
    ]
    sign = [[w["actual"], "________"], [w["made"], "________"], [w["checked"], "________"]]
    doc.build(
        [
            Table(head, style=[("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]),
            Spacer(1, 12),
            Table(ingredients, style=GRID, repeatRows=1),
            Spacer(1, 24),
            Table(sign),
        ]
    )
    return out.getvalue()


async def sheet(order: ProductionOut, language: str) -> bytes:
    return await asyncio.to_thread(_sheet, order, language)  # CPU work off the event loop
