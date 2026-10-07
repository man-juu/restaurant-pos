"""Approval rules skeleton (docs/03 sections 6 and 7, FR-TEN-007).

Document modules call these helpers before approving anything. Approval rules per document
type and amount (approval_rules table) arrive with tenant settings in Phase 1.
"""

import uuid

from app.core.errors import AppError


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
