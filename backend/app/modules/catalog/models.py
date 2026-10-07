"""Catalog tables (docs/05 section 2.2, FR-CAT-001, 002, 004, 008, 009).

Units with tenant_id NULL are platform units (g, kg, ml, l, pcs) readable by every tenant.
Translatable names live in item_translations; tenant tables carry tenant_id and composite
(tenant_id, id) foreign keys so a row can never point at another tenant's row.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
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
CHANNEL_KINDS = ("dine_in", "takeaway", "platform", "wholesale")


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


class Channel(Base):
    """FR-CAT-004: where an item is sold. `code` is what tenant settings refer to (for example
    service_charge.channels), so it never changes after creation."""

    __tablename__ = "channels"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "code"),
        _check_in("kind", CHANNEL_KINDS),
        CheckConstraint("(kind = 'platform') = (platform IS NOT NULL)", name="platform_kind"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(Text)
    platform: Mapped[str | None] = mapped_column(String(40))
    sort_order: Mapped[int] = mapped_column(server_default="0")
    is_active: Mapped[bool] = mapped_column(server_default="true")


class ItemPrice(Base):
    """FR-CAT-004 list price of an item on a channel from `valid_from` (docs/09 0.20).

    The price on a date is the row with the latest valid_from on or before it. outlet_id and
    valid_to follow docs/05 but stay NULL until per-outlet overrides arrive in Phase 2.
    Money is integer minor units (CLAUDE.md rule 5)."""

    __tablename__ = "item_prices"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "item_id"], ["items.tenant_id", "items.id"]),
        ForeignKeyConstraint(["tenant_id", "channel_id"], ["channels.tenant_id", "channels.id"]),
        ForeignKeyConstraint(["tenant_id", "outlet_id"], ["outlets.tenant_id", "outlets.id"]),
        UniqueConstraint(
            "tenant_id",
            "item_id",
            "channel_id",
            "outlet_id",
            "valid_from",
            postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint("price >= 0", name="price_not_negative"),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="valid_range"),
        Index(None, "tenant_id", "channel_id", "item_id", "valid_from"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    item_id: Mapped[uuid.UUID] = mapped_column()
    channel_id: Mapped[uuid.UUID] = mapped_column()
    outlet_id: Mapped[uuid.UUID | None] = mapped_column()
    price: Mapped[int] = mapped_column(BigInteger)
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = _created_at()
    created_by: Mapped[uuid.UUID | None] = mapped_column()
