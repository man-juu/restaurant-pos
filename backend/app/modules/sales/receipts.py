"""Receipts (FR-SAL-010): the same content for the PDF and for Bluetooth thermal printers
(the browser turns it into ESC/POS), so both always agree. Before payment the same view is
a bill to check ("pre-bill")."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import cast
from zoneinfo import ZoneInfo

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Outlet, Tenant, User
from app.core.settings import service as settings
from app.core.settings.schemas import PaymentMethodSettings, ReceiptSettings
from app.modules.sales.models import Payment, PosOrder, SalesDocument
from app.modules.sales.orders import lines_of, totals


class ReceiptLine(BaseModel):
    name: str
    qty: Decimal
    unit_price: int
    total: int
    modifiers: list[str]
    discount: int


class ReceiptPayment(BaseModel):
    method: str
    amount: int
    tendered: int | None
    change: int


class SaleReceiptOut(BaseModel):
    business: str
    outlet: str
    address: str | None
    header: str
    footer: str
    paper_mm: int
    number: str
    label: str | None
    at: str  # local date and time at the outlet, already formatted
    cashier: str
    paid: bool
    lines: list[ReceiptLine]
    subtotal: int
    discount: int
    service_charge: int
    tax: int
    rounding: int
    tip: int
    total: int  # what the customer pays: total + rounding + tip
    payments: list[ReceiptPayment]


async def _method_names(db: AsyncSession, tenant_id: uuid.UUID) -> dict[str, str]:
    found = cast(
        PaymentMethodSettings, await settings.get_setting(db, tenant_id, "payment_methods")
    )
    return {m.code: m.name for m in found.methods}


async def _payments(db: AsyncSession, order: PosOrder) -> list[ReceiptPayment]:
    if order.document_id is None:
        return []
    names = await _method_names(db, order.tenant_id)
    rows = await db.scalars(
        select(Payment).where(Payment.document_id == order.document_id).order_by(Payment.paid_at)
    )
    return [
        ReceiptPayment(
            method=names.get(r.method_code, r.method_code),
            amount=r.amount,
            tendered=r.tendered,
            change=r.change,
        )
        for r in rows
    ]


async def receipt(db: AsyncSession, order: PosOrder, language: str) -> SaleReceiptOut:
    tenant = cast(Tenant, await db.get(Tenant, order.tenant_id))
    outlet = cast(Outlet, await db.get(Outlet, order.outlet_id))
    conf = cast(ReceiptSettings, await settings.get_setting(db, order.tenant_id, "receipt"))
    lines = [ln for ln in await lines_of(db, order, language) if ln.status != "void"]
    t = await totals(db, order, lines)
    doc = await db.get(SalesDocument, order.document_id) if order.document_id else None
    rounding, tip = (doc.rounding, doc.tip) if doc else (0, 0)
    who = order.paid_by or order.created_by
    cashier = await db.scalar(select(User.name).where(User.id == who))
    when: datetime = order.paid_at or order.created_at
    return SaleReceiptOut(
        business=tenant.name,
        outlet=outlet.name,
        address=outlet.address,
        header=conf.header,
        footer=conf.footer,
        paper_mm=conf.paper_mm,
        number=order.number,
        label=order.label,
        at=when.astimezone(ZoneInfo(outlet.timezone)).strftime("%d/%m/%Y %H:%M"),
        cashier=cashier or "",
        paid=order.status in ("paid", "refunded"),
        lines=[
            ReceiptLine(
                name=ln.name,
                qty=ln.qty,
                unit_price=ln.unit_price,
                total=ln.line_total,
                modifiers=[m.name for m in ln.modifiers],
                discount=ln.discount,
            )
            for ln in lines
        ],
        subtotal=t.gross,
        discount=t.discount,
        service_charge=t.taxed.service_charge,
        tax=t.taxed.tax_total,
        rounding=rounding,
        tip=tip,
        total=t.taxed.total + rounding + tip,
        payments=await _payments(db, order),
    )
