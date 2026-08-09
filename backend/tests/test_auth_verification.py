"""
tests/test_auth_verification.py — Email-OTP-gated signup (app/api/auth.py:
register/verify-otp/resend-otp) and OTP-based forgot-password/reset-password.
Supabase's OTP send/verify (app/core/supabase_otp.py) is always mocked --
these tests never touch the network.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from sqlalchemy import select

from app.core.security import hash_password, verify_password
from app.core.supabase_otp import SupabaseOtpError
from app.models.user import Organization, User, UserRole


async def _make_verified_user(db, *, password: str = "password123") -> User:
    org = Organization(name=f"Org {uuid.uuid4().hex[:6]}", slug=f"org-{uuid.uuid4().hex[:8]}", is_active=True)
    db.add(org)
    await db.flush()
    user = User(
        org_id=org.id,
        email=f"user-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password(password),
        full_name="Test User",
        role=UserRole.ADMIN,
        is_active=True,
        email_verified_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def test_register_requires_phone(client):
    resp = await client.post(
        "/api/auth/register",
        json={
            "full_name": "No Phone",
            "company_name": f"NoPhoneCo {uuid.uuid4().hex[:6]}",
            "email": f"nophone-{uuid.uuid4().hex[:8]}@example.com",
            "password": "password123",
        },
    )
    assert resp.status_code == 422


async def test_login_blocked_before_email_verified(client, db):
    email = f"unverified-{uuid.uuid4().hex[:8]}@example.com"
    with patch("app.api.auth.send_otp", new_callable=AsyncMock):
        resp = await client.post(
            "/api/auth/register",
            json={
                "full_name": "Unverified",
                "company_name": f"UvCo {uuid.uuid4().hex[:6]}",
                "email": email,
                "password": "password123",
                "phone": "+919876543210",
            },
        )
    assert resp.status_code == 201

    resp = await client.post("/api/auth/login", json={"email": email, "password": "password123"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "EMAIL_NOT_VERIFIED"


async def test_verify_otp_wrong_code_does_not_verify(client, db):
    email = f"badcode-{uuid.uuid4().hex[:8]}@example.com"
    with patch("app.api.auth.send_otp", new_callable=AsyncMock):
        await client.post(
            "/api/auth/register",
            json={
                "full_name": "Bad Code",
                "company_name": f"BcCo {uuid.uuid4().hex[:6]}",
                "email": email,
                "password": "password123",
                "phone": "+919876543210",
            },
        )

    with patch("app.api.auth.verify_otp", new_callable=AsyncMock, return_value=False):
        resp = await client.post("/api/auth/verify-otp", json={"email": email, "code": "000000"})
    assert resp.status_code == 401

    user = await db.scalar(select(User).where(User.email == email))
    assert user.email_verified_at is None


async def test_resend_otp_rate_limited(client, db, fake_redis):
    email = f"resend-{uuid.uuid4().hex[:8]}@example.com"
    with patch("app.api.auth.send_otp", new_callable=AsyncMock):
        await client.post(
            "/api/auth/register",
            json={
                "full_name": "Resend",
                "company_name": f"RsCo {uuid.uuid4().hex[:6]}",
                "email": email,
                "password": "password123",
                "phone": "+919876543210",
            },
        )

    with patch("app.api.auth.send_otp", new_callable=AsyncMock) as mock_send:
        resp = await client.post("/api/auth/resend-otp", json={"email": email})
        assert resp.status_code == 204
        mock_send.assert_awaited_once_with(email)

        # Second immediate request should be rate-limited, not send again.
        resp2 = await client.post("/api/auth/resend-otp", json={"email": email})
        assert resp2.status_code == 409
        mock_send.assert_awaited_once()


async def test_forgot_password_does_not_leak_unknown_email(client):
    with patch("app.api.auth.send_otp", new_callable=AsyncMock) as mock_send:
        resp = await client.post(
            "/api/auth/forgot-password", json={"email": "no-such-account@example.com"}
        )
    assert resp.status_code == 204
    mock_send.assert_not_called()


async def test_forgot_password_then_reset(client, db):
    user = await _make_verified_user(db)

    with patch("app.api.auth.send_otp", new_callable=AsyncMock) as mock_send:
        resp = await client.post("/api/auth/forgot-password", json={"email": user.email})
    assert resp.status_code == 204
    mock_send.assert_awaited_once_with(user.email)

    with patch("app.api.auth.verify_otp", new_callable=AsyncMock, return_value=True) as mock_verify:
        resp = await client.post(
            "/api/auth/reset-password",
            json={"email": user.email, "code": "123456", "new_password": "newpassword456"},
        )
    assert resp.status_code == 204
    mock_verify.assert_awaited_once_with(user.email, "123456")

    await db.refresh(user)
    assert verify_password("newpassword456", user.hashed_password)
    assert not verify_password("password123", user.hashed_password)

    # Old password no longer works, new one does.
    resp = await client.post("/api/auth/login", json={"email": user.email, "password": "password123"})
    assert resp.status_code == 401
    resp = await client.post("/api/auth/login", json={"email": user.email, "password": "newpassword456"})
    assert resp.status_code == 200


async def test_reset_password_wrong_code_rejected(client, db):
    user = await _make_verified_user(db)

    with patch("app.api.auth.verify_otp", new_callable=AsyncMock, return_value=False):
        resp = await client.post(
            "/api/auth/reset-password",
            json={"email": user.email, "code": "000000", "new_password": "newpassword456"},
        )
    assert resp.status_code == 401

    await db.refresh(user)
    assert verify_password("password123", user.hashed_password)


async def test_supabase_otp_error_surfaces_as_validation_error(client):
    email = f"svcdown-{uuid.uuid4().hex[:8]}@example.com"
    with patch(
        "app.api.auth.send_otp", new_callable=AsyncMock, side_effect=SupabaseOtpError("service down")
    ):
        resp = await client.post(
            "/api/auth/register",
            json={
                "full_name": "Svc Down",
                "company_name": f"SdCo {uuid.uuid4().hex[:6]}",
                "email": email,
                "password": "password123",
                "phone": "+919876543210",
            },
        )
    assert resp.status_code == 422
