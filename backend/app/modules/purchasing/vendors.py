"""Vendors and vendor items (FR-PUR-001, 002). Bank details are encrypted at rest."""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.crypto import SecretBox
from app.core.errors import AppError, ConflictError, NotFoundError
from app.modules.catalog.interface import base_factors, stock_items
from app.modules.purchasing.models import Vendor, VendorItem
from app.modules.purchasing.schemas import VendorIn, VendorItemIn, VendorOut

_BANK = b"vendor-bank-details"  # encryption context: a blob cannot be reused for another field


class InvalidVendorReference(AppError):
    status_code, code = 422, "invalid_reference"


def out(v: Vendor) -> VendorOut:
    return VendorOut(
        id=v.id,
        name=v.name,
        contact_name=v.contact_name,
        phone=v.phone,
        email=v.email,
        address=v.address,
        tax_id=v.tax_id,
        payment_terms_days=v.payment_terms_days,
        lead_time_days=v.lead_time_days,
        has_bank_details=v.bank_details_enc is not None,
        is_active=v.is_active,
    )


async def list_vendors(db: AsyncSession, include_inactive: bool) -> list[Vendor]:
    stmt = select(Vendor).order_by(Vendor.name)
    if not include_inactive:
        stmt = stmt.where(Vendor.is_active)
    return list(await db.scalars(stmt))


async def get_vendor(db: AsyncSession, vendor_id: uuid.UUID) -> Vendor:
    vendor = await db.get(Vendor, vendor_id)
    if vendor is None:
        raise NotFoundError("vendor_not_found")
    return vendor


async def save_vendor(
    db: AsyncSession,
    box: SecretBox,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    data: VendorIn,
    vendor_id: uuid.UUID | None = None,
) -> Vendor:
    fields = data.model_dump(exclude={"bank_details"})
    vendor = Vendor(tenant_id=tenant_id) if vendor_id is None else await get_vendor(db, vendor_id)
    for key, value in fields.items():
        setattr(vendor, key, value)
    if data.bank_details is not None:  # None keeps what is stored; "" clears it
        vendor.bank_details_enc = (
            box.encrypt(data.bank_details, context=_BANK) if data.bank_details else None
        )
    db.add(vendor)
    try:
        await db.flush()
    except IntegrityError:
        raise ConflictError("vendor_name_taken") from None
    await audit.record(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action="purchasing.vendor.save",
        target_type="vendor",
        target_id=vendor.id,
        summary={"after": fields, "bank_details_changed": data.bank_details is not None},
    )
    return vendor


async def reveal_bank_details(
    db: AsyncSession,
    box: SecretBox,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    vendor_id: uuid.UUID,
) -> str | None:
    """Audited: who looked at a vendor's bank details, and when."""
    vendor = await get_vendor(db, vendor_id)
    await audit.record(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action="purchasing.vendor.bank_details_viewed",
        target_type="vendor",
        target_id=vendor.id,
    )
    return box.decrypt(vendor.bank_details_enc, context=_BANK) if vendor.bank_details_enc else None


async def list_vendor_items(db: AsyncSession, vendor_id: uuid.UUID) -> list[VendorItem]:
    stmt = (
        select(VendorItem)
        .where(VendorItem.vendor_id == vendor_id)
        .order_by(VendorItem.item_id, VendorItem.valid_from.desc())
    )
    return list(await db.scalars(stmt))


async def add_vendor_item(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    vendor_id: uuid.UUID,
    data: VendorItemIn,
) -> VendorItem:
    await get_vendor(db, vendor_id)
    if data.item_id not in await stock_items(db, {data.item_id}):
        raise InvalidVendorReference(details={"item_id": str(data.item_id)})
    await base_factors(db, {(data.item_id, data.pack_unit_id)})  # the pack must convert
    row = VendorItem(tenant_id=tenant_id, vendor_id=vendor_id, **data.model_dump())
    db.add(row)
    try:
        await db.flush()
    except IntegrityError:
        raise ConflictError("vendor_item_exists") from None
    await audit.record(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action="purchasing.vendor_item.add",
        target_type="vendor_item",
        target_id=row.id,
        summary=data.model_dump(mode="json"),
    )
    return row
