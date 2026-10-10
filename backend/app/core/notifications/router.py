"""The signed-in user's notifications (FR-NTF-001). Any member may read their own: rows are
filtered by the session user, never by an id from the client alone."""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel
from sqlalchemy import func, select, update

from app.core.access.policy import Principal, require_member
from app.core.notifications.models import Notification
from app.core.tenancy import tenant_session

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])
Member = Annotated[Principal, Depends(require_member())]
PAGE = 50


class NotificationOut(BaseModel):
    id: uuid.UUID
    kind: str
    params: dict[str, Any]
    link: str | None
    created_at: datetime
    read_at: datetime | None


class UnreadOut(BaseModel):
    unread: int


def _db(request: Request, p: Principal):  # type: ignore[no-untyped-def]
    return tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id)


@router.get("", response_model=list[NotificationOut])
async def list_notifications(request: Request, p: Member) -> list[NotificationOut]:
    async with _db(request, p) as db:
        stmt = (
            select(Notification)
            .where(Notification.user_id == p.user_id)
            .order_by(Notification.read_at.is_not(None), Notification.created_at.desc())
            .limit(PAGE)
        )
        rows = await db.scalars(stmt)
        return [NotificationOut.model_validate(n, from_attributes=True) for n in rows]


@router.get("/unread-count", response_model=UnreadOut)
async def unread_count(request: Request, p: Member) -> UnreadOut:
    async with _db(request, p) as db:
        n = await db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == p.user_id, Notification.read_at.is_(None))
        )
    return UnreadOut(unread=n or 0)


@router.post("/{notification_id}/read", status_code=204)
async def mark_read(notification_id: uuid.UUID, request: Request, p: Member) -> Response:
    async with _db(request, p) as db:
        await db.execute(
            update(Notification)
            .where(Notification.id == notification_id, Notification.user_id == p.user_id)
            .values(read_at=func.coalesce(Notification.read_at, datetime.now(UTC)))
        )
    return Response(status_code=204)


@router.post("/read-all", status_code=204)
async def mark_all_read(request: Request, p: Member) -> Response:
    async with _db(request, p) as db:
        await db.execute(
            update(Notification)
            .where(Notification.user_id == p.user_id, Notification.read_at.is_(None))
            .values(read_at=datetime.now(UTC))
        )
    return Response(status_code=204)
