"""The tenant's audit log (FR-AUD-002, 004): read-only, filterable by person, action, date
and target, paged newest first, and exportable for a date range. Rows are never edited or
deleted (the table is append-only); this router only reads."""

import uuid
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import ColumnElement, Select, select

from app.core.access.policy import Principal, require
from app.core.errors import AppError
from app.core.imports.http import table_file
from app.core.models import AuditLog, Membership, User
from app.core.pagination import Page, PageParams, page_params, paginate
from app.core.tenancy import tenant_session

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])
View = Annotated[Principal, Depends(require("audit.log.view"))]
EXPORT_MAX_DAYS = 366
EXPORT_MAX_ROWS = 50_000


class ExportRangeRequired(AppError):
    status_code, code = 422, "range_too_long"


class AuditRow(BaseModel):
    id: uuid.UUID
    at: datetime
    actor_type: str
    user_id: uuid.UUID | None
    user_name: str | None
    outlet_id: uuid.UUID | None
    action: str
    target_type: str | None
    target_id: uuid.UUID | None
    summary: dict[str, Any]


class Filters(BaseModel):
    date_from: date | None = None
    date_to: date | None = None
    user_id: uuid.UUID | None = None
    action: str | None = None  # prefix, e.g. "purchasing." or "sales.day.lock"
    target_type: str | None = None
    target_id: uuid.UUID | None = None


def filters(
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    user_id: uuid.UUID | None = None,
    action: Annotated[str | None, Query(max_length=100, pattern=r"^[a-z_.]+$")] = None,
    target_type: Annotated[str | None, Query(max_length=100, pattern=r"^[a-z_]+$")] = None,
    target_id: uuid.UUID | None = None,
) -> Filters:
    return Filters(
        date_from=date_from,
        date_to=date_to,
        user_id=user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
    )


def _query(f: Filters) -> Select[Any]:
    # Names only for this tenant's members (users is a shared table).
    name = (
        select(User.name)
        .join(Membership, Membership.user_id == User.id)
        .where(User.id == AuditLog.user_id)
        .scalar_subquery()
    )
    stmt = select(AuditLog, name.label("user_name"))
    conditions: dict[str, Callable[[Any], ColumnElement[bool]]] = {
        "date_from": lambda v: AuditLog.at >= datetime.combine(v, time.min),
        "date_to": lambda v: AuditLog.at < datetime.combine(v + timedelta(days=1), time.min),
        "user_id": lambda v: AuditLog.user_id == v,
        # The pattern allows only [a-z_.]: no LIKE wildcards can come from the client.
        "action": lambda v: AuditLog.action.startswith(v),
        "target_type": lambda v: AuditLog.target_type == v,
        "target_id": lambda v: AuditLog.target_id == v,
    }
    for key, make in conditions.items():
        value = getattr(f, key)
        if value is not None:
            stmt = stmt.where(make(value))
    return stmt


def _row(log: AuditLog, user_name: str | None) -> AuditRow:
    return AuditRow(
        id=log.id,
        at=log.at,
        actor_type=log.actor_type,
        user_id=log.user_id,
        user_name=user_name,
        outlet_id=log.outlet_id,
        action=log.action,
        target_type=log.target_type,
        target_id=log.target_id,
        summary=log.summary,
    )


@router.get("", response_model=Page[AuditRow])
async def list_audit(
    request: Request,
    p: View,
    params: Annotated[PageParams, Depends(page_params)],
    f: Annotated[Filters, Depends(filters)],
) -> Page[AuditRow]:
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        at = cast(ColumnElement[Any], AuditLog.at)
        rows, cursor = await paginate(
            db,
            _query(f),
            PageParams(limit=params.limit, cursor=params.cursor, sort=params.sort or "-at"),
            id_column=cast(ColumnElement[Any], AuditLog.id),
            sortable={"at": at},
            default_sort="-at",
        )
    return Page(items=[_row(r[0], r[1]) for r in rows], next_cursor=cursor)


@router.get("/export")
async def export_audit(
    request: Request,
    p: View,
    f: Annotated[Filters, Depends(filters)],
    fmt: Annotated[Literal["csv", "xlsx"], Query(alias="format")] = "csv",
) -> Response:
    """FR-AUD-004: a date range is required and capped, so an export stays bounded."""
    if (
        f.date_from is None
        or f.date_to is None
        or (f.date_to - f.date_from).days >= EXPORT_MAX_DAYS
    ):
        raise ExportRangeRequired(details={"max_days": EXPORT_MAX_DAYS})
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        stmt = _query(f).order_by(AuditLog.at, AuditLog.id).limit(EXPORT_MAX_ROWS)
        rows = [_row(log, name) for log, name in (await db.execute(stmt)).all()]
    header = (
        "at",
        "actor_type",
        "user",
        "action",
        "target_type",
        "target_id",
        "outlet_id",
        "summary",
    )
    data = [
        [
            r.at.isoformat(),
            r.actor_type,
            r.user_name or "",
            r.action,
            r.target_type or "",
            str(r.target_id or ""),
            str(r.outlet_id or ""),
            str(r.summary),
        ]
        for r in rows
    ]
    return table_file(fmt, f"audit-{f.date_from}-{f.date_to}", header, data)
