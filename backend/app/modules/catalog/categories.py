"""Item categories (FR-CAT-003). Runs inside tenant_session: a parent another tenant owns
is "not found", and a parent chain may not loop."""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.errors import ConflictError, NotFoundError
from app.modules.catalog.models import ItemCategory
from app.modules.catalog.schemas import CategoryIn
from app.modules.catalog.service import InvalidCatalogReference


async def list_categories(db: AsyncSession) -> list[ItemCategory]:
    stmt = select(ItemCategory).order_by(ItemCategory.sort_order, ItemCategory.name)
    return list((await db.execute(stmt)).scalars())


async def _check_parent(
    db: AsyncSession, parent_id: uuid.UUID | None, self_id: uuid.UUID | None = None
) -> None:
    """Parent must exist in this tenant and must not create a loop."""
    seen = {self_id} if self_id else set()
    current = parent_id
    while current is not None:
        if current in seen:
            raise InvalidCatalogReference("category_cycle")
        seen.add(current)
        current_row = await db.get(ItemCategory, current)
        if current_row is None:
            raise InvalidCatalogReference(details={"parent_id": str(parent_id)})
        current = current_row.parent_id
        if len(seen) > 20:
            raise InvalidCatalogReference("category_too_deep")


async def save_category(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    data: CategoryIn,
    category_id: uuid.UUID | None = None,
) -> ItemCategory:
    await _check_parent(db, data.parent_id, category_id)
    if category_id is None:
        row = ItemCategory(tenant_id=tenant_id, **data.model_dump())
        db.add(row)
        action, before = "catalog.category.create", None
    else:
        found = await db.get(ItemCategory, category_id)
        if found is None:
            raise NotFoundError("category_not_found")
        row = found
        before = CategoryIn.model_validate(row, from_attributes=True).model_dump(mode="json")
        for key, value in data.model_dump().items():
            setattr(row, key, value)
        action = "catalog.category.update"
    try:
        await db.flush()
    except IntegrityError:
        raise ConflictError("category_name_taken") from None
    await audit.record(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action=action,
        target_type="item_category",
        target_id=row.id,
        summary={"before": before, "after": data.model_dump(mode="json")},
    )
    return row
