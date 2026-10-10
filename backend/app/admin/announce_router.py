"""Platform announcements (FR-ADM-005): super admins write them; support may read them."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import delete, select

from app.admin.router import _tx
from app.admin.security import AdminContext, require_admin
from app.core.announcements.models import Announcement, AnnouncementTarget
from app.core.errors import ConflictError, NotFoundError
from app.core.models import Tenant

router = APIRouter(prefix="/admin-api/announcements", tags=["admin"])
SuperAdmin = Annotated[AdminContext, Depends(require_admin("super_admin"))]
Support = Annotated[AdminContext, Depends(require_admin("super_admin", "support"))]
Title = Annotated[str, Field(min_length=1, max_length=120)]
Body = Annotated[str, Field(min_length=1, max_length=2000)]


class AnnouncementIn(BaseModel):
    title_en: Title
    title_id: Title
    body_en: Body
    body_id: Body
    level: Literal["info", "warning"] = "info"
    starts_at: datetime
    ends_at: datetime
    tenant_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)  # empty: all

    @model_validator(mode="after")
    def _window(self) -> "AnnouncementIn":
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class AnnouncementRow(AnnouncementIn):
    id: uuid.UUID


async def _row(db, a: Announcement) -> AnnouncementRow:  # type: ignore[no-untyped-def]
    ids = list(
        await db.scalars(
            select(AnnouncementTarget.tenant_id).where(AnnouncementTarget.announcement_id == a.id)
        )
    )
    fields = {k: getattr(a, k) for k in AnnouncementIn.model_fields if k != "tenant_ids"}
    return AnnouncementRow(id=a.id, tenant_ids=ids, **fields)


async def _save(db, a: Announcement, body: AnnouncementIn) -> None:  # type: ignore[no-untyped-def]
    if body.tenant_ids:
        known = set(await db.scalars(select(Tenant.id).where(Tenant.id.in_(body.tenant_ids))))
        if missing := sorted(str(t) for t in set(body.tenant_ids) - known):
            raise ConflictError("unknown_tenant", details={"tenant_ids": missing})
    for k, v in body.model_dump(exclude={"tenant_ids"}).items():
        setattr(a, k, v)
    a.all_tenants = not body.tenant_ids
    db.add(a)
    await db.flush()
    await db.execute(delete(AnnouncementTarget).where(AnnouncementTarget.announcement_id == a.id))
    db.add_all(AnnouncementTarget(tenant_id=t, announcement_id=a.id) for t in set(body.tenant_ids))
    await db.flush()


@router.get("", response_model=list[AnnouncementRow])
async def list_all(request: Request, admin: Support) -> list[AnnouncementRow]:
    async with _tx(request) as db:
        rows = await db.scalars(select(Announcement).order_by(Announcement.starts_at.desc()))
        return [await _row(db, a) for a in rows]


@router.post("", response_model=AnnouncementRow, status_code=201)
async def create(body: AnnouncementIn, request: Request, admin: SuperAdmin) -> AnnouncementRow:
    async with _tx(request) as db:
        a = Announcement(created_by=admin.admin_id)
        await _save(db, a, body)
        return await _row(db, a)


@router.put("/{announcement_id}", response_model=AnnouncementRow)
async def update(
    announcement_id: uuid.UUID, body: AnnouncementIn, request: Request, admin: SuperAdmin
) -> AnnouncementRow:
    """Change or end one (set ends_at to now to take it down)."""
    async with _tx(request) as db:
        a = await db.get(Announcement, announcement_id)
        if a is None:
            raise NotFoundError()
        await _save(db, a, body)
        return await _row(db, a)
