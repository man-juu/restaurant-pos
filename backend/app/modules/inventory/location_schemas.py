"""Storage locations (FR-INV-017) and labels (FR-INV-019)."""

import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class LocationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outlet_id: uuid.UUID
    name: Name
    sort_order: int = Field(default=0, ge=0, le=1000)
    is_active: bool = True


class LocationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name
    sort_order: int = Field(default=0, ge=0, le=1000)
    is_active: bool = True


class LocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    outlet_id: uuid.UUID
    name: str
    sort_order: int
    is_active: bool


class AssignIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)


class HomeOut(BaseModel):
    item_id: uuid.UUID
    location_id: uuid.UUID
    sku: str
    name: str
