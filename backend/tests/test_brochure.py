"""Brochure after a call (agents brochure upload, app/services/brochure.py) and
reply counting (app/workers/tasks/email_replies.py, app/core/mail_inbox.py)."""
from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, patch

from sqlalchemy import select

from app.core.crypto import encrypt_value
from app.core.mail_inbox import InboxMessage, _parse
from app.core.security import create_access_token, hash_password, sign_webhook_payload
from app.models.agent import AgentTemplate
from app.models.call import Call, CallDirection, CallStatus
from app.models.campaign import Campaign, CampaignContact, ContactStatus
from app.models.lead import Lead, LeadActivity
from app.models.user import Organization, User, UserRole
from app.services.brochure import deliver_brochure_for_call
from app.workers.tasks.email_replies import record_replies

PDF = b"%PDF-1.4 fake brochure"
PHONE = "+919812345678"


class FakeStorage:
    def __init__(self):
        self.files = {}

    async def upload(self, bucket, key, data, content_type="application/octet-stream"):
        self.files[key] = data
        return key

    async def download(self, bucket, key):
        return self.files[key]

    async def delete(self, bucket, key):
        self.files.pop(key, None)


async def _setup(db, *, smtp=True, contact_email=None):
    org = Organization(name=f"Org {uuid.uuid4().hex[:6]}", slug=f"org-{uuid.uuid4().hex[:8]}", is_active=True)
    if smtp:
        org.smtp_host, org.smtp_port, org.smtp_security = "smtp.acme.in", 587, "starttls"
        org.smtp_username = org.smtp_from_email = f"sales-{uuid.uuid4().hex[:6]}@acme.in"
        org.smtp_password = encrypt_value("pw")
    db.add(org)
    await db.flush()
    user = User(org_id=org.id, email=f"a-{uuid.uuid4().hex[:6]}@acme.in", hashed_password=hash_password("pw-123456"),
                full_name="Priya", role=UserRole.ADMIN, is_active=True)
    agent = AgentTemplate(org_id=org.id, name="Ananya")
    db.add_all([user, agent])
    await db.flush()
    camp = Campaign(org_id=org.id, agent_template_id=agent.id, name="C")
    db.add(camp)
    await db.flush()
    contact = CampaignContact(campaign_id=camp.id, org_id=org.id, name="Asha", phone=PHONE, company="Acme",
                              email=contact_email, status=ContactStatus.DIALING)
    db.add(contact)
    await db.flush()
    call = Call(org_id=org.id, campaign_id=camp.id, contact_id=contact.id, livekit_room_name=f"r-{uuid.uuid4().hex}",
                phone_number=PHONE, direction=CallDirection.OUTBOUND, status=CallStatus.COMPLETED)
    db.add(call)
    await db.commit()
    headers = {"Authorization": f"Bearer {create_access_token(str(user.id), str(org.id), user.role)}"}
    return org, agent, call, headers


async def _report(client, call_id, extracted):
    body = json.dumps({"outcome": "interested", "summary": "Wants brochure", "extracted_data": extracted}).encode()
    with patch("app.workers.tasks.brochure.send_brochure.delay") as delay:
        r = await client.post(f"/api/calls/{call_id}/agent-report", content=body,
                              headers={"Content-Type": "application/json", "X-Webhook-Signature": sign_webhook_payload(body)})
    assert r.status_code == 204
    return delay


async def _upload(client, agent, headers, storage, data=PDF, name="Baner Towers.pdf"):
    with patch("app.storage.backend.get_storage", return_value=storage):
        return await client.post(f"/api/agents/{agent.id}/brochure", files={"file": (name, data, "application/pdf")},
                                 headers=headers)


# ── upload ───────────────────────────────────────────────────────────────────

async def test_upload_checks_content_and_fills_default_email(client, db):
    _, agent, _, h = await _setup(db)
    storage = FakeStorage()
    assert (await _upload(client, agent, h, storage, data=b"MZ\x90 not a pdf", name="x.pdf")).status_code == 422
    r = await _upload(client, agent, h, storage)
    assert r.status_code == 200
    out = r.json()
    assert out["brochure_filename"] == "Baner Towers.pdf"
    assert out["brochure_email_subject"] and "{name}" in out["brochure_email_body"]
    with patch("app.storage.backend.get_storage", return_value=storage):
        got = await client.get(f"/api/agents/{agent.id}/brochure", headers=h)
        assert got.content == PDF
        assert (await client.delete(f"/api/agents/{agent.id}/brochure", headers=h)).json()["brochure_filename"] is None
    assert storage.files == {}


# ── automatic send after the call ────────────────────────────────────────────

async def _with_brochure(client, db, agent, h, storage):
    await _upload(client, agent, h, storage)
    await db.refresh(agent)


async def test_customer_agreed_on_call_gets_brochure_from_org_mailbox(client, db):
    org, agent, call, h = await _setup(db, contact_email="old@asha.in")
    storage = FakeStorage()
    await _with_brochure(client, db, agent, h, storage)
    delay = await _report(client, call.id, {"brochure_request": {"email": "asha.k@gmail.com"}})
    delay.assert_called_once_with(str(call.id))

    with patch("app.storage.backend.get_storage", return_value=storage), \
         patch("app.services.brochure.send_email", new=AsyncMock(return_value="<m1@acme.in>")) as send:
        ok, detail = await deliver_brochure_for_call(db, call.id)
    assert ok and detail == "Brochure sent"
    cfg = send.await_args.args[0]
    kw = send.await_args.kwargs
    assert cfg.from_email == org.smtp_from_email           # this customer's own mailbox
    assert kw["to"] == "asha.k@gmail.com"                   # spoken on the call wins over the CSV email
    assert kw["subject"] == "Brochure as discussed" and kw["body"].startswith("Hi Asha,")
    att = kw["attachments"][0]
    assert (att.filename, att.data, att.content_type) == ("Baner Towers.pdf", PDF, "application/pdf")

    lead = (await db.execute(select(Lead).where(Lead.org_id == org.id).execution_options(populate_existing=True))).scalar_one()
    assert lead.email_status == "sent" and lead.email == "old@asha.in"  # the lead keeps the email on file
    act = (await db.execute(select(LeadActivity).where(LeadActivity.lead_id == lead.id, LeadActivity.type == "email"))).scalar_one()
    assert act.payload["kind"] == "brochure" and act.payload["ok"] is True and act.payload["message_id"] == "<m1@acme.in>"


async def test_no_email_anywhere_is_recorded_not_sent(client, db):
    org, agent, call, h = await _setup(db)
    storage = FakeStorage()
    await _with_brochure(client, db, agent, h, storage)
    await _report(client, call.id, {"brochure_request": {"email": ""}})
    with patch("app.services.brochure.send_email", new=AsyncMock()) as send:
        ok, detail = await deliver_brochure_for_call(db, call.id)
    send.assert_not_awaited()
    assert not ok and "No email address" in detail


async def test_without_mailbox_the_reason_is_recorded(client, db):
    _, agent, call, h = await _setup(db, smtp=False, contact_email="asha@x.in")
    storage = FakeStorage()
    await _with_brochure(client, db, agent, h, storage)
    await _report(client, call.id, {"brochure_request": {"email": ""}})
    ok, detail = await deliver_brochure_for_call(db, call.id)
    assert not ok and "Settings" in detail


async def test_call_without_request_sends_nothing(client, db):
    _, _, call, _ = await _setup(db, contact_email="asha@x.in")
    delay = await _report(client, call.id, {})
    delay.assert_not_called()
    assert await deliver_brochure_for_call(db, call.id) is None


async def test_team_can_resend_from_the_lead(client, db):
    org, agent, call, h = await _setup(db, contact_email="asha@x.in")
    storage = FakeStorage()
    await _with_brochure(client, db, agent, h, storage)
    await _report(client, call.id, {})
    lead_id = (await client.get("/api/leads", headers=h)).json()["items"][0]["id"]
    with patch("app.storage.backend.get_storage", return_value=storage), \
         patch("app.services.brochure.send_email", new=AsyncMock(return_value="<m2@acme.in>")) as send:
        r = await client.post(f"/api/leads/{lead_id}/brochure", headers=h)
    assert r.json() == {"ok": True, "detail": "Brochure sent"} and send.await_args.kwargs["to"] == "asha@x.in"


# ── reply counting ───────────────────────────────────────────────────────────

def _msg(uid, mid, frm, thread=()):
    return InboxMessage(uid=uid, message_id=mid, thread_ids=tuple(thread), from_email=frm, subject="Re: brochure", date="")


async def test_replies_matched_by_thread_or_sender_once(client, db):
    org, agent, call, h = await _setup(db, contact_email="asha@x.in")
    await _report(client, call.id, {})
    lead = (await db.execute(select(Lead).where(Lead.org_id == org.id))).scalar_one()
    lead.email, lead.email_status = "asha@x.in", "sent"
    db.add(LeadActivity(org_id=org.id, lead_id=lead.id, type="email", payload={"message_id": "<sent1@acme.in>", "ok": True}))
    await db.commit()

    messages = [
        _msg(1, "<r1@gmail.com>", "someone.else@gmail.com", ["<sent1@acme.in>"]),  # thread match (forwarded reply)
        _msg(2, "<r2@gmail.com>", "asha@x.in"),                                      # sender match
        _msg(3, "<r3@gmail.com>", "random@spam.com"),                                # unrelated
        _msg(4, "<r4@acme.in>", org.smtp_from_email, ["<sent1@acme.in>"]),           # our own copy
    ]
    assert await record_replies(db, org, messages) == 2
    await db.commit()
    assert await record_replies(db, org, messages[:2]) == 0  # already counted
    await db.refresh(lead)
    assert lead.email_status == "replied"


def test_inbox_header_parsing():
    raw = (b"From: Asha K <ASHA@X.IN>\r\nSubject: Re: Brochure\r\nMessage-ID: <r9@gmail.com>\r\n"
           b"In-Reply-To: <sent1@acme.in>\r\nReferences: <a@b.c>\r\n <sent1@acme.in>\r\n\r\n")
    m = _parse(7, raw)
    assert (m.uid, m.from_email, m.message_id) == (7, "asha@x.in", "<r9@gmail.com>")
    assert set(m.thread_ids) == {"<sent1@acme.in>", "<a@b.c>"}
