"""FR-IMP-004: a delivery platform's sales export becomes daily sales entries. The saved
mapping names the date, item code, quantity and (optionally) amount columns; rows are summed
per day and item and posted through the normal day entry (stock out by recipe, journal by
event). Codes match the platform codes on the channel (FR-CAT-010), then item SKUs."""

import re
import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.imports.runner import Builder, Outcome
from app.modules.catalog.interface import item_ids_by_code, item_ids_by_sku
from app.modules.sales import service
from app.modules.sales.platform_import_models import PlatformImportMapping
from app.modules.sales.schemas import DayEntryIn

MAX_DAYS = 62  # one file covers at most two months; keeps one request bounded
Lines = dict[uuid.UUID, list[Decimal | int]]


class RowError(Exception):
    pass


def parse_date(value: str, fmt: str) -> date:
    """The day part of '2026-10-09', '09/10/2026 12:30' or '2026-10-09T12:30:00'."""
    text = re.split(r"[ T]", value.strip(), maxsplit=1)[0]
    parts = re.split(r"[-/.]", text)
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ValueError(value)
    a, b, c = (int(p) for p in parts)
    if len(parts[0]) == 4:  # year first, whatever the saved format
        return date(a, b, c)
    return date(c, b, a) if fmt == "dmy" else date(c, a, b)


def parse_amount(value: str) -> int:
    """Whole currency units from 'Rp 25.000', '25,000', '25000.00' or '25.000,00'."""
    text = re.sub(r"[^\d.,-]", "", value)
    text = re.sub(r"[.,]\d{1,2}$", "", text)  # cents part (none in IDR)
    digits = re.sub(r"[.,]", "", text)
    if not re.fullmatch(r"\d{1,15}", digits):
        raise ValueError(value)
    return int(digits)


def parse_qty(value: str) -> Decimal:
    try:
        qty = Decimal(value.strip().replace(",", "."))
    except InvalidOperation:
        raise ValueError(value) from None
    if not qty.is_finite() or qty <= 0:
        raise ValueError(value)
    return qty


def _row(row: dict[str, str], m: PlatformImportMapping, items: dict[str, uuid.UUID]):  # type: ignore[no-untyped-def]
    """(day, item, qty, amount) or RowError(field)."""
    steps = (
        ("date", lambda: parse_date(row.get(m.date_column, ""), m.date_format)),
        ("code", lambda: items[row.get(m.code_column, "").strip().lower()]),
        ("qty", lambda: parse_qty(row.get(m.qty_column, ""))),
        ("amount", lambda: parse_amount(row[m.amount_column]) if m.amount_column else 0),
    )
    values = []
    for field, step in steps:
        try:
            values.append(step())
        except (KeyError, ValueError):
            raise RowError(field) from None
    return values


async def lookup(
    db: AsyncSession, m: PlatformImportMapping, rows: list[dict[str, str]]
) -> dict[str, uuid.UUID]:
    codes = {r.get(m.code_column, "").strip() for r in rows} - {""}
    found = await item_ids_by_code(db, m.channel_id, codes) if codes else {}
    by_code = {c.lower(): i for c, i in found.items()}
    return {**await item_ids_by_sku(db), **by_code}  # a platform code wins over a SKU


def group(
    rows: list[dict[str, str]], m: PlatformImportMapping, items: dict[str, uuid.UUID], out: Outcome
) -> dict[date, Lines]:
    days: dict[date, Lines] = defaultdict(dict)
    for n, row in enumerate(rows, start=2):
        try:
            day, item, qty, amount = _row(row, m, items)
        except RowError as exc:
            out.errors.append({"row": n, "field": str(exc)})
            continue
        line = days[day].setdefault(item, [Decimal(0), 0])
        line[0] += qty
        line[1] += amount
    return days


def entry(
    outlet_id: uuid.UUID, channel_id: uuid.UUID, day: date, lines: Lines, with_amount: bool
) -> DayEntryIn:
    """Unit prices round up so the list total covers the platform amount; the few rupiah
    above it become the document discount, so the posted total is exactly the file's."""
    body: list[dict[str, object]] = []
    for item_id, (qty, amount) in lines.items():
        line: dict[str, object] = {"item_id": item_id, "qty": qty}
        if with_amount:
            line["unit_price"] = int(-(-Decimal(amount) // Decimal(qty)))
        body.append(line)
    reported = sum(a for _, a in lines.values()) if with_amount else None
    return DayEntryIn.model_validate(
        {
            "outlet_id": outlet_id,
            "business_date": day,
            "channel_id": channel_id,
            "lines": body,
            "reported_total": reported,
            "note": "import",
        }
    )


def builder(
    user_id: uuid.UUID, tenant_id: uuid.UUID, outlet_id: uuid.UUID, m: PlatformImportMapping
) -> Builder:
    async def build(db: AsyncSession, rows: list[dict[str, str]]) -> Outcome:
        out = Outcome()
        days = group(rows, m, await lookup(db, m, rows), out)
        if len(days) > MAX_DAYS:
            out.errors.append({"row": 0, "field": "too_many_days", "max": MAX_DAYS})
        if out.errors:
            return out
        for day, lines in sorted(days.items()):
            try:
                data = entry(outlet_id, m.channel_id, day, lines, m.amount_column is not None)
                async with db.begin_nested():
                    doc = await service.enter_day(
                        db, tenant_id=tenant_id, user_id=user_id, data=data
                    )
                out.created.append(doc.id)
            except ValidationError:
                out.errors.append({"row": 0, "field": "lines", "date": day.isoformat()})
            except AppError as exc:
                out.errors.append({"row": 0, "field": exc.code, "date": day.isoformat()})
        return out

    return build
