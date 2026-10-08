"""Transfer endpoints (FR-TRF-001 to 004). Outlet scope follows the role in the flow: the
receiving outlet requests and receives, the source approves and ships; either side may
read. A transfer outside the caller's outlets looks like one that does not exist."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import or_, select

from app.core.access.policy import Principal, require
from app.core.errors import NotFoundError
from app.core.idempotency import (
    remember,
    replay_or_none,
    request_fingerprint,
    required_idempotency_key,
)
from app.core.models import Outlet
from app.core.tenancy import tenant_session
from app.modules.catalog.interface import item_names
from app.modules.transfers import pdf, service
from app.modules.transfers import permissions as perm
from app.modules.transfers.models import Transfer
from app.modules.transfers.schemas import (
    TransferApproveIn,
    TransferOut,
    TransferReceiveIn,
    TransferRequestIn,
    TransferShipIn,
)

router = APIRouter(prefix="/api/v1/transfers", tags=["transfers"])

View = Annotated[Principal, Depends(require(perm.VIEW))]
Ask = Annotated[Principal, Depends(require(perm.REQUEST))]
Approve = Annotated[Principal, Depends(require(perm.APPROVE))]
Receive = Annotated[Principal, Depends(require(perm.RECEIVE))]
Key = Annotated[uuid.UUID, Depends(required_idempotency_key)]
Lang = Literal["en", "id"]
Side = Literal["from", "to", "either"]


def _db(request: Request, p: Principal):  # type: ignore[no-untyped-def]
    return tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id)


def _check_side(p: Principal, t: Transfer, side: Side) -> None:
    allowed = {
        "from": p.can_access_outlet(t.from_outlet_id),
        "to": p.can_access_outlet(t.to_outlet_id),
    }
    ok = allowed["from"] or allowed["to"] if side == "either" else allowed[side]
    if not ok:
        raise NotFoundError()


async def _scoped(db, p: Principal, transfer_id: uuid.UUID, side: Side) -> Transfer:  # type: ignore[no-untyped-def]
    t = await service.get_transfer(db, transfer_id)
    _check_side(p, t, side)
    return t


@router.get("", response_model=list[TransferOut])
async def list_transfers(
    outlet_id: uuid.UUID, request: Request, p: View, lang: Lang = "en"
) -> list[TransferOut]:
    p.require_outlet(outlet_id)
    async with _db(request, p) as db:
        stmt = (
            select(Transfer)
            .where(or_(Transfer.from_outlet_id == outlet_id, Transfer.to_outlet_id == outlet_id))
            .order_by(Transfer.created_at.desc())
            .limit(100)
        )
        return [await service.transfer_out(db, t, lang) for t in await db.scalars(stmt)]


@router.get("/{transfer_id}", response_model=TransferOut)
async def get_transfer(
    transfer_id: uuid.UUID, request: Request, p: View, lang: Lang = "en"
) -> TransferOut:
    async with _db(request, p) as db:
        return await service.transfer_out(db, await _scoped(db, p, transfer_id, "either"), lang)


@router.post("", response_model=TransferOut, status_code=201)
async def request_transfer(
    body: TransferRequestIn, request: Request, p: Ask, key: Key
) -> TransferOut | JSONResponse:
    p.require_outlet(body.to_outlet_id)  # the receiving outlet asks
    fingerprint = await request_fingerprint(request)
    async with _db(request, p) as db:
        if stored := await replay_or_none(db, key, fingerprint):
            return JSONResponse(stored.body, status_code=stored.status)
        t = await service.request(db, tenant_id=p.tenant_id, user_id=p.user_id, data=body)
        out = await service.transfer_out(db, t)
        await remember(db, p.tenant_id, key, fingerprint, 201, out.model_dump(mode="json"))
        return out


@router.post("/{transfer_id}/approve", response_model=TransferOut)
async def approve_transfer(
    transfer_id: uuid.UUID, body: TransferApproveIn, request: Request, p: Approve
) -> TransferOut:
    async with _db(request, p) as db:
        await _scoped(db, p, transfer_id, "from")
        t = await service.approve(db, user_id=p.user_id, transfer_id=transfer_id, data=body)
        return await service.transfer_out(db, t)


@router.post("/{transfer_id}/ship", response_model=TransferOut)
async def ship_transfer(
    transfer_id: uuid.UUID, body: TransferShipIn, request: Request, p: Approve
) -> TransferOut:
    async with _db(request, p) as db:
        await _scoped(db, p, transfer_id, "from")
        t = await service.ship(db, user_id=p.user_id, transfer_id=transfer_id, data=body)
        return await service.transfer_out(db, t)


@router.post("/{transfer_id}/receive", response_model=TransferOut)
async def receive_transfer(
    transfer_id: uuid.UUID, body: TransferReceiveIn, request: Request, p: Receive
) -> TransferOut:
    async with _db(request, p) as db:
        await _scoped(db, p, transfer_id, "to")
        t = await service.receive_transfer(
            db, user_id=p.user_id, transfer_id=transfer_id, data=body
        )
        return await service.transfer_out(db, t)


@router.post("/{transfer_id}/cancel", response_model=TransferOut)
async def cancel_transfer(transfer_id: uuid.UUID, request: Request, p: Ask) -> TransferOut:
    async with _db(request, p) as db:
        await _scoped(db, p, transfer_id, "either")
        t = await service.cancel(db, user_id=p.user_id, transfer_id=transfer_id)
        return await service.transfer_out(db, t)


@router.get("/{transfer_id}/delivery-note")
async def delivery_note(
    transfer_id: uuid.UUID, request: Request, p: View, lang: Lang = "en"
) -> Response:
    async with _db(request, p) as db:
        t = await _scoped(db, p, transfer_id, "either")
        picks = await service.transfer_picks(db, t.id)
        lines = {ln.id: ln for ln in await service.transfer_lines(db, t.id)}
        names = await item_names(db, t.tenant_id, lang, {pk.item_id for pk in picks})
        outlets = dict(
            (
                await db.execute(
                    select(Outlet.id, Outlet.name).where(
                        Outlet.id.in_([t.from_outlet_id, t.to_outlet_id])
                    )
                )
            ).all()
        )
    if t.status not in ("shipped", "received"):
        raise NotFoundError("not_shipped")
    rows = [
        [
            names[pk.item_id].name[:40],
            pk.lot_code or "-",
            pk.expiry_date.strftime("%d/%m/%Y") if pk.expiry_date else "-",
            f"{pk.qty.normalize():f} {names[pk.item_id].unit_code}",
            "" if lines[pk.line_id].received_qty is None else "[  ]",
        ]
        for pk in picks
    ]
    facts = [
        [f"{outlets.get(t.from_outlet_id, '')} -> {outlets.get(t.to_outlet_id, '')}"],
        [t.shipped_on.strftime("%d/%m/%Y") if t.shipped_on else ""],
    ]
    body = await pdf.render(t.number, facts, rows, lang)
    return Response(
        body,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{t.number}.pdf"',
            "X-Content-Type-Options": "nosniff",
        },
    )
