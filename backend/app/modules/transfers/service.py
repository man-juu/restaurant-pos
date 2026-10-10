"""Transfers (FR-TRF-001 to 004): requested by the receiving outlet -> approved by the source
(quantities may change) -> shipped (stock leaves the source FEFO, batches recorded) ->
received (the same batches arrive at the same cost; shortage or damage becomes an
adjustment through the tenant's approval rules). Stock moves only through inventory."""

import uuid
from collections import defaultdict
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.errors import ConflictError, NotFoundError
from app.core.settings import service as settings
from app.core.settings.schemas import TransferSettings
from app.modules.catalog.interface import item_names, stock_items, tenant_today
from app.modules.inventory.interface import (
    InLine,
    OutLine,
    Posting,
    batch_details,
    consume,
    loss_adjustment,
    negative_allowed,
    receive,
    visible_outlet,
)
from app.modules.transfers.models import Transfer, TransferLine, TransferPick
from app.modules.transfers.schemas import (
    TransferApproveIn,
    TransferLineOut,
    TransferOut,
    TransferReceiveIn,
    TransferRequestIn,
    TransferShipIn,
)

DOC = "transfer"


async def get_transfer(db: AsyncSession, transfer_id: uuid.UUID, *, lock: bool = False) -> Transfer:
    t = await db.get(Transfer, transfer_id, with_for_update=lock)
    if t is None:
        raise NotFoundError("transfer_not_found")
    return t


async def transfer_lines(db: AsyncSession, transfer_id: uuid.UUID) -> list[TransferLine]:
    stmt = select(TransferLine).where(TransferLine.transfer_id == transfer_id)
    return list(await db.scalars(stmt.order_by(TransferLine.id)))


async def transfer_picks(db: AsyncSession, transfer_id: uuid.UUID) -> list[TransferPick]:
    stmt = select(TransferPick).where(TransferPick.transfer_id == transfer_id)
    return list(await db.scalars(stmt.order_by(TransferPick.item_id, TransferPick.expiry_date)))


async def transfer_out(
    db: AsyncSession, t: Transfer, lang: str = "en", *, show_cost: bool = False
) -> TransferOut:
    """Values only with catalog.cost.view (docs/03 rule 5); hidden unless the caller says so."""
    rows = await transfer_lines(db, t.id)
    names = await item_names(db, t.tenant_id, lang, {ln.item_id for ln in rows})
    lines = [
        TransferLineOut.model_validate(ln, from_attributes=True).model_copy(
            update={"item_name": names[ln.item_id].name, "unit_code": names[ln.item_id].unit_code}
        )
        for ln in rows
    ]
    fields = {k: getattr(t, k) for k in TransferOut.model_fields if k != "lines"}
    out = TransferOut(**fields, lines=lines)
    if show_cost:
        return out
    hidden = [ln.model_copy(update={"value": None, "charge": None}) for ln in out.lines]
    return out.model_copy(update={"shipped_value": None, "charge_total": None, "lines": hidden})


async def _audit(db: AsyncSession, t: Transfer, user_id: uuid.UUID, action: str) -> None:
    await audit.record(
        db,
        tenant_id=t.tenant_id,
        user_id=user_id,
        outlet_id=t.from_outlet_id,
        action=f"transfers.transfer.{action}",
        target_type=DOC,
        target_id=t.id,
        summary={
            "number": t.number,
            "status": t.status,
            "to_outlet_id": str(t.to_outlet_id),
            "shipped_value": t.shipped_value,
        },
    )


def _ensure_status(t: Transfer, *allowed: str) -> None:
    if t.status not in allowed:
        raise ConflictError("wrong_status", details={"status": t.status})


async def request(
    db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID, data: TransferRequestIn
) -> Transfer:
    if data.from_outlet_id == data.to_outlet_id:
        raise ConflictError("same_outlet")
    await visible_outlet(db, data.from_outlet_id)
    await visible_outlet(db, data.to_outlet_id)
    ids = {ln.item_id for ln in data.lines}
    items = await stock_items(db, ids)
    if bad := {i for i in ids if i not in items or not items[i].is_stocked}:
        raise NotFoundError("item_not_found", details={"item_ids": sorted(map(str, bad))})
    today = await tenant_today(db, tenant_id)
    t = Transfer(
        tenant_id=tenant_id,
        requested_by=user_id,
        number=await settings.allocate_number(db, tenant_id=tenant_id, doc_type=DOC, on=today),
        **data.model_dump(exclude={"lines"}),
    )
    db.add(t)
    await db.flush()
    db.add_all(
        TransferLine(
            tenant_id=tenant_id, transfer_id=t.id, item_id=ln.item_id, requested_qty=ln.qty, value=0
        )
        for ln in data.lines
    )
    await db.flush()
    await _audit(db, t, user_id, "request")
    return t


async def approve(
    db: AsyncSession, *, user_id: uuid.UUID, transfer_id: uuid.UUID, data: TransferApproveIn
) -> Transfer:
    t = await get_transfer(db, transfer_id, lock=True)
    _ensure_status(t, "requested")
    lines = {ln.item_id: ln for ln in await transfer_lines(db, t.id)}
    if unknown := {a.item_id for a in data.lines} - lines.keys():
        raise NotFoundError("item_not_found", details={"item_ids": sorted(map(str, unknown))})
    changed = {a.item_id: a.qty for a in data.lines}
    for item_id, ln in lines.items():
        ln.approved_qty = changed.get(item_id, ln.requested_qty)
    if not any(ln.approved_qty for ln in lines.values()):
        raise ConflictError("nothing_to_send")
    t.status, t.approved_by, t.approved_at = "approved", user_id, datetime.now(UTC)
    await _audit(db, t, user_id, "approve")
    return t


async def ship(
    db: AsyncSession, *, user_id: uuid.UUID, transfer_id: uuid.UUID, data: TransferShipIn
) -> Transfer:
    """Stock leaves the source by FEFO at its moving average; the batches are recorded."""
    t = await get_transfer(db, transfer_id, lock=True)
    _ensure_status(t, "approved")
    lines = [ln for ln in await transfer_lines(db, t.id) if ln.approved_qty]
    p = Posting(t.tenant_id, t.from_outlet_id, user_id, DOC, t.id, data.business_date)
    allowed = await negative_allowed(db, t.tenant_id, "transfer", confirmed=data.confirm_negative)
    outs = [OutLine(ln.item_id, ln.approved_qty, doc_line_id=ln.id) for ln in lines]  # type: ignore[arg-type]
    result = await consume(db, p, "transfer_out", outs, allow_negative=allowed)
    batches = await batch_details(db, {m.batch_id for m in result.movements if m.batch_id})
    values: dict[uuid.UUID | None, int] = defaultdict(int)
    for m in result.movements:
        info = batches.get(m.batch_id) if m.batch_id else None
        db.add(
            TransferPick(
                tenant_id=t.tenant_id,
                transfer_id=t.id,
                line_id=m.doc_line_id,
                item_id=m.item_id,
                batch_id=m.batch_id,
                lot_code=info.lot_code if info else None,
                expiry_date=info.expiry_date if info else None,
                qty=-m.qty,
                unit_cost=m.unit_cost,
            )
        )
        values[m.doc_line_id] -= m.value
    markup = await _markup_bp(db, t.tenant_id)
    for ln in lines:
        ln.shipped_qty, ln.value = ln.approved_qty, values[ln.id]
        ln.charge = _charge(ln.value, markup)
    t.shipped_value = sum(values.values())
    t.charge_total = sum(ln.charge for ln in lines)
    t.status, t.shipped_by, t.shipped_at = "shipped", user_id, datetime.now(UTC)
    t.shipped_on = data.business_date
    await db.flush()
    await _audit(db, t, user_id, "ship")
    return t


async def _markup_bp(db: AsyncSession, tenant_id: uuid.UUID) -> int | None:
    """FR-TRF-006: None when outlets do not charge each other (transfers at cost)."""
    conf = cast(TransferSettings, await settings.get_setting(db, tenant_id, "transfers"))
    return conf.markup_bp if conf.price_mode == "cost_plus" else None


def _charge(value: int, markup_bp: int | None) -> int:
    if markup_bp is None:
        return 0
    return int((Decimal(value) * (10_000 + markup_bp) / 10_000).quantize(Decimal(1), ROUND_HALF_UP))


def _apply_received(lines: list[TransferLine], data: TransferReceiveIn) -> dict[uuid.UUID, Decimal]:
    """Set what arrived; return the missing or damaged base quantity per item."""
    by_item = {ln.item_id: ln for ln in lines}
    if unknown := {r.item_id for r in data.lines} - by_item.keys():
        raise NotFoundError("item_not_found", details={"item_ids": sorted(map(str, unknown))})
    said = {r.item_id: r for r in data.lines}
    losses: dict[uuid.UUID, Decimal] = {}
    for ln in lines:
        shipped = ln.shipped_qty or Decimal(0)
        got = said.get(ln.item_id)
        ln.received_qty = shipped if got is None else got.qty
        if ln.received_qty > shipped:
            raise ConflictError("more_than_shipped", details={"item_id": str(ln.item_id)})
        if ln.received_qty < shipped:
            if got is None or got.reason is None:
                raise ConflictError("reason_required", details={"item_id": str(ln.item_id)})
            ln.discrepancy_reason = got.reason
            losses[ln.item_id] = shipped - ln.received_qty
    return losses


async def receive_transfer(
    db: AsyncSession, *, user_id: uuid.UUID, transfer_id: uuid.UUID, data: TransferReceiveIn
) -> Transfer:
    """FR-TRF-004: the shipped batches arrive at the source's cost. What did not arrive in
    good condition is then taken out by an adjustment that follows the approval rules."""
    t = await get_transfer(db, transfer_id, lock=True)
    _ensure_status(t, "shipped")
    lines = [ln for ln in await transfer_lines(db, t.id) if ln.shipped_qty]
    losses = _apply_received(lines, data)
    p = Posting(t.tenant_id, t.to_outlet_id, user_id, DOC, t.id, data.business_date)
    ins = [
        InLine(pk.item_id, pk.qty, pk.unit_cost, pk.lot_code, pk.expiry_date, pk.line_id)
        for pk in await transfer_picks(db, t.id)
    ]
    if ins:
        await receive(db, p, "transfer_in", ins)
    if losses:
        adj = await loss_adjustment(
            db,
            tenant_id=t.tenant_id,
            user_id=user_id,
            outlet_id=t.to_outlet_id,
            business_date=data.business_date,
            losses=losses,
            note=f"Transfer {t.number}: short or damaged on arrival",
        )
        t.adjustment_id = adj.id
    t.status, t.received_by, t.received_at = "received", user_id, datetime.now(UTC)
    t.received_on = data.business_date
    await _audit(db, t, user_id, "receive")
    return t


async def cancel(db: AsyncSession, *, user_id: uuid.UUID, transfer_id: uuid.UUID) -> Transfer:
    t = await get_transfer(db, transfer_id, lock=True)
    _ensure_status(t, "requested", "approved")  # nothing has moved yet
    t.status = "cancelled"
    await _audit(db, t, user_id, "cancel")
    return t
