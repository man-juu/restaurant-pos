"""Aging buckets for receivables (sales) and payables (purchasing), FR-FIN-006. In core so
both modules use the same buckets."""

import uuid
from collections.abc import Iterable
from datetime import date

from pydantic import BaseModel

BUCKETS = ("current", "days_1_30", "days_31_60", "days_61_90", "over_90")


def bucket(due: date, today: date) -> str:
    late = (today - due).days
    if late <= 0:
        return "current"
    if late <= 30:
        return "days_1_30"
    if late <= 60:
        return "days_31_60"
    return "days_61_90" if late <= 90 else "over_90"


def age(
    rows: Iterable[tuple[uuid.UUID, date, int]], today: date
) -> dict[uuid.UUID, dict[str, int]]:
    """(party, due date, open balance) rows -> per party the balance in each bucket."""
    out: dict[uuid.UUID, dict[str, int]] = {}
    for party, due, balance in rows:
        sums = out.setdefault(party, dict.fromkeys(BUCKETS, 0))
        sums[bucket(due, today)] += balance
    return out


class AgingRow(BaseModel):
    """One customer or vendor: open balances by how long they are past due."""

    party_id: uuid.UUID
    party_name: str
    current: int
    days_1_30: int
    days_31_60: int
    days_61_90: int
    over_90: int
    total: int
