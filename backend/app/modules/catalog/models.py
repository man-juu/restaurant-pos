"""Catalog tables (docs/05 section 2.2, FR-CAT-001, 002, 004 to 006, 008, 009).

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

import app.core.uploads.models  # noqa: F401 - uploads table for the photo foreign key
from app.core.models import Base, _check_in, _created_at, _id

UNIT_DIMENSIONS = ("mass", "volume", "count")
ITEM_TYPES = ("ingredient", "semi_finished", "menu")
# exact: every movement counts; estimated: hard to measure (rice, oil, gas), never blocks a
# posting, corrected with "set on hand"; untracked: no stock at all (is_stocked false).
TRACKING_MODES = ("exact", "estimated", "untracked")
STORAGE_TYPES = ("frozen", "chilled", "dry")
CHANNEL_KINDS = ("dine_in", "takeaway", "platform", "wholesale")
BOM_STATUSES = ("draft", "active")


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
        _check_in("tracking_mode", TRACKING_MODES),
        CheckConstraint(
            "(tracking_mode = 'untracked') = (NOT is_stocked)", name="tracking_matches_stocked"
        ),
        CheckConstraint("standard_cost IS NULL OR standard_cost >= 0", name="standard_cost"),
        CheckConstraint(
            "target_food_cost_bp IS NULL"
            " OR (target_food_cost_bp > 0 AND target_food_cost_bp <= 10000)",
            name="target_food_cost_bp",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "category_id"], ["item_categories.tenant_id", "item_categories.id"]
        ),
        ForeignKeyConstraint(["tenant_id", "photo_upload_id"], ["uploads.tenant_id", "uploads.id"]),
        Index(None, "tenant_id", "type", "is_active"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    sku: Mapped[str] = mapped_column(String(64))
    type: Mapped[str] = mapped_column(Text)
    category_id: Mapped[uuid.UUID | None] = mapped_column()
    base_unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("units.id"))
    is_stocked: Mapped[bool] = mapped_column(server_default="true")
    tracking_mode: Mapped[str] = mapped_column(Text, server_default="exact")
    # Minor units per base unit, used when the ledger has no average yet (or never will).
    standard_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    # FR-CAT-012: food cost (HPP) target, basis points of the net price (3500 = 35 %);
    # empty = the tenant default.
    target_food_cost_bp: Mapped[int | None] = mapped_column()
    shelf_life_days: Mapped[int | None] = mapped_column()
    storage_type: Mapped[str | None] = mapped_column(Text)
    allergens: Mapped[list[str]] = mapped_column(ARRAY(String(40)), server_default="{}")
    photo_upload_id: Mapped[uuid.UUID | None] = mapped_column()  # optional (FR-CAT-001)
    # FR-CAT-003 availability: false = sold out today; still active, just not sellable.
    is_available: Mapped[bool] = mapped_column(server_default="true")
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


class Bom(Base):
    """FR-CAT-005/006: one recipe version of an item.

    A draft can be edited and deleted. Activating it fixes its lines (sales and production
    record which version they used) and gives it a start date; the previous active version
    then ends the day before. The recipe on a date is the active version whose range holds it.
    Yield: how much of the item one batch makes (menu items: 1 base unit).
    """

    __tablename__ = "boms"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "item_id", "version"),
        ForeignKeyConstraint(["tenant_id", "item_id"], ["items.tenant_id", "items.id"]),
        _check_in("status", BOM_STATUSES),
        CheckConstraint("yield_qty > 0", name="yield_positive"),
        CheckConstraint("(status = 'active') = (valid_from IS NOT NULL)", name="active_dated"),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="valid_range"),
        Index(None, "tenant_id", "item_id", "status", "valid_from"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    item_id: Mapped[uuid.UUID] = mapped_column()
    version: Mapped[int] = mapped_column()
    yield_qty: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    yield_unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("units.id"))
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(Text, server_default="draft")
    created_at: Mapped[datetime] = _created_at()
    created_by: Mapped[uuid.UUID | None] = mapped_column()


class BomLine(Base):
    """One component: `qty` of `unit_id` goes into the dish (net). `waste_pct` is the share
    lost in preparation, so the quantity taken from stock is qty / (1 - waste_pct / 100)."""

    __tablename__ = "bom_lines"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "bom_id"], ["boms.tenant_id", "boms.id"], ondelete="CASCADE"
        ),
        ForeignKeyConstraint(["tenant_id", "component_item_id"], ["items.tenant_id", "items.id"]),
        CheckConstraint("qty > 0", name="qty_positive"),
        CheckConstraint("waste_pct >= 0 AND waste_pct < 100", name="waste_range"),
        Index(None, "tenant_id", "bom_id"),
        Index(None, "tenant_id", "component_item_id"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    bom_id: Mapped[uuid.UUID] = mapped_column()
    component_item_id: Mapped[uuid.UUID] = mapped_column()
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("units.id"))
    waste_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), server_default="0")


class PlatformItemMap(Base):
    """FR-CAT-010: the code a delivery platform uses for a menu item, per channel, so platform
    sales entered or imported by code land on the right recipe."""

    __tablename__ = "platform_item_map"
    __table_args__ = (
        UniqueConstraint("tenant_id", "channel_id", "platform_code"),
        ForeignKeyConstraint(["tenant_id", "channel_id"], ["channels.tenant_id", "channels.id"]),
        ForeignKeyConstraint(["tenant_id", "item_id"], ["items.tenant_id", "items.id"]),
        Index(None, "tenant_id", "item_id"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    channel_id: Mapped[uuid.UUID] = mapped_column()
    platform_code: Mapped[str] = mapped_column(String(64))
    item_id: Mapped[uuid.UUID] = mapped_column()


# Menu options live in menu_models.py (file size limit); re-exported here for callers.
from app.modules.catalog.menu_models import (  # noqa: E402
    ComboComponent,
    ItemModifierGroup,
    ModifierGroup,
    ModifierOption,
    OutletItemOverride,
)

__all__ = [
    "ComboComponent",
    "ItemModifierGroup",
    "ModifierGroup",
    "ModifierOption",
    "OutletItemOverride",
]
