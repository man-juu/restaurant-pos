"""Kitchen display (FR-KDS-001 to 004)."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class StationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outlet_id: uuid.UUID
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
    category_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    is_default: bool = False
    is_active: bool = True


class StationOut(StationIn):
    id: uuid.UUID


class TicketItemOut(BaseModel):
    id: uuid.UUID
    name: str
    qty: Decimal
    modifiers: str | None
    note: str | None
    status: Literal["active", "void"]


class TicketOut(BaseModel):
    id: uuid.UUID
    station_id: uuid.UUID | None
    order_id: uuid.UUID
    order_number: str
    label: str | None
    channel_name: str
    platform: str | None
    status: Literal["new", "preparing", "ready", "bumped"]
    created_at: datetime
    ready_at: datetime | None
    bumped_at: datetime | None
    late: bool  # FR-KDS-004: older than the late threshold and not ready yet
    items: list[TicketItemOut]
