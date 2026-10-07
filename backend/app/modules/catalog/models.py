"""Catalog tables (docs/05 section 2.2, FR-CAT-001, 002, 008, 009).

Units with tenant_id NULL are platform units (g, kg, ml, l, pcs) readable by every tenant.
Translatable names live in item_translations; tenant tables carry tenant_id and composite
(tenant_id, id) foreign keys so a row can never point at another tenant's row.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, _check_in, _created_at, _id

UNIT_DIMENSIONS = ("mass", "volume", "count")
ITEM_TYPES = ("ingredient", "semi_finished", "menu")
STORAGE_TYPES = ("frozen", "chilled", "dry")


class Unit(Base):
    __tablename__ = "units"
    __table_args__ = (
        _check_in("dimension", UNIT_DIMENSIONS),
        UniqueConstraint("tenant_id", "code", postgresql_nulls_not_distinct=True),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tenants.id"))
    code: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(80))
    dimension: Mapped[str] = mapped_column(Text)


class ItemCategory(Base):
    __tablename__ = "item_categories"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "parent_id", "name", postgresql_nulls_not_distinct=True),
        ForeignKeyConstraint(
            ["tenant_id", "parent_id"], ["item_categories.tenant_id", "item_categories.id"]
        ),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    parent_id: Mapped[uuid.UUID | None] = mapped_column()
    name: Mapped[str] = mapped_column(String(120))
    sort_order: Mapped[int] = mapped_column(server_default="0")
    is_active: Mapped[bool] = mapped_column(server_default="true")


class Item(Base):
    __tablename__ = "items"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "sku"),
        _check_in("type", ITEM_TYPES),
        CheckConstraint(
            "storage_type IS NULL OR storage_type IN ('frozen', 'chilled', 'dry')",
            name="storage_type_valid",
        ),
        CheckConstraint("shelf_life_days IS NULL OR shelf_life_days > 0", name="shelf_life"),
        ForeignKeyConstraint(
            ["tenant_id", "category_id"], ["item_categories.tenant_id", "item_categories.id"]
        ),
        Index(None, "tenant_id", "type", "is_active"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    sku: Mapped[str] = mapped_column(String(64))
    type: Mapped[str] = mapped_column(Text)
    category_id: Mapped[uuid.UUID | None] = mapped_column()
    base_unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("units.id"))
    is_stocked: Mapped[bool] = mapped_column(server_default="true")
    shelf_life_days: Mapped[int | None] = mapped_column()
    storage_type: Mapped[str | None] = mapped_column(Text)
    allergens: Mapped[list[str]] = mapped_column(ARRAY(String(40)), server_default="{}")
    is_active: Mapped[bool] = mapped_column(server_default="true")
    version: Mapped[int] = mapped_column(server_default="1")
    created_at: Mapped[datetime] = _created_at()
    created_by: Mapped[uuid.UUID | None] = mapped_column()
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_by: Mapped[uuid.UUID | None] = mapped_column()

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012 - optimistic locking


class ItemTranslation(Base):
    __tablename__ = "item_translations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "item_id"], ["items.tenant_id", "items.id"], ondelete="CASCADE"
        ),
        Index(None, "tenant_id", "language", "name"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    item_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    language: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)


class ItemUnitConversion(Base):
    """FR-CAT-002: 1 <unit> = factor_to_base <item base unit>. Exact decimal."""

    __tablename__ = "item_unit_conversions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "item_id"], ["items.tenant_id", "items.id"], ondelete="CASCADE"
        ),
        CheckConstraint("factor_to_base > 0", name="factor_positive"),
        Index(None, "tenant_id", "item_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    item_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("units.id"), primary_key=True)
    factor_to_base: Mapped[Decimal] = mapped_column(Numeric(18, 6))
