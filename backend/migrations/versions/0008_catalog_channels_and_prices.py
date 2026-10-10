"""catalog: channels and item list prices with start dates (slice 1b part 2, FR-CAT-004)

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-07 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from migrations.helpers import enable_tenant_rls, grant

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "channels",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("platform", sa.String(length=40), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.CheckConstraint(
            "(kind = 'platform') = (platform IS NOT NULL)", name=op.f("ck_channels_platform_kind")
        ),
        sa.CheckConstraint(
            "kind IN ('dine_in', 'takeaway', 'platform', 'wholesale')",
            name=op.f("ck_channels_kind_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_channels_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_channels")),
        sa.UniqueConstraint("tenant_id", "code", name=op.f("uq_channels_tenant_id_code")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_channels_tenant_id_id")),
    )
    op.create_table(
        "item_prices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("channel_id", sa.Uuid(), nullable=False),
        sa.Column("outlet_id", sa.Uuid(), nullable=True),
        sa.Column("price", sa.BigInteger(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.CheckConstraint("price >= 0", name=op.f("ck_item_prices_price_not_negative")),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from", name=op.f("ck_item_prices_valid_range")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "channel_id"],
            ["channels.tenant_id", "channels.id"],
            name=op.f("fk_item_prices_tenant_id_channel_id_channels"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "item_id"],
            ["items.tenant_id", "items.id"],
            name=op.f("fk_item_prices_tenant_id_item_id_items"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "outlet_id"],
            ["outlets.tenant_id", "outlets.id"],
            name=op.f("fk_item_prices_tenant_id_outlet_id_outlets"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_item_prices_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_item_prices")),
        sa.UniqueConstraint(
            "tenant_id",
            "item_id",
            "channel_id",
            "outlet_id",
            "valid_from",
            name=op.f("uq_item_prices_tenant_id_item_id_channel_id_outlet_id_valid_from"),
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index(
        op.f("ix_item_prices_tenant_id_channel_id_item_id_valid_from"),
        "item_prices",
        ["tenant_id", "channel_id", "item_id", "valid_from"],
        unique=False,
    )

    grant("channels", "SELECT, INSERT, UPDATE")  # archived via is_active, never deleted
    # DELETE only for prices that have not started yet (checked in the service).
    grant("item_prices", "SELECT, INSERT, UPDATE, DELETE")
    for table in ("channels", "item_prices"):
        enable_tenant_rls(table)


def downgrade() -> None:
    op.drop_index(
        op.f("ix_item_prices_tenant_id_channel_id_item_id_valid_from"), table_name="item_prices"
    )
    op.drop_table("item_prices")
    op.drop_table("channels")
