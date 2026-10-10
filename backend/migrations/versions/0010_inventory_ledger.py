"""inventory: ledger, batches, balances, moving average costs (slice 1e, FR-INV-001 to 005)

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-07 23:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from migrations.helpers import enable_tenant_rls, grant, make_append_only

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MOVEMENT_TYPES = (
    "purchase_receipt",
    "production_output",
    "transfer_in",
    "opening_balance",
    "sale_consumption",
    "production_consumption",
    "transfer_out",
    "waste",
    "vendor_return",
    "adjustment",
    "count_correction",
)


def _tenant_fks(table: str, *, batch: bool = False) -> list[sa.ForeignKeyConstraint]:
    fks = [
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f(f"fk_{table}_tenant_id_tenants")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "outlet_id"],
            ["outlets.tenant_id", "outlets.id"],
            name=op.f(f"fk_{table}_tenant_id_outlet_id_outlets"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "item_id"],
            ["items.tenant_id", "items.id"],
            name=op.f(f"fk_{table}_tenant_id_item_id_items"),
        ),
    ]
    if batch:
        fks.append(
            sa.ForeignKeyConstraint(
                ["tenant_id", "batch_id"],
                ["stock_batches.tenant_id", "stock_batches.id"],
                name=op.f(f"fk_{table}_tenant_id_batch_id_stock_batches"),
            )
        )
    return fks


def upgrade() -> None:
    op.create_table(
        "stock_batches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("outlet_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("lot_code", sa.String(length=64), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("unit_cost", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("source_doc_type", sa.String(length=40), nullable=False),
        sa.Column("source_doc_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("unit_cost >= 0", name=op.f("ck_stock_batches_unit_cost_not_negative")),
        *_tenant_fks("stock_batches"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stock_batches")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_stock_batches_tenant_id_id")),
    )
    op.create_index(
        op.f("ix_stock_batches_tenant_id_outlet_id_item_id_expiry_date"),
        "stock_batches",
        ["tenant_id", "outlet_id", "item_id", "expiry_date"],
    )

    types = ", ".join(f"'{t}'" for t in MOVEMENT_TYPES)
    op.create_table(
        "stock_movements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("outlet_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=True),
        sa.Column("movement_type", sa.Text(), nullable=False),
        sa.Column("qty", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("unit_cost", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("value", sa.BigInteger(), nullable=False),
        sa.Column("doc_type", sa.String(length=40), nullable=False),
        sa.Column("doc_id", sa.Uuid(), nullable=False),
        sa.Column("doc_line_id", sa.Uuid(), nullable=True),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column(
            "posted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("posted_by", sa.Uuid(), nullable=True),
        sa.Column("reverses_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            f"movement_type IN ({types})", name=op.f("ck_stock_movements_movement_type_valid")
        ),
        sa.CheckConstraint("qty <> 0", name=op.f("ck_stock_movements_qty_not_zero")),
        sa.CheckConstraint(
            "unit_cost >= 0", name=op.f("ck_stock_movements_unit_cost_not_negative")
        ),
        *_tenant_fks("stock_movements", batch=True),
        sa.ForeignKeyConstraint(
            ["tenant_id", "reverses_id"],
            ["stock_movements.tenant_id", "stock_movements.id"],
            name=op.f("fk_stock_movements_tenant_id_reverses_id_stock_movements"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stock_movements")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_stock_movements_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id", "reverses_id", name=op.f("uq_stock_movements_tenant_id_reverses_id")
        ),
    )
    op.create_index(
        op.f("ix_stock_movements_tenant_id_outlet_id_item_id_business_date"),
        "stock_movements",
        ["tenant_id", "outlet_id", "item_id", "business_date"],
    )
    op.create_index(
        op.f("ix_stock_movements_tenant_id_doc_type_doc_id"),
        "stock_movements",
        ["tenant_id", "doc_type", "doc_id"],
    )

    op.create_table(
        "stock_balances",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("outlet_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=True),
        sa.Column("qty", sa.Numeric(precision=18, scale=4), nullable=False),
        *_tenant_fks("stock_balances", batch=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stock_balances")),
        sa.UniqueConstraint(
            "tenant_id",
            "outlet_id",
            "item_id",
            "batch_id",
            name=op.f("uq_stock_balances_tenant_id_outlet_id_item_id_batch_id"),
            postgresql_nulls_not_distinct=True,
        ),
    )

    op.create_table(
        "item_costs",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("outlet_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("avg_cost", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("qty_on_hand_for_avg", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("avg_cost >= 0", name=op.f("ck_item_costs_avg_not_negative")),
        *_tenant_fks("item_costs"),
        sa.PrimaryKeyConstraint("outlet_id", "item_id", name=op.f("pk_item_costs")),
    )
    op.create_index(op.f("ix_item_costs_tenant_id_item_id"), "item_costs", ["tenant_id", "item_id"])

    grant("stock_batches", "SELECT, INSERT")  # a lot's facts never change
    grant("stock_movements", "SELECT, INSERT")  # append-only (docs/05 ledger rule 1)
    grant("stock_balances", "SELECT, INSERT, UPDATE")  # caches, same transaction
    grant("item_costs", "SELECT, INSERT, UPDATE")
    make_append_only("stock_movements")
    for table in ("stock_batches", "stock_movements", "stock_balances", "item_costs"):
        enable_tenant_rls(table)


def downgrade() -> None:
    op.drop_table("item_costs")
    op.drop_table("stock_balances")
    op.drop_table("stock_movements")
    op.drop_table("stock_batches")
