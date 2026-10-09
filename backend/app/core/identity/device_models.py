"""Registered devices and PINs (FR-IDN-004, docs/05 `devices`).

A manager registers a shared till or tablet once; the browser keeps a long-lived device
cookie. Staff who signed in fully on that device may later sign in there with a short PIN.
PINs belong to a membership (tenant and user) and lock after repeated failures."""

import uuid
from datetime import datetime

from sqlalchemy import (
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, _created_at, _id


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(["tenant_id", "outlet_id"], ["outlets.tenant_id", "outlets.id"]),
        Index(None, "tenant_id", "revoked_at"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    name: Mapped[str] = mapped_column(String(80))
    outlet_id: Mapped[uuid.UUID | None] = mapped_column()  # docs/03: may be locked to one outlet
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    registered_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = _created_at()
    last_seen_at: Mapped[datetime | None] = mapped_column()
    revoked_at: Mapped[datetime | None] = mapped_column()


class DeviceUser(Base):
    """People who completed a full sign-in on the device: only they may use a PIN there."""

    __tablename__ = "device_users"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "device_id"], ["devices.tenant_id", "devices.id"]),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    device_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    created_at: Mapped[datetime] = _created_at()


class UserPin(Base):
    __tablename__ = "user_pins"

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    pin_hash: Mapped[str] = mapped_column(Text)  # Argon2id, like passwords
    failed_count: Mapped[int] = mapped_column(server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column()
    set_at: Mapped[datetime] = _created_at()
