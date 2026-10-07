"""inventory: waste logs, adjustments and stock counts (slice 1i, FR-INV-007 to 009)

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-08 00:30:00.000000
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

from migrations.helpers import enable_tenant_rls, grant

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = sa.DateTime(timezone=True)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _header(table: str, status_default: str, *, flow: bool) -> list[Any]:
    items: list[Any] = [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("outlet_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.String(length=40), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("status", sa.Text(), server_default=status_default, nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f(f"fk_{table}_tenant_id_tenants")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "outlet_id"],
            ["outlets.tenant_id", "outlets.id"],
            name=op.f(f"fk_{table}_tenant_id_outlet_id_outlets"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f(f"uq_{table}_tenant_id_id")),
        sa.UniqueConstraint("tenant_id", "number", name=op.f(f"uq_{table}_tenant_id_number")),
    ]
    if flow:
        items += [
            sa.Column("submitted_at", TS, nullable=True),
            sa.Column("decided_by", sa.Uuid(), nullable=True),
            sa.Column("decided_at", TS, nullable=True),
            sa.CheckConstraint(
                _in("status", ("draft", "submitted", "posted", "rejected")),
                name=op.f(f"ck_{table}_status_valid"),
            ),
        ]
    return items


def _line(table: str, parent_col: str, parent: str) -> list[Any]:
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(parent_col, sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f(f"fk_{table}_tenant_id_tenants")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", parent_col],
            [f"{parent}.tenant_id", f"{parent}.id"],
            name=op.f(f"fk_{table}_tenant_id_{parent_col}_{parent}"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "item_id"],
            ["items.tenant_id", "items.id"],
            name=op.f(f"fk_{table}_tenant_id_item_id_items"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
    ]


def _unit(table: str) -> list[Any]:
    return [
        sa.Column("unit_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"], name=op.f(f"fk_{table}_unit_id_units")),
    ]


def upgrade() -> None:
    waste_reasons = ("spoilage", "expired", "preparation_loss", "damaged", "staff_meal", "other")
    op.create_table(
        "waste_logs",
        *_header("waste_logs", "posted", flow=False),
        sa.Column("reason_code", sa.Text(), nullable=False),
        sa.Column("photo_ref", sa.String(length=200), nullable=True),
        sa.CheckConstraint(
            _in("reason_code", waste_reasons), name=op.f("ck_waste_logs_reason_code_valid")
        ),
        sa.CheckConstraint(
            _in("status", ("posted", "reversed")), name=op.f("ck_waste_logs_status_valid")
        ),
    )
    op.create_index(
        op.f("ix_waste_logs_tenant_id_outlet_id_business_date"),
        "waste_logs",
        ["tenant_id", "outlet_id", "business_date"],
    )
    op.create_table(
        "waste_lines",
        *_line("waste_lines", "waste_id", "waste_logs"),
        sa.Column("qty", sa.Numeric(precision=18, scale=4), nullable=False),
        *_unit("waste_lines"),
        sa.CheckConstraint("qty > 0", name=op.f("ck_waste_lines_qty_positive")),
    )
    op.create_index(
        op.f("ix_waste_lines_tenant_id_waste_id"), "waste_lines", ["tenant_id", "waste_id"]
    )

    reasons = ("correction", "found", "theft", "damaged", "other")
    op.create_table(
        "adjustments",
        *_header("adjustments", "draft", flow=True),
        sa.Column("reason_code", sa.Text(), nullable=False),
        sa.CheckConstraint(
            _in("reason_code", reasons), name=op.f("ck_adjustments_reason_code_valid")
        ),
    )
    op.create_index(
        op.f("ix_adjustments_tenant_id_outlet_id_status"),
        "adjustments",
        ["tenant_id", "outlet_id", "status"],
    )
    op.create_table(
        "adjustment_lines",
        *_line("adjustment_lines", "adjustment_id", "adjustments"),
        sa.Column("qty", sa.Numeric(precision=18, scale=4), nullable=False),
        *_unit("adjustment_lines"),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.CheckConstraint("qty <> 0", name=op.f("ck_adjustment_lines_qty_not_zero")),
    )
    op.create_index(
        op.f("ix_adjustment_lines_tenant_id_adjustment_id"),
        "adjustment_lines",
        ["tenant_id", "adjustment_id"],
    )

    op.create_table(
        "stock_counts",
        *_header("stock_counts", "draft", flow=True),
        sa.Column("count_type", sa.Text(), nullable=False),
        sa.Column("blind", sa.Boolean(), server_default="false", nullable=False),
        sa.CheckConstraint(
            _in("count_type", ("full", "spot", "cycle")),
            name=op.f("ck_stock_counts_count_type_valid"),
        ),
    )
    op.create_index(
        op.f("ix_stock_counts_tenant_id_outlet_id_status"),
        "stock_counts",
        ["tenant_id", "outlet_id", "status"],
    )
    op.create_table(
        "stock_count_lines",
        *_line("stock_count_lines", "count_id", "stock_counts"),
        sa.Column("batch_id", sa.Uuid(), nullable=True),
        sa.Column("system_qty", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("counted_qty", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.CheckConstraint(
            "counted_qty IS NULL OR counted_qty >= 0",
            name=op.f("ck_stock_count_lines_counted_not_negative"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "count_id",
            "item_id",
            name=op.f("uq_stock_count_lines_tenant_id_count_id_item_id"),
        ),
    )

    grant("waste_logs", "SELECT, INSERT, UPDATE")  # status only: posted -> reversed
    grant("waste_lines", "SELECT, INSERT")
    grant("adjustments", "SELECT, INSERT, UPDATE")
    grant("adjustment_lines", "SELECT, INSERT, DELETE")  # replaced as a set while a draft
    grant("stock_counts", "SELECT, INSERT, UPDATE")
    grant("stock_count_lines", "SELECT, INSERT, UPDATE")  # counted quantities
    for table in (
        "waste_logs",
        "waste_lines",
        "adjustments",
        "adjustment_lines",
        "stock_counts",
        "stock_count_lines",
    ):
        enable_tenant_rls(table)


def downgrade() -> None:
    for table in (
        "stock_count_lines",
        "stock_counts",
        "adjustment_lines",
        "adjustments",
        "waste_lines",
        "waste_logs",
    ):
        op.drop_table(table)
