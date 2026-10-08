"""Approval rules skeleton (docs/03 sections 6 and 7, FR-TEN-007).

Document modules call these helpers before approving anything. Approval rules per document
type and amount (approval_rules table) arrive with tenant settings in Phase 1.
"""

import uuid
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ConflictError, ForbiddenError
from app.core.models import Role
from app.core.settings.service import required_approver_roles


class SelfApprovalForbidden(AppError):
    status_code, code = 403, "cannot_approve_own_request"


class LimitExceeded(AppError):
    status_code, code = 403, "limit_exceeded"


def ensure_not_own_request(*, requested_by: uuid.UUID, approver: uuid.UUID) -> None:
    """docs/03 rule 1: nobody approves their own request, whatever their role."""
    if requested_by == approver:
        raise SelfApprovalForbidden()


def ensure_within_limit(value: int, limit: int | None, *, what: str) -> None:
    """docs/03 rule 7: per-role limits (discount %, refund or approval amount). None means
    no limit set on the role, which only owner and co-owner templates use."""
    if limit is not None and value > limit:
        raise LimitExceeded(details={"limit": limit, "what": what})


# ─── Submit / approve / reject flow shared by every document module ───────


class FlowDoc(Protocol):
    id: uuid.UUID
    tenant_id: uuid.UUID
    outlet_id: uuid.UUID
    status: str
    created_by: uuid.UUID | None
    submitted_at: datetime | None
    decided_by: uuid.UUID | None
    decided_at: datetime | None


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
