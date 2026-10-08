"""Item photos (FR-CAT-001): optional; one photo per item. The bytes go through the shared
upload engine (app.core.uploads), which checks, re-encodes and stores them."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.access.policy import Principal, require
from app.core.errors import NotFoundError
from app.core.tenancy import tenant_session
from app.core.uploads import service as uploads
from app.core.uploads.models import Upload
from app.modules.catalog import permissions as perm
from app.modules.catalog.models import Item

router = APIRouter(prefix="/api/v1/catalog", tags=["catalog"])

Update = Annotated[Principal, Depends(require(perm.ITEM_UPDATE))]


class PhotoOut(uploads.UploadRef):
    pass


async def _set_photo(
    db: AsyncSession, p: Principal, item_id: uuid.UUID, upload_id: uuid.UUID | None
) -> None:
    # A plain UPDATE: a photo change does not bump the item version used by the edit form.
    result = await db.execute(
        update(Item).where(Item.id == item_id).values(photo_upload_id=upload_id)
    )
    if result.rowcount == 0:  # type: ignore[attr-defined]  # RLS: other tenants' items are invisible
        raise NotFoundError("item_not_found")
    await audit.record(
        db,
        tenant_id=p.tenant_id,
        user_id=p.user_id,
        action="catalog.item.photo",
        target_type="item",
        target_id=item_id,
        summary={"upload_id": str(upload_id) if upload_id else None},
    )


@router.put("/items/{item_id}/photo", response_model=PhotoOut)
async def put_photo(item_id: uuid.UUID, request: Request, p: Update) -> PhotoOut:
    """Body: the raw image bytes (JPEG, PNG or WebP). One transaction: stored and linked, or
    neither."""
    settings = request.app.state.settings
    raw = await uploads.read_body(request, settings.upload_max_bytes)
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        if await db.get(Item, item_id) is None:
            raise NotFoundError("item_not_found")
        row = await uploads.store_image(
            db, settings, tenant_id=p.tenant_id, user_id=p.user_id, purpose="item_photo", raw=raw
        )
        await _set_photo(db, p, item_id, row.id)
        return PhotoOut.model_validate(row, from_attributes=True)


@router.delete("/items/{item_id}/photo", status_code=204)
async def delete_photo(item_id: uuid.UUID, request: Request, p: Update) -> None:
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        await _set_photo(db, p, item_id, None)


@router.put("/items/{item_id}/photo/{upload_id}", response_model=PhotoOut)
async def use_existing_photo(
    item_id: uuid.UUID, upload_id: uuid.UUID, request: Request, p: Update
) -> PhotoOut:
    """Accept an image already stored for this tenant (for example an AI image)."""
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        row = await db.get(Upload, upload_id)  # RLS: another tenant's upload is not found
        if row is None or row.purpose != "item_photo":
            raise NotFoundError("upload_not_found")
        await _set_photo(db, p, item_id, upload_id)
        return PhotoOut.model_validate(row, from_attributes=True)
