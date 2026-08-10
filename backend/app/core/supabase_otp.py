"""
app/core/supabase_otp.py — Email OTP send/verify via Supabase Auth (GoTrue).

Used purely as an email-ownership-proof mechanism (signup verification,
forgot-password) — the platform's own users/passwords/JWT sessions
(app/api/auth.py) are completely separate and untouched by this. Supabase
creates a shadow "auth user" internally on first OTP send; it's never
referenced again.

Calls GoTrue's REST endpoints directly with aiohttp rather than the official
`supabase` package: that package pulls in `realtime`, which requires
pydantic>=2.11.7 — incompatible with this project's pinned pydantic==2.10.3
(a real dependency-resolver conflict, confirmed via `pip install`), and drags
in storage3/postgrest that aren't needed just for OTP. The exact request
shape below was confirmed by extracting the `supabase-auth` wheel and reading
_sync/gotrue_client.py + gotrue_base_api.py directly, not guessed.

Manual setup steps (Supabase dashboard, not code) — Auth → Email Templates:
BOTH of these must include `{{ .Token }}`, or Supabase sends a clickable
link instead of a numeric code:
  - "Magic Link" — used when the email already exists (e.g. resend on login)
  - "Confirm signup" — used the FIRST time an email is seen (e.g. new org
    creation, since create_user=True below creates a fresh Supabase user).
    Easy to miss: editing only "Magic Link" leaves brand-new signups still
    getting the default link-based template, whose link redirects to
    whatever Auth → URL Configuration → Site URL is set to (defaults to
    http://localhost:3000 on a fresh Supabase project) — set that to the
    production app URL too.
"""
from __future__ import annotations

import aiohttp
import structlog

from app.config import settings

log = structlog.get_logger(__name__)


class SupabaseOtpError(Exception):
    """Base for Supabase OTP send/verify failures. Message is safe to show the caller."""


class SupabaseNotConfiguredError(SupabaseOtpError):
    """SUPABASE_URL/SUPABASE_ANON_KEY are not set on this server."""


def _base_url() -> str:
    return f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1"


def _headers() -> dict[str, str]:
    return {
        "apikey": settings.SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
    }


async def send_otp(email: str) -> None:
    """Send a one-time code to `email` via Supabase's mailer. Raises SupabaseOtpError on failure."""
    if not settings.SUPABASE_URL or not settings.SUPABASE_ANON_KEY:
        raise SupabaseNotConfiguredError("Email verification is not configured on this server")

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as http:
            async with http.post(
                f"{_base_url()}/otp",
                headers=_headers(),
                json={"email": email, "create_user": True},
            ) as resp:
                if resp.status not in (200, 201):
                    body_text = await resp.text()
                    log.warning("supabase_otp_send_error", status=resp.status, body=body_text[:500])
                    raise SupabaseOtpError("Could not send verification email — please try again")
    except SupabaseOtpError:
        raise
    except Exception as exc:
        log.warning("supabase_otp_send_failed", error=str(exc))
        raise SupabaseOtpError("Could not reach the email service — please try again") from exc


async def verify_otp(email: str, code: str) -> bool:
    """True if `code` is a valid, unexpired OTP for `email`. Never raises on a wrong/expired code —
    only on a genuine service failure (misconfiguration, network), so callers can tell "bad code"
    apart from "couldn't check the code" and show the right message for each.
    """
    if not settings.SUPABASE_URL or not settings.SUPABASE_ANON_KEY:
        raise SupabaseNotConfiguredError("Email verification is not configured on this server")

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as http:
            async with http.post(
                f"{_base_url()}/verify",
                headers=_headers(),
                json={"email": email, "token": code, "type": "email"},
            ) as resp:
                if resp.status in (200, 201):
                    return True
                if resp.status in (400, 401, 403, 422):
                    return False
                body_text = await resp.text()
                log.warning("supabase_otp_verify_error", status=resp.status, body=body_text[:500])
                raise SupabaseOtpError("Could not verify the code — please try again")
    except SupabaseOtpError:
        raise
    except Exception as exc:
        log.warning("supabase_otp_verify_failed", error=str(exc))
        raise SupabaseOtpError("Could not reach the email service — please try again") from exc
