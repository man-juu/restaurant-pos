"""Reading a sales day (FR-SAL-002): status and its live documents with lines."""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.interface import item_names
from app.modules.sales.models import SalesDay, SalesDocument, SalesLine
from app.modules.sales.schemas import DayOut, SalesDocOut, SalesLineOut


async def day_out(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    outlet_id: uuid.UUID,
    on: date,
    *,
    language: str,
    show_cost: bool,
) -> DayOut:
    day = await db.scalar(
        select(SalesDay).where(SalesDay.outlet_id == outlet_id, SalesDay.business_date == on)
    )
    docs = list(
        await db.scalars(
            select(SalesDocument)
            .where(
                SalesDocument.outlet_id == outlet_id,
                SalesDocument.business_date == on,
                SalesDocument.status == "posted",
            )
            .order_by(SalesDocument.created_at)
        )
    )
    lines = list(
        await db.scalars(select(SalesLine).where(SalesLine.document_id.in_([d.id for d in docs])))
    )
    names = await item_names(db, tenant_id, language, {ln.item_id for ln in lines})
    out = []
    for d in docs:
        rows = [
            SalesLineOut(
                item_id=ln.item_id,
                name=names[ln.item_id].name,
                qty=ln.qty,
                unit_price=ln.unit_price,
                platform_code=ln.platform_code,
            )
            for ln in lines
            if ln.document_id == d.id
        ]
        fields = {k: getattr(d, k) for k in SalesDocOut.model_fields if k not in ("lines", "cost")}
        out.append(SalesDocOut(**fields, cost=d.cost if show_cost else None, lines=rows))
    return DayOut(
        outlet_id=outlet_id,
        business_date=on,
        status=day.status if day else "open",
        documents=out,
    )
