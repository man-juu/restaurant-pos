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
    # "ok" signed in; "verify" enter your authenticator code; "enroll" set up 2FA first.
    mfa_state: str


class SwitchTenantRequest(BaseModel):
    tenant_id: uuid.UUID


class SessionOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    last_seen_at: datetime
    ip: str | None
    user_agent: str | None
    current: bool


class CodeRequest(BaseModel):
    # A 6-digit TOTP code or a recovery code like "ABCDE-FGHIJ".
    code: str = Field(min_length=6, max_length=20)


class MfaSetupOut(BaseModel):
    secret: str  # for manual entry if the QR code cannot be scanned
    otpauth_uri: str  # render as a QR code


class RecoveryCodesOut(BaseModel):
    recovery_codes: list[str]  # shown once; only hashes are stored


class PasswordResetRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+$")


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    new_password: str = Field(min_length=1, max_length=1024)


class InvitationCreate(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+$")
    role_id: uuid.UUID


class InvitationOut(BaseModel):
    id: uuid.UUID
    email: str
    expires_at: datetime


class InvitationAccept(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    name: str | None = Field(default=None, min_length=1, max_length=200)  # new accounts only
    password: str = Field(min_length=1, max_length=1024)
