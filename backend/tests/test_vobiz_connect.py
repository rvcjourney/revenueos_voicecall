"""
tests/test_vobiz_connect.py — Self-serve Vobiz trunk provisioning tests.

Mocks the Vobiz validation call (app.core.vobiz.validate_vobiz_account_and_did),
the Vobiz trunk-creation call (app.core.vobiz.create_vobiz_outbound_trunk), and
the LiveKit SDK (app.api.sip_trunks.LiveKitAPI) so these run without any real
network access to Vobiz or LiveKit Cloud.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

from app.config import settings
from app.core.security import create_access_token, hash_password, verify_vobiz_webhook_token
from app.core.vobiz import VobizAuthError, VobizDidNotOwnedError
from app.models.sip import SipTrunk
from app.models.user import Organization, User, UserRole


async def _make_org_and_admin(db) -> tuple[Organization, User, str]:
    org = Organization(name="Acme Inc", slug="acme-inc")
    db.add(org)
    await db.flush()

    user = User(
        org_id=org.id,
        email="admin@acme.test",
        hashed_password=hash_password("admin-pw-123"),
        full_name="Acme Admin",
        role=UserRole.ADMIN,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(org)
    await db.refresh(user)

    token = create_access_token(str(user.id), str(user.org_id), user.role)
    return org, user, token


def _fake_livekit_client(*, trunk_id: str = "ST_fake123", participant_error: Exception | None = None):
    """A MagicMock standing in for LiveKitAPI, with async methods pre-wired."""
    fake = MagicMock()
    fake.sip.create_outbound_trunk = AsyncMock(return_value=MagicMock(sip_trunk_id=trunk_id))
    fake.room.create_room = AsyncMock()
    fake.room.delete_room = AsyncMock()
    if participant_error:
        fake.sip.create_sip_participant = AsyncMock(side_effect=participant_error)
    else:
        fake.sip.create_sip_participant = AsyncMock()
    fake.aclose = AsyncMock()
    return fake


async def test_connect_vobiz_invalid_creds_returns_400(client, db, monkeypatch):
    _org, _user, token = await _make_org_and_admin(db)
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "https://test.example.com")

    with patch(
        "app.api.sip_trunks.validate_vobiz_account_and_did",
        new=AsyncMock(side_effect=VobizAuthError("Invalid Vobiz auth_id or auth_token")),
    ):
        resp = await client.post(
            "/api/sip-trunks/connect-vobiz",
            json={"auth_id": "bad_id", "auth_token": "bad_token", "did": "+912212345678"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 400


async def test_connect_vobiz_did_not_owned_returns_400(client, db, monkeypatch):
    _org, _user, token = await _make_org_and_admin(db)
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "https://test.example.com")

    with patch(
        "app.api.sip_trunks.validate_vobiz_account_and_did",
        new=AsyncMock(side_effect=VobizDidNotOwnedError("+912212345678 is not on this Vobiz account")),
    ):
        resp = await client.post(
            "/api/sip-trunks/connect-vobiz",
            json={"auth_id": "real_id", "auth_token": "real_token", "did": "+912212345678"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 400


async def test_connect_vobiz_happy_path_creates_inactive_trunk_with_encrypted_password(client, db, monkeypatch):
    org, _user, token = await _make_org_and_admin(db)
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "https://test.example.com")

    fake_lk = _fake_livekit_client(trunk_id="ST_livekit_abc")

    with patch("app.api.sip_trunks.validate_vobiz_account_and_did", new=AsyncMock(return_value=None)), \
         patch(
             "app.api.sip_trunks.create_vobiz_outbound_trunk",
             new=AsyncMock(return_value="abc123.sip.vobiz.ai"),
         ) as mock_create_trunk, \
         patch("app.api.sip_trunks.LiveKitAPI", return_value=fake_lk):
        resp = await client.post(
            "/api/sip-trunks/connect-vobiz",
            json={"auth_id": "real_id", "auth_token": "super-secret-vobiz-token", "did": "+912212345678"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "pending_test"
    assert body["did"] == "+912212345678"

    # The Vobiz trunk-create call should carry our webhook URL, built from
    # PUBLIC_BASE_URL, with a per-trunk tid/wt token so app/api/webhooks.py can
    # verify + scope the callback instead of trusting an unauthenticated POST.
    mock_create_trunk.assert_awaited_once()
    webhook_url = mock_create_trunk.call_args.kwargs["webhook_url"]
    assert webhook_url.startswith("https://test.example.com/webhooks/vobiz/recording?tid=")
    assert f"tid={body['trunk_id']}" in webhook_url
    assert "&wt=" in webhook_url
    wt = webhook_url.split("&wt=", 1)[1]
    assert verify_vobiz_webhook_token(UUID(body["trunk_id"]), wt)

    trunk = await db.get(SipTrunk, UUID(body["trunk_id"]))
    assert trunk is not None
    assert trunk.org_id == org.id
    assert trunk.is_active is False
    assert trunk.is_default is False  # not defaulted until it passes /test (see _rebalance_default)
    assert trunk.livekit_trunk_id == "ST_livekit_abc"
    assert trunk.sip_domain == "abc123.sip.vobiz.ai"  # the org's own new Vobiz trunk domain

    # Raw stored value must never contain the plaintext secret...
    assert "super-secret-vobiz-token" not in trunk.sip_password_encrypted
    assert "super-secret-vobiz-token" not in trunk.vobiz_auth_token_encrypted
    # ...but decrypting it must round-trip correctly.
    assert trunk.sip_password == "super-secret-vobiz-token"
    assert trunk.vobiz_auth_token == "super-secret-vobiz-token"


async def test_trunk_test_endpoint_flips_is_active_to_true_on_success(client, db, monkeypatch):
    org, _user, token = await _make_org_and_admin(db)

    trunk = SipTrunk(
        org_id=org.id,
        name="Vobiz +912212345678",
        livekit_trunk_id="ST_livekit_abc",
        sip_domain="test.sip.vobiz.ai",
        sip_username="real_id",
        sip_password="super-secret-vobiz-token",
        caller_id="+912212345678",
        is_default=True,
        is_active=False,
    )
    db.add(trunk)
    await db.commit()
    await db.refresh(trunk)
    assert trunk.is_active is False

    fake_lk = _fake_livekit_client()

    with patch("app.api.sip_trunks.LiveKitAPI", return_value=fake_lk):
        resp = await client.post(
            f"/api/sip-trunks/{trunk.id}/test",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    assert resp.json()["is_active"] is True

    refreshed = await db.get(SipTrunk, trunk.id)
    assert refreshed.is_active is True
