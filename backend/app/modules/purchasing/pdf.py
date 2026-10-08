"""Purchase order PDF (FR-PUR-010) with ReportLab. Built in memory from our own data only:
no HTML or user markup is rendered, so a vendor name cannot inject anything into the file."""

import asyncio
import io
from dataclasses import dataclass

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Outlet, Tenant
from app.modules.catalog.interface import item_names
from app.modules.purchasing.models import PurchaseOrder, Vendor
from app.modules.purchasing.orders import order_lines


@dataclass(frozen=True)
class PdfData:
    title: str
    facts: list[tuple[str, str]]
    rows: list[list[str]]
    total: str


def _money(value: int, currency: str) -> str:
    return f"{currency} {value:,}".replace(",", ".")  # IDR style grouping, no decimals


async def order_pdf_data(db: AsyncSession, po: PurchaseOrder, language: str) -> PdfData:
    tenant = await db.get(Tenant, po.tenant_id)
    vendor = await db.get(Vendor, po.vendor_id)
    outlet = await db.scalar(select(Outlet.name).where(Outlet.id == po.outlet_id))
    lines = await order_lines(db, po.id)
    names = await item_names(db, po.tenant_id, language, {ln.item_id for ln in lines})
    currency = tenant.currency if tenant else ""
    rows = [
        [
            names[ln.item_id].sku,
            names[ln.item_id].name,
            f"{ln.qty.normalize():f}",
            _money(ln.unit_price, currency),
            _money(int(ln.qty * ln.unit_price), currency),
        ]
        for ln in lines
    ]
    facts = [
        ("Buyer", tenant.name if tenant else ""),
        ("Deliver to", outlet or ""),
        ("Vendor", vendor.name if vendor else ""),
        ("Order date", po.order_date.isoformat()),
        ("Expected", po.expected_date.isoformat() if po.expected_date else "-"),
    ]
    return PdfData(
        f"Purchase order {po.number or '(draft)'}", facts, rows, _money(po.total, currency)
    )


def _esc(text: str) -> str:
    """ReportLab paragraphs read a small markup language: escape it so text stays text."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _render(data: PdfData) -> bytes:
    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm)
    styles = getSampleStyleSheet()
    facts = Table([[k, _esc(v)] for k, v in data.facts], colWidths=[35 * mm, 120 * mm])
    head = [["SKU", "Item", "Qty", "Price", "Line total"]]
    body = [
        [Paragraph(_esc(c), styles["BodyText"]) if i == 1 else c for i, c in enumerate(r)]
        for r in data.rows
    ]
    lines = Table(head + body + [["", "", "", "Total", data.total]], repeatRows=1)
    lines.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1d2833")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -2), 0.25, colors.HexColor("#c3cfda")),
                ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ]
        )
    )
    doc.build([Paragraph(_esc(data.title), styles["Title"]), facts, Spacer(1, 6 * mm), lines])
    return out.getvalue()


async def render(data: PdfData) -> bytes:
    return await asyncio.to_thread(_render, data)  # CPU work off the event loop
