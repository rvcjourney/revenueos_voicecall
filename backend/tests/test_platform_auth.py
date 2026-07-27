"""
tests/test_platform_auth.py — SuperAdmin (platform) auth + core API tests.

Covers the separation between the org-user token path (app/api/auth.py,
require_admin) and the platform-admin token path (app/api/platform.py,
require_platform_admin): each must reject the other's token outright.
"""
from __future__ import annotations

from sqlalchemy import select

from app.core.security import create_access_token, create_platform_token, hash_password
from app.models.audit_log import AuditLog
from app.models.platform_admin import PlatformAdmin
from app.models.user import Organization, User, UserRole


async def _make_platform_admin(db, email: str, password: str) -> PlatformAdmin:
    admin = PlatformAdmin(
        email=email,
        hashed_password=hash_password(password),
        full_name="Super Admin",
        is_active=True,
    )
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    return admin


async def _make_org_and_user(db) -> tuple[Organization, User]:
    org = Organization(name="Acme Inc", slug="acme-inc")
    db.add(org)
    await db.flush()

    user = User(
        org_id=org.id,
        email="admin@acme.test",
        hashed_password=hash_password("user-pw-123"),
        full_name="Acme Admin",
        role=UserRole.ADMIN,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(org)
    await db.refresh(user)
    return org, user


async def test_platform_login_success(client, db):
    await _make_platform_admin(db, "super1@motmvoice.com", "correct-horse-1")

    resp = await client.post(
        "/api/platform/login",
        json={"email": "super1@motmvoice.com", "password": "correct-horse-1"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["admin"]["email"] == "super1@motmvoice.com"


async def test_platform_login_wrong_password(client, db):
    await _make_platform_admin(db, "super2@motmvoice.com", "correct-horse-2")

    resp = await client.post(
        "/api/platform/login",
        json={"email": "super2@motmvoice.com", "password": "wrong-password"},
    )
    assert resp.status_code == 401


async def test_platform_token_rejected_by_org_route(client, db):
    admin = await _make_platform_admin(db, "super3@motmvoice.com", "correct-horse-3")
    token = create_platform_token(str(admin.id))

    resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


async def test_org_token_rejected_by_platform_route(client, db):
    org, user = await _make_org_and_user(db)
    token = create_access_token(str(user.id), str(user.org_id), user.role)

    resp = await client.get("/api/platform/orgs", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


async def test_patch_org_writes_audit_log(client, db):
    admin = await _make_platform_admin(db, "super4@motmvoice.com", "correct-horse-4")
    org, _user = await _make_org_and_user(db)
    token = create_platform_token(str(admin.id))

    resp = await client.patch(
        f"/api/platform/orgs/{org.id}",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    audit_rows = (await db.execute(
        select(AuditLog).where(AuditLog.org_id == org.id, AuditLog.action == "org.update")
    )).scalars().all()
    assert len(audit_rows) == 1
    assert audit_rows[0].actor_type == "platform_admin"
    assert audit_rows[0].actor_id == admin.id
