"""Printable labels (FR-INV-019): batch labels with a QR code (item, lot, use-by) and item
labels with a Code128 barcode of the SKU. A grid of 3 x 8 labels per A4 page, which fits
common sticker sheets; plain strings only, like the other PDFs."""

import asyncio
import io
from dataclasses import dataclass
from datetime import date

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode import code128, qr
from reportlab.graphics.shapes import Drawing
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

COLS, ROWS = 3, 8
WORDS = {
    "en": {"use_by": "Use by", "lot": "Lot"},
    "id": {"use_by": "Gunakan sebelum", "lot": "Lot"},
}


@dataclass(frozen=True)
class Label:
    title: str  # item name
    code: str  # what the scanner reads
    lot: str | None = None
    use_by: date | None = None
    qr: bool = True  # batch labels; item labels use a linear barcode


def _cut(text: str, size: int) -> str:
    return text if len(text) <= size else text[: size - 1] + "…"


def _draw(c: canvas.Canvas, label: Label, x: float, y: float, words: dict[str, str]) -> None:
    h = A4[1] / ROWS
    if label.qr:
        widget = qr.QrCodeWidget(label.code)
        x0, y0, x1, y1 = widget.getBounds()
        side = h - 8 * mm
        d = Drawing(side, side, transform=[side / (x1 - x0), 0, 0, side / (y1 - y0), 0, 0])
        d.add(widget)
        renderPDF.draw(d, c, x + 3 * mm, y + 4 * mm)
        text_x = x + side + 5 * mm
    else:
        bar = code128.Code128(label.code, barHeight=h / 3, barWidth=0.3 * mm)
        bar.drawOn(c, x + 3 * mm, y + 4 * mm)
        text_x = x + 3 * mm
    c.setFont("Helvetica-Bold", 8)
    c.drawString(text_x, y + h - 7 * mm, _cut(label.title, 24))
    c.setFont("Helvetica", 7)
    line = y + h - 11 * mm
    if label.lot:
        c.drawString(text_x, line, f"{words['lot']}: {_cut(label.lot, 20)}")
        line -= 3.5 * mm
    if label.use_by:
        c.drawString(text_x, line, f"{words['use_by']}: {label.use_by.isoformat()}")
    if not label.qr:
        c.drawString(text_x, y + 1.5 * mm, _cut(label.code, 30))


def _sheet(labels: list[Label], language: str) -> bytes:
    words = WORDS.get(language[:2], WORDS["en"])
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4[0] / COLS, A4[1] / ROWS
    for n, label in enumerate(labels):
        if n and n % (COLS * ROWS) == 0:
            c.showPage()
        slot = n % (COLS * ROWS)
        _draw(c, label, (slot % COLS) * w, A4[1] - (slot // COLS + 1) * h, words)
    c.save()
    return buf.getvalue()


async def render(labels: list[Label], language: str) -> bytes:
    return await asyncio.to_thread(_sheet, labels, language)
