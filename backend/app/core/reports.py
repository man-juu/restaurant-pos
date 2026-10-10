"""Shared report plumbing (FR-RPT-006, 010, 011): a date range, the outlets the caller may
see, and one response shape that can also be downloaded as CSV or Excel.

Each module serves the reports over its own tables (CLAUDE.md rule 4); this file only holds
what they share. Reports are computed on request from indexed tables and carry the time
they were computed; a background cache comes when measured need appears (FR-RPT-010)."""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel

from app.core.access.policy import Principal
from app.core.errors import AppError
from app.core.imports.http import table_file

MAX_DAYS = 366
Format = Literal["json", "csv", "xlsx"]


class RangeTooLong(AppError):
    status_code, code = 422, "range_too_long"


@dataclass(frozen=True)
class Period:
    date_from: date
    date_to: date
    outlet_id: uuid.UUID | None
    fmt: Format

    @property
    def days(self) -> int:
        return (self.date_to - self.date_from).days + 1

    def previous(self) -> "Period":
        """The period of the same length just before (for comparisons)."""
        end = self.date_from - timedelta(days=1)
        return Period(end - timedelta(days=self.days - 1), end, self.outlet_id, self.fmt)


def period(
    date_from: Annotated[date, Query(alias="from")],
    date_to: Annotated[date, Query(alias="to")],
    outlet_id: uuid.UUID | None = None,
    fmt: Annotated[Format, Query(alias="format")] = "json",
) -> Period:
    if date_to < date_from or (date_to - date_from).days >= MAX_DAYS:
        raise RangeTooLong(details={"max_days": MAX_DAYS})
    return Period(date_from, date_to, outlet_id, fmt)


PeriodDep = Annotated[Period, Depends(period)]


def outlet_filter(p: Principal, period: Period) -> list[uuid.UUID] | None:
    """The outlets to include: the one asked for (if visible), else every outlet the caller
    may see (None = all outlets of the tenant)."""
    if period.outlet_id is not None:
        p.require_outlet(period.outlet_id)
        return [period.outlet_id]
    return p.visible_outlets()


class Report(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    computed_at: datetime
    totals: dict[str, Any] = {}


def build(
    columns: list[str], rows: list[dict[str, Any]], totals: dict[str, Any] | None = None
) -> Report:
    return Report(columns=columns, rows=rows, computed_at=datetime.now(UTC), totals=totals or {})


def respond(report: Report, period: Period, name: str) -> Report | Response:
    if period.fmt == "json":
        return report
    rows = [[r.get(c) for c in report.columns] for r in report.rows]
    stamp = f"{name}-{period.date_from.isoformat()}-{period.date_to.isoformat()}"
    return table_file(period.fmt, stamp, tuple(report.columns), rows)
