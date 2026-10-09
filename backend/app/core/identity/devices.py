"""Registered devices and PIN sign-in (FR-IDN-004).

Security choices, briefly:
- The device cookie is httpOnly, Secure, SameSite=Strict and `__Host-` prefixed; only its
  SHA-256 hash is stored, like session tokens. Revoking a device stops it at once.
- A PIN works only on a registered device, only for people who completed a full sign-in
  there, never for roles that require 2FA (owners), and locks after 5 wrong tries for 15
  minutes. A per-device limit stops guessing across many staff accounts.
- The device is looked up by token through a narrow SECURITY DEFINER function (no tenant
  is known yet); everything after that runs in that tenant's RLS session.
"""

import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Request, Response
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.identity import service
from app.core.identity.device_models import Device, DeviceUser, UserPin
from app.core.identity.passwords import hash_password, verify_password

DEVICE_COOKIE = "__Host-pos_device"
DEVICE_COOKIE_DAYS = 400  # browsers cap cookie lifetime around 400 days
PIN = re.compile(r"^\d{4,6}$")
PIN_MAX_FAILURES = 5
PIN_LOCK = timedelta(minutes=15)
DEVICE_MAX_FAILURES = 20  # across all staff on one device


@dataclass(frozen=True)
class DeviceRef:
    id: uuid.UUID
    tenant_id: uuid.UUID
    outlet_id: uuid.UUID | None
    name: str


def set_device_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        DEVICE_COOKIE,
        token,
        max_age=DEVICE_COOKIE_DAYS * 86400,
        path="/",
        secure=True,
        httponly=True,
        samesite="strict",
    )


async def new_device(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    name: str,
    outlet_id: uuid.UUID | None,
) -> tuple[str, Device]:
    token = secrets.token_urlsafe(32)
    device = Device(
        tenant_id=tenant_id,
        name=name,
        outlet_id=outlet_id,
        token_hash=service.hash_token(token),
        registered_by=user_id,
    )
    db.add(device)
    await db.flush()
    db.add(DeviceUser(tenant_id=tenant_id, device_id=device.id, user_id=user_id))
    await db.flush()
    return token, device


async def device_from_cookie(request: Request) -> DeviceRef | None:
    """The live device this browser is registered as, or None."""
    token = request.cookies.get(DEVICE_COOKIE)
    if not token:
        return None
    async with request.app.state.sessionmaker() as db, db.begin():
        row = (
            await db.execute(
                text("SELECT * FROM auth_device_by_token(:h)"), {"h": service.hash_token(token)}
            )
        ).one_or_none()
    if row is None or row.revoked_at is not None:
        return None
    return DeviceRef(row.id, row.tenant_id, row.outlet_id, row.name)


async def enrol(db: AsyncSession, device: DeviceRef, user_id: uuid.UUID) -> None:
    found = await db.get(DeviceUser, (device.tenant_id, device.id, user_id))
    if found is None:
        db.add(DeviceUser(tenant_id=device.tenant_id, device_id=device.id, user_id=user_id))
        await db.flush()


async def set_pin(db: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID, pin: str) -> None:
    hashed = await hash_password(pin)
    row = await db.get(UserPin, (tenant_id, user_id))
    if row is None:
        db.add(UserPin(tenant_id=tenant_id, user_id=user_id, pin_hash=hashed))
    else:
        row.pin_hash, row.failed_count, row.locked_until = hashed, 0, None
        row.set_at = datetime.now(UTC)
    await db.flush()


async def reset_pin(db: AsyncSession, user_id: uuid.UUID) -> bool:
    done = await db.execute(delete(UserPin).where(UserPin.user_id == user_id))
    return bool(done.rowcount)  # type: ignore[attr-defined]


async def pin_staff(db: AsyncSession, device: DeviceRef) -> list[tuple[uuid.UUID, str]]:
    """Who may use a PIN here: enrolled on this device, has a PIN, active, no 2FA role."""
    rows = (
        await db.execute(
            text(
                "SELECT u.id, u.name FROM device_users d"
                " JOIN user_pins p ON p.user_id = d.user_id AND p.tenant_id = d.tenant_id"
                " JOIN users u ON u.id = d.user_id"
                " JOIN memberships m ON m.user_id = d.user_id AND m.tenant_id = d.tenant_id"
                " JOIN roles r ON r.id = m.role_id"
                " WHERE d.device_id = :device AND u.status = 'active' AND m.status = 'active'"
                " AND NOT r.requires_mfa AND u.totp_enabled_at IS NULL ORDER BY u.name"
            ),
            {"device": device.id},
        )
    ).all()
    return [(r.id, r.name) for r in rows]


class PinResult:
    OK, WRONG, LOCKED, NOT_ALLOWED = "ok", "wrong", "locked", "not_allowed"


async def check_pin(
    db: AsyncSession, device: DeviceRef, user_id: uuid.UUID, pin: str
) -> tuple[str, datetime | None]:
    """Verify a PIN for a person on this device; counts failures and locks."""
    allowed = {uid for uid, _ in await pin_staff(db, device)}
    row = await db.get(UserPin, (device.tenant_id, user_id), with_for_update=True)
    if user_id not in allowed or row is None:
        # Same slow hash either way, so timing does not tell who has a PIN.
        await verify_password(None, pin)
        return PinResult.NOT_ALLOWED, None
    now = datetime.now(UTC)
    if row.locked_until is not None and row.locked_until > now:
        return PinResult.LOCKED, row.locked_until
    if await verify_password(row.pin_hash, pin):
        row.failed_count, row.locked_until = 0, None
        await db.execute(
            text("UPDATE devices SET last_seen_at = now() WHERE id = :id"), {"id": device.id}
        )
        return PinResult.OK, None
    row.failed_count += 1
    if row.failed_count >= PIN_MAX_FAILURES:
        row.failed_count, row.locked_until = 0, now + PIN_LOCK
        return PinResult.LOCKED, row.locked_until
    return PinResult.WRONG, None
