"""Customer endpoints (FR-SAL-012). Search needs at least two characters, so the list of
guests cannot be pulled in one call."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, StringConstraints

from app.core.access.policy import Principal, require
from app.core.customers import service
from app.core.tenancy import tenant_session

router = APIRouter(prefix="/api/v1/customers", tags=["customers"])

View = Annotated[Principal, Depends(require("tenant.customer.view"))]
Manage = Annotated[Principal, Depends(require("tenant.customer.manage"))]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Phone = Annotated[str, StringConstraints(strip_whitespace=True, max_length=30)]


class CustomerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name
    phone: Phone | None = None
    consent: bool = False  # the guest agreed that the business keeps these details
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None


class CustomerOut(BaseModel):
    id: uuid.UUID
    name: str
    phone: str | None
    consent_at: datetime | None
    note: str | None


def _db(request: Request, p: Principal):  # type: ignore[no-untyped-def]
    return tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id)


@router.get("", response_model=list[CustomerOut])
async def search(
    q: Annotated[str, Query(min_length=2, max_length=60)], request: Request, p: View
) -> list[CustomerOut]:
    async with _db(request, p) as db:
        return [
            CustomerOut.model_validate(c, from_attributes=True) for c in await service.search(db, q)
        ]


@router.post("", response_model=CustomerOut, status_code=201)
async def create(body: CustomerIn, request: Request, p: Manage) -> CustomerOut:
    async with _db(request, p) as db:
        row = await service.save(db, tenant_id=p.tenant_id, user_id=p.user_id, **body.model_dump())
        return CustomerOut.model_validate(row, from_attributes=True)


@router.put("/{customer_id}", response_model=CustomerOut)
async def update(
    customer_id: uuid.UUID, body: CustomerIn, request: Request, p: Manage
) -> CustomerOut:
    async with _db(request, p) as db:
        found = await service.get(db, customer_id)
        row = await service.save(
            db, tenant_id=p.tenant_id, user_id=p.user_id, customer=found, **body.model_dump()
        )
        return CustomerOut.model_validate(row, from_attributes=True)


@router.delete("/{customer_id}", status_code=204)
async def erase(customer_id: uuid.UUID, request: Request, p: Manage) -> None:
    """Remove the guest's personal data (on their request); history stays, anonymous."""
    async with _db(request, p) as db:
        await service.erase(db, await service.get(db, customer_id), p.user_id)
