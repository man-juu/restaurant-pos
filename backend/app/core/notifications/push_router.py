"""Web push subscriptions for the signed-in person (FR-NTF-005)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.core.access.policy import Principal, require_member
from app.core.notifications import push
from app.core.tenancy import tenant_session

router = APIRouter(prefix="/api/v1/push", tags=["notifications"])
Member = Annotated[Principal, Depends(require_member())]


class PushKey(BaseModel):
    enabled: bool
    public_key: str | None  # VAPID public key for PushManager.subscribe


class Keys(BaseModel):
    p256dh: str = Field(min_length=20, max_length=200)
    auth: str = Field(min_length=8, max_length=100)


class SubscriptionIn(BaseModel):
    endpoint: str = Field(min_length=10, max_length=1000)
    keys: Keys


class EndpointIn(BaseModel):
    endpoint: str = Field(min_length=10, max_length=1000)


@router.get("/key", response_model=PushKey)
async def key(request: Request, p: Member) -> PushKey:
    s = request.app.state.settings
    return PushKey(enabled=s.push_enabled, public_key=s.vapid_public_key or None)


@router.put("/subscription", status_code=204)
async def subscribe(body: SubscriptionIn, request: Request, p: Member) -> None:
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        await push.subscribe(
            db,
            tenant_id=p.tenant_id,
            user_id=p.user_id,
            endpoint=body.endpoint,
            p256dh=body.keys.p256dh,
            auth=body.keys.auth,
        )


@router.post("/subscription/delete", status_code=204)
async def unsubscribe(body: EndpointIn, request: Request, p: Member) -> None:
    async with tenant_session(request.app.state.sessionmaker, p.tenant_id, p.user_id) as db:
        await push.unsubscribe(db, p.user_id, body.endpoint)
