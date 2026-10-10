"""Storage locations (FR-INV-017), scanning and labels (FR-INV-019). Outlet scope on every
call."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access.policy import Principal, require
from app.core.tenancy import tenant_session
from app.modules.catalog.interface import item_names
from app.modules.inventory import labels_pdf, locations, scan
from app.modules.inventory import permissions as perm
from app.modules.inventory.location_models import StorageLocation
from app.modules.inventory.location_schemas import (
    AssignIn,
    HomeOut,
    LocationIn,
    LocationOut,
    LocationUpdate,
)
from app.modules.inventory.models import StockBatch
from app.modules.inventory.scan import ScanOut

router = APIRouter(prefix="/api/v1/inventory", tags=["inventory"])

View = Annotated[Principal, Depends(require(perm.STOCK_VIEW))]
Manage = Annotated[Principal, Depends(require(perm.LEVEL_MANAGE))]
Lang = Annotated[str, Query(pattern=r"^[a-z]{2}(-[A-Z]{2})?$")]
Code = Annotated[str, Query(min_length=1, max_length=80)]
Ids = Annotated[list[uuid.UUID], Query(max_length=100)]


def _db(request: Request, p: Principal):  # type: ignore[no-untyped-def]
    return tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id)


@router.get("/locations", response_model=list[LocationOut])
async def list_locations(outlet_id: uuid.UUID, request: Request, p: View) -> list[LocationOut]:
    p.require_outlet(outlet_id)
    async with _db(request, p) as db:
        rows = await db.scalars(
            select(StorageLocation)
            .where(StorageLocation.outlet_id == outlet_id)
            .order_by(StorageLocation.sort_order, StorageLocation.name)
        )
        return [LocationOut.model_validate(r) for r in rows]


@router.post("/locations", response_model=LocationOut, status_code=201)
async def create_location(body: LocationIn, request: Request, p: Manage) -> LocationOut:
    p.require_outlet(body.outlet_id)
    async with _db(request, p) as db:
        row = StorageLocation(tenant_id=p.tenant_id, **body.model_dump())
        return LocationOut.model_validate(await locations.save(db, row, p.user_id, "create"))


@router.put("/locations/{location_id}", response_model=LocationOut)
async def update_location(
    location_id: uuid.UUID, body: LocationUpdate, request: Request, p: Manage
) -> LocationOut:
    async with _db(request, p) as db:
        row = await locations.get(db, location_id)
        p.require_outlet(row.outlet_id)
        row.name, row.sort_order, row.is_active = body.name, body.sort_order, body.is_active
        return LocationOut.model_validate(await locations.save(db, row, p.user_id, "update"))


@router.get("/locations/homes", response_model=list[HomeOut])
async def homes(
    outlet_id: uuid.UUID, request: Request, p: View, lang: Lang = "en"
) -> list[HomeOut]:
    p.require_outlet(outlet_id)
    async with _db(request, p) as db:
        found = await locations.homes(db, outlet_id)
        names = await item_names(db, p.tenant_id, lang, found)
        return sorted(
            (
                HomeOut(item_id=i, location_id=loc, sku=names[i].sku, name=names[i].name)
                for i, loc in found.items()
                if i in names
            ),
            key=lambda h: h.name,
        )


@router.put("/locations/{location_id}/items", status_code=204)
async def assign(location_id: uuid.UUID, body: AssignIn, request: Request, p: Manage) -> None:
    async with _db(request, p) as db:
        row = await locations.get(db, location_id)
        p.require_outlet(row.outlet_id)
        await locations.assign(
            db, tenant_id=p.tenant_id, user_id=p.user_id, location=row, item_ids=body.item_ids
        )


@router.delete("/locations/homes/{item_id}", status_code=204)
async def unassign(item_id: uuid.UUID, outlet_id: uuid.UUID, request: Request, p: Manage) -> None:
    p.require_outlet(outlet_id)
    async with _db(request, p) as db:
        await locations.unassign(db, outlet_id, item_id, p.user_id)


@router.get("/scan", response_model=ScanOut)
async def resolve(
    outlet_id: uuid.UUID, code: Code, request: Request, p: View, lang: Lang = "en"
) -> ScanOut:
    p.require_outlet(outlet_id)
    async with _db(request, p) as db:
        return await scan.resolve(db, p.tenant_id, outlet_id, code, lang)


async def _labels(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    outlet_id: uuid.UUID,
    batch_ids: list[uuid.UUID],
    item_ids: list[uuid.UUID],
    lang: str,
) -> list[labels_pdf.Label]:
    batches = list(
        await db.scalars(
            select(StockBatch).where(
                StockBatch.outlet_id == outlet_id, StockBatch.id.in_(batch_ids)
            )
        )
    )
    names = await item_names(db, tenant_id, lang, {b.item_id for b in batches} | set(item_ids))
    out = [
        labels_pdf.Label(names[b.item_id].name, scan.batch_code(b.id), b.lot_code, b.expiry_date)
        for b in batches
    ]
    out += [labels_pdf.Label(names[i].name, names[i].sku, qr=False) for i in item_ids if i in names]
    return out


@router.get("/labels")
async def labels(
    outlet_id: uuid.UUID,
    request: Request,
    p: View,
    batch_id: Ids = [],  # noqa: B006 - FastAPI query lists
    item_id: Ids = [],  # noqa: B006
    copies: Annotated[int, Query(ge=1, le=24)] = 1,
    lang: Lang = "en",
) -> Response:
    """A sheet of labels: one QR label per batch and one barcode label per item."""
    p.require_outlet(outlet_id)
    async with _db(request, p) as db:
        found = await _labels(db, p.tenant_id, outlet_id, batch_id, item_id, lang)
    body = await labels_pdf.render([lb for lb in found for _ in range(copies)], lang)
    return Response(
        body,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'inline; filename="labels.pdf"',
            "X-Content-Type-Options": "nosniff",
        },
    )
