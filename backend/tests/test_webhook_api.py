"""Org webhook settings (app/api/admin.py) and the agent-report trigger (app/api/calls.py)."""
from __future__ import annotations

import json
import uuid
from unittest.mock import patch

from app.core.crypto import decrypt_value, encrypt_value
from app.core.security import create_access_token, hash_password, sign_webhook_payload
from app.models.call import Call, CallDirection, CallStatus
from app.models.user import Organization, User, UserRole

URL = "https://hooks.example.com/abc"


async def _org_admin(db, role=UserRole.ADMIN):
    org = Organization(name=f"Org {uuid.uuid4().hex[:6]}", slug=f"org-{uuid.uuid4().hex[:8]}", is_active=True)
    db.add(org)
    await db.flush()
    user = User(
        org_id=org.id, email=f"u-{uuid.uuid4().hex[:8]}@acme.test", hashed_password=hash_password("pw-123456"),
        full_name="U", role=role, is_active=True,
    )
    db.add(user)
    await db.commit()
    token = create_access_token(str(user.id), str(user.org_id), user.role)
    return org, {"Authorization": f"Bearer {token}"}


def _no_dns():
    return patch("app.core.webhook_delivery.assert_public_https_url", lambda u: None)


async def test_save_returns_secret_once_and_stores_it_encrypted(client, db):
    org, h = await _org_admin(db)
    with _no_dns():
        r = await client.put("/api/admin/webhook", json={"url": URL}, headers=h)
        assert r.status_code == 200 and r.json()["secret"].startswith("whsec_")
        secret = r.json()["secret"]
        again = await client.put("/api/admin/webhook", json={"url": URL}, headers=h)
        assert again.json()["secret"] is None  # not shown again
    await db.refresh(org)
    assert org.webhook_secret != secret and decrypt_value(org.webhook_secret) == secret
    got = await client.get("/api/admin/webhook", headers=h)
    assert got.json() == {"url": URL, "has_secret": True}


async def test_http_and_private_urls_rejected(client, db):
    _org, h = await _org_admin(db)
    for bad in ["http://hooks.example.com/x", "https://127.0.0.1/x", "https://10.1.2.3/x"]:
        r = await client.put("/api/admin/webhook", json={"url": bad}, headers=h)
        assert 400 <= r.status_code < 500, (bad, r.status_code)


async def test_non_admin_cannot_set_webhook(client, db):
    _org, h = await _org_admin(db, role=UserRole.MEMBER)
    r = await client.put("/api/admin/webhook", json={"url": URL}, headers=h)
    assert r.status_code in (401, 403)


async def test_blank_url_turns_webhook_off(client, db):
    org, h = await _org_admin(db)
    org.webhook_url, org.webhook_secret = URL, encrypt_value("whsec_x")
    await db.commit()
    r = await client.put("/api/admin/webhook", json={"url": ""}, headers=h)
    assert r.status_code == 200
    await db.refresh(org)
    assert org.webhook_url is None and org.webhook_secret is None


async def _report(client, call_id):
    body = json.dumps({"outcome": "interested", "summary": "ok"}).encode()
    return await client.post(
        f"/api/calls/{call_id}/agent-report", content=body,
        headers={"Content-Type": "application/json", "X-Webhook-Signature": sign_webhook_payload(body)},
    )


async def _call(db, with_webhook: bool):
    org, _ = await _org_admin(db)
    if with_webhook:
        org.webhook_url, org.webhook_secret = URL, encrypt_value("whsec_x")
    call = Call(
        org_id=org.id, livekit_room_name=f"room-{uuid.uuid4().hex}", phone_number="+911234567890",
        direction=CallDirection.OUTBOUND, status=CallStatus.COMPLETED,
    )
    db.add(call)
    await db.commit()
    return call


async def test_report_fires_webhook_once_even_if_agent_retries(client, db):
    call = await _call(db, with_webhook=True)
    with patch("app.workers.tasks.webhook.deliver_webhook.delay") as delay:
        assert (await _report(client, call.id)).status_code == 204
        assert (await _report(client, call.id)).status_code == 204  # agent retry
    delay.assert_called_once_with(str(call.id))


async def test_report_without_webhook_queues_nothing(client, db):
    call = await _call(db, with_webhook=False)
    with patch("app.workers.tasks.webhook.deliver_webhook.delay") as delay:
        assert (await _report(client, call.id)).status_code == 204
    delay.assert_not_called()


async def test_report_still_succeeds_if_queue_is_down(client, db):
    call = await _call(db, with_webhook=True)
    with patch("app.workers.tasks.webhook.deliver_webhook.delay", side_effect=ConnectionError("broker down")):
        assert (await _report(client, call.id)).status_code == 204
