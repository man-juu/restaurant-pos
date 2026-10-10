"""FR-IMP-004: how one delivery platform's sales export is laid out, saved per channel so the
next file imports with no setup."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, ForeignKeyConstraint, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, _check_in, _created_at, _id

DATE_FORMATS = ("ymd", "dmy", "mdy")


class PlatformImportMapping(Base):
    __tablename__ = "platform_import_mappings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "channel_id"),
        ForeignKeyConstraint(["tenant_id", "channel_id"], ["channels.tenant_id", "channels.id"]),
        _check_in("date_format", DATE_FORMATS),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    channel_id: Mapped[uuid.UUID] = mapped_column()
    date_column: Mapped[str] = mapped_column(String(100))
    code_column: Mapped[str] = mapped_column(String(100))
    qty_column: Mapped[str] = mapped_column(String(100))
    amount_column: Mapped[str | None] = mapped_column(String(100))
    date_format: Mapped[str] = mapped_column(Text, server_default="ymd")
    updated_by: Mapped[uuid.UUID] = mapped_column()
    updated_at: Mapped[datetime] = _created_at()
