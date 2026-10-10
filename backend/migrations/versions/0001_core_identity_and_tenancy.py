"""core identity and tenancy

Revision ID: 0001
Revises:
Create Date: 2026-10-07 06:32:07.846402
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from migrations.helpers import (
    enable_tenant_rls,
    ensure_roles,
    grant,
    make_append_only,
)

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")  # case-insensitive email
    ensure_roles()

    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("legal_name", sa.String(length=200), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("language", sa.String(length=10), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("profile", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="active", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("country ~ '^[A-Z]{2}$'", name=op.f("ck_tenants_country_iso")),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name=op.f("ck_tenants_currency_iso")),
        sa.CheckConstraint(
            "profile IN ('restaurant', 'cloud_kitchen', 'central_kitchen_group', 'hybrid')",
            name=op.f("ck_tenants_profile_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('active', 'suspended', 'deleted')", name=op.f("ck_tenants_status_valid")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenants")),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("totp_secret_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column("locale", sa.String(length=10), server_default="id", nullable=False),
        sa.Column("status", sa.Text(), server_default="active", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("status IN ('active', 'disabled')", name=op.f("ck_users_status_valid")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("actor_type", sa.Text(), server_default="user", nullable=False),
        sa.Column("outlet_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("target_type", sa.String(length=100), nullable=True),
        sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column(
            "summary", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_audit_log_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_index(
        op.f("ix_audit_log_tenant_id_at"), "audit_log", ["tenant_id", "at"], unique=False
    )
    op.create_index(
        op.f("ix_audit_log_tenant_id_target_type_target_id"),
        "audit_log",
        ["tenant_id", "target_type", "target_id"],
        unique=False,
    )
    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.Uuid(), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_body", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_idempotency_keys_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_idempotency_keys")),
        sa.UniqueConstraint("tenant_id", "key", name=op.f("uq_idempotency_keys_tenant_id_key")),
    )
    op.create_table(
        "outlets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("day_cutoff", sa.Time(), server_default="04:00", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "type IN ('restaurant', 'branch', 'cloud_kitchen', 'central_kitchen', 'warehouse')",
            name=op.f("ck_outlets_type_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_outlets_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outlets")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_outlets_tenant_id_id")),
    )
    op.create_index(
        op.f("ix_outlets_tenant_id_is_active"), "outlets", ["tenant_id", "is_active"], unique=False
    )
    op.create_table(
        "roles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("is_template", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "is_template = (tenant_id IS NULL)", name=op.f("ck_roles_template_has_no_tenant")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_roles_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_roles")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_roles_tenant_id_id")),
        sa.UniqueConstraint("tenant_id", "name", name=op.f("uq_roles_tenant_id_name")),
    )
    op.create_table(
        "memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("scope", sa.Text(), server_default="all", nullable=False),
        sa.Column("status", sa.Text(), server_default="active", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("scope IN ('all', 'outlets')", name=op.f("ck_memberships_scope_valid")),
        sa.CheckConstraint(
            "status IN ('active', 'invited', 'disabled')", name=op.f("ck_memberships_status_valid")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "role_id"],
            ["roles.tenant_id", "roles.id"],
            name=op.f("fk_memberships_tenant_id_role_id_roles"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_memberships_tenant_id_tenants")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_memberships_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_memberships")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_memberships_tenant_id_id")),
        sa.UniqueConstraint("tenant_id", "user_id", name=op.f("uq_memberships_tenant_id_user_id")),
    )
    op.create_index(op.f("ix_memberships_user_id"), "memberships", ["user_id"], unique=False)
    op.create_table(
        "role_permissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("permission_code", sa.String(length=100), nullable=False),
        sa.Column("limit_value", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "permission_code ~ '^[a-z_]+\\.[a-z_]+\\.[a-z_]+$'",
            name=op.f("ck_role_permissions_permission_code_format"),
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
            name=op.f("fk_role_permissions_role_id_roles"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "role_id"],
            ["roles.tenant_id", "roles.id"],
            name=op.f("fk_role_permissions_tenant_id_role_id_roles"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_role_permissions")),
        sa.UniqueConstraint(
            "tenant_id",
            "role_id",
            "permission_code",
            name=op.f("uq_role_permissions_tenant_id_role_id_permission_code"),
        ),
    )
    op.create_table(
        "membership_outlets",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("outlet_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "membership_id"],
            ["memberships.tenant_id", "memberships.id"],
            name=op.f("fk_membership_outlets_tenant_id_membership_id_memberships"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "outlet_id"],
            ["outlets.tenant_id", "outlets.id"],
            name=op.f("fk_membership_outlets_tenant_id_outlet_id_outlets"),
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id", "membership_id", "outlet_id", name=op.f("pk_membership_outlets")
        ),
    )

    # Privileges: the app role gets only what it needs (deny by default).
    grant("tenants", "SELECT, UPDATE")  # tenants are created by the admin path (slice 0.6)
    grant("users", "SELECT, INSERT, UPDATE")
    for table in ("outlets", "roles", "role_permissions", "memberships", "membership_outlets"):
        grant(table, "SELECT, INSERT, UPDATE, DELETE")
    grant("audit_log", "SELECT, INSERT")  # append-only (FR-AUD-002)
    grant("idempotency_keys", "SELECT, INSERT, UPDATE, DELETE")

    # Row-level security (CLAUDE.md rule 1). users is global identity, so it has none.
    enable_tenant_rls("tenants", column="id")
    for table in ("outlets", "memberships", "membership_outlets", "audit_log", "idempotency_keys"):
        enable_tenant_rls(table)
    for table in ("roles", "role_permissions"):
        enable_tenant_rls(table, readable_templates=True)

    make_append_only("audit_log")


def downgrade() -> None:
    # Roles and the citext extension are cluster or database level and may be shared,
    # so they are left in place.
    op.drop_table("membership_outlets")
    op.drop_table("role_permissions")
    op.drop_index(op.f("ix_memberships_user_id"), table_name="memberships")
    op.drop_table("memberships")
    op.drop_table("roles")
    op.drop_index(op.f("ix_outlets_tenant_id_is_active"), table_name="outlets")
    op.drop_table("outlets")
    op.drop_table("idempotency_keys")
    op.drop_index(op.f("ix_audit_log_tenant_id_target_type_target_id"), table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_tenant_id_at"), table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_table("users")
    op.drop_table("tenants")
    op.execute("DROP FUNCTION IF EXISTS reject_change()")
