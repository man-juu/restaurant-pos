"""Cursor (keyset) pagination, sorting and filtering for list endpoints (FR-X-004).

Why keyset instead of OFFSET: OFFSET scans and discards every skipped row, so page 1000 is
slow; keyset seeks straight to the last row seen using an index, so every page costs the same.
The cursor is opaque to clients (base64url JSON of the last row's sort value and id).
"""

import base64
import binascii
import json
from collections.abc import Mapping, Sequence
from typing import Annotated, Any

from fastapi import Query
from pydantic import BaseModel
from sqlalchemy import ColumnElement, Select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError

MAX_LIMIT = 200


class InvalidCursor(AppError):
    status_code, code = 400, "invalid_cursor"


class InvalidSort(AppError):
    status_code, code = 400, "invalid_sort"


class Page[T](BaseModel):
    items: list[T]
    next_cursor: str | None


class PageParams(BaseModel):
    limit: int = 50
    cursor: str | None = None
    sort: str | None = None  # "name" ascending, "-name" descending


def page_params(
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 50,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    sort: Annotated[str | None, Query(max_length=64)] = None,
) -> PageParams:
    return PageParams(limit=limit, cursor=cursor, sort=sort)


def encode_cursor(values: Sequence[Any]) -> str:
    raw = json.dumps(list(values), default=str, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> list[Any]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        values = json.loads(raw)
    except (binascii.Error, ValueError):
        raise InvalidCursor() from None
    if not isinstance(values, list) or len(values) != 2:
        raise InvalidCursor()
    return values


async def paginate(
    session: AsyncSession,
    stmt: Select[Any],
    params: PageParams,
    *,
    id_column: ColumnElement[Any],
    sortable: Mapping[str, ColumnElement[Any]],
    default_sort: str,
) -> tuple[list[Any], str | None]:
    """Run `stmt` one page at a time. Only whitelisted columns can be sorted on (no injection,
    and each should be indexed). `id_column` breaks ties so ordering is total and stable.
    Returns rows (scalars if the statement selects one entity) and the next cursor.
    """
    sort = params.sort or default_sort
    descending = sort.startswith("-")
    column = sortable.get(sort.lstrip("-"))
    if column is None:
        raise InvalidSort(details={"allowed": sorted(sortable)})

    if params.cursor:
        last_value, last_id = decode_cursor(params.cursor)
        # Row-value comparison written out, so NULL-free sort columns use the index.
        if descending:
            seek = or_(column < last_value, and_(column == last_value, id_column < last_id))
        else:
            seek = or_(column > last_value, and_(column == last_value, id_column > last_id))
        stmt = stmt.where(seek)

    order = (column.desc(), id_column.desc()) if descending else (column.asc(), id_column.asc())
    stmt = stmt.add_columns(column.label("_sort"), id_column.label("_id")).order_by(*order)
    rows = (await session.execute(stmt.limit(params.limit + 1))).all()  # one extra: is there more?

    has_more = len(rows) > params.limit
    rows = rows[: params.limit]
    next_cursor = encode_cursor([rows[-1]._sort, rows[-1]._id]) if has_more else None
    items = [row[0] if len(row) == 3 else tuple(row[:-2]) for row in rows]
    return items, next_cursor
