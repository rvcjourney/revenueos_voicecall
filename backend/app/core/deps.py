"""
app/core/deps.py — FastAPI dependency: extract and validate the JWT Bearer token.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends
from jwt.exceptions import InvalidTokenError

from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.core.security import decode_token

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class TokenPayload:
    user_id: UUID
    org_id: UUID
    role: str


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> TokenPayload:
    if credentials is None:
        raise AuthenticationError("Missing Bearer token")
    try:
        payload = decode_token(credentials.credentials)
    except InvalidTokenError:
        raise AuthenticationError("Invalid or expired token")

    if payload.get("type") != "access":
        raise AuthenticationError("Not an access token")

    # Check Redis blocklist — tokens revoked via /auth/logout are stored here until expiry
    jti = payload.get("jti")
    if jti:
        try:
            from app.core.redis import get_redis
            r = await get_redis()
            if await r.exists(f"motm:auth:blocklist:{jti}"):
                raise AuthenticationError("Token has been revoked")
        except AuthenticationError:
            raise
        except Exception:
            pass  # fail open — don't block requests if Redis is temporarily down

    return TokenPayload(
        user_id=UUID(payload["sub"]),
        org_id=UUID(payload["org_id"]),
        role=payload["role"],
    )


async def require_admin(
    token: TokenPayload = Depends(get_current_user),
) -> TokenPayload:
    if token.role != "admin":
        raise PermissionDeniedError("Admin access required")
    return token


async def require_member_or_admin(
    token: TokenPayload = Depends(get_current_user),
) -> TokenPayload:
    if token.role not in ("admin", "member"):
        raise PermissionDeniedError("Access denied")
    return token
