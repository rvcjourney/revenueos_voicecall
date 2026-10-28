"""Lead CRM: auto-fill from call reports (app/services/leads.py) and /api/leads."""
from __future__ import annotations

import csv
import io
import json
import uuid
from unittest.mock import AsyncMock, patch

from sqlalchemy import select

from app.core.security import create_access_token, hash_password, sign_webhook_payload
from app.models.agent import AgentTemplate
from app.models.call import Call, CallDirection, CallStatus
from app.models.campaign import Campaign, CampaignContact, ContactStatus
from app.models.lead import Lead, LeadActivity
from app.models.user import Organization, User, UserRole

PHONE = "+919812345678"


async def _org(db, role=UserRole.ADMIN):
    org = Organization(name=f"Org {uuid.uuid4().hex[:6]}", slug=f"org-{uuid.uuid4().hex[:8]}", is_active=True)
    db.add(org)
    await db.flush()
    user = User(
        org_id=org.id, email=f"u-{uuid.uuid4().hex[:8]}@acme.test", hashed_password=hash_password("pw-123456"),
        full_name="Priya", role=role, is_active=True,
    )
    db.add(user)
    await db.commit()
    return org, user, {"Authorization": f"Bearer {create_access_token(str(user.id), str(org.id), user.role)}"}


async def _campaign_call(db, org, phone=PHONE, name="Asha", campaign=True):
    contact_id = campaign_id = None
    if campaign:
        agent = AgentTemplate(org_id=org.id, name="A")
        db.add(agent)
        await db.flush()
        camp = Campaign(org_id=org.id, agent_template_id=agent.id, name="C")
        db.add(camp)
        await db.flush()
        contact = CampaignContact(
            campaign_id=camp.id, org_id=org.id, name=name, phone=phone, company="Acme",
            custom_fields={"city": "Pune"}, status=ContactStatus.DIALING,
        )
        db.add(contact)
        await db.flush()
        contact_id, campaign_id = contact.id, camp.id
    call = Call(
        org_id=org.id, campaign_id=campaign_id, contact_id=contact_id, livekit_room_name=f"r-{uuid.uuid4().hex}",
        phone_number=phone, direction=CallDirection.OUTBOUND, status=CallStatus.COMPLETED,
    )
    db.add(call)
    await db.commit()
    return call


async def _report(client, call_id, **payload):
    body = json.dumps({"outcome": "not_interested", "summary": "s", **payload}).encode()
    r = await client.post(
        f"/api/calls/{call_id}/agent-report", content=body,
        headers={"Content-Type": "application/json", "X-Webhook-Signature": sign_webhook_payload(body)},
    )
    assert r.status_code == 204
    return r


async def _lead(db, org, phone=PHONE) -> Lead:
    # populate_existing: re-read the row the API just changed through the same session.
    return (await db.execute(
        select(Lead).where(Lead.org_id == org.id, Lead.phone == phone).execution_options(populate_existing=True)
    )).scalar_one()


async def _activity_types(db, lead):
    return [a.type for a in (await db.execute(
        select(LeadActivity).where(LeadActivity.lead_id == lead.id).order_by(LeadActivity.created_at)
    )).scalars().all()]


# ── auto-fill from calls ─────────────────────────────────────────────────────

async def test_call_report_creates_lead_from_contact(client, db):
    org, _, _ = await _org(db)
    call = await _campaign_call(db, org)
    await _report(client, call.id, summary="Not now", extracted_data={"caller_email": "asha@x.in"})
    lead = await _lead(db, org)
    assert (lead.name, lead.company, lead.email) == ("Asha", "Acme", "asha@x.in")
    assert lead.custom_fields == {"city": "Pune"}
    assert lead.status == "contacted" and lead.last_summary == "Not now" and lead.last_call_id == call.id
    assert lead.email_status == "captured"
    assert await _activity_types(db, lead) == ["call", "status_change"]


async def test_same_phone_in_two_campaigns_is_one_lead(client, db):
    org, _, _ = await _org(db)
    first = await _campaign_call(db, org)
    await _report(client, first.id)
    second = await _campaign_call(db, org)
    await _report(client, second.id, outcome="interested", summary="Send prices")
    leads = (await db.execute(select(Lead).where(Lead.org_id == org.id))).scalars().all()
    assert len(leads) == 1
    lead = await _lead(db, org)
    assert lead.status == "interested" and lead.last_call_id == second.id and lead.last_summary == "Send prices"


async def test_booking_sets_meeting(client, db):
    org, _, _ = await _org(db)
    call = await _campaign_call(db, org)
    booking = {"date_time": "Tuesday 4pm", "reference": "NS-ABC123", "next_step_type": "demo"}
    await _report(client, call.id, outcome="interested", extracted_data={"next_step_booking": booking})
    lead = await _lead(db, org)
    assert (lead.status, lead.meeting_status, lead.meeting_at_text, lead.meeting_ref) == (
        "meeting_scheduled", "scheduled", "Tuesday 4pm", "NS-ABC123")


async def test_won_lead_is_not_downgraded_but_dnc_is_respected(client, db):
    org, _, _ = await _org(db)
    await _report(client, (await _campaign_call(db, org)).id)
    lead = await _lead(db, org)
    lead.status = "won"
    await db.commit()
    await _report(client, (await _campaign_call(db, org)).id, outcome="not_interested")
    assert (await _lead(db, org)).status == "won"

    lead = await _lead(db, org)
    lead.status = "lost"
    await db.commit()
    await _report(client, (await _campaign_call(db, org)).id, outcome="do_not_call")
    assert (await _lead(db, org)).status == "do_not_call"


async def test_manual_name_is_never_overwritten_by_a_call(client, db):
    org, _, _ = await _org(db)
    await _report(client, (await _campaign_call(db, org)).id)
    lead = await _lead(db, org)
    lead.name = "Asha Sharma (typed)"
    await db.commit()
    await _report(client, (await _campaign_call(db, org, name="Someone Else")).id)
    assert (await _lead(db, org)).name == "Asha Sharma (typed)"


async def test_retried_report_does_not_double_the_timeline(client, db):
    org, _, _ = await _org(db)
    call = await _campaign_call(db, org)
    await _report(client, call.id)
    await _report(client, call.id)
    assert (await _activity_types(db, await _lead(db, org))).count("call") == 1


async def test_test_call_without_campaign_creates_no_lead(client, db):
    org, _, _ = await _org(db)
    call = await _campaign_call(db, org, campaign=False)
    await _report(client, call.id)
    assert (await db.execute(select(Lead).where(Lead.org_id == org.id))).scalars().first() is None


async def test_backfill_builds_leads_from_old_calls_and_is_rerunnable(db):
    from datetime import datetime, timezone

    from scripts.backfill_leads import main as backfill

    org, _, _ = await _org(db)
    long_ago = datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc)
    for outcome in ("not_interested", "interested"):
        call = await _campaign_call(db, org)
        call.reported_at, call.outcome, call.summary = datetime.now(timezone.utc), outcome, outcome
        call.started_at = long_ago
    await db.commit()

    await backfill()
    await backfill()  # second run must not add timeline entries again
    lead = await _lead(db, org)
    assert lead.status == "interested" and lead.last_summary == "interested"
    assert (await _activity_types(db, lead)).count("call") == 2
    stamps = (await db.execute(select(LeadActivity.created_at).where(LeadActivity.lead_id == lead.id))).scalars().all()
    assert all(s == long_ago for s in stamps)  # timeline shows when the calls happened, not when backfill ran


# ── API ──────────────────────────────────────────────────────────────────────

async def test_list_is_org_scoped_and_filters(client, db):
    org, user, h = await _org(db)
    other_org, _, other_h = await _org(db)
    await _report(client, (await _campaign_call(db, org)).id, outcome="interested")
    await _report(client, (await _campaign_call(db, org, phone="+919800000001", name="Ravi")).id)
    await _report(client, (await _campaign_call(db, other_org)).id)

    r = (await client.get("/api/leads", headers=h)).json()
    assert r["total"] == 2 and r["status_counts"] == {"interested": 1, "contacted": 1}
    assert (await client.get("/api/leads?status=interested", headers=h)).json()["items"][0]["name"] == "Asha"
    assert (await client.get("/api/leads?q=ravi", headers=h)).json()["total"] == 1
    assert (await client.get("/api/leads?owner=me", headers=h)).json()["total"] == 0
    assert (await client.get("/api/leads", headers=other_h)).json()["total"] == 1

    lead_id = (await client.get("/api/leads?q=ravi", headers=h)).json()["items"][0]["id"]
    assert (await client.get(f"/api/leads/{lead_id}", headers=other_h)).status_code == 404


async def test_patch_writes_timeline_and_checks_owner(client, db):
    org, user, h = await _org(db)
    _, stranger, _ = await _org(db)
    lead_id = (await client.post("/api/leads", json={"phone": "98123 45678", "name": "Asha"}, headers=h)).json()["id"]

    r = await client.patch(f"/api/leads/{lead_id}", json={
        "status": "qualified", "owner_id": str(user.id), "custom_fields": {"budget": "5L"},
        "meeting_status": "scheduled", "meeting_at_text": "Fri 11am",
    }, headers=h)
    assert r.status_code == 200
    out = r.json()
    assert out["phone"] == PHONE and out["status"] == "qualified" and out["owner_name"] == "Priya"
    assert out["custom_fields"] == {"budget": "5L"}
    assert (await client.get("/api/leads?owner=me", headers=h)).json()["total"] == 1

    bad = await client.patch(f"/api/leads/{lead_id}", json={"owner_id": str(stranger.id)}, headers=h)
    assert bad.status_code == 422 or 400 <= bad.status_code < 500

    await client.post(f"/api/leads/{lead_id}/notes", json={"text": "Call after Diwali"}, headers=h)
    detail = (await client.get(f"/api/leads/{lead_id}", headers=h)).json()
    types = [a["type"] for a in detail["activities"]]
    assert {"note", "status_change", "meeting", "edit"} <= set(types)
    note = next(a for a in detail["activities"] if a["type"] == "note")
    assert note["payload"]["text"] == "Call after Diwali" and note["user_name"] == "Priya"


async def test_create_rejects_duplicate_and_bad_phone(client, db):
    _, _, h = await _org(db)
    assert (await client.post("/api/leads", json={"phone": PHONE}, headers=h)).status_code == 201
    assert (await client.post("/api/leads", json={"phone": "09812345678"}, headers=h)).status_code == 409
    assert 400 <= (await client.post("/api/leads", json={"phone": "abcde"}, headers=h)).status_code < 500


async def test_deleted_lead_disappears_and_returns_when_called(client, db):
    org, _, h = await _org(db)
    await _report(client, (await _campaign_call(db, org)).id)
    lead = await _lead(db, org)
    assert (await client.delete(f"/api/leads/{lead.id}", headers=h)).status_code == 204
    assert (await client.get("/api/leads", headers=h)).json()["total"] == 0
    await _report(client, (await _campaign_call(db, org)).id)
    assert (await client.get("/api/leads", headers=h)).json()["total"] == 1


async def test_import_creates_and_updates(client, db):
    _, _, h = await _org(db)
    await client.post("/api/leads", json={"phone": PHONE, "name": "Old"}, headers=h)
    data = "name,phone,email,city\nAsha,9812345678,a@x.in,Pune\nRavi,98000-00001,,Delhi\n"
    r = await client.post("/api/leads/import", files={"file": ("l.csv", data, "text/csv")}, headers=h)
    assert r.json() == {"created": 1, "updated": 1}
    items = {i["phone"]: i for i in (await client.get("/api/leads", headers=h)).json()["items"]}
    assert items[PHONE]["name"] == "Asha" and items[PHONE]["email"] == "a@x.in"
    assert items[PHONE]["custom_fields"]["city"] == "Pune"
    assert items["+919800000001"]["name"] == "Ravi"


async def test_export_csv_guards_formulas(client, db):
    _, _, h = await _org(db)
    await client.post("/api/leads", json={"phone": PHONE, "name": "=HYPERLINK(\"x\")"}, headers=h)
    r = await client.get("/api/leads/export.csv", headers=h)
    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[0][:2] == ["Phone", "Name"] and rows[1][0] == PHONE and rows[1][1].startswith("'=")


async def test_email_send_success_and_failure_are_recorded(client, db):
    from app.core.crypto import encrypt_value
    from app.core.email_sender import EmailSendError

    org, user, h = await _org(db)
    lead_id = (await client.post("/api/leads", json={"phone": PHONE, "name": "Asha", "email": "a@x.in"}, headers=h)).json()["id"]
    body = {"subject": "Hi {name}", "body": "Prices attached, {name}."}

    # No mail server saved for this org yet.
    assert (await client.get("/api/leads/meta", headers=h)).json()["email_enabled"] is False
    assert 400 <= (await client.post(f"/api/leads/{lead_id}/email", json=body, headers=h)).status_code < 500

    org.smtp_host, org.smtp_port, org.smtp_security = "smtp.acme.in", 587, "starttls"
    org.smtp_username, org.smtp_password, org.smtp_from_email = "sales@acme.in", encrypt_value("pw"), "sales@acme.in"
    await db.commit()
    assert (await client.get("/api/leads/meta", headers=h)).json()["email_enabled"] is True

    with patch("app.api.leads.send_email", new=AsyncMock(return_value="<msg_1@acme.in>")) as send:
        r = await client.post(f"/api/leads/{lead_id}/email", json=body, headers=h)
    assert r.json()["ok"] is True
    cfg = send.await_args.args[0]
    assert (cfg.host, cfg.password, cfg.from_email) == ("smtp.acme.in", "pw", "sales@acme.in")  # this org's own server
    kw = send.await_args.kwargs
    assert kw["subject"] == "Hi Asha" and kw["to"] == "a@x.in"
    assert (await client.get(f"/api/leads/{lead_id}", headers=h)).json()["email_status"] == "sent"

    with patch("app.api.leads.send_email", new=AsyncMock(side_effect=EmailSendError("refused"))):
        r = await client.post(f"/api/leads/{lead_id}/email", json=body, headers=h)
    assert r.json() == {"ok": False, "detail": "refused"}
    detail = (await client.get(f"/api/leads/{lead_id}", headers=h)).json()
    assert detail["email_status"] == "failed"
    assert [a["payload"]["ok"] for a in detail["activities"] if a["type"] == "email"] == [False, True]
