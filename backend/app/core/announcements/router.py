"""Announcements for the signed-in person (FR-ADM-005): active ones meant for this tenant,
in the person's language, not yet dismissed by them."""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert

from app.core.access.policy import Principal, require_member
from app.core.announcements.models import (
    Announcement,
    AnnouncementDismissal,
    AnnouncementTarget,
)
from app.core.errors import NotFoundError
from app.core.tenancy import tenant_session

router = APIRouter(prefix="/api/v1/announcements", tags=["tenant"])
Member = Annotated[Principal, Depends(require_member())]


class AnnouncementOut(BaseModel):
    id: uuid.UUID
    level: str
    title: str
    body: str
    ends_at: datetime


def _db(request: Request, p: Principal):  # type: ignore[no-untyped-def]
    return tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id)


def _visible(p: Principal, now: datetime):  # type: ignore[no-untyped-def]
    targeted = select(AnnouncementTarget.announcement_id)  # RLS: this tenant's targets only
    dismissed = select(AnnouncementDismissal.announcement_id).where(
        AnnouncementDismissal.user_id == p.user_id
    )
    return select(Announcement).where(
        Announcement.starts_at <= now,
        Announcement.ends_at > now,
        or_(Announcement.all_tenants, Announcement.id.in_(targeted)),
        Announcement.id.not_in(dismissed),
    )


@router.get("", response_model=list[AnnouncementOut])
async def mine(
    request: Request, p: Member, lang: Literal["en", "id"] = "en"
) -> list[AnnouncementOut]:
    async with _db(request, p) as db:
        rows = await db.scalars(_visible(p, datetime.now(UTC)).order_by(Announcement.starts_at))
        return [
            AnnouncementOut(
                id=a.id,
                level=a.level,
                title=a.title_id if lang == "id" else a.title_en,
                body=a.body_id if lang == "id" else a.body_en,
                ends_at=a.ends_at,
            )
            for a in rows
        ]


@router.post("/{announcement_id}/dismiss", status_code=204)
async def dismiss(announcement_id: uuid.UUID, request: Request, p: Member) -> None:
    async with _db(request, p) as db:
        visible = await db.scalar(
            _visible(p, datetime.now(UTC)).where(Announcement.id == announcement_id)
        )
        if visible is None:
            raise NotFoundError("announcement_not_found")
        await db.execute(
            insert(AnnouncementDismissal)
            .values(tenant_id=p.tenant_id, user_id=p.user_id, announcement_id=announcement_id)
            .on_conflict_do_nothing()
        )
