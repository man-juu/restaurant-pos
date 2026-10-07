"""FR-X-004: keyset pagination and whitelisted sorting, against real PostgreSQL."""

import pytest
from hypothesis import given
from hypothesis import strategies as st
from sqlalchemy import Column, Integer, MetaData, String, Table, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import (
    InvalidCursor,
    InvalidSort,
    PageParams,
    decode_cursor,
    encode_cursor,
    paginate,
)

items = Table(
    "_test_items",
    MetaData(),
    Column("id", Integer, primary_key=True),
    Column("name", String, nullable=False),
    prefixes=["TEMPORARY"],
)
SORTABLE = {"name": items.c.name, "id": items.c.id}


@given(st.one_of(st.text(), st.integers()), st.integers())
def test_cursor_round_trip(value: object, row_id: int) -> None:
    assert decode_cursor(encode_cursor([value, row_id])) == [value, row_id]


@pytest.mark.parametrize("bad", ["", "%%%", encode_cursor([1, 2, 3]), "bm90IGpzb24"])
def test_invalid_cursor(bad: str) -> None:
    with pytest.raises(InvalidCursor):
        decode_cursor(bad)


async def _seed(session: AsyncSession) -> None:
    await session.run_sync(lambda s: items.create(s.connection()))
    # Duplicate names on purpose: the id tie-breaker must keep the order stable.
    rows = [{"id": i, "name": f"item-{i % 7:02d}"} for i in range(1, 31)]
    await session.execute(insert(items), rows)


async def _all_pages(session: AsyncSession, sort: str, limit: int) -> list[int]:
    seen: list[int] = []
    cursor = None
    while True:
        page, cursor = await paginate(
            session,
            select(items.c.id),
            PageParams(limit=limit, cursor=cursor, sort=sort),
            id_column=items.c.id,
            sortable=SORTABLE,
            default_sort="id",
        )
        assert len(page) <= limit
        seen.extend(page)
        if cursor is None:
            return seen


@pytest.mark.anyio
@pytest.mark.parametrize("sort", ["name", "-name", "id", "-id"])
async def test_fr_x_004_pages_cover_every_row_once_in_order(
    session: AsyncSession, sort: str
) -> None:
    await _seed(session)
    expected = list(
        (
            await session.execute(
                select(items.c.id).order_by(
                    *(
                        c.desc() if sort.startswith("-") else c.asc()
                        for c in (SORTABLE[sort.lstrip("-")], items.c.id)
                    )
                )
            )
        ).scalars()
    )
    assert await _all_pages(session, sort, limit=4) == expected


@pytest.mark.anyio
async def test_fr_x_004_rejects_unlisted_sort_column(session: AsyncSession) -> None:
    await _seed(session)
    with pytest.raises(InvalidSort):
        await paginate(
            session,
            select(items.c.id),
            PageParams(sort="password"),
            id_column=items.c.id,
            sortable=SORTABLE,
            default_sort="id",
        )
