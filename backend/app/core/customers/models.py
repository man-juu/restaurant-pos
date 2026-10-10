"""Customers (docs/05 2.6, FR-SAL-012): only name and phone, with consent. Used for
reservations, wholesale invoices and (later) loyalty, never for marketing without consent."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, _created_at, _id


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        # One record per phone number in a business (digits only, see service.normal_phone).
        Index("uq_customers_phone", "tenant_id", "phone", unique=True),
        Index(None, "tenant_id", "name"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(20))
    # When the guest agreed that the business keeps their contact details (UU PDP).
    consent_at: Mapped[datetime | None] = mapped_column()
    note: Mapped[str | None] = mapped_column(Text)
    erased_at: Mapped[datetime | None] = mapped_column()  # personal data removed on request
    created_by: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = _created_at()
