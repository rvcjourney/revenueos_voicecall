"""
app/core/google_signin.py — "Sign in with Google" on the login/signup pages.

Same OAuth client as the agent calendar (app/core/google_calendar.py), but only
the openid/email/profile scopes. Google redirects back to the FRONTEND
(<origin>/auth/google), which posts the code to POST /api/auth/google/signin.
"""
from __future__ import annotations

import base64
import json
from urllib.parse import urlencode

import httpx

from app.config import settings
from app.core.google_calendar import AUTH_URL, TOKEN_URL


class GoogleSignInError(Exception):
    """Safe to show the user."""


def configured() -> bool:
    return bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)


def redirect_uri(origin: str) -> str:
    return f"{origin.rstrip('/')}/auth/google"


def auth_url(redirect: str, state: str) -> str:
    return AUTH_URL + "?" + urlencode({
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": redirect,
        "response_type": "code",
        "scope": "openid email profile",
        "prompt": "select_account",
        "state": state,
    })


async def exchange_code(code: str, redirect: str) -> tuple[str, str]:
    """Callback code → (verified email, full name)."""
    async with httpx.AsyncClient(timeout=15.0) as http:
        resp = await http.post(TOKEN_URL, data={
            "client_id": settings.GOOGLE_CLIENT_ID, "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "code": code, "grant_type": "authorization_code", "redirect_uri": redirect,
        })
    if resp.status_code != 200:
        raise GoogleSignInError("Google sign-in failed. Please try again.")
    # The id_token came straight from Google's token endpoint over TLS, so its claims can be trusted as-is.
    claims_b64 = resp.json().get("id_token", "..").split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(claims_b64 + "=" * (-len(claims_b64) % 4)) or b"{}")
    email = str(claims.get("email") or "").strip().lower()
    if not email or claims.get("email_verified") is not True:
        raise GoogleSignInError("Your Google account's email isn't verified.")
    return email, str(claims.get("name") or "").strip()
