"""Settings endpoints (FR-TEN-004 to 009). Reading needs tenant.settings.view; changing needs
tenant.settings.configure (owner and co-owner by default). Every change is audited."""

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from app.core import audit
from app.core.access.policy import Principal, require
from app.core.errors import NotFoundError
from app.core.models import ALERT_TYPES, APPROVAL_DOCUMENTS, AlertRule, ApprovalRule
from app.core.settings import service
from app.core.settings.schemas import AllSettings
from app.core.tenancy import tenant_session

router = APIRouter(prefix="/api/v1", tags=["settings"])

View = Annotated[Principal, Depends(require("tenant.settings.view"))]
Configure = Annotated[Principal, Depends(require("tenant.settings.configure"))]


@router.get("/settings", response_model=AllSettings)
async def all_settings(request: Request, p: View) -> AllSettings:
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        settings = await service.get_all_settings(db, p.tenant_id)
    return AllSettings.model_validate({k: v.model_dump() for k, v in settings.items()})


@router.put("/settings/{key}")
async def put_setting(
    key: str, body: dict[str, Any], request: Request, p: Configure
) -> dict[str, Any]:
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        saved = await service.put_setting(
            db, tenant_id=p.tenant_id, user_id=p.user_id, key=key, value=body
        )
    return saved.model_dump(mode="json")


DocumentType = Literal[
    "purchase_order", "transfer", "adjustment", "count", "void", "refund", "discount", "journal"
]
AlertType = Literal[
    "below_reorder_point",
    "low_days_of_inventory",
    "batch_near_expiry",
    "expired_stock",
    "negative_stock",
    "count_variance",
    "food_cost_above_target",
    "approval_requested",
]
assert set(DocumentType.__args__) == set(APPROVAL_DOCUMENTS)  # type: ignore[attr-defined]  # noqa: S101
assert set(AlertType.__args__) == set(ALERT_TYPES)  # type: ignore[attr-defined]  # noqa: S101


class ApprovalRuleIn(BaseModel):
    document_type: DocumentType
    outlet_id: uuid.UUID | None = None
    min_amount: int = Field(ge=0, le=10**15)
    approver_role_id: uuid.UUID


class ApprovalRuleOut(ApprovalRuleIn):
    id: uuid.UUID


class AlertRuleIn(BaseModel):
    alert_type: AlertType
    recipient_role_id: uuid.UUID | None = None
    recipient_user_id: uuid.UUID | None = None
    channel: Literal["in_app", "email"] = "in_app"


class AlertRuleOut(AlertRuleIn):
    id: uuid.UUID


@router.get("/approval-rules", response_model=list[ApprovalRuleOut])
async def list_approval_rules(request: Request, p: View) -> list[ApprovalRuleOut]:
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        rows = (
            await db.execute(
                select(ApprovalRule).order_by(ApprovalRule.document_type, ApprovalRule.min_amount)
            )
        ).scalars()
        return [ApprovalRuleOut.model_validate(r, from_attributes=True) for r in rows]


@router.post("/approval-rules", status_code=201, response_model=ApprovalRuleOut)
async def create_approval_rule(
    body: ApprovalRuleIn, request: Request, p: Configure
) -> ApprovalRuleOut:
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        # Role and outlet must belong to this tenant: the composite foreign keys plus RLS
        # reject anything else at the database.
        rule = ApprovalRule(tenant_id=p.tenant_id, **body.model_dump())
        db.add(rule)
        await db.flush()
        await audit.record(
            db,
            tenant_id=p.tenant_id,
            user_id=p.user_id,
            action="settings.approval_rule.created",
            target_type="approval_rule",
            target_id=rule.id,
            summary=body.model_dump(mode="json"),
        )
        return ApprovalRuleOut.model_validate(rule, from_attributes=True)


@router.delete("/approval-rules/{rule_id}", status_code=204)
async def delete_approval_rule(rule_id: uuid.UUID, request: Request, p: Configure) -> None:
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        result = await db.execute(delete(ApprovalRule).where(ApprovalRule.id == rule_id))
        if not result.rowcount:  # type: ignore[attr-defined]
            raise NotFoundError()
        await audit.record(
            db,
            tenant_id=p.tenant_id,
            user_id=p.user_id,
            action="settings.approval_rule.deleted",
            target_type="approval_rule",
            target_id=rule_id,
        )


@router.get("/alert-rules", response_model=list[AlertRuleOut])
async def list_alert_rules(request: Request, p: View) -> list[AlertRuleOut]:
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        rows = (await db.execute(select(AlertRule).order_by(AlertRule.alert_type))).scalars()
        return [AlertRuleOut.model_validate(r, from_attributes=True) for r in rows]


@router.post("/alert-rules", status_code=201, response_model=AlertRuleOut)
async def create_alert_rule(body: AlertRuleIn, request: Request, p: Configure) -> AlertRuleOut:
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        rule = AlertRule(tenant_id=p.tenant_id, **body.model_dump())
        db.add(rule)
        await db.flush()
        await audit.record(
            db,
            tenant_id=p.tenant_id,
            user_id=p.user_id,
            action="settings.alert_rule.created",
            target_type="alert_rule",
            target_id=rule.id,
            summary=body.model_dump(mode="json"),
        )
        return AlertRuleOut.model_validate(rule, from_attributes=True)


@router.delete("/alert-rules/{rule_id}", status_code=204)
async def delete_alert_rule(rule_id: uuid.UUID, request: Request, p: Configure) -> None:
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        result = await db.execute(delete(AlertRule).where(AlertRule.id == rule_id))
        if not result.rowcount:  # type: ignore[attr-defined]
            raise NotFoundError()
        await audit.record(
            db,
            tenant_id=p.tenant_id,
            user_id=p.user_id,
            action="settings.alert_rule.deleted",
            target_type="alert_rule",
            target_id=rule_id,
        )
