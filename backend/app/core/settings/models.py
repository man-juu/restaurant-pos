"""Settings tables (FR-TEN-004 to 009): stored settings, approval and alert rules, document
number counters."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, _check_in, _created_at, _id


class TenantSetting(Base):
    """FR-TEN-004 to 009: one row per setting key, validated by app/core/settings/schemas."""

    __tablename__ = "tenant_settings"

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_by: Mapped[uuid.UUID | None] = mapped_column()


APPROVAL_DOCUMENTS = (
    "purchase_order",
    "transfer",
    "adjustment",
    "count",
    "void",
    "refund",
    "discount",
    "journal",
)


class ApprovalRule(Base):
    """FR-TEN-007: documents of this type at or above min_amount need this role's approval."""

    __tablename__ = "approval_rules"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "approver_role_id"], ["roles.tenant_id", "roles.id"]),
        ForeignKeyConstraint(["tenant_id", "outlet_id"], ["outlets.tenant_id", "outlets.id"]),
        _check_in("document_type", APPROVAL_DOCUMENTS),
        CheckConstraint("min_amount >= 0", name="min_amount_non_negative"),
        Index(None, "tenant_id", "document_type"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    document_type: Mapped[str] = mapped_column(Text)
    outlet_id: Mapped[uuid.UUID | None] = mapped_column()  # NULL: every outlet
    min_amount: Mapped[int] = mapped_column(BigInteger)  # minor units
    approver_role_id: Mapped[uuid.UUID] = mapped_column()
    created_at: Mapped[datetime] = _created_at()


ALERT_TYPES = (
    "below_reorder_point",
    "low_days_of_inventory",
    "batch_near_expiry",
    "expired_stock",
    "negative_stock",
    "count_variance",
    "food_cost_above_target",
    "approval_requested",
    "transfer_requested",  # a branch asks the central kitchen for stock
)


class AlertRule(Base):
    """FR-TEN-008: which alert goes to which role or user, on which channel."""

    __tablename__ = "alert_rules"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "recipient_role_id"], ["roles.tenant_id", "roles.id"]),
        _check_in("alert_type", ALERT_TYPES),
        _check_in("channel", ("in_app", "email")),
        CheckConstraint(
            "(recipient_role_id IS NULL) <> (recipient_user_id IS NULL)", name="one_recipient"
        ),
        Index(None, "tenant_id", "alert_type"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    alert_type: Mapped[str] = mapped_column(Text)
    recipient_role_id: Mapped[uuid.UUID | None] = mapped_column()
    recipient_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    channel: Mapped[str] = mapped_column(Text, server_default="in_app")
    created_at: Mapped[datetime] = _created_at()


class NumberingCounter(Base):
    """FR-TEN-009: last number per tenant, outlet, document type and year. Allocation is one
    atomic upsert, so concurrent documents never get the same number."""

    __tablename__ = "numbering_counters"

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    # The nil UUID means "tenant-wide" (primary key columns cannot be NULL).
    outlet_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    doc_type: Mapped[str] = mapped_column(String(40), primary_key=True)
    year: Mapped[int] = mapped_column(primary_key=True)  # 0 when the format never resets
    last_number: Mapped[int] = mapped_column(BigInteger)
