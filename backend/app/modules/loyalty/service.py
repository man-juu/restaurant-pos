"""Earning, redeeming and paying with vouchers (FR-SAL-016). The points balance is the sum of
the guest's ledger entries; a guest's row is locked while points are spent, so two tills
cannot spend the same points twice."""

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.access.policy import Principal
from app.core.customers.models import Customer
from app.core.errors import ConflictError, NotFoundError
from app.core.settings import service as settings
from app.core.settings.schemas import LoyaltySettings
from app.modules.catalog.interface import tenant_today
from app.modules.loyalty.models import LoyaltyEntry, Voucher
from app.modules.loyalty.schemas import RedeemIn, VoucherIn
from app.modules.sales.interface import document_money, tenders_of_kind

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I to misread


async def conf(db: AsyncSession, tenant_id: uuid.UUID) -> LoyaltySettings:
    return cast(LoyaltySettings, await settings.get_setting(db, tenant_id, "loyalty"))


async def balance(db: AsyncSession, customer_id: uuid.UUID) -> int:
    stmt = select(func.coalesce(func.sum(LoyaltyEntry.points), 0)).where(
        LoyaltyEntry.customer_id == customer_id
    )
    return int(await db.scalar(stmt) or 0)


async def _audit(db: AsyncSession, row: LoyaltyEntry | Voucher, verb: str, summary: dict) -> None:  # type: ignore[type-arg]
    await audit.record(
        db,
        tenant_id=row.tenant_id,
        user_id=row.created_by,
        action=f"loyalty.{verb}",
        target_type=type(row).__tablename__,
        target_id=row.id,
        summary=summary,
    )


async def guest(db: AsyncSession, customer_id: uuid.UUID, lock: bool = False) -> Customer:
    row = await db.get(Customer, customer_id, with_for_update=lock)
    if row is None or row.erased_at is not None:
        raise NotFoundError("customer_not_found")
    return row


async def earn(
    db: AsyncSession,
    p: Principal,
    document_id: uuid.UUID,
    customer_id: uuid.UUID,
) -> int:
    """Points for a paid till receipt: net sales (before service and tax) / earn_per, rounded
    down. Once per receipt; asking again returns what it earned. The receipt's outlet must be
    one the caller works at."""
    tenant_id, user_id = p.tenant_id, p.user_id
    await guest(db, customer_id)
    try:
        doc = await document_money(db, document_id)
    except LookupError:
        raise NotFoundError("document_not_found") from None
    if doc.source != "pos" or doc.status != "posted":
        raise ConflictError("document_not_eligible")
    p.require_outlet(doc.outlet_id)
    done = await db.scalar(
        select(LoyaltyEntry).where(
            LoyaltyEntry.document_id == document_id, LoyaltyEntry.kind == "earn"
        )
    )
    if done is not None:
        if done.customer_id != customer_id:
            raise ConflictError("points_already_given")
        return done.points
    points = (doc.subtotal - doc.discount) // (await conf(db, tenant_id)).earn_per
    if points <= 0:
        return 0
    stmt = insert(LoyaltyEntry).values(
        tenant_id=tenant_id,
        customer_id=customer_id,
        kind="earn",
        points=points,
        document_id=document_id,
        outlet_id=doc.outlet_id,
        created_by=user_id,
    )
    added = await db.execute(  # a parallel request may already have given them
        stmt.on_conflict_do_nothing().returning(LoyaltyEntry.id)
    )
    if (entry_id := added.scalar()) is not None:
        await audit.record(
            db,
            tenant_id=tenant_id,
            user_id=user_id,
            outlet_id=doc.outlet_id,
            action="loyalty.earn",
            target_type="loyalty_entries",
            target_id=entry_id,
            summary={"points": points, "document": doc.number},
        )
    return points


def _code() -> str:
    return "-".join("".join(secrets.choice(ALPHABET) for _ in range(4)) for _ in range(2))


async def _new_voucher(db: AsyncSession, row: Voucher) -> Voucher:
    for _ in range(5):  # 32^8 codes: a clash is very unlikely; try again if one happens
        row.code = _code()
        exists = await db.scalar(select(Voucher.id).where(Voucher.code == row.code))
        if exists is None:
            db.add(row)
            await db.flush()
            return row
    raise ConflictError("voucher_code_clash")


async def _expiry(db: AsyncSession, tenant_id: uuid.UUID, days: int):  # type: ignore[no-untyped-def]
    return await tenant_today(db, tenant_id) + timedelta(days=days) if days else None


async def redeem(
    db: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID, data: RedeemIn
) -> Voucher:
    await guest(db, data.customer_id, lock=True)  # one spend at a time per guest
    c = await conf(db, tenant_id)
    if data.points < c.min_redeem_points:
        raise ConflictError("points_below_minimum", details={"min": c.min_redeem_points})
    have = await balance(db, data.customer_id)
    if data.points > have:
        raise ConflictError("points_not_enough", details={"balance": have})
    voucher = await _new_voucher(
        db,
        Voucher(
            tenant_id=tenant_id,
            amount=data.points * c.point_value,
            customer_id=data.customer_id,
            points=data.points,
            expires_on=await _expiry(db, tenant_id, c.voucher_valid_days),
            created_by=user_id,
        ),
    )
    entry = LoyaltyEntry(
        tenant_id=tenant_id,
        customer_id=data.customer_id,
        kind="redeem",
        points=-data.points,
        voucher_id=voucher.id,
        created_by=user_id,
    )
    db.add(entry)
    await db.flush()
    await _audit(db, voucher, "redeem", {"points": data.points, "amount": voucher.amount})
    return voucher


async def issue(
    db: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID, data: VoucherIn
) -> Voucher:
    if data.customer_id is not None:
        await guest(db, data.customer_id)
    voucher = await _new_voucher(
        db,
        Voucher(
            tenant_id=tenant_id,
            amount=data.amount,
            customer_id=data.customer_id,
            note=data.note,
            expires_on=data.expires_on,
            created_by=user_id,
        ),
    )
    await _audit(db, voucher, "voucher.issue", {"amount": voucher.amount})
    return voucher


async def void(db: AsyncSession, voucher_id: uuid.UUID, user_id: uuid.UUID) -> Voucher:
    """Void an unused voucher; points it was bought with come back to the guest."""
    row = await db.get(Voucher, voucher_id, with_for_update=True)
    if row is None:
        raise NotFoundError("voucher_not_found")
    if row.status != "active":
        raise ConflictError("voucher_not_active")
    row.status = "void"
    if row.points and row.customer_id:
        db.add(
            LoyaltyEntry(
                tenant_id=row.tenant_id,
                customer_id=row.customer_id,
                kind="adjust",
                points=row.points,
                voucher_id=row.id,
                created_by=user_id,
            )
        )
    await db.flush()
    await audit.record(
        db,
        tenant_id=row.tenant_id,
        user_id=user_id,
        action="loyalty.voucher.void",
        target_type="vouchers",
        target_id=row.id,
        summary={"amount": row.amount},
    )
    return row


async def spend_vouchers(db: AsyncSession, tenant_id: uuid.UUID, document_id: uuid.UUID) -> None:
    """On payment: each voucher tender names its code; the voucher must be active, unexpired
    and worth at least what it pays. Raising here rolls the whole payment back."""
    today = await tenant_today(db, tenant_id)
    for ref, amount in await tenders_of_kind(db, document_id, "voucher"):
        code = (ref or "").strip().upper()
        row = await db.scalar(select(Voucher).where(Voucher.code == code).with_for_update())
        if row is None:
            raise ConflictError("voucher_not_found", details={"code": code})
        if row.status != "active" or (row.expires_on is not None and row.expires_on < today):
            raise ConflictError("voucher_not_active", details={"code": code})
        if amount > row.amount:
            raise ConflictError("voucher_too_small", details={"code": code, "amount": row.amount})
        row.status, row.used_document_id, row.used_at = "used", document_id, datetime.now(UTC)
    await db.flush()


async def undo_for_document(
    db: AsyncSession, document_id: uuid.UUID, user_id: uuid.UUID | None
) -> None:
    """A refunded or replaced receipt takes back its points and frees its vouchers."""
    earned = await db.scalar(
        select(LoyaltyEntry).where(
            LoyaltyEntry.document_id == document_id, LoyaltyEntry.kind == "earn"
        )
    )
    if earned is not None:
        stmt = insert(LoyaltyEntry).values(
            tenant_id=earned.tenant_id,
            customer_id=earned.customer_id,
            kind="reverse",
            points=-earned.points,
            document_id=document_id,
            outlet_id=earned.outlet_id,
            created_by=user_id,
        )
        await db.execute(stmt.on_conflict_do_nothing())
    used = await db.scalars(
        select(Voucher).where(Voucher.used_document_id == document_id).with_for_update()
    )
    for v in used:
        v.status, v.used_document_id, v.used_at = "active", None, None
    await db.flush()


async def find_voucher(db: AsyncSession, code: str) -> Voucher:
    row = await db.scalar(select(Voucher).where(Voucher.code == code.strip().upper()))
    if row is None:
        raise NotFoundError("voucher_not_found")
    return row
