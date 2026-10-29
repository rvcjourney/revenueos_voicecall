"""Leads management: source / priority / follow-up auto-fill, filters + summary, bulk actions."""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.models.campaign import Campaign, CampaignContact, CampaignStatus
from app.models.lead import LeadActivity

from tests.test_leads import PHONE, _campaign_call, _lead, _org, _report

IST = ZoneInfo("Asia/Kolkata")


# ── auto-fill from calls ─────────────────────────────────────────────────────

async def test_call_sets_source_priority_and_callback_follow_up(client, db):
    org, _, _ = await _org(db)
    call = await _campaign_call(db, org)
    await _report(client, call.id, outcome="callback_requested")
    lead = await _lead(db, org)
    assert lead.source == "campaign" and lead.source_campaign_id == call.campaign_id
    follow = lead.next_follow_up_at.astimezone(IST)
    assert follow.hour == 10 and follow.date() == (call.started_at or datetime.now(IST)).astimezone(IST).date() + timedelta(days=1)

    call2 = await _campaign_call(db, org)
    await _report(client, call2.id, outcome="interested")
    lead = await _lead(db, org)
    assert lead.priority == "hot"
    assert lead.source_campaign_id == call.campaign_id  # the first campaign stays the source


async def test_manual_priority_is_never_overwritten_by_calls(client, db):
    org, _, h = await _org(db)
    call = await _campaign_call(db, org)
    await _report(client, call.id, outcome="interested")
    lead = await _lead(db, org)
    assert (await client.patch(f"/api/leads/{lead.id}", json={"priority": "warm"}, headers=h)).status_code == 200
    call2 = await _campaign_call(db, org)
    await _report(client, call2.id, outcome="not_interested")
    assert (await _lead(db, org)).priority == "warm"


async def test_manual_and_import_sources(client, db):
    org, _, h = await _org(db)
    r = await client.post("/api/leads", json={"phone": "+919800000001", "name": "M"}, headers=h)
    assert r.json()["source"] == "manual"
    data = "name,phone\nIra,9800000002\n"
    r = await client.post("/api/leads/import", files={"file": ("l.csv", data, "text/csv")}, headers=h)
    assert r.json() == {"created": 1, "updated": 0}, r.text
    assert (await _lead(db, org, "+919800000002")).source == "import"


# ── list filters + summary ───────────────────────────────────────────────────

async def test_follow_up_filters_and_summary(client, db):
    org, _, h = await _org(db)
    now = datetime.now(IST)
    for i, when in enumerate([now - timedelta(days=2), now.replace(hour=23, minute=0), now + timedelta(days=3), None]):
        r = await client.post("/api/leads", json={"phone": f"+91980000010{i}"}, headers=h)
        patch = {"next_follow_up_at": when.isoformat() if when else None, "note": f"n{i}"}
        if i == 0:
            patch["priority"] = "hot"
        await client.patch(f"/api/leads/{r.json()['id']}", json=patch, headers=h)

    body = (await client.get("/api/leads", headers=h)).json()
    assert body["summary"] == {"total": 4, "due_today": 1, "overdue": 1, "hot": 1}
    assert {i["note"] for i in body["items"]} == {"n0", "n1", "n2", "n3"}
    for follow_up, phone in (("overdue", "+919800000100"), ("due_today", "+919800000101"), ("upcoming", "+919800000102")):
        items = (await client.get("/api/leads", params={"follow_up": follow_up}, headers=h)).json()["items"]
        assert [i["phone"] for i in items] == [phone]
    assert len((await client.get("/api/leads", params={"priority": "hot"}, headers=h)).json()["items"]) == 1


async def test_date_range_and_campaign_filter(client, db):
    org, _, h = await _org(db)
    call = await _campaign_call(db, org)
    await _report(client, call.id, outcome="interested")
    await client.post("/api/leads", json={"phone": "+919800000200"}, headers=h)
    today = datetime.now(IST).date()
    by_campaign = (await client.get("/api/leads", params={"campaign_id": str(call.campaign_id)}, headers=h)).json()
    assert [i["phone"] for i in by_campaign["items"]] == [PHONE]
    assert by_campaign["items"][0]["source_campaign_name"] == "C"
    future = (await client.get("/api/leads", params={"date_from": str(today + timedelta(days=1))}, headers=h)).json()
    assert future["total"] == 0
    assert (await client.get("/api/leads", params={"date_from": str(today), "date_to": str(today)}, headers=h)).json()["total"] == 2


# ── bulk ─────────────────────────────────────────────────────────────────────

async def _two_leads(client, h):
    ids = []
    for i in range(2):
        ids.append((await client.post("/api/leads", json={"phone": f"+91980000030{i}", "name": f"L{i}"}, headers=h)).json()["id"])
    return ids


async def test_bulk_actions(client, db):
    org, user, h = await _org(db)
    ids = await _two_leads(client, h)

    async def bulk(action, value):
        r = await client.post("/api/leads/bulk", json={"ids": ids, "action": action, "value": value}, headers=h)
        assert r.status_code == 200, r.text
        return r.json()

    assert (await bulk("assign", str(user.id)))["updated"] == 2
    await bulk("status", "qualified")
    await bulk("priority", "cold")
    await bulk("follow_up", "2026-11-05T11:00")
    await bulk("tag", "VIP")
    items = (await client.get("/api/leads", headers=h)).json()["items"]
    for it in items:
        assert it["owner_id"] == str(user.id) and it["status"] == "qualified" and it["priority"] == "cold"
        assert it["tags"] == ["VIP"]
        assert datetime.fromisoformat(it["next_follow_up_at"]) == datetime(2026, 11, 5, 11, 0, tzinfo=IST)  # no tz = India time
    lead = await _lead(db, org, "+919800000300")
    assert lead.priority_by_user is True
    assert (await db.scalar(select(LeadActivity.id).where(LeadActivity.lead_id == lead.id, LeadActivity.type == "status_change")))

    await bulk("delete", None)
    assert (await client.get("/api/leads", headers=h)).json()["total"] == 0


async def test_bulk_is_org_scoped_and_validated(client, db):
    _, _, h1 = await _org(db)
    _, _, h2 = await _org(db)
    ids = await _two_leads(client, h1)
    r = await client.post("/api/leads/bulk", json={"ids": ids, "action": "delete"}, headers=h2)
    assert r.json()["updated"] == 0
    assert (await client.get("/api/leads", headers=h1)).json()["total"] == 2
    bad = await client.post("/api/leads/bulk", json={"ids": ids, "action": "status", "value": "nope"}, headers=h1)
    assert bad.status_code == 422


async def test_add_to_campaign_skips_dnc_and_duplicates(client, db):
    org, _, h = await _org(db)
    ids = await _two_leads(client, h)
    await client.patch(f"/api/leads/{ids[1]}", json={"status": "do_not_call"}, headers=h)
    camp = Campaign(org_id=org.id, name="Again", status=CampaignStatus.DRAFT, total_contacts=0)
    running = Campaign(org_id=org.id, name="Live", status=CampaignStatus.RUNNING)
    db.add_all([camp, running])
    await db.commit()

    body = {"ids": ids, "action": "add_to_campaign", "value": str(camp.id)}
    r = (await client.post("/api/leads/bulk", json=body, headers=h)).json()
    assert r == {"added": 1, "skipped": 1, "campaign": "Again"}
    r2 = (await client.post("/api/leads/bulk", json=body, headers=h)).json()
    assert r2["added"] == 0  # already in that campaign
    contacts = (await db.execute(select(CampaignContact).where(CampaignContact.campaign_id == camp.id))).scalars().all()
    assert [c.phone for c in contacts] == ["+919800000300"] and contacts[0].status == "pending"
    await db.refresh(camp)
    assert camp.total_contacts == 1

    rr = await client.post("/api/leads/bulk", json={**body, "value": str(running.id)}, headers=h)
    assert rr.status_code == 422
    meta = (await client.get("/api/leads/meta", headers=h)).json()
    assert {c["name"] for c in meta["campaigns"]} == {"Again", "Live"}


async def test_export_selected_only(client, db):
    _, _, h = await _org(db)
    ids = await _two_leads(client, h)
    r = await client.get("/api/leads/export.csv", params={"ids": [ids[0]]}, headers=h)
    lines = r.text.strip().splitlines()
    assert len(lines) == 2 and "Next follow-up" in lines[0] and "+919800000300" in lines[1]


async def test_lead_out_has_new_fields(client, db):
    _, _, h = await _org(db)
    r = (await client.post("/api/leads", json={"phone": "+919800000400"}, headers=h)).json()
    for key in ("priority", "next_follow_up_at", "note", "source", "source_campaign_id", "source_campaign_name"):
        assert key in r
