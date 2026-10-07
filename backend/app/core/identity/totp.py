"""TOTP two-factor codes (RFC 6238 over RFC 4226), FR-IDN-002.

Implemented with the standard library (about 30 lines) instead of a dependency; tests check it
against the RFC 6238 reference vectors. 30-second steps, 6 digits, SHA-1: the settings every
authenticator app (Google Authenticator, Microsoft Authenticator, Aegis, 1Password) supports.
"""

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote, urlencode

STEP_SECONDS = 30
DIGITS = 6
WINDOW = 1  # accept the previous and next step too, for phone clock drift


def new_secret() -> str:
    """160-bit random secret, base32 as authenticator apps expect."""
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _code(secret: str, counter: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**DIGITS).zfill(DIGITS)


def current_step(now: float | None = None) -> int:
    return int((time.time() if now is None else now) // STEP_SECONDS)


def code_at(secret: str, step: int) -> str:
    return _code(secret, step)


def verify(
    secret: str, code: str, *, last_used_step: int | None, now: float | None = None
) -> int | None:
    """Return the matched step, or None. A step at or before `last_used_step` is refused, so
    a code seen over someone's shoulder cannot be replayed within its 30-90 s lifetime."""
    code = code.strip().replace(" ", "")
    if len(code) != DIGITS or not code.isdigit():
        return None
    step = current_step(now)
    for candidate in range(step - WINDOW, step + WINDOW + 1):
        if last_used_step is not None and candidate <= last_used_step:
            continue
        if hmac.compare_digest(_code(secret, candidate), code):
            return candidate
    return None


def provisioning_uri(secret: str, *, account: str, issuer: str) -> str:
    """otpauth:// URI the frontend turns into a QR code for the authenticator app."""
    label = quote(f"{issuer}:{account}")
    query = urlencode(
        {"secret": secret, "issuer": issuer, "digits": DIGITS, "period": STEP_SECONDS}
    )
    return f"otpauth://totp/{label}?{query}"
