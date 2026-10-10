"""Printable shelf-life labels (FR-PRD-007) and the daily prep list (FR-PRD-008), drawn
with ReportLab from our own data. Text is drawn as plain strings (no markup is parsed), so
an item name cannot inject anything into the file."""

import asyncio
import io
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

from app.modules.production.schemas import PrepRow

LABEL_SIZE = (60 * mm, 40 * mm)  # common thermal label roll
MAX_COPIES = 50

WORDS: dict[str, dict[str, Any]] = {
    "en": {
        "lot": "Lot",
        "made": "Made",
        "use_by": "USE BY",
        "storage": "Storage",
        "allergens": "Allergens",
        "frozen": "Frozen",
        "chilled": "Chilled",
        "dry": "Dry",
        "prep": "Prep list",
        "head": ["Item", "Par", "On hand", "Requested", "Planned", "To make", "Done"],
    },
    "id": {
        "lot": "Lot",
        "made": "Dibuat",
        "use_by": "GUNAKAN SEBELUM",
        "storage": "Simpan",
        "allergens": "Alergen",
        "frozen": "Beku",
        "chilled": "Dingin",
        "dry": "Kering",
        "prep": "Daftar persiapan",
        "head": ["Barang", "Par", "Stok", "Diminta", "Direncanakan", "Dibuat", "Selesai"],
    },
}


def words(language: str) -> dict[str, Any]:
    return WORDS.get(language[:2], WORDS["en"])


@dataclass(frozen=True)
class Label:
    name: str
    lot: str
    made_at: datetime | None
    use_by: date | None
    storage: str | None
    allergens: tuple[str, ...]
    timezone: str
    language: str


def _qty(q: Decimal) -> str:
    return f"{q.normalize():f}"


def _cut(text: str, size: int) -> str:
    return text if len(text) <= size else text[: size - 1] + "…"


def _label_lines(lb: Label) -> list[tuple[str, int, str]]:
    """(font, size, text) from top to bottom."""
    w = words(lb.language)
    made = (
        lb.made_at.astimezone(ZoneInfo(lb.timezone)).strftime("%d/%m/%Y %H:%M")
        if lb.made_at
        else "-"
    )
    out = [("Helvetica-Bold", 11, _cut(lb.name, 30)), ("Helvetica", 8, f"{w['lot']}: {lb.lot}")]
    out.append(("Helvetica", 8, f"{w['made']}: {made}"))
    if lb.use_by:
        out.append(("Helvetica-Bold", 10, f"{w['use_by']}: {lb.use_by.strftime('%d/%m/%Y')}"))
    if lb.storage:
        out.append(("Helvetica", 8, f"{w['storage']}: {w.get(lb.storage, lb.storage)}"))
    if lb.allergens:
        out.append(("Helvetica", 7, _cut(f"{w['allergens']}: {', '.join(lb.allergens)}", 45)))
    return out


def _labels(lb: Label, copies: int) -> bytes:
    out = io.BytesIO()
    pdf = Canvas(out, pagesize=LABEL_SIZE)
    for _ in range(copies):
        y = LABEL_SIZE[1] - 8 * mm
        for font, size, text in _label_lines(lb):
            pdf.setFont(font, size)
            pdf.drawString(4 * mm, y, text)
            y -= size + 3
        pdf.showPage()
    pdf.save()
    return out.getvalue()


def _prep(title: str, rows: list[PrepRow], language: str) -> bytes:
    w = words(language)
    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=A4, title=title)
    head = [list(w["head"])]
    body = [
        [
            _cut(r.name, 40),
            f"{_qty(r.par_qty)} {r.unit_code}",
            _qty(r.on_hand),
            _qty(r.requested),
            _qty(r.planned),
            f"{_qty(r.suggested)} {r.unit_code}",
            "[  ]",
        ]
        for r in rows
    ]
    table = Table(head + body, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1d2833")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c3cfda")),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ]
        )
    )
    title_table = Table([[title]], style=[("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold")])
    doc.build([title_table, table])
    return out.getvalue()


async def labels(lb: Label, copies: int) -> bytes:
    return await asyncio.to_thread(_labels, lb, copies)  # CPU work off the event loop


async def prep(title: str, rows: list[PrepRow], language: str) -> bytes:
    return await asyncio.to_thread(_prep, title, rows, language)
