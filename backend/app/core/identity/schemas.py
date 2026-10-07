import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    # Light check only (no extra dependency); the lookup decides whether the account exists.
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+$")
    password: str = Field(min_length=1, max_length=1024)


class TenantOption(BaseModel):
    id: uuid.UUID
    name: str


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    locale: str


class SessionInfo(BaseModel):
    user: UserOut
    tenants: list[TenantOption]
    active_tenant_id: uuid.UUID | None
    csrf_token: str  # send back as X-CSRF-Token on every state-changing request


class SwitchTenantRequest(BaseModel):
    tenant_id: uuid.UUID


class SessionOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    last_seen_at: datetime
    ip: str | None
    user_agent: str | None
    current: bool
