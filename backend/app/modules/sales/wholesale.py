"""Wholesale invoices to business customers (FR-SAL-011) and their receivables (FR-FIN-006).

An invoice is a sales document on a wholesale channel: prices from that channel's list (or
agreed per line), tax by the tenant's rules, stock out at once, journaled by finance as a
receivable. Customers pay later, in parts; payments are append-only and reversible. An
unpaid invoice entered by mistake is voided: stock comes back and the journal reverses."""

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.aging import AgingRow, age
from app.core.customers import service as customers
from app.core.customers.models import Customer
from app.core.errors import ConflictError, NotFoundError
from app.core.events import Event, publish
from app.core.settings import service as settings
from app.core.settings.pricing import calculate
from app.core.settings.schemas import (
    PaymentMethodSettings,
    ServiceChargeSettings,
    TaxSettings,
    WholesaleSettings,
)
from app.modules.catalog.interface import channel_code, channel_kind
from app.modules.inventory.interface import Posting, reverse, visible_outlet
from app.modules.sales import doc_events
from app.modules.sales.models import SalesDocument, SalesLine
from app.modules.sales.schemas import DayEntryIn
from app.modules.sales.service import _money, _prices, _resolve, consume_for_sale
from app.modules.sales.wholesale_models import Receivable, ReceivablePayment
from app.modules.sales.wholesale_schemas import (
    InvoiceIn,
    InvoiceLineOut,
    InvoiceOut,
    ReceiptIn,
)

DOC = "wholesale_invoice"
RECEIVABLE_PAID = "sales.receivable.paid"  # finance: Dr cash or bank, Cr receivable


async def _audit(
    db: AsyncSession, r: Receivable, user_id: uuid.UUID, verb: str, extra: dict[str, object]
) -> None:
    await audit.record(
        db,
        tenant_id=r.tenant_id,
        user_id=user_id,
        outlet_id=r.outlet_id,
        action=f"sales.invoice.{verb}",
        target_type="receivable",
        target_id=r.id,
        summary=extra,
    )


async def create_invoice(
    db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID, data: InvoiceIn
) -> Receivable:
    await visible_outlet(db, data.outlet_id)
    if await channel_kind(db, data.channel_id) != "wholesale":
        raise ConflictError("not_a_wholesale_channel")
    customer = await customers.get(db, data.customer_id)
    if customer.erased_at is not None:
        raise ConflictError("customer_erased")
    entry = DayEntryIn(
        outlet_id=data.outlet_id,
        business_date=data.invoice_date,
        channel_id=data.channel_id,
        lines=data.lines,
    )
    rows = await _resolve(db, data.channel_id, data.lines)
    prices = await _prices(db, entry, rows)
    subtotal = sum(_money(ln.qty, p) for (_, ln), p in zip(rows, prices, strict=True))
    tax = cast(TaxSettings, await settings.get_setting(db, tenant_id, "tax"))
    sc = cast(ServiceChargeSettings, await settings.get_setting(db, tenant_id, "service_charge"))
    totals = calculate(
        [subtotal],
        tax=tax,
        service_charge=sc,
        channel=await channel_code(db, data.channel_id),
        outlet_id=data.outlet_id,
    )
    number = await settings.allocate_number(
        db, tenant_id=tenant_id, doc_type=DOC, on=data.invoice_date
    )
    doc = SalesDocument(
        tenant_id=tenant_id,
        number=number,
        outlet_id=data.outlet_id,
        channel_id=data.channel_id,
        business_date=data.invoice_date,
        source="wholesale",
        status="posted",
        subtotal=subtotal,
        service_charge=totals.service_charge,
        tax=totals.tax_total,
        total=totals.total,
        cost=0,
        note=data.note,
        created_by=user_id,
    )
    db.add(doc)
    await db.flush()
    qty: dict[uuid.UUID, Decimal] = {}
    for item_id, ln in rows:
        qty[item_id] = qty.get(item_id, Decimal(0)) + ln.qty
    used = await consume_for_sale(db, doc, qty, user_id, DOC)
    db.add_all(
        SalesLine(
            tenant_id=tenant_id,
            document_id=doc.id,
            item_id=i,
            qty=ln.qty,
            unit_price=p,
            bom_id=used.get(i),
        )
        for (i, ln), p in zip(rows, prices, strict=True)
    )
    terms = cast(WholesaleSettings, await settings.get_setting(db, tenant_id, "wholesale"))
    due = data.due_date or data.invoice_date + timedelta(days=terms.payment_terms_days)
    if due < data.invoice_date:
        raise ConflictError("due_before_invoice")
    row = Receivable(
        tenant_id=tenant_id,
        document_id=doc.id,
        customer_id=customer.id,
        outlet_id=data.outlet_id,
        invoice_date=data.invoice_date,
        due_date=due,
        total=doc.total,
        created_by=user_id,
    )
    db.add(row)
    await db.flush()
    await doc_events.posted(db, doc, user_id)
    await _audit(db, row, user_id, "create", {"number": number, "total": doc.total})
    return row


async def get(db: AsyncSession, receivable_id: uuid.UUID, *, lock: bool = False) -> Receivable:
    row = await db.get(Receivable, receivable_id, with_for_update=lock)
    if row is None:
        raise NotFoundError("invoice_not_found")
    return row


def _settle(r: Receivable) -> None:
    r.status = "paid" if r.paid >= r.total else "partially_paid" if r.paid else "open"


async def _kind(db: AsyncSession, tenant_id: uuid.UUID, code: str) -> str:
    methods = cast(
        PaymentMethodSettings, await settings.get_setting(db, tenant_id, "payment_methods")
    )
    kinds = {m.code: m.kind for m in methods.methods if m.active}
    if code not in kinds:
        raise NotFoundError("payment_method_not_found")
    return kinds[code]


async def _announce(
    db: AsyncSession, r: Receivable, user_id: uuid.UUID, day: date, amount: int, kind: str
) -> None:
    data = {
        "receivable_id": r.id,
        "outlet_id": r.outlet_id,
        "paid_on": day.isoformat(),
        "amount": amount,
        "method_kind": kind,
    }
    await publish(db, Event(RECEIVABLE_PAID, r.tenant_id, user_id, data))


async def receive(db: AsyncSession, r: Receivable, *, user_id: uuid.UUID, data: ReceiptIn) -> None:
    if r.status in ("paid", "void"):
        raise ConflictError("invoice_not_open", details={"status": r.status})
    if data.amount > r.total - r.paid:
        raise ConflictError("payment_exceeds_balance", details={"balance": r.total - r.paid})
    kind = await _kind(db, r.tenant_id, data.method)
    db.add(
        ReceivablePayment(
            tenant_id=r.tenant_id, receivable_id=r.id, created_by=user_id, **data.model_dump()
        )
    )
    r.paid += data.amount
    _settle(r)
    await db.flush()
    await _announce(db, r, user_id, data.paid_on, data.amount, kind)
    await _audit(db, r, user_id, "payment", {"amount": data.amount, "method": data.method})


async def reverse_payment(
    db: AsyncSession, r: Receivable, payment_id: uuid.UUID, *, user_id: uuid.UUID, on: date
) -> None:
    original = await db.get(ReceivablePayment, payment_id)
    if original is None or original.receivable_id != r.id or original.amount < 0:
        raise NotFoundError("payment_not_found")
    if await db.scalar(
        select(ReceivablePayment.id).where(ReceivablePayment.reverses_id == original.id)
    ):
        raise ConflictError("already_reversed")
    db.add(
        ReceivablePayment(
            tenant_id=r.tenant_id,
            receivable_id=r.id,
            paid_on=on,
            amount=-original.amount,
            method=original.method,
            reference=original.reference,
            reverses_id=original.id,
            created_by=user_id,
        )
    )
    r.paid -= original.amount
    _settle(r)
    await db.flush()
    await _announce(
        db, r, user_id, on, -original.amount, await _kind(db, r.tenant_id, original.method)
    )
    await _audit(db, r, user_id, "payment_reverse", {"amount": original.amount})


async def void(db: AsyncSession, r: Receivable, *, user_id: uuid.UUID) -> None:
    """An invoice entered by mistake, before any payment: stock back, journal reversed."""
    if r.status == "void":
        raise ConflictError("already_void")
    if r.paid:
        raise ConflictError("invoice_has_payments")
    doc = cast(SalesDocument, await db.get(SalesDocument, r.document_id, with_for_update=True))
    p = Posting(r.tenant_id, r.outlet_id, user_id, DOC, doc.id, doc.business_date)
    try:
        await reverse(db, p, DOC, doc.id)
    except ConflictError as err:  # untracked items only: no stock was taken
        if err.code != "nothing_to_reverse":
            raise
    doc.status, r.status = "reversed", "void"
    await db.flush()
    await doc_events.reversed_(db, doc, user_id)
    await _audit(db, r, user_id, "void", {"number": doc.number})


async def out(db: AsyncSession, rows: list[Receivable]) -> list[InvoiceOut]:
    docs = {
        d.id: d
        for d in await db.scalars(
            select(SalesDocument).where(SalesDocument.id.in_({r.document_id for r in rows}))
        )
    }
    people = {
        c.id: c
        for c in await db.scalars(
            select(Customer).where(Customer.id.in_({r.customer_id for r in rows}))
        )
    }
    lines = list(await db.scalars(select(SalesLine).where(SalesLine.document_id.in_(docs))))
    return [
        InvoiceOut(
            id=r.id,
            document_id=r.document_id,
            number=docs[r.document_id].number,
            customer_id=r.customer_id,
            customer_name=people[r.customer_id].name,
            outlet_id=r.outlet_id,
            invoice_date=r.invoice_date,
            due_date=r.due_date,
            subtotal=docs[r.document_id].subtotal,
            tax=docs[r.document_id].tax,
            total=r.total,
            paid=r.paid,
            balance=0 if r.status == "void" else r.total - r.paid,
            status=r.status,
            lines=[
                InvoiceLineOut(item_id=ln.item_id, qty=str(ln.qty), unit_price=ln.unit_price)
                for ln in lines
                if ln.document_id == r.document_id
            ],
        )
        for r in rows
    ]


async def aging(db: AsyncSession, today: date, outlet_ids: set[uuid.UUID] | None) -> list[AgingRow]:
    stmt = select(Receivable).where(Receivable.status.in_(("open", "partially_paid")))
    if outlet_ids is not None:
        stmt = stmt.where(Receivable.outlet_id.in_(outlet_ids))
    rows = list(await db.scalars(stmt.limit(5000)))
    sums = age(((r.customer_id, r.due_date, r.total - r.paid) for r in rows), today)
    names = {c.id: c.name for c in await db.scalars(select(Customer).where(Customer.id.in_(sums)))}
    return sorted(
        (
            AgingRow(party_id=p, party_name=names.get(p, ""), total=sum(b.values()), **b)
            for p, b in sums.items()
        ),
        key=lambda a: -a.total,
    )
