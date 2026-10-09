"""Device registration, PINs and PIN sign-in (FR-IDN-004). See devices.py for the rules."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import select, update

from app.core.access.policy import Principal, public, require, require_member
from app.core.config import Settings
from app.core.errors import AppError, NotFoundError
from app.core.identity import devices, service
from app.core.identity.device_models import Device
from app.core.identity.passwords import verify_password
from app.core.identity.schemas import SessionInfo
from app.core.identity.web import (
    InvalidCredentials,
    TooManyAttempts,
    audit_auth,
    client_info,
    session_info,
    set_session_cookie,
)
from app.core.models import Outlet, User
from app.core.tenancy import tenant_session

router = APIRouter(prefix="/api/v1", tags=["devices"])
auth_router = APIRouter(prefix="/api/v1/auth", tags=["auth"], dependencies=[Depends(public())])

Manage = Annotated[Principal, Depends(require("tenant.device.manage"))]
Member = Annotated[Principal, Depends(require_member())]
Reset = Annotated[Principal, Depends(require("tenant.pin.reset"))]
Pin = Annotated[str, StringConstraints(pattern=r"^\d{4,6}$")]


class PinNotAllowed(AppError):
    status_code, code = 403, "pin_not_allowed"


class DeviceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    outlet_id: uuid.UUID | None = None


class DeviceOut(BaseModel):
    id: uuid.UUID
    name: str
    outlet_id: uuid.UUID | None
    created_at: datetime
    last_seen_at: datetime | None
    revoked_at: datetime | None


class PinIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pin: Pin
    password: str = Field(min_length=1, max_length=256)  # proves it is really you


class StaffOut(BaseModel):
    user_id: uuid.UUID
    name: str


class ThisDeviceOut(BaseModel):
    name: str
    outlet_id: uuid.UUID | None
    staff: list[StaffOut]


class PinLoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: uuid.UUID
    pin: Pin


def _db(request: Request, p: Principal):  # type: ignore[no-untyped-def]
    return tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id)


@router.post("/devices", response_model=DeviceOut, status_code=201)
async def register(body: DeviceIn, request: Request, response: Response, p: Manage) -> DeviceOut:
    """Run on the shared till itself: this browser becomes the registered device."""
    if body.outlet_id is not None:
        p.require_outlet(body.outlet_id)
    async with _db(request, p) as db:
        if body.outlet_id is not None and await db.get(Outlet, body.outlet_id) is None:
            raise NotFoundError("outlet_not_found")
        token, device = await devices.new_device(
            db, p.tenant_id, p.user_id, body.name, body.outlet_id
        )
        out = DeviceOut.model_validate(device, from_attributes=True)
    devices.set_device_cookie(response, token)
    await audit_auth(
        request, p.tenant_id, "device.register", p.user_id, device=str(out.id), name=out.name
    )
    return out


@router.get("/devices", response_model=list[DeviceOut])
async def list_devices(request: Request, p: Manage) -> list[DeviceOut]:
    async with _db(request, p) as db:
        rows = await db.scalars(select(Device).order_by(Device.created_at.desc()))
        return [DeviceOut.model_validate(d, from_attributes=True) for d in rows]


@router.delete("/devices/{device_id}", status_code=204)
async def revoke_device(device_id: uuid.UUID, request: Request, p: Manage) -> None:
    async with _db(request, p) as db:
        done = await db.execute(
            update(Device)
            .where(Device.id == device_id, Device.revoked_at.is_(None))
            .values(revoked_at=datetime.now().astimezone())
        )
        if not done.rowcount:
            raise NotFoundError("device_not_found")
    await audit_auth(request, p.tenant_id, "device.revoke", p.user_id, device=str(device_id))


@router.post("/devices/this/enrol", status_code=204)
async def enrol(request: Request, p: Member) -> None:
    """After a full sign-in on a registered device: allow this person's PIN here."""
    device = await devices.device_from_cookie(request)
    if device is None or device.tenant_id != p.tenant_id:
        raise NotFoundError("device_not_found")
    async with _db(request, p) as db:
        await devices.enrol(db, device, p.user_id)


@router.put("/me/pin", status_code=204)
async def set_my_pin(body: PinIn, request: Request, p: Member) -> None:
    async with request.app.state.sessionmaker() as db, db.begin():
        user = (await db.execute(select(User).where(User.id == p.user_id))).scalar_one()
        mfa_role = await service.requires_mfa(db, p.user_id)
    if not await verify_password(user.password_hash, body.password):
        raise InvalidCredentials()
    if mfa_role:
        raise PinNotAllowed()  # owners and co-owners always sign in fully with 2FA
    async with _db(request, p) as db:
        await devices.set_pin(db, p.tenant_id, p.user_id, body.pin)
    await audit_auth(request, p.tenant_id, "auth.pin_set", p.user_id)


@router.delete("/pins/{user_id}", status_code=204)
async def reset_pin(user_id: uuid.UUID, request: Request, p: Reset) -> None:
    async with _db(request, p) as db:
        if not await devices.reset_pin(db, user_id):
            raise NotFoundError("pin_not_found")
    await audit_auth(request, p.tenant_id, "auth.pin_reset", p.user_id, target_user=str(user_id))


@auth_router.get("/device", response_model=ThisDeviceOut)
async def this_device(request: Request) -> ThisDeviceOut:
    """For the PIN screen: which device this is and who may use a PIN on it."""
    device = await devices.device_from_cookie(request)
    if device is None:
        raise NotFoundError("device_not_found")
    async with tenant_session(request.app.state.sessionmaker, device.tenant_id) as db:
        staff = await devices.pin_staff(db, device)
    return ThisDeviceOut(
        name=device.name,
        outlet_id=device.outlet_id,
        staff=[StaffOut(user_id=u, name=n) for u, n in staff],
    )


@auth_router.post("/pin-login", response_model=SessionInfo)
async def pin_login(body: PinLoginIn, request: Request, response: Response) -> SessionInfo:
    device = await devices.device_from_cookie(request)
    if device is None:
        raise NotFoundError("device_not_found")
    settings: Settings = request.app.state.settings
    key = service.throttle_key("device", str(device.id))
    async with request.app.state.sessionmaker() as db, db.begin():
        until = await service.locked_until(db, [key])
    if until is not None:
        raise TooManyAttempts(details={"retry_at": until.isoformat()})
    async with tenant_session(request.app.state.sessionmaker, device.tenant_id) as db:
        result, locked = await devices.check_pin(db, device, body.user_id, body.pin)
    if result != devices.PinResult.OK:
        async with request.app.state.sessionmaker() as db, db.begin():
            await service.record_failure(db, [key], devices.DEVICE_MAX_FAILURES)
        if result != devices.PinResult.NOT_ALLOWED:  # a real staff account: owners see it
            await audit_auth(
                request, device.tenant_id, "auth.pin_failed", body.user_id, device=str(device.id)
            )
        if result == devices.PinResult.LOCKED:
            raise TooManyAttempts(details={"retry_at": locked.isoformat() if locked else None})
        raise InvalidCredentials()
    ip, user_agent = client_info(request)
    async with request.app.state.sessionmaker() as db, db.begin():
        token, row = await service.create_session(
            db,
            user_id=body.user_id,
            tenant_id=device.tenant_id,
            ip=ip,
            user_agent=user_agent,
            settings=settings,
        )
        user = (await db.execute(select(User).where(User.id == body.user_id))).scalar_one()
        info = await session_info(db, user, row)
    await audit_auth(
        request, device.tenant_id, "auth.pin_login", body.user_id, device=str(device.id)
    )
    set_session_cookie(response, token, settings)
    return info
