"""Per-org SMTP: admin settings (app/api/admin.py) and the sender (app/core/email_sender.py)."""
from __future__ import annotations

import smtplib
import ssl
import uuid
from unittest.mock import patch

import pytest

from app.core import email_sender as es
from app.core.crypto import decrypt_value
from app.core.security import create_access_token, hash_password
from app.models.user import Organization, User, UserRole

GOOD = {
    "sender_name": "Acme Sales", "sender_email": "sales@acme.in", "host": "smtp.acme.in",
    "security": "starttls", "password": "app-pass-1", "imap_host": "",
}


async def _org_admin(db, role=UserRole.ADMIN):
    org = Organization(name=f"Org {uuid.uuid4().hex[:6]}", slug=f"org-{uuid.uuid4().hex[:8]}", is_active=True)
    db.add(org)
    await db.flush()
    user = User(
        org_id=org.id, email=f"admin-{uuid.uuid4().hex[:6]}@acme.in", hashed_password=hash_password("pw-123456"),
        full_name="Priya", role=role, is_active=True,
    )
    db.add(user)
    await db.commit()
    return org, user, {"Authorization": f"Bearer {create_access_token(str(user.id), str(org.id), user.role)}"}


def _no_dns():
    # The real check resolves DNS; tests use a made-up host.
    return patch("app.api.admin.assert_public_host", lambda *a: None)


# ── admin settings ───────────────────────────────────────────────────────────

async def test_save_encrypts_password_and_never_returns_it(client, db):
    org, _, h = await _org_admin(db)
    with _no_dns():
        r = await client.put("/api/admin/smtp", json=GOOD, headers=h)
    assert r.status_code == 200
    out = r.json()
    assert "password" not in out and out["has_password"] is True and out["configured"] is True
    await db.refresh(org)
    assert org.smtp_password != "app-pass-1" and decrypt_value(org.smtp_password) == "app-pass-1"

    # Saving again without a password keeps the old one (the form never shows it).
    with _no_dns():
        await client.put("/api/admin/smtp", json={**GOOD, "password": None, "sender_name": "Acme"}, headers=h)
    await db.refresh(org)
    assert decrypt_value(org.smtp_password) == "app-pass-1" and org.smtp_from_name == "Acme"
    # The sender email is the login and the security choice fixes the port.
    assert (org.smtp_username, org.smtp_port) == ("sales@acme.in", 587)
    assert (await client.get("/api/admin/smtp", headers=h)).json()["host"] == "smtp.acme.in"


async def test_blank_host_turns_email_off(client, db):
    org, _, h = await _org_admin(db)
    with _no_dns():
        await client.put("/api/admin/smtp", json=GOOD, headers=h)
    r = await client.put("/api/admin/smtp", json={"host": ""}, headers=h)
    assert r.json()["configured"] is False
    await db.refresh(org)
    assert org.smtp_password is None and org.smtp_host is None


@pytest.mark.parametrize("bad", [
    {"security": "none"},                  # plaintext login not allowed
    {"host": "smtp.acme.in:587"},
    {"host": "localhost"},
    {"imap_host": "imap.acme.in:143"},
    {"sender_email": "not-an-email"},
    {"sender_name": "Acme\r\nBcc: x@evil.in"},
    {"password": None},                    # nothing saved yet, so a password is required
])
async def test_bad_settings_rejected(client, db, bad):
    _, _, h = await _org_admin(db)
    with _no_dns():
        r = await client.put("/api/admin/smtp", json={**GOOD, **bad}, headers=h)
    assert 400 <= r.status_code < 500


@pytest.mark.parametrize("host", ["127.0.0.1", "10.0.0.5", "169.254.169.254"])
async def test_private_mail_servers_rejected(client, db, host):
    _, _, h = await _org_admin(db)
    r = await client.put("/api/admin/smtp", json={**GOOD, "host": host}, headers=h)
    assert 400 <= r.status_code < 500


async def test_one_mailbox_serves_only_one_customer(client, db):
    _, _, h1 = await _org_admin(db)
    _, _, h2 = await _org_admin(db)
    with _no_dns():
        assert (await client.put("/api/admin/smtp", json=GOOD, headers=h1)).status_code == 200
        r = await client.put("/api/admin/smtp", json={**GOOD, "sender_email": "SALES@acme.in"}, headers=h2)
    assert r.status_code == 409 and "only one customer" in r.json()["detail"].lower() + r.text.lower()
    with _no_dns():  # the same org saving again is fine
        assert (await client.put("/api/admin/smtp", json=GOOD, headers=h1)).status_code == 200


async def test_imap_host_saved_and_mailbox_change_restarts_reply_reading(client, db):
    org, _, h = await _org_admin(db)
    with _no_dns():
        await client.put("/api/admin/smtp", json={**GOOD, "imap_host": "imap.acme.in"}, headers=h)
    await db.refresh(org)
    org.imap_last_uid = 500
    await db.commit()
    with _no_dns():
        out = (await client.put("/api/admin/smtp", json={**GOOD, "imap_host": "imap.acme.in"}, headers=h)).json()
    await db.refresh(org)
    assert out["imap_host"] == "imap.acme.in" and org.imap_last_uid == 500  # same mailbox: keep position
    with _no_dns():
        await client.put("/api/admin/smtp", json={**GOOD, "sender_email": "info@acme.in"}, headers=h)
    await db.refresh(org)
    assert org.imap_last_uid is None and org.imap_host is None


async def test_member_cannot_change_smtp(client, db):
    _, _, h = await _org_admin(db, role=UserRole.MEMBER)
    assert (await client.put("/api/admin/smtp", json=GOOD, headers=h)).status_code in (401, 403)
    assert (await client.get("/api/admin/smtp", headers=h)).status_code in (401, 403)


async def test_test_email_goes_to_the_admin_through_the_saved_server(client, db):
    _, user, h = await _org_admin(db)
    assert 400 <= (await client.post("/api/admin/smtp/test", headers=h)).status_code < 500  # nothing saved yet
    with _no_dns():
        await client.put("/api/admin/smtp", json=GOOD, headers=h)

    sent = []
    with patch.object(es, "assert_public_host", lambda *a: None), \
         patch.object(es, "_send_sync", lambda cfg, msg: sent.append((cfg, msg))):
        r = await client.post("/api/admin/smtp/test", headers=h)
    assert r.json()["ok"] is True
    cfg, msg = sent[0]
    assert cfg.password == "app-pass-1" and msg["To"] == user.email and msg["From"] == "Acme Sales <sales@acme.in>"
    assert msg["Reply-To"] is None  # replies stay in the org mailbox, where IMAP counts them

    def refuse(cfg, msg):
        raise smtplib.SMTPAuthenticationError(535, b"bad credentials")
    with patch.object(es, "assert_public_host", lambda *a: None), patch.object(es, "_send_sync", refuse):
        r = await client.post("/api/admin/smtp/test", headers=h)
    assert r.json()["ok"] is False and "app password" in r.json()["detail"]


# ── sender ───────────────────────────────────────────────────────────────────

CFG = es.SmtpConfig("smtp.acme.in", 587, "starttls", "u", "p", "sales@acme.in", "Acme")


def test_header_injection_is_blocked():
    with pytest.raises(es.EmailSendError):
        es.build_message(CFG, to="a@x.in", subject="Hi\r\nBcc: victim@x.in", body="b")
    with pytest.raises(es.EmailSendError):
        es.build_message(CFG, to="a@x.in\nBcc: victim@x.in", subject="Hi", body="b")


@pytest.mark.parametrize("exc, words", [
    (smtplib.SMTPAuthenticationError(535, b"no"), "app password"),
    (smtplib.SMTPRecipientsRefused({"a@x.in": (550, b"no")}), "refused the address"),
    (ssl.SSLError("wrong version"), "Secure connection failed"),
    (TimeoutError(), "Could not send through smtp.acme.in:587"),
])
async def test_send_errors_become_plain_messages(exc, words):
    def boom(cfg, msg):
        raise exc
    with patch.object(es, "assert_public_host", lambda *a: None), patch.object(es, "_send_sync", boom):
        with pytest.raises(es.EmailSendError, match=words):
            await es.send_email(CFG, to="a@x.in", subject="s", body="b")


async def test_server_hanging_up_on_login_reads_as_bad_password():
    class HangsUpOnLogin:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self, **k): pass
        def login(self, u, p): raise smtplib.SMTPServerDisconnected("Connection unexpectedly closed")
        def send_message(self, msg): raise AssertionError("must not send after a failed login")

    with patch.object(es, "assert_public_host", lambda *a: None), patch.object(es.smtplib, "SMTP", HangsUpOnLogin):
        with pytest.raises(es.EmailSendError, match="username or password"):
            await es.send_email(CFG, to="a@x.in", subject="s", body="b")


async def test_send_rechecks_host_at_send_time():
    # A host that was public when saved but now resolves privately must not be contacted.
    called = []
    with patch.object(es, "_send_sync", lambda *a: called.append(1)):
        with pytest.raises(es.EmailSendError, match="public address"):
            await es.send_email(es.SmtpConfig("127.0.0.1", 587, "starttls", "", "", "a@b.in", ""), to="a@x.in", subject="s", body="b")
    assert called == []
