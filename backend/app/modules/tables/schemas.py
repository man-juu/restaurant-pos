"""Floors, tables and sessions (FR-TBL-001 to 004)."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
TableName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]


class In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FloorIn(In):
    outlet_id: uuid.UUID
    name: Name
    sort_order: int = Field(default=0, ge=0, le=1000)
    is_active: bool = True


class FloorOut(FloorIn):
    id: uuid.UUID


class TableIn(In):
    floor_id: uuid.UUID
    name: TableName
    capacity: int = Field(default=4, ge=1, le=100)
    x: int = Field(default=0, ge=0, le=50)
    y: int = Field(default=0, ge=0, le=50)
    is_active: bool = True


class TableBillOut(BaseModel):
    id: uuid.UUID
    number: str
    status: str
    subtotal: int
    lines: int


class TableSessionOut(BaseModel):
    id: uuid.UUID
    status: Literal["open", "closed"]
    party_size: int
    opened_at: datetime
    channel_id: uuid.UUID
    table_ids: list[uuid.UUID]
    orders: list[TableBillOut]
    open_amount: int  # open orders at their prices, before discount, service and tax


class TableOut(BaseModel):
    id: uuid.UUID
    outlet_id: uuid.UUID
    floor_id: uuid.UUID
    name: str
    capacity: int
    x: int
    y: int
    status: Literal["available", "occupied", "reserved", "needs_cleaning"]
    is_active: bool
    session: TableSessionOut | None = None  # FR-TBL-004: who sits here, since when, how much


class SeatIn(In):
    channel_id: uuid.UUID
    party_size: int = Field(default=2, ge=1, le=200)


class MoveIn(In):
    to_table_id: uuid.UUID


class MergeIn(In):
    session_id: uuid.UUID  # the other party joins this one


class SplitIn(In):
    from_order_id: uuid.UUID
    line_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


class StatusIn(In):
    status: Literal["available", "reserved", "needs_cleaning"]
