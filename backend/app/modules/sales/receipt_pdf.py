"""Receipt PDF on thermal paper width (FR-SAL-010). Text is drawn as plain strings (no
markup), so names cannot inject anything into the file."""

import asyncio
import io

from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas

from app.modules.sales.receipts import SaleReceiptOut

WORDS = {
    "en": {
        "bill": "BILL (not paid)",
        "subtotal": "Subtotal",
        "discount": "Discount",
        "service": "Service",
        "tax": "Tax",
        "rounding": "Rounding",
        "tip": "Tip",
        "total": "TOTAL",
        "change": "Change",
        "cashier": "Cashier",
    },
    "id": {
        "bill": "TAGIHAN (belum dibayar)",
        "subtotal": "Subtotal",
        "discount": "Diskon",
        "service": "Layanan",
        "tax": "Pajak",
        "rounding": "Pembulatan",
        "tip": "Tip",
        "total": "TOTAL",
        "change": "Kembali",
        "cashier": "Kasir",
    },
}
LINE = 4 * mm


def _money(v: int) -> str:
    return f"{v:,}".replace(",", ".")


Row = tuple[str, str, bool]  # left text, right text, bold
BLANK: Row = ("", "", False)


def _head(r: SaleReceiptOut, w: dict[str, str]) -> list[Row]:
    extra = (r.address or "").splitlines() + r.header.splitlines()
    rows: list[Row] = [(r.business, "", True), (r.outlet, "", False)]
    rows += [(part, "", False) for part in extra if part]
    rows += [BLANK, (r.number, r.at, False)]
    if r.label:
        rows.append((r.label, "", False))
    rows.append((f"{w['cashier']}: {r.cashier}", "", False))
    if not r.paid:
        rows.append((w["bill"], "", True))
    return rows


def _items(r: SaleReceiptOut, w: dict[str, str]) -> list[Row]:
    rows: list[Row] = []
    for ln in r.lines:
        rows.append((f"{ln.qty.normalize():f} x {ln.name}", _money(ln.total), False))
        rows += [(f"  + {m}", "", False) for m in ln.modifiers]
        if ln.discount:
            rows.append((f"  {w['discount']}", f"-{_money(ln.discount)}", False))
    return rows


def _sums(r: SaleReceiptOut, w: dict[str, str]) -> list[Row]:
    parts = (
        ("discount", -r.discount),
        ("service", r.service_charge),
        ("tax", r.tax),
        ("rounding", r.rounding),
        ("tip", r.tip),
    )
    rows: list[Row] = [(w["subtotal"], _money(r.subtotal), False)]
    rows += [(w[key], _money(value), False) for key, value in parts if value]
    rows.append((w["total"], _money(r.total), True))
    for p in r.payments:
        rows.append((p.method, _money(p.tendered or p.amount), False))
        if p.change:
            rows.append((w["change"], _money(p.change), False))
    return rows


def _rows(r: SaleReceiptOut, lang: str) -> list[Row]:
    w = WORDS.get(lang[:2], WORDS["en"])
    footer: list[Row] = [(part, "", False) for part in r.footer.splitlines() if part]
    return [*_head(r, w), BLANK, *_items(r, w), BLANK, *_sums(r, w), BLANK, *footer]


def _draw(r: SaleReceiptOut, lang: str) -> bytes:
    rows = _rows(r, lang)
    width = r.paper_mm * mm
    height = (len(rows) + 4) * LINE
    buf = io.BytesIO()
    c = Canvas(buf, pagesize=(width, height))
    y = height - 2 * LINE
    for left, right, bold in rows:
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 7)
        c.drawString(3 * mm, y, left[:48])
        if right:
            c.drawRightString(width - 3 * mm, y, right)
        y -= LINE
    c.showPage()
    c.save()
    return buf.getvalue()


async def receipt_pdf(r: SaleReceiptOut, lang: str) -> bytes:
    return await asyncio.to_thread(_draw, r, lang)  # keep drawing off the event loop
