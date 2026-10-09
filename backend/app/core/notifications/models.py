"""Alerts and the in-app notification center (FR-INV-012, FR-NTF-001, docs/05 2.1 and 2.3).

An alert is a condition (one per type, outlet, item and batch while it is open); it is
resolved when the condition clears. Each alert notifies its recipients once. Notifications
are kept 90 days (docs/05 retention)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, ForeignKeyConstraint, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, _check_in, _created_at, _id
from app.core.settings.models import ALERT_TYPES

ALERT_STATES = ("open", "resolved")


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        _check_in("type", ALERT_TYPES),
        _check_in("state", ALERT_STATES),
        ForeignKeyConstraint(["tenant_id", "outlet_id"], ["outlets.tenant_id", "outlets.id"]),
        # One open alert per condition: the scan can run often without duplicates.
        Index(
            "uq_alerts_open_key",
            "tenant_id",
            "type",
            "key",
            unique=True,
            postgresql_where=text("state = 'open'"),
        ),
        Index(None, "tenant_id", "state", "raised_at"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    type: Mapped[str] = mapped_column(Text)
    key: Mapped[str] = mapped_column(String(200))  # outlet:item:batch, stable per condition
    outlet_id: Mapped[uuid.UUID | None] = mapped_column()
    item_id: Mapped[uuid.UUID | None] = mapped_column()
    batch_id: Mapped[uuid.UUID | None] = mapped_column()
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    state: Mapped[str] = mapped_column(Text, server_default="open")
    raised_at: Mapped[datetime] = _created_at()
    resolved_at: Mapped[datetime | None] = mapped_column()


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (Index(None, "tenant_id", "user_id", "read_at", "created_at"),)

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    alert_id: Mapped[uuid.UUID | None] = mapped_column()
    kind: Mapped[str] = mapped_column(Text)  # an alert type
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")  # for the text
    link: Mapped[str | None] = mapped_column(String(200))  # in-app path, never a full URL
    created_at: Mapped[datetime] = _created_at()
    read_at: Mapped[datetime | None] = mapped_column()
