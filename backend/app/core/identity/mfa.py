"""TOTP enrolment, verification and recovery codes (FR-IDN-002, docs/06 section 3)."""

import base64
import hashlib
import secrets
import uuid

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import SecretBox
from app.core.identity import totp
from app.core.models import RecoveryCode, User

RECOVERY_CODE_COUNT = 10


def _context(user_id: uuid.UUID) -> bytes:
    return b"totp:" + user_id.bytes


def _hash_code(code: str) -> bytes:
    normalised = code.strip().upper().replace("-", "").replace(" ", "")
    return hashlib.sha256(normalised.encode()).digest()


def new_recovery_code() -> str:
    raw = base64.b32encode(secrets.token_bytes(10)).decode()[:10]  # 50 bits
    return f"{raw[:5]}-{raw[5:]}"


async def start_setup(
    session: AsyncSession, box: SecretBox, user: User, *, issuer: str
) -> tuple[str, str]:
    """Store a new (unconfirmed) secret and return it with its otpauth URI."""
    secret = totp.new_secret()
    await session.execute(
        update(User)
        .where(User.id == user.id)
        .values(
            totp_secret_encrypted=box.encrypt(secret, context=_context(user.id)),
            totp_enabled_at=None,
            totp_last_step=None,
        )
    )
    return secret, totp.provisioning_uri(secret, account=user.email, issuer=issuer)


async def check_totp(session: AsyncSession, box: SecretBox, user: User, code: str) -> bool:
    """Verify a TOTP code and burn its time step (no replay)."""
    if user.totp_secret_encrypted is None:
        return False
    secret = box.decrypt(user.totp_secret_encrypted, context=_context(user.id))
    step = totp.verify(secret, code, last_used_step=user.totp_last_step)
    if step is None:
        return False
    await session.execute(update(User).where(User.id == user.id).values(totp_last_step=step))
    return True


async def use_recovery_code(session: AsyncSession, user_id: uuid.UUID, code: str) -> bool:
    result = await session.execute(
        update(RecoveryCode)
        .where(
            RecoveryCode.user_id == user_id,
            RecoveryCode.code_hash == _hash_code(code),
            RecoveryCode.used_at.is_(None),
        )
        .values(used_at=func.now())
    )
    return bool(result.rowcount)  # type: ignore[attr-defined]


async def enable(session: AsyncSession, user_id: uuid.UUID) -> list[str]:
    """Mark TOTP active and issue a fresh set of recovery codes (old ones are deleted)."""
    await session.execute(update(User).where(User.id == user_id).values(totp_enabled_at=func.now()))
    await session.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user_id))
    codes = [new_recovery_code() for _ in range(RECOVERY_CODE_COUNT)]
    await session.execute(
        insert(RecoveryCode), [{"user_id": user_id, "code_hash": _hash_code(c)} for c in codes]
    )
    return codes


async def load_user(session: AsyncSession, user_id: uuid.UUID) -> User:
    return (await session.execute(select(User).where(User.id == user_id))).scalar_one()
