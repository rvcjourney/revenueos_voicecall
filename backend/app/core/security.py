"""
app/core/security.py — JWT, password hashing, API key generation, HMAC webhook helpers.

HMAC helpers (sign_webhook_payload / verify_webhook_signature) are used by:
  - agent.py: signs every POST to /api/webhooks/call-ended
  - app/api/webhooks.py: verifies signature before processing
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt as pyjwt

from app.config import settings

_ALGORITHM = "HS256"
_API_KEY_PREFIX = "motm_"


# ── Passwords ─────────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    """bcrypt hash at configured cost factor. Never store plain passwords."""
    return bcrypt.hashpw(
        plain.encode("utf-8"),
        bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS),
    ).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# ── JWT ───────────────────────────────────────────────────────────────────────

def create_access_token(subject: str, org_id: str, role: str) -> str:
    """
    Create a short-lived access token.
    Payload includes jti (unique ID) for future revocation support.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "org_id": org_id,
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        "jti": secrets.token_hex(16),
    }
    return pyjwt.encode(payload, settings.SECRET_KEY, algorithm=_ALGORITHM)


def create_refresh_token(subject: str, org_id: str) -> str:
    """
    Create a long-lived refresh token.
    Stored hashed in Redis; invalidated on logout via blocklist.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "org_id": org_id,
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        "jti": secrets.token_hex(16),
    }
    return pyjwt.encode(payload, settings.SECRET_KEY, algorithm=_ALGORITHM)


def create_platform_token(admin_id: str) -> str:
    """
    Create an access token for a PlatformAdmin (SuperAdmin tier).
    scope="platform" and no org_id — this is what lets require_platform_admin
    and the org-user dependencies each reject the other's tokens outright.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": admin_id,
        "scope": "platform",
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        "jti": secrets.token_hex(16),
    }
    return pyjwt.encode(payload, settings.SECRET_KEY, algorithm=_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """
    Decode and verify a JWT.
    Raises jwt.exceptions.InvalidTokenError (or subclass) on failure.
    Callers should catch InvalidTokenError and raise AuthenticationError.
    """
    return pyjwt.decode(token, settings.SECRET_KEY, algorithms=[_ALGORITHM])


# ── API keys ──────────────────────────────────────────────────────────────────

def generate_api_key() -> tuple[str, str, str]:
    """
    Generate a new API key.

    Returns:
        (full_key, key_hash, key_prefix)
        - full_key   : shown to the user ONCE on creation, never stored
        - key_hash   : SHA-256 hex digest, stored in api_keys table
        - key_prefix : first 12 chars (e.g. "motm_a3f9b2c1"), stored for UI display
    """
    raw = secrets.token_hex(32)
    full_key = f"{_API_KEY_PREFIX}{raw}"
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()
    key_prefix = full_key[: len(_API_KEY_PREFIX) + 8]
    return full_key, key_hash, key_prefix


def hash_api_key(full_key: str) -> str:
    """Hash an incoming API key for database lookup."""
    return hashlib.sha256(full_key.encode()).hexdigest()


# ── HMAC webhook signatures ───────────────────────────────────────────────────
# Signed string format: "{timestamp}.{raw_body_bytes}"
# Header format:        "t={timestamp},v1={hmac_sha256_hex}"
#
# The timestamp is included in the signed payload to prevent replay attacks.
# verify_webhook_signature rejects signatures older than max_age_seconds.
# hmac.compare_digest is used throughout to prevent timing attacks.

def sign_webhook_payload(body: bytes, timestamp: int | None = None) -> str:
    """
    Generate an HMAC-SHA256 signature header for a webhook payload.

    Args:
        body:      Raw request body bytes to sign.
        timestamp: Unix timestamp (defaults to now). Explicitly injectable for testing.

    Returns:
        Header value string, e.g. "t=1715500000,v1=abc123..."
    """
    ts = timestamp if timestamp is not None else int(time.time())
    signed = f"{ts}.".encode() + body
    mac = hmac.new(
        settings.AGENT_WEBHOOK_SECRET.encode(),
        signed,
        hashlib.sha256,
    ).hexdigest()
    return f"t={ts},v1={mac}"


def verify_webhook_signature(
    body: bytes,
    signature_header: str,
    *,
    max_age_seconds: int = 300,
) -> bool:
    """
    Verify an inbound webhook signature.

    Returns False (never raises) so callers can return a clean 401.
    Rejects payloads older than max_age_seconds to block replay attacks.
    Uses hmac.compare_digest to prevent timing-based secret extraction.

    Args:
        body:             Raw request body bytes.
        signature_header: Value of the X-Webhook-Signature header.
        max_age_seconds:  Maximum tolerated age of the signed timestamp.
    """
    try:
        parts = dict(part.split("=", 1) for part in signature_header.split(","))
        ts = int(parts["t"])
        provided_mac = parts["v1"]
    except (KeyError, ValueError):
        return False

    if abs(int(time.time()) - ts) > max_age_seconds:
        return False

    signed = f"{ts}.".encode() + body
    expected_mac = hmac.new(
        settings.AGENT_WEBHOOK_SECRET.encode(),
        signed,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected_mac, provided_mac)
