"""
app/core/crypto.py — Fernet symmetric encryption for secrets stored at rest
(SIP passwords, Vobiz auth tokens) in columns that must never hold plaintext.

FERNET_KEY (app/config.py) must be a urlsafe-base64-encoded 32-byte key:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
Never hardcode it or commit it — it lives in .env (gitignored) like every
other secret in this codebase.
"""
from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


class DecryptionError(Exception):
    """Raised when a stored value can't be decrypted (wrong/rotated key, corrupted data, or plaintext)."""


@lru_cache
def _fernet() -> Fernet:
    return Fernet(settings.FERNET_KEY.encode("utf-8"))


def encrypt_value(plaintext: str) -> str:
    """Encrypt a string for storage. Returns a urlsafe-base64 Fernet token."""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_value(token: str) -> str:
    """Decrypt a value previously produced by encrypt_value."""
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise DecryptionError(
            "Could not decrypt stored value — wrong FERNET_KEY, corrupted data, or unencrypted plaintext"
        ) from exc
