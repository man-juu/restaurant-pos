"""Delivery note PDF (FR-TRF-002): every batch shipped with lot and expiry. Cells are plain
strings in a ReportLab table (no markup is parsed), so names cannot inject anything."""

import asyncio
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Spacer, Table, TableStyle

HEAD = {
    "en": ["Item", "Lot", "Expiry", "Qty", "Received"],
    "id": ["Barang", "Lot", "Kedaluwarsa", "Jumlah", "Diterima"],
}
TITLE = {"en": "Delivery note", "id": "Surat jalan"}


def _render(title: str, facts: list[list[str]], rows: list[list[str]], lang: str) -> bytes:
    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=A4, title=title)
    table = Table([HEAD.get(lang, HEAD["en"]), *rows], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1d2833")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c3cfda")),
                ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
            ]
        )
    )
    head = Table([[f"{TITLE.get(lang, TITLE['en'])} {title}"], *facts])
    head.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]))
    doc.build([head, Spacer(1, 12), table])
    return out.getvalue()


async def render(title: str, facts: list[list[str]], rows: list[list[str]], lang: str) -> bytes:
    return await asyncio.to_thread(_render, title, facts, rows, lang)
