"""Usage counters for free AI images (ADR-022).

`ai_usage_daily` is platform-wide (no tenant_id, no tenant data: just a date and a number), so
every tenant's request counts against the one free allowance. `ai_image_requests` is the
per-tenant log used for the tenant's daily cap and for audit."""

import uuid
from datetime import date, datetime

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, _created_at, _id


class AiUsageDaily(Base):
    __tablename__ = "ai_usage_daily"

    day: Mapped[date] = mapped_column(primary_key=True)  # UTC day: the provider resets at 00:00 UTC
    neurons: Mapped[int] = mapped_column(server_default="0")
    images: Mapped[int] = mapped_column(server_default="0")


class AiImageRequest(Base):
    __tablename__ = "ai_image_requests"
    __table_args__ = (Index(None, "tenant_id", "created_at"),)

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    user_id: Mapped[uuid.UUID] = mapped_column()
    prompt: Mapped[str] = mapped_column(String(300))
    neurons: Mapped[int] = mapped_column()
    succeeded: Mapped[bool] = mapped_column()
    upload_id: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = _created_at()
