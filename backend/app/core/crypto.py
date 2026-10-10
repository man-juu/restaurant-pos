"""Encryption of small secrets at rest (TOTP secrets), docs/06.

AES-256-GCM from `cryptography` (authenticated: a tampered value fails to decrypt). The key
comes from the environment, never the database, so a stolen database or backup alone cannot
produce valid 2FA codes. Each value has a random 96-bit nonce; the user ID is bound as
associated data so an encrypted secret copied onto another user's row does not decrypt.
"""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

NONCE_BYTES = 12
VERSION = b"\x01"  # lets us rotate the scheme or key later


class SecretBox:
    def __init__(self, key_b64: str) -> None:
        key = base64.b64decode(key_b64)
        if len(key) != 32:
            raise ValueError("encryption key must be 32 bytes (base64-encoded)")
        self._aead = AESGCM(key)

    def encrypt(self, plaintext: str, *, context: bytes) -> bytes:
        nonce = os.urandom(NONCE_BYTES)
        return VERSION + nonce + self._aead.encrypt(nonce, plaintext.encode(), context)

    def decrypt(self, blob: bytes, *, context: bytes) -> str:
        if blob[:1] != VERSION:
            raise ValueError("unknown encryption version")
        nonce, ciphertext = blob[1 : 1 + NONCE_BYTES], blob[1 + NONCE_BYTES :]
        return self._aead.decrypt(nonce, ciphertext, context).decode()
