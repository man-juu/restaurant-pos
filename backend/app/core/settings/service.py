"""Tenant settings, numbering and approval lookups (FR-TEN-004 to 009)."""

import uuid
from datetime import date
from typing import Any, cast

from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.errors import AppError, NotFoundError
from app.core.models import ApprovalRule, Tenant, TenantSetting
from app.core.settings.defaults import default_for
from app.core.settings.schemas import SETTINGS, NumberingFormat, NumberingSettings, Strict

NIL_OUTLET = uuid.UUID(int=0)


class InvalidSetting(AppError):
    status_code, code = 422, "invalid_setting"


async def _tenant(db: AsyncSession, tenant_id: uuid.UUID) -> Tenant:
    return (await db.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one()


async def get_setting(db: AsyncSession, tenant_id: uuid.UUID, key: str) -> Strict:
    """Stored value, or the country default if the tenant never changed it."""
    model = SETTINGS.get(key)
    if model is None:
        raise NotFoundError()
    row = (
        await db.execute(select(TenantSetting.value).where(TenantSetting.key == key))
    ).scalar_one_or_none()
    if row is None:
        row = default_for((await _tenant(db, tenant_id)).country, key)
    return model.model_validate(row)


async def get_all_settings(db: AsyncSession, tenant_id: uuid.UUID) -> dict[str, Strict]:
    """Every setting in two queries (stored rows, then the tenant's country for defaults)."""
    result = await db.execute(select(TenantSetting.key, TenantSetting.value))
    rows: dict[str, Any] = {key: value for key, value in result.all()}
    country = None if set(SETTINGS) <= rows.keys() else (await _tenant(db, tenant_id)).country
    return {
        key: model.model_validate(rows[key] if key in rows else default_for(country or "", key))
        for key, model in SETTINGS.items()
    }


async def put_setting(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    key: str,
    value: dict[str, Any],
) -> Strict:
    model = SETTINGS.get(key)
    if model is None:
        raise NotFoundError()
    try:
        parsed = model.model_validate(value)
    except ValidationError as exc:
        details = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
        raise InvalidSetting(details=details) from None
    if key == "service_charge" and getattr(parsed, "enabled", False):
        # FR-TEN-005: service charge is always off for the cloud kitchen profile.
        if (await _tenant(db, tenant_id)).profile == "cloud_kitchen":
            raise InvalidSetting("service_charge_not_allowed")
    before = await get_setting(db, tenant_id, key)
    stored = parsed.model_dump(mode="json")
    stmt = insert(TenantSetting).values(
        tenant_id=tenant_id, key=key, value=stored, updated_by=user_id
    )
    await db.execute(
        stmt.on_conflict_do_update(
            index_elements=[TenantSetting.tenant_id, TenantSetting.key],
            set_={"value": stmt.excluded.value, "updated_by": user_id, "updated_at": text("now()")},
        )
    )
    await audit.record(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action=f"settings.{key}.updated",
        target_type="setting",
        summary={"before": before.model_dump(mode="json"), "after": stored},
    )
    return parsed


_ALLOCATE = text("""
    INSERT INTO numbering_counters (tenant_id, outlet_id, doc_type, year, last_number)
    VALUES (:tenant_id, :outlet_id, :doc_type, :year, 1)
    ON CONFLICT (tenant_id, outlet_id, doc_type, year)
    DO UPDATE SET last_number = numbering_counters.last_number + 1
    RETURNING last_number
""")


async def allocate_number(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    doc_type: str,
    on: date,
    outlet_id: uuid.UUID | None = None,
) -> str:
    """Next document number, e.g. PO-2026-00042. One atomic upsert inside the document's own
    transaction: concurrent callers wait on the row lock, so numbers never repeat, and a
    rolled-back document does not consume a number."""
    formats = cast(NumberingSettings, await get_setting(db, tenant_id, "numbering"))
    fmt = formats.formats.get(doc_type) or NumberingFormat(prefix=doc_type[:10].upper())
    year = on.year if fmt.reset == "yearly" else 0
    number = (
        await db.execute(
            _ALLOCATE,
            {
                "tenant_id": tenant_id,
                "outlet_id": outlet_id or NIL_OUTLET,
                "doc_type": doc_type,
                "year": year,
            },
        )
    ).scalar_one()
    middle = f"-{on.year}" if fmt.reset == "yearly" else ""
    return f"{fmt.prefix}{middle}-{number:0{fmt.padding}d}"


async def required_approver_roles(
    db: AsyncSession, *, document_type: str, outlet_id: uuid.UUID | None, amount: int
) -> set[uuid.UUID]:
    """FR-TEN-007: roles whose approval the document needs. Outlet-specific rules override
    tenant-wide ones for that outlet. Empty set: no approval needed."""
    rules = (
        (
            await db.execute(
                select(ApprovalRule).where(
                    ApprovalRule.document_type == document_type,
                    ApprovalRule.min_amount <= amount,
                )
            )
        )
        .scalars()
        .all()
    )
    specific = [r for r in rules if outlet_id is not None and r.outlet_id == outlet_id]
    chosen = specific or [r for r in rules if r.outlet_id is None]
    return {r.approver_role_id for r in chosen}
