"""Tenant data exports (FR-TEN-010, FR-ADM-007): asked for by the owner or a platform admin,
built by the worker in the tenant's own RLS context, downloadable for a week."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, _check_in, _created_at, _id

EXPORT_STATUSES = ("queued", "ready", "failed")


class DataExport(Base):
    __tablename__ = "data_exports"
    __table_args__ = (
        _check_in("status", EXPORT_STATUSES),
        Index(None, "tenant_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    status: Mapped[str] = mapped_column(Text, server_default="queued")
    requested_by: Mapped[uuid.UUID | None] = mapped_column()  # a tenant member
    requested_by_admin: Mapped[uuid.UUID | None] = mapped_column()  # or a platform admin
    file_key: Mapped[str | None] = mapped_column(String(120))
    byte_size: Mapped[int | None] = mapped_column(BigInteger)
    error: Mapped[str | None] = mapped_column(String(200))  # exception type only
    created_at: Mapped[datetime] = _created_at()
    finished_at: Mapped[datetime | None] = mapped_column()
    expires_at: Mapped[datetime | None] = mapped_column()
