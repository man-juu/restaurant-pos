"""Platform announcements (FR-ADM-005): written by the platform admin, shown in-app to all
tenants or chosen ones between two moments; each person can dismiss one. Plain text only."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, _check_in, _created_at, _id

LEVELS = ("info", "warning")


class Announcement(Base):
    """Platform table (no tenant): the app role may only read it."""

    __tablename__ = "announcements"
    __table_args__ = (
        _check_in("level", LEVELS),
        CheckConstraint("ends_at > starts_at", name="window"),
        Index(None, "starts_at", "ends_at"),
    )

    id: Mapped[uuid.UUID] = _id()
    title_en: Mapped[str] = mapped_column(String(120))
    title_id: Mapped[str] = mapped_column(String(120))
    body_en: Mapped[str] = mapped_column(Text)
    body_id: Mapped[str] = mapped_column(Text)
    level: Mapped[str] = mapped_column(Text, server_default="info")
    all_tenants: Mapped[bool] = mapped_column(server_default="true")
    starts_at: Mapped[datetime] = mapped_column()
    ends_at: Mapped[datetime] = mapped_column()
    created_by: Mapped[uuid.UUID] = mapped_column()  # admin user
    created_at: Mapped[datetime] = _created_at()


class AnnouncementTarget(Base):
    """One chosen tenant of an announcement that is not for all tenants."""

    __tablename__ = "announcement_targets"
    __table_args__ = (UniqueConstraint("tenant_id", "announcement_id"),)

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    announcement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("announcements.id"))


class AnnouncementDismissal(Base):
    __tablename__ = "announcement_dismissals"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", "announcement_id"),)

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    user_id: Mapped[uuid.UUID] = mapped_column()
    announcement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("announcements.id"))
    at: Mapped[datetime] = _created_at()
