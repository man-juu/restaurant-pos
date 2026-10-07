"""Uploaded files (docs/05 section 2.2a). The row holds metadata; the bytes live on disk under
`storage_key`, a random name that never comes from the client."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, _check_in, _created_at, _id

UPLOAD_PURPOSES = ("item_photo", "background", "waste_photo", "invoice")


class Upload(Base):
    __tablename__ = "uploads"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "purpose", "sha256"),
        _check_in("purpose", UPLOAD_PURPOSES),
        Index(None, "tenant_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    purpose: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(String(40))
    byte_size: Mapped[int] = mapped_column()
    width: Mapped[int | None] = mapped_column()
    height: Mapped[int | None] = mapped_column()
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(120))
    created_by: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = _created_at()
