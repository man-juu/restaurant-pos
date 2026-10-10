"""Stock reports (FR-RPT-004, FR-INV-015) from the ledger. Values need catalog.cost.view.

Variance: what recipes say was used (sales and production consumption) against what the
counts found missing or extra (count corrections) and what was thrown away (waste). A count
correction of -2 kg means 2 kg more left the shelf than the recipes and logs explain."""

import uuid
from collections import defaultdict
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Outlet
from app.core.reports import Period, Report, build
from app.modules.catalog.interface import item_names
from app.modules.inventory.doc_models import WasteLog
from app.modules.inventory.models import StockBalance, StockBatch, StockMovement

COLUMNS = {
    "purchase_receipt": "received",
    "production_output": "produced",
    "transfer_in": "transfer_in",
    "opening_balance": "opening",
    "sale_consumption": "sold",
    "production_consumption": "used_in_production",
    "transfer_out": "transfer_out",
    "waste": "waste",
    "vendor_return": "returned",
    "adjustment": "adjusted",
    "count_correction": "count_correction",
}


def _num(q: Decimal) -> str:
    return f"{q.normalize():f}"


def _in_period(stmt: Any, period: Period, outlets: list[uuid.UUID] | None) -> Any:
    stmt = stmt.where(
        StockMovement.business_date >= period.date_from,
        StockMovement.business_date <= period.date_to,
    )
    return stmt if outlets is None else stmt.where(StockMovement.outlet_id.in_(outlets))


async def movements(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    period: Period,
    outlets: list[uuid.UUID] | None,
    *,
    language: str,
    show_cost: bool,
) -> Report:
    """Per item: quantity in and out by movement type over the period (base units)."""
    stmt = _in_period(
        select(
            StockMovement.item_id,
            StockMovement.movement_type,
            func.sum(StockMovement.qty),
            func.sum(StockMovement.value),
        ).group_by(StockMovement.item_id, StockMovement.movement_type),
        period,
        outlets,
    )
    per: dict[uuid.UUID, dict[str, Any]] = defaultdict(dict)
    for item_id, kind, qty, value in (await db.execute(stmt)).all():
        per[item_id][COLUMNS[kind]] = _num(qty)
        if show_cost:
            per[item_id]["net_value"] = per[item_id].get("net_value", 0) + int(value)
    names = await item_names(db, tenant_id, language, per)
    rows = [{"item": names[i].name, "unit": names[i].unit_code, **v} for i, v in per.items()]
    rows.sort(key=lambda r: r["item"].lower())
    cols = ["item", "unit", *COLUMNS.values()] + (["net_value"] if show_cost else [])
    return build(cols, rows)


async def waste(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    period: Period,
    outlets: list[uuid.UUID] | None,
    *,
    language: str,
    show_cost: bool,
) -> Report:
    """Waste by item and reason (reversed waste logs excluded)."""
    stmt = _in_period(
        select(
            StockMovement.item_id,
            WasteLog.reason_code,
            func.sum(-StockMovement.qty),
            func.sum(-StockMovement.value),
        )
        .join(WasteLog, WasteLog.id == StockMovement.doc_id)
        .where(StockMovement.movement_type == "waste", WasteLog.status == "posted")
        .group_by(StockMovement.item_id, WasteLog.reason_code),
        period,
        outlets,
    )
    found = (await db.execute(stmt)).all()
    names = await item_names(db, tenant_id, language, {r[0] for r in found})
    rows = []
    for item_id, reason, qty, value in found:
        row: dict[str, Any] = {
            "item": names[item_id].name,
            "unit": names[item_id].unit_code,
            "reason": reason,
            "qty": _num(qty),
        }
        if show_cost:
            row["value"] = int(value)
        rows.append(row)
    rows.sort(key=lambda r: (-r.get("value", 0), r["item"].lower()))
    total = {"value": sum(r.get("value", 0) for r in rows)} if show_cost else {}
    return build(["item", "unit", "reason", "qty"] + (["value"] if show_cost else []), rows, total)


async def expiry(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    period: Period,
    outlets: list[uuid.UUID] | None,
    *,
    language: str,
) -> Report:
    """Batches on hand that expire on or before the end of the period (already expired too)."""
    stmt = (
        select(
            Outlet.name,
            StockBalance.item_id,
            StockBatch.lot_code,
            StockBatch.expiry_date,
            StockBalance.qty,
        )
        .join(StockBatch, StockBatch.id == StockBalance.batch_id)
        .join(Outlet, Outlet.id == StockBalance.outlet_id)
        .where(StockBalance.qty > 0, StockBatch.expiry_date <= period.date_to)
        .order_by(StockBatch.expiry_date)
    )
    if outlets is not None:
        stmt = stmt.where(StockBalance.outlet_id.in_(outlets))
    found = (await db.execute(stmt)).all()
    names = await item_names(db, tenant_id, language, {r[1] for r in found})
    rows = [
        {
            "outlet": o,
            "item": names[i].name,
            "lot": lot or "",
            "expiry": e.isoformat() if e else "",
            "qty": _num(q),
            "unit": names[i].unit_code,
        }
        for o, i, lot, e, q in found
    ]
    return build(["outlet", "item", "lot", "expiry", "qty", "unit"], rows)


async def variance(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    period: Period,
    outlets: list[uuid.UUID] | None,
    *,
    language: str,
    show_cost: bool,
) -> Report:
    """FR-INV-015: theoretical use vs what counts and waste show, per item."""
    kinds = ("sale_consumption", "production_consumption", "waste", "count_correction")
    stmt = _in_period(
        select(
            StockMovement.item_id,
            StockMovement.movement_type,
            func.sum(StockMovement.qty),
            func.sum(StockMovement.value),
        )
        .where(StockMovement.movement_type.in_(kinds))
        .group_by(StockMovement.item_id, StockMovement.movement_type),
        period,
        outlets,
    )
    per: dict[uuid.UUID, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for item_id, kind, qty, value in (await db.execute(stmt)).all():
        per[item_id][kind] += qty
        per[item_id][f"{kind}_value"] += value
    names = await item_names(db, tenant_id, language, per)
    rows = [_variance_row(names[i].name, names[i].unit_code, v, show_cost) for i, v in per.items()]
    rows.sort(key=lambda r: (r.get("variance_value", 0), r["item"].lower()))
    cols = ["item", "unit", "theoretical", "waste", "count_difference", "variance_pct"]
    return build(cols + (["variance_value"] if show_cost else []), rows)


def _variance_row(name: str, unit: str, v: dict[str, Decimal], show_cost: bool) -> dict[str, Any]:
    theoretical = -(v["sale_consumption"] + v["production_consumption"])
    diff = v["count_correction"]
    row: dict[str, Any] = {
        "item": name,
        "unit": unit,
        "theoretical": _num(theoretical),
        "waste": _num(-v["waste"]),
        "count_difference": _num(diff),
        "variance_pct": f"{diff * 100 / theoretical:.1f}" if theoretical else None,
    }
    if show_cost:
        row["variance_value"] = int(v["count_correction_value"])
    return row
