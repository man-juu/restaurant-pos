"""Platform admin tables (docs/05: not tenant-scoped). Only the admin app, connected as the
`pos_admin` database role, can read or write them; the tenant API role has no grants."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import CITEXT, INET
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, _created_at, _id

ADMIN_ROLES = ("super_admin", "support")


class AdminUser(Base):
    """FR-ADM-002: separate from tenant users; TOTP is mandatory for every admin."""

    __tablename__ = "admin_users"
    __table_args__ = (
        CheckConstraint("role IN ('super_admin', 'support')", name="role_valid"),
        CheckConstraint("status IN ('active', 'disabled')", name="status_valid"),
    )

    id: Mapped[uuid.UUID] = _id()
    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(Text)
    totp_secret_encrypted: Mapped[bytes | None] = mapped_column()
    totp_enabled_at: Mapped[datetime | None] = mapped_column()
    totp_last_step: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(Text, server_default="active")
    created_at: Mapped[datetime] = _created_at()


class AdminSession(Base):
    __tablename__ = "admin_sessions"
    __table_args__ = (
        Index(None, "admin_id", "revoked_at"),
        CheckConstraint("mfa_state IN ('ok', 'verify', 'enroll')", name="mfa_state_valid"),
    )

    id: Mapped[uuid.UUID] = _id()
    token_hash: Mapped[bytes] = mapped_column(unique=True)
    admin_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("admin_users.id"))
    csrf_token: Mapped[str] = mapped_column(String(64))
    mfa_state: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()
    last_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column()
    revoked_at: Mapped[datetime | None] = mapped_column()
    ip: Mapped[str | None] = mapped_column(INET)


class Impersonation(Base):
    """FR-ADM-003: read-only support access to one tenant, with a reason and an expiry."""

    __tablename__ = "impersonation_sessions"
    __table_args__ = (Index(None, "tenant_id", "started_at"),)

    id: Mapped[uuid.UUID] = _id()
    admin_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("admin_users.id"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    reason: Mapped[str] = mapped_column(String(500))
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column()
    ended_at: Mapped[datetime | None] = mapped_column()


class JobFailure(Base):
    """FR-ADM-004: a background job that failed for a tenant (platform table, admin only).
    The message is the exception type only: never tenant data or secrets."""

    __tablename__ = "job_failures"
    __table_args__ = (Index(None, "tenant_id", "at"),)

    id: Mapped[uuid.UUID] = _id()
    job: Mapped[str] = mapped_column(String(60))
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tenants.id"))
    error: Mapped[str] = mapped_column(String(200))
    at: Mapped[datetime] = _created_at()


class RestoreRequest(Base):
    """FR-ADM-007: a recorded request to restore a tenant to a point in time. Restoring is a
    runbook procedure (docs/runbooks/backup-restore.md, point-in-time recovery); this row is
    the request and its outcome, never an automatic restore. Platform table, admin only."""

    __tablename__ = "restore_requests"
    __table_args__ = (Index(None, "tenant_id", "requested_at"),)

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    restore_to: Mapped[datetime] = mapped_column()
    reason: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), server_default="requested")
    requested_by: Mapped[uuid.UUID] = mapped_column()
    requested_at: Mapped[datetime] = _created_at()
