"""Menu options (FR-CAT-003, 011, FR-TEN-011): modifier groups and options, combos, and
per-outlet overrides. Kept apart from models.py for size; the tables are the catalog's."""

import uuid
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, _id


class ModifierGroup(Base):
    """FR-CAT-003: a choice on a menu item ("Size", "Add-ons", "Spice level"). The cashier
    must pick between min_select and max_select options."""

    __tablename__ = "modifier_groups"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "name"),
        CheckConstraint(
            "min_select >= 0 AND max_select >= 1 AND min_select <= max_select", name="selects"
        ),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    name: Mapped[str] = mapped_column(String(120))
    min_select: Mapped[int] = mapped_column(server_default="0")
    max_select: Mapped[int] = mapped_column(server_default="1")
    is_active: Mapped[bool] = mapped_column(server_default="true")


class ModifierOption(Base):
    """One option: a price change and optionally an ingredient change in the ingredient's base
    unit (positive = extra, negative = without). Options are never deleted, only switched
    off, because sold order lines keep pointing at them."""

    __tablename__ = "modifier_options"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "group_id"], ["modifier_groups.tenant_id", "modifier_groups.id"]
        ),
        ForeignKeyConstraint(["tenant_id", "ingredient_item_id"], ["items.tenant_id", "items.id"]),
        CheckConstraint(
            "(ingredient_item_id IS NULL) = (ingredient_qty IS NULL)"
            " AND (ingredient_qty IS NULL OR ingredient_qty <> 0)",
            name="ingredient",
        ),
        Index(None, "tenant_id", "group_id"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    group_id: Mapped[uuid.UUID] = mapped_column()
    name: Mapped[str] = mapped_column(String(120))
    price_delta: Mapped[int] = mapped_column(BigInteger, server_default="0")
    ingredient_item_id: Mapped[uuid.UUID | None] = mapped_column()
    ingredient_qty: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    sort_order: Mapped[int] = mapped_column(server_default="0")
    is_active: Mapped[bool] = mapped_column(server_default="true")


class ItemModifierGroup(Base):
    """Which groups a menu item offers, in display order."""

    __tablename__ = "item_modifier_groups"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "item_id"], ["items.tenant_id", "items.id"]),
        ForeignKeyConstraint(
            ["tenant_id", "group_id"], ["modifier_groups.tenant_id", "modifier_groups.id"]
        ),
        Index(None, "tenant_id", "group_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    item_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    group_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    sort_order: Mapped[int] = mapped_column(server_default="0")


class ComboComponent(Base):
    """FR-CAT-011: a combo (a menu item sold at its own bundle price) and the menu items in
    it. Selling the combo takes each component's recipe out of stock."""

    __tablename__ = "combo_components"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "combo_item_id"], ["items.tenant_id", "items.id"]),
        ForeignKeyConstraint(["tenant_id", "component_item_id"], ["items.tenant_id", "items.id"]),
        CheckConstraint("qty > 0", name="qty"),
        CheckConstraint("combo_item_id <> component_item_id", name="not_itself"),
        Index(None, "tenant_id", "component_item_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    combo_item_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    component_item_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    sort_order: Mapped[int] = mapped_column(server_default="0")


class OutletItemOverride(Base):
    """FR-TEN-011: one outlet's own sold-out switch for an item; the master menu is shared
    by default. Outlet prices live in item_prices with an outlet_id."""

    __tablename__ = "outlet_item_overrides"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "outlet_id"], ["outlets.tenant_id", "outlets.id"]),
        ForeignKeyConstraint(["tenant_id", "item_id"], ["items.tenant_id", "items.id"]),
        Index(None, "tenant_id", "item_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    outlet_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    item_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    is_available: Mapped[bool] = mapped_column(server_default="true")
    note: Mapped[str | None] = mapped_column(String(200))
