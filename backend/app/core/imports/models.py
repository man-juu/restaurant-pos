"""Import history (docs/05 section 2.2a, FR-IMP-002): one row per committed file, so the same
file is never imported twice and an import can be undone."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, _check_in, _created_at, _id

IMPORT_KINDS = ("items", "recipes", "vendors", "opening_stock", "platform_sales")
IMPORT_STATUSES = ("committed", "reverted")


class ImportBatch(Base):
    __tablename__ = "import_batches"
    __table_args__ = (
        UniqueConstraint("tenant_id", "kind", "file_sha256"),
        _check_in("kind", IMPORT_KINDS),
        _check_in("status", IMPORT_STATUSES),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    kind: Mapped[str] = mapped_column(Text)
    file_sha256: Mapped[str] = mapped_column(String(64))
    file_name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(Text, server_default="committed")
    row_count: Mapped[int] = mapped_column()
    created_ids: Mapped[list[Any]] = mapped_column(JSONB)
    created_by: Mapped[uuid.UUID] = mapped_column()
    created_at: Mapped[datetime] = _created_at()
    reverted_at: Mapped[datetime | None] = mapped_column()
