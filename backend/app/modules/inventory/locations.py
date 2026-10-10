"""Storage locations and where each item is kept (FR-INV-017)."""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.errors import ConflictError, NotFoundError
from app.modules.catalog.interface import stock_items
from app.modules.inventory.location_models import ItemLocation, StorageLocation
from app.modules.inventory.opening import visible_outlet


async def _audit(
    db: AsyncSession, row: StorageLocation, user_id: uuid.UUID, action: str, **summary: object
) -> None:
    await audit.record(
        db,
        tenant_id=row.tenant_id,
        user_id=user_id,
        outlet_id=row.outlet_id,
        action=f"inventory.location.{action}",
        target_type="storage_location",
        target_id=row.id,
        summary={"name": row.name, **summary},
    )


async def get(db: AsyncSession, location_id: uuid.UUID) -> StorageLocation:
    row = await db.get(StorageLocation, location_id)
    if row is None:
        raise NotFoundError("location_not_found")
    return row


async def save(
    db: AsyncSession,
    row: StorageLocation,
    user_id: uuid.UUID,
    action: str,
) -> StorageLocation:
    await visible_outlet(db, row.outlet_id)
    db.add(row)
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError:
        raise ConflictError("location_name_taken") from None
    await _audit(db, row, user_id, action, active=row.is_active)
    return row


async def assign(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    location: StorageLocation,
    item_ids: list[uuid.UUID],
) -> None:
    """Make `location` the home of these items at its outlet (moving them from another)."""
    found = await stock_items(db, item_ids)
    if bad := sorted(str(i) for i in item_ids if i not in found or not found[i].is_stocked):
        raise ConflictError("invalid_reference", details={"item_ids": bad})
    rows = [
        {
            "tenant_id": tenant_id,
            "outlet_id": location.outlet_id,
            "item_id": i,
            "location_id": location.id,
        }
        for i in item_ids
    ]
    stmt = insert(ItemLocation).values(rows)
    await db.execute(
        stmt.on_conflict_do_update(
            index_elements=["tenant_id", "outlet_id", "item_id"],
            set_={"location_id": stmt.excluded.location_id},
        )
    )
    await _audit(db, location, user_id, "assign", items=len(item_ids))


async def unassign(
    db: AsyncSession, outlet_id: uuid.UUID, item_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    kept = await db.scalar(
        select(ItemLocation).where(
            ItemLocation.outlet_id == outlet_id, ItemLocation.item_id == item_id
        )
    )
    if kept is None:
        return
    location = await get(db, kept.location_id)
    await db.execute(delete(ItemLocation).where(ItemLocation.id == kept.id))
    await _audit(db, location, user_id, "unassign", item_id=str(item_id))


async def items_at(
    db: AsyncSession, outlet_id: uuid.UUID, location_id: uuid.UUID
) -> set[uuid.UUID]:
    location = await get(db, location_id)
    if location.outlet_id != outlet_id:
        raise ConflictError("location_other_outlet")
    rows = await db.scalars(
        select(ItemLocation.item_id).where(ItemLocation.location_id == location_id)
    )
    return set(rows)


async def homes(db: AsyncSession, outlet_id: uuid.UUID) -> dict[uuid.UUID, uuid.UUID]:
    """Item -> its location at this outlet."""
    rows = await db.execute(
        select(ItemLocation.item_id, ItemLocation.location_id).where(
            ItemLocation.outlet_id == outlet_id
        )
    )
    return dict(rows.tuples().all())
