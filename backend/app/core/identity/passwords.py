"""Password hashing and policy (FR-IDN-001, docs/06 section 3).

Argon2id is memory-hard, so guessing passwords from a stolen database is expensive even with
GPUs. Parameters are the OWASP minimum (19 MiB, 2 passes): a hash takes tens of
milliseconds and little memory, which suits a small VPS. Hashing runs in a worker thread so
it never blocks the event loop.
"""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from starlette.concurrency import run_in_threadpool

from app.core.errors import AppError

_hasher = PasswordHasher(time_cost=2, memory_cost=19 * 1024, parallelism=1)
# Verifying against this when the email is unknown makes both cases take the same time, so
# response timing does not reveal which emails have accounts.
_DUMMY_HASH = _hasher.hash("timing-equaliser-not-a-real-password")

MIN_LENGTH_PRIVILEGED = 12  # owners, co-owners, admins
MIN_LENGTH_STAFF = 10
MAX_LENGTH = 256  # bounds hashing cost; docs/06 only forbids a maximum below 128


class WeakPassword(AppError):
    status_code, code = 422, "weak_password"


def validate_new_password(password: str, *, privileged: bool) -> None:
    """Length only: no composition rules, no forced rotation (docs/06, NIST SP 800-63B).
    The breached-password check is added with password changes in slice 0.4b."""
    minimum = MIN_LENGTH_PRIVILEGED if privileged else MIN_LENGTH_STAFF
    if not minimum <= len(password) <= MAX_LENGTH:
        raise WeakPassword(details={"min_length": minimum, "max_length": MAX_LENGTH})


async def hash_password(password: str) -> str:
    return await run_in_threadpool(_hasher.hash, password)


async def verify_password(password_hash: str | None, password: str) -> bool:
    if len(password) > MAX_LENGTH:
        return False
    try:
        return await run_in_threadpool(_hasher.verify, password_hash or _DUMMY_HASH, password) and (
            password_hash is not None
        )
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """True when the stored hash used older parameters; it is upgraded at next sign-in."""
    return _hasher.check_needs_rehash(password_hash)
