"""
tests/test_google_signin.py — "Sign in with Google" (app/api/auth.py: /google/url,
/google/signin, /google/complete). Google's token endpoint is always mocked.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse

import jwt as pyjwt
import pytest
from sqlalchemy import select

from app.config import settings
from app.core.google_signin import GoogleSignInError
from app.core.security import hash_password
from app.models.user import Organization, User, UserRole

ORIGIN = "http://localhost:5173"


@pytest.fixture(autouse=True)
def _google_configured(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "secret")
    monkeypatch.setattr(settings, "CORS_ORIGINS", [ORIGIN])


async def _state(client, nonce="n1") -> str:
    resp = await client.get("/api/auth/google/url", params={"origin": ORIGIN, "nonce": nonce})
    assert resp.status_code == 200
    q = parse_qs(urlparse(resp.json()["url"]).query)
    assert q["redirect_uri"] == [f"{ORIGIN}/auth/google"]
    return q["state"][0]


def _google_says(email, name="Asha Patil"):
    return patch("app.core.google_signin.exchange_code", new=AsyncMock(return_value=(email, name)))


async def _signin(client, state, nonce="n1"):
    return await client.post("/api/auth/google/signin", json={"code": "c", "state": state, "nonce": nonce})


async def test_url_rejects_unknown_origin(client):
    resp = await client.get("/api/auth/google/url", params={"origin": "https://evil.example", "nonce": "x"})
    assert resp.status_code == 422


async def test_existing_user_logs_in_and_gets_verified(client, db):
    org = Organization(name="Acme", slug=f"acme-{uuid.uuid4().hex[:6]}", is_active=True)
    db.add(org)
    await db.flush()
    user = User(org_id=org.id, email="Asha@Example.com", hashed_password=hash_password("pw123456"),
                full_name="Asha", role=UserRole.ADMIN, is_active=True, email_verified_at=None)
    db.add(user)
    await db.commit()

    state = await _state(client)
    with _google_says("asha@example.com"):
        resp = await _signin(client, state)
    body = resp.json()
    assert resp.status_code == 200 and body["status"] == "ok"
    assert body["access_token"] and body["user"]["org_name"] == "Acme"
    await db.refresh(user)
    assert user.email_verified_at is not None


async def test_nonce_mismatch_rejected(client):
    state = await _state(client, nonce="mine")
    with _google_says("x@example.com") as m:
        resp = await _signin(client, state, nonce="attackers")
    assert resp.status_code == 401
    m.assert_not_awaited()


async def test_unverified_google_email_rejected(client):
    state = await _state(client)
    with patch("app.core.google_signin.exchange_code",
               new=AsyncMock(side_effect=GoogleSignInError("Your Google account's email isn't verified."))):
        resp = await _signin(client, state)
    assert resp.status_code == 401


async def test_new_user_creates_org_without_otp(client, db):
    state = await _state(client)
    with _google_says("new@example.com", "New Person"):
        resp = await _signin(client, state)
    body = resp.json()
    assert body["status"] == "signup" and body["email"] == "new@example.com" and body["full_name"] == "New Person"

    resp = await client.post("/api/auth/google/complete", json={
        "signup_token": body["signup_token"], "full_name": "New Person",
        "company_name": "New Co", "phone": "98765 43210",
    })
    assert resp.status_code == 201, resp.text
    assert resp.json()["user"]["role"] == "admin"
    user = await db.scalar(select(User).where(User.email == "new@example.com"))
    org = await db.get(Organization, user.org_id)
    assert user.email_verified_at is not None
    assert org.phone == "+919876543210" and org.is_active is False  # still needs a plan, like /register


async def test_new_user_joins_team_by_code(client, db):
    org = Organization(name="Team", slug=f"team-{uuid.uuid4().hex[:6]}", is_active=True)
    db.add(org)
    await db.commit()
    token = pyjwt.encode({"type": "google_signup", "email": "rep@example.com",
                          "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}, settings.SECRET_KEY)
    resp = await client.post("/api/auth/google/complete", json={
        "signup_token": token, "full_name": "Rep", "org_code": org.id.hex[:8].upper(),
    })
    assert resp.status_code == 201, resp.text
    assert resp.json()["user"]["role"] == "member" and resp.json()["user"]["org_id"] == str(org.id)


async def test_complete_rejects_forged_token(client):
    forged = pyjwt.encode({"type": "google_signup", "email": "x@example.com"}, "not-our-secret")
    resp = await client.post("/api/auth/google/complete", json={
        "signup_token": forged, "full_name": "X", "company_name": "XCo", "phone": "9876543210",
    })
    assert resp.status_code == 401
