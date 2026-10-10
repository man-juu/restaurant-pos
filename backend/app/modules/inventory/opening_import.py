"""Opening stock import (FR-IMP-001): one row per item and outlet; one opening document per
outlet, posted through the normal opening flow (same checks as the screen: units, expiry for
perishable items, no opening after movements). Undo posts reversals, never deletes."""

import uuid
from collections import defaultdict
from datetime import date

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access.policy import Principal
from app.core.errors import AppError
from app.core.imports.runner import Outcome
from app.core.models import Outlet
from app.modules.catalog.interface import item_ids_by_sku, unit_ids_by_code
from app.modules.inventory import opening
from app.modules.inventory.schemas import OpeningIn

COLUMNS = ("outlet", "sku", "qty", "unit", "unit_cost", "lot_code", "expiry_date")
REQUIRED = ("outlet", "sku", "qty", "unit", "unit_cost")
SAMPLE = [
    ["Main kitchen", "BEEF-150", "40", "pcs", "18000", "B-0101", "2026-12-31"],
    ["Main kitchen", "RICE", "25", "kg", "14000", "", ""],
]

Lookup = dict[str, uuid.UUID]


def _date(value: str) -> date | None:
    """Accept 2026-12-31 and 31/12/2026 (common in Indonesian sheets)."""
    if not value:
        return None
    if "/" in value:
        d, m, y = value.split("/")
        return date(int(y), int(m), int(d))
    return date.fromisoformat(value[:10])


def _line(row: dict[str, str], skus: Lookup, units: Lookup) -> dict[str, object]:
    for field, table, key in (("sku", skus, "sku"), ("unit", units, "unit")):
        if row.get(key, "").lower() not in table:
            raise KeyError(field)
    try:
        expiry = _date(row.get("expiry_date", ""))
    except ValueError:
        raise KeyError("expiry_date") from None
    return {
        "item_id": skus[row["sku"].lower()],
        "qty": row.get("qty"),
        "unit_id": units[row["unit"].lower()],
        "unit_cost": row.get("unit_cost"),
        "lot_code": row.get("lot_code") or None,
        "expiry_date": expiry,
    }


def builder(p: Principal, business_date: date):  # type: ignore[no-untyped-def]
    async def build(db: AsyncSession, rows: list[dict[str, str]]) -> Outcome:
        out = Outcome()
        skus, units = await item_ids_by_sku(db), await unit_ids_by_code(db)
        outlets = {
            n.lower(): i for i, n in (await db.execute(select(Outlet.id, Outlet.name))).all()
        }
        groups: dict[str, list[tuple[int, dict[str, str]]]] = defaultdict(list)
        for n, row in enumerate(rows, start=2):
            groups[row.get("outlet", "").lower()].append((n, row))
        for name, group in groups.items():
            await _one(db, p, outlets.get(name), group, (skus, units, business_date), out)
        return out

    return build


async def _one(
    db: AsyncSession,
    p: Principal,
    outlet_id: uuid.UUID | None,
    group: list[tuple[int, dict[str, str]]],
    ctx: tuple[Lookup, Lookup, date],
    out: Outcome,
) -> None:
    first_row = group[0][0]
    if outlet_id is None or not p.can_access_outlet(outlet_id):
        out.errors.append({"row": first_row, "field": "outlet"})  # unknown or not yours
        return
    skus, units, business_date = ctx
    lines = []
    for n, row in group:
        try:
            lines.append(_line(row, skus, units))
        except KeyError as exc:
            out.errors.append({"row": n, "field": str(exc.args[0])})
    if len(lines) != len(group):
        return
    try:
        data = OpeningIn.model_validate(
            {"outlet_id": outlet_id, "business_date": business_date, "lines": lines}
        )
        async with db.begin_nested():
            posted = await opening.post_opening(
                db, tenant_id=p.tenant_id, user_id=p.user_id, data=data
            )
        out.created.append(posted.doc_id)
    except ValidationError as exc:
        out.errors.extend({"row": first_row, "field": str(e["loc"][-1])} for e in exc.errors())
    except AppError as exc:
        out.errors.append({"row": first_row, "field": exc.code})


async def undo(db: AsyncSession, p: Principal, doc_ids: list[uuid.UUID]) -> int:
    for doc_id in doc_ids:
        p.require_outlet(await opening.document_outlet(db, doc_id))
        await opening.reverse_opening(db, tenant_id=p.tenant_id, user_id=p.user_id, doc_id=doc_id)
    return len(doc_ids)
