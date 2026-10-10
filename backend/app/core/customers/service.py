"""Customer records (FR-SAL-012). Phone numbers are stored as digits with the country code
(08123... becomes 628123...), so the same guest is found however the number was typed.
Erasing a customer removes the personal data but keeps the record, so reservations and
invoices that point at it stay consistent."""

import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.customers.models import Customer
from app.core.errors import ConflictError, NotFoundError

ERASED = "-"


def normal_phone(raw: str | None, country_code: str = "62") -> str | None:
    """Digits only; a leading 0 becomes the country code (Indonesia: 62)."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("0"):
        digits = country_code + digits[1:]
    return digits or None


async def _audit(db: AsyncSession, c: Customer, user_id: uuid.UUID, verb: str) -> None:
    # No name or phone in the audit summary: the log is append-only and must not keep PII.
    await audit.record(
        db,
        tenant_id=c.tenant_id,
        user_id=user_id,
        action=f"customers.customer.{verb}",
        target_type="customer",
        target_id=c.id,
        summary={},
    )


async def get(db: AsyncSession, customer_id: uuid.UUID) -> Customer:
    row = await db.get(Customer, customer_id)
    if row is None:
        raise NotFoundError("customer_not_found")
    return row


async def by_phone(db: AsyncSession, phone: str | None) -> Customer | None:
    number = normal_phone(phone)
    if number is None:
        return None
    return await db.scalar(select(Customer).where(Customer.phone == number))


async def save(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    name: str,
    phone: str | None,
    consent: bool,
    note: str | None = None,
    customer: Customer | None = None,
) -> Customer:
    """Create, or update `customer`. Consent is recorded once, when first given."""
    row = customer or Customer(tenant_id=tenant_id, created_by=user_id)
    if row.erased_at is not None:
        raise ConflictError("customer_erased")
    row.name, row.phone, row.note = name, normal_phone(phone), note
    if consent and row.consent_at is None:
        row.consent_at = datetime.now(UTC)
    if not consent:
        row.consent_at = None
    db.add(row)
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError:
        raise ConflictError("customer_phone_exists") from None
    await _audit(db, row, user_id, "save")
    return row


async def find_or_create(
    db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID, name: str, phone: str | None
) -> Customer:
    """For a reservation or a waitlist entry: the guest with this phone, or a new record."""
    found = await by_phone(db, phone)
    if found is not None:
        return found
    return await save(
        db, tenant_id=tenant_id, user_id=user_id, name=name, phone=phone, consent=False
    )


async def search(db: AsyncSession, text: str, limit: int = 20) -> list[Customer]:
    term = text.strip()
    digits = re.sub(r"\D", "", term)
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    conditions: list[ColumnElement[bool]] = [Customer.name.ilike(f"%{escaped}%", escape="\\")]
    if len(digits) >= 4:
        conditions.append(Customer.phone.contains(normal_phone(digits) or digits))
    stmt = (
        select(Customer)
        .where(Customer.erased_at.is_(None), or_(*conditions))
        .order_by(Customer.name)
        .limit(limit)
    )
    return list(await db.scalars(stmt))


async def erase(db: AsyncSession, customer: Customer, user_id: uuid.UUID) -> None:
    """Right to erasure (UU PDP): name, phone and note go; the record and its history stay."""
    customer.name, customer.phone, customer.note = ERASED, None, None
    customer.consent_at, customer.erased_at = None, datetime.now(UTC)
    await db.flush()
    await _audit(db, customer, user_id, "erase")
