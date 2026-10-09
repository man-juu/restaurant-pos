"""Platform item codes per channel (FR-CAT-010): list, replace, and look up by code."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.access.policy import Principal, require
from app.core.errors import ConflictError, NotFoundError
from app.core.tenancy import tenant_session
from app.modules.catalog import permissions as perm
from app.modules.catalog.models import Channel, Item, PlatformItemMap

Code = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


class MappingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform_code: Code
    item_id: uuid.UUID


class MappingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mappings: list[MappingIn] = Field(max_length=1000)


class MappingOut(MappingIn):
    pass


router = APIRouter(prefix="/api/v1/catalog/channels", tags=["catalog"])
View = Annotated[Principal, Depends(require(perm.ITEM_VIEW))]
Update = Annotated[Principal, Depends(require(perm.ITEM_UPDATE))]


async def _channel(db: AsyncSession, channel_id: uuid.UUID) -> Channel:
    channel = await db.get(Channel, channel_id)
    if channel is None:
        raise NotFoundError("channel_not_found")
    return channel


async def item_ids_by_code(
    db: AsyncSession, channel_id: uuid.UUID, codes: set[str]
) -> dict[str, uuid.UUID]:
    stmt = select(PlatformItemMap.platform_code, PlatformItemMap.item_id).where(
        PlatformItemMap.channel_id == channel_id, PlatformItemMap.platform_code.in_(codes)
    )
    return {row[0]: row[1] for row in (await db.execute(stmt)).all()}


@router.get("/{channel_id}/mappings", response_model=list[MappingOut])
async def list_mappings(channel_id: uuid.UUID, request: Request, p: View) -> list[MappingOut]:
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        await _channel(db, channel_id)
        stmt = select(PlatformItemMap).where(PlatformItemMap.channel_id == channel_id)
        rows = await db.scalars(stmt.order_by(PlatformItemMap.platform_code))
        return [MappingOut(platform_code=r.platform_code, item_id=r.item_id) for r in rows]


@router.put("/{channel_id}/mappings", response_model=list[MappingOut])
async def replace_mappings(
    channel_id: uuid.UUID, body: MappingsIn, request: Request, p: Update
) -> list[MappingOut]:
    """The whole list for the channel; a code appears once."""
    codes = [m.platform_code for m in body.mappings]
    if len(codes) != len(set(codes)):
        raise ConflictError("duplicate_platform_code")
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        await _channel(db, channel_id)
        ids = {m.item_id for m in body.mappings}
        found = set(await db.scalars(select(Item.id).where(Item.id.in_(ids))))
        if missing := ids - found:
            raise NotFoundError("item_not_found", details={"item_ids": sorted(map(str, missing))})
        await db.execute(delete(PlatformItemMap).where(PlatformItemMap.channel_id == channel_id))
        if body.mappings:
            await db.execute(
                insert(PlatformItemMap),
                [
                    {"tenant_id": p.tenant_id, "channel_id": channel_id, **m.model_dump()}
                    for m in body.mappings
                ],
            )
        await audit.record(
            db,
            tenant_id=p.tenant_id,
            user_id=p.user_id,
            action="catalog.platform_map.replace",
            target_type="channel",
            target_id=channel_id,
            summary={"count": len(body.mappings)},
        )
    return [MappingOut(**m.model_dump()) for m in body.mappings]
