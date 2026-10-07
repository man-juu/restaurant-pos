"""catalog: recipes (boms, bom_lines) with versions (slice 1c, FR-CAT-005, 006)

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-07 23:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from migrations.helpers import enable_tenant_rls, grant

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "boms",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("yield_qty", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("yield_unit_id", sa.Uuid(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("status", sa.Text(), server_default="draft", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "(status = 'active') = (valid_from IS NOT NULL)", name=op.f("ck_boms_active_dated")
        ),
        sa.CheckConstraint("status IN ('draft', 'active')", name=op.f("ck_boms_status_valid")),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from", name=op.f("ck_boms_valid_range")
        ),
        sa.CheckConstraint("yield_qty > 0", name=op.f("ck_boms_yield_positive")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "item_id"],
            ["items.tenant_id", "items.id"],
            name=op.f("fk_boms_tenant_id_item_id_items"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_boms_tenant_id_tenants")
        ),
        sa.ForeignKeyConstraint(
            ["yield_unit_id"], ["units.id"], name=op.f("fk_boms_yield_unit_id_units")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_boms")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_boms_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id", "item_id", "version", name=op.f("uq_boms_tenant_id_item_id_version")
        ),
    )
    op.create_index(
        op.f("ix_boms_tenant_id_item_id_status_valid_from"),
        "boms",
        ["tenant_id", "item_id", "status", "valid_from"],
        unique=False,
    )
    op.create_table(
        "bom_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("bom_id", sa.Uuid(), nullable=False),
        sa.Column("component_item_id", sa.Uuid(), nullable=False),
        sa.Column("qty", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("unit_id", sa.Uuid(), nullable=False),
        sa.Column(
            "waste_pct", sa.Numeric(precision=5, scale=2), server_default="0", nullable=False
        ),
        sa.CheckConstraint("qty > 0", name=op.f("ck_bom_lines_qty_positive")),
        sa.CheckConstraint(
            "waste_pct >= 0 AND waste_pct < 100", name=op.f("ck_bom_lines_waste_range")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "bom_id"],
            ["boms.tenant_id", "boms.id"],
            name=op.f("fk_bom_lines_tenant_id_bom_id_boms"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "component_item_id"],
            ["items.tenant_id", "items.id"],
            name=op.f("fk_bom_lines_tenant_id_component_item_id_items"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_bom_lines_tenant_id_tenants")
        ),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"], name=op.f("fk_bom_lines_unit_id_units")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bom_lines")),
    )
    op.create_index(
        op.f("ix_bom_lines_tenant_id_bom_id"), "bom_lines", ["tenant_id", "bom_id"], unique=False
    )
    op.create_index(
        op.f("ix_bom_lines_tenant_id_component_item_id"),
        "bom_lines",
        ["tenant_id", "component_item_id"],
        unique=False,
    )

    # Drafts are deleted; active versions are kept (sales and production refer to them).
    grant("boms", "SELECT, INSERT, UPDATE, DELETE")
    grant("bom_lines", "SELECT, INSERT, DELETE")  # replaced as a set while a draft
    for table in ("boms", "bom_lines"):
        enable_tenant_rls(table)
    # Defence in depth: the lines of an active recipe can never change, even by a bug.
    op.execute(
        "CREATE FUNCTION bom_lines_frozen() RETURNS trigger LANGUAGE plpgsql AS $$ "
        "BEGIN IF EXISTS (SELECT 1 FROM boms WHERE id = COALESCE(OLD.bom_id, NEW.bom_id) "
        "AND status = 'active') THEN RAISE EXCEPTION 'lines of an active recipe are fixed' "
        "USING ERRCODE = 'insufficient_privilege'; END IF; RETURN COALESCE(NEW, OLD); END $$"
    )
    op.execute(
        "CREATE TRIGGER bom_lines_frozen BEFORE INSERT OR UPDATE OR DELETE ON bom_lines "
        "FOR EACH ROW EXECUTE FUNCTION bom_lines_frozen()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS bom_lines_frozen ON bom_lines")
    op.execute("DROP FUNCTION IF EXISTS bom_lines_frozen()")
    op.drop_index(op.f("ix_bom_lines_tenant_id_component_item_id"), table_name="bom_lines")
    op.drop_index(op.f("ix_bom_lines_tenant_id_bom_id"), table_name="bom_lines")
    op.drop_table("bom_lines")
    op.drop_index(op.f("ix_boms_tenant_id_item_id_status_valid_from"), table_name="boms")
    op.drop_table("boms")
