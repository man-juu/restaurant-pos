"""Web push subscriptions (FR-NTF-005): one per browser that a person allowed to notify."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, _created_at, _id


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "endpoint"),
        Index(None, "tenant_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    endpoint: Mapped[str] = mapped_column(String(1000))  # a browser push service URL
    p256dh: Mapped[str] = mapped_column(String(200))  # the browser's public key
    auth_secret: Mapped[str] = mapped_column(String(100))  # the browser's auth secret
    created_at: Mapped[datetime] = _created_at()
    last_ok_at: Mapped[datetime | None] = mapped_column()
    failures: Mapped[int] = mapped_column(server_default="0")
