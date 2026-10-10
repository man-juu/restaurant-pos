"""Storage locations inside an outlet (FR-INV-017): walk-in freezer, chiller, dry store.
Each item has one home location per outlet; a count can cover one location. Stock balances
stay per outlet: a location says where an item is kept, not a separate stock pool."""

import uuid

from sqlalchemy import ForeignKey, ForeignKeyConstraint, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, _id
from app.modules.inventory.models import _item_fk, _outlet_fk


class StorageLocation(Base):
    __tablename__ = "storage_locations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "outlet_id", "name"),
        _outlet_fk(),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    outlet_id: Mapped[uuid.UUID] = mapped_column()
    name: Mapped[str] = mapped_column(String(80))
    sort_order: Mapped[int] = mapped_column(server_default="0")
    is_active: Mapped[bool] = mapped_column(server_default="true")


class ItemLocation(Base):
    __tablename__ = "item_locations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "outlet_id", "item_id"),
        _outlet_fk(),
        _item_fk(),
        ForeignKeyConstraint(
            ["tenant_id", "location_id"], ["storage_locations.tenant_id", "storage_locations.id"]
        ),
        Index(None, "tenant_id", "location_id"),
    )

    id: Mapped[uuid.UUID] = _id()
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    outlet_id: Mapped[uuid.UUID] = mapped_column()
    item_id: Mapped[uuid.UUID] = mapped_column()
    location_id: Mapped[uuid.UUID] = mapped_column()
