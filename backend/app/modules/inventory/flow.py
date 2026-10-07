"""Shared steps of stock documents: numbering, quantities in base units, value for approval
rules, and the submit/approve/reject flow (FR-TEN-007, docs/03 sections 6 and 7)."""

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.approvals import ensure_not_own_request
from app.core.errors import ConflictError, ForbiddenError
from app.core.models import Role
from app.core.settings.service import allocate_number, required_approver_roles
from app.modules.catalog.interface import base_factors
from app.modules.inventory.models import ItemCost
from app.modules.inventory.service import money

QTY = Decimal("0.0001")


class FlowDoc(Protocol):
    id: uuid.UUID
    tenant_id: uuid.UUID
    outlet_id: uuid.UUID
    status: str
    created_by: uuid.UUID | None
    submitted_at: datetime | None
    decided_by: uuid.UUID | None
    decided_at: datetime | None


async def next_number(db: AsyncSession, tenant_id: uuid.UUID, doc_type: str, doc: object) -> str:
    return await allocate_number(
        db,
        tenant_id=tenant_id,
        doc_type=doc_type,
        on=getattr(doc, "business_date"),  # noqa: B009 - every header has it
        outlet_id=getattr(doc, "outlet_id"),  # noqa: B009
    )


async def to_base(
    db: AsyncSession, lines: Iterable[tuple[uuid.UUID, uuid.UUID, Decimal]]
) -> dict[uuid.UUID, Decimal]:
    """(item, unit, qty) -> item: qty in the item's base unit (exact, 4 decimals)."""
    rows = list(lines)
    factors = await base_factors(db, {(i, u) for i, u, _ in rows})
    return {i: (q * factors[(i, u)]).quantize(QTY, rounding=ROUND_HALF_UP) for i, u, q in rows}


async def average_costs(
    db: AsyncSession, outlet_id: uuid.UUID, items: Iterable[uuid.UUID]
) -> dict[uuid.UUID, Decimal]:
    stmt = select(ItemCost.item_id, ItemCost.avg_cost).where(
        ItemCost.outlet_id == outlet_id, ItemCost.item_id.in_(set(items))
    )
    return {row[0]: row[1] for row in (await db.execute(stmt)).all()}


async def value_of(db: AsyncSession, outlet_id: uuid.UUID, qty: dict[uuid.UUID, Decimal]) -> int:
    """Approval amount: what the stock change is worth at today's average, ignoring sign."""
    costs = await average_costs(db, outlet_id, qty)
    return sum(money(abs(q), costs.get(i, Decimal(0))) for i, q in qty.items())


def ensure_status(doc: FlowDoc, *allowed: str) -> None:
    if doc.status not in allowed:
        raise ConflictError("wrong_status", details={"status": doc.status})


async def approvers_needed(
    db: AsyncSession, document_type: str, doc: FlowDoc, amount: int
) -> set[uuid.UUID]:
    return await required_approver_roles(
        db, document_type=document_type, outlet_id=doc.outlet_id, amount=amount
    )


async def ensure_may_decide(
    db: AsyncSession, doc: FlowDoc, roles: set[uuid.UUID], *, user_id: uuid.UUID, role_id: uuid.UUID
) -> None:
    """docs/03 rule 1 (never your own request) and rule 7 (the rule's role, or an owner)."""
    if doc.created_by is not None:
        ensure_not_own_request(requested_by=doc.created_by, approver=user_id)
    if role_id in roles:
        return
    template = await db.scalar(select(Role.template_key).where(Role.id == role_id))
    if template != "owner":
        raise ForbiddenError("approver_role_required", details={"roles": sorted(map(str, roles))})


def mark_decided(doc: FlowDoc, status: str, user_id: uuid.UUID) -> None:
    doc.status, doc.decided_by, doc.decided_at = status, user_id, datetime.now(UTC)


def mark_submitted(doc: FlowDoc) -> None:
    doc.status, doc.submitted_at = "submitted", datetime.now(UTC)
