"""
app/core/exceptions.py — Application exception hierarchy.
Each class maps to a specific HTTP status code via handlers in app/main.py.
"""
from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base for all application errors. Unmapped subclasses → HTTP 500."""
    code: str = "INTERNAL_ERROR"
    message: str = "An internal error occurred."

    def __init__(self, message: str | None = None, code: str | None = None) -> None:
        self.message = message or self.__class__.message
        self.code = code or self.__class__.code
        super().__init__(self.message)


class NotFoundError(AppError):
    """HTTP 404."""
    code = "NOT_FOUND"
    message = "Resource not found."


class PermissionDeniedError(AppError):
    """HTTP 403 — org isolation violation or insufficient role."""
    code = "PERMISSION_DENIED"
    message = "You do not have permission to perform this action."


class AuthenticationError(AppError):
    """HTTP 401 — invalid or expired credentials."""
    code = "UNAUTHENTICATED"
    message = "Authentication required."


class ConflictError(AppError):
    """HTTP 409 — duplicate resource."""
    code = "CONFLICT"
    message = "Resource already exists."


class ValidationError(AppError):
    """HTTP 422 — domain-level validation failure (distinct from Pydantic request validation)."""
    code = "VALIDATION_ERROR"
    message = "Validation failed."

    def __init__(
        self,
        message: str | None = None,
        errors: list[dict[str, Any]] | None = None,
        code: str | None = None,
    ) -> None:
        super().__init__(message, code)
        self.errors: list[dict[str, Any]] = errors or []


class QuotaExceededError(AppError):
    """HTTP 402 — org has exceeded its monthly call quota."""
    code = "QUOTA_EXCEEDED"
    message = "Monthly call quota exceeded. Please upgrade your plan or wait for the next billing period."


class DNCBlockedError(AppError):
    """HTTP 422 — phone number is on the org's Do Not Call list."""
    code = "DNC_BLOCKED"
    message = "This phone number is on the Do Not Call list and cannot be dialled."


class CampaignStateError(AppError):
    """HTTP 409 — action is not valid for the campaign's current state."""
    code = "INVALID_CAMPAIGN_STATE"
    message = "This action is not allowed in the current campaign state."


class WebhookAuthError(AppError):
    """HTTP 401 — HMAC signature on an inbound webhook is invalid or stale."""
    code = "WEBHOOK_AUTH_FAILED"
    message = "Webhook signature verification failed."


class StorageError(AppError):
    """HTTP 502 — object storage operation failed."""
    code = "STORAGE_ERROR"
    message = "A storage operation failed."


class RateLimitedError(AppError):
    """HTTP 429 — too many requests to a rate-limited endpoint (app/core/rate_limit.py)."""
    code = "RATE_LIMITED"
    message = "Too many attempts. Please wait a bit and try again."

    def __init__(
        self,
        message: str | None = None,
        code: str | None = None,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message, code)
        # How long until the caller's rate-limit window resets, if known --
        # surfaced by app/main.py's handler as both a Retry-After header and a
        # response field so the frontend can show a countdown instead of just
        # a static "try again later".
        self.retry_after_seconds = retry_after_seconds
