"""Announce sales documents to finance (FR-FIN-003) and let it read what it needs."""

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import Event, publish
from app.modules.catalog.interface import channel_kind
from app.modules.sales.events import DOCUMENT_POSTED, DOCUMENT_REVERSED
from app.modules.sales.models import Payment, SalesDocument


async def posted(db: AsyncSession, doc: SalesDocument, user_id: uuid.UUID | None) -> None:
    await publish(db, Event(DOCUMENT_POSTED, doc.tenant_id, user_id, {"document_id": doc.id}))


async def reversed_(db: AsyncSession, doc: SalesDocument, user_id: uuid.UUID | None) -> None:
    await publish(db, Event(DOCUMENT_REVERSED, doc.tenant_id, user_id, {"document_id": doc.id}))


@dataclass(frozen=True)
class DocumentMoney:
    """A sales document's money, for its journal."""

    id: uuid.UUID
    number: str
    outlet_id: uuid.UUID
    business_date: date
    channel_kind: str  # dine_in, takeaway, platform, wholesale
    subtotal: int
    discount: int
    service_charge: int
    tax: int
    tip: int
    rounding: int
    total: int  # subtotal - discount + service charge + tax
    paid: dict[str, int]  # payment method kind -> amount; empty for a daily sales entry
    source: str = "pos"  # pos, manual_day, ...
    status: str = "posted"


async def document_money(db: AsyncSession, document_id: uuid.UUID) -> DocumentMoney:
    doc = await db.get(SalesDocument, document_id)
    if doc is None:
        raise LookupError(document_id)
    stmt = (
        select(Payment.kind, func.sum(Payment.amount))
        .where(Payment.document_id == doc.id)
        .group_by(Payment.kind)
    )
    paid = {k: int(v) for k, v in (await db.execute(stmt)).all()}
    return DocumentMoney(
        id=doc.id,
        number=doc.number,
        outlet_id=doc.outlet_id,
        business_date=doc.business_date,
        channel_kind=await channel_kind(db, doc.channel_id),
        subtotal=doc.subtotal,
        discount=doc.discount,
        service_charge=doc.service_charge,
        tax=doc.tax,
        tip=doc.tip,
        rounding=doc.rounding,
        total=doc.total,
        paid=paid,
        source=doc.source,
        status=doc.status,
    )


async def tenders_of_kind(
    db: AsyncSession, document_id: uuid.UUID, kind: str
) -> list[tuple[str | None, int]]:
    """(reference, amount) of each payment of this kind on a document, e.g. voucher codes."""
    stmt = select(Payment.reference, Payment.amount).where(
        Payment.document_id == document_id, Payment.kind == kind
    )
    return [(ref, int(amount)) for ref, amount in (await db.execute(stmt)).all()]
