"""Google Calendar per agent (app/core/google_calendar.py, app/api/calendar.py).
Google itself is mocked; these check the slot maths, the OAuth state, and what
the agent gets back mid-call."""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from app.config import settings
from app.core import google_calendar as gcal
from app.core.crypto import decrypt_value, encrypt_value
from app.core.security import create_access_token, hash_password, sign_webhook_payload
from app.models.agent import AgentTemplate
from app.models.call import Call, CallDirection, CallStatus
from app.models.campaign import Campaign, CampaignContact, ContactStatus
from app.models.user import Organization, User, UserRole

IST = ZoneInfo("Asia/Kolkata")
CFG = gcal.merged_settings({})
PHONE = "+919812345678"
THU = date(2026, 10, 29)  # a Thursday
NOW = datetime(2026, 10, 28, 9, 0, tzinfo=IST)


def _at(day, hh, mm=0):
    return datetime(day.year, day.month, day.day, hh, mm, tzinfo=IST)


# ── slot maths ───────────────────────────────────────────────────────────────

def test_free_slots_skip_busy_and_respect_hours():
    busy = [(_at(THU, 11), _at(THU, 12))]
    slots = gcal.free_slots(THU, busy, CFG, NOW)
    times = [s.strftime("%H:%M") for s in slots]
    assert times[0] == "10:00" and times[-1] == "18:30"  # 30-min meeting must end by 19:00
    assert "10:30" in times and "11:00" not in times and "11:30" not in times and "12:00" in times


def test_sunday_past_and_too_soon_are_not_free():
    sunday = date(2026, 11, 1)
    assert gcal.free_slots(sunday, [], CFG, NOW) == []
    today = NOW.date()
    assert not gcal.is_free(_at(today, 9, 30), [], CFG, NOW)   # before opening, and < 1h notice
    assert not gcal.is_free(_at(today, 10, 0), [], CFG, NOW + timedelta(minutes=30))  # only 30 min notice
    assert gcal.is_free(_at(today, 10, 30), [], CFG, NOW)
    assert not gcal.is_free(_at(THU, 18, 45), [], CFG, NOW)    # would end 19:15


def test_spoken_time_is_readable():
    assert gcal.spoken(_at(THU, 15), "Asia/Kolkata") == "Thursday 29 October, 3:00 PM"


# ── setup ────────────────────────────────────────────────────────────────────

async def _setup(db, *, connected=True, contact_email="ravi@acme.in"):
    org = Organization(name=f"Org {uuid.uuid4().hex[:6]}", slug=f"org-{uuid.uuid4().hex[:8]}", is_active=True)
    db.add(org)
    await db.flush()
    user = User(org_id=org.id, email=f"a-{uuid.uuid4().hex[:6]}@acme.in", hashed_password=hash_password("pw-123456"),
                full_name="Priya", role=UserRole.ADMIN, is_active=True)
    agent = AgentTemplate(org_id=org.id, name="Ananya")
    if connected:
        agent.gcal_refresh_token, agent.gcal_email = encrypt_value("refresh-1"), "sales@acme.in"
    db.add_all([user, agent])
    await db.flush()
    camp = Campaign(org_id=org.id, agent_template_id=agent.id, name="C")
    db.add(camp)
    await db.flush()
    contact = CampaignContact(campaign_id=camp.id, org_id=org.id, name="Ravi", phone=PHONE, company="Acme",
                              email=contact_email, status=ContactStatus.DIALING)
    db.add(contact)
    await db.flush()
    call = Call(org_id=org.id, campaign_id=camp.id, contact_id=contact.id, livekit_room_name=f"r-{uuid.uuid4().hex}",
                phone_number=PHONE, direction=CallDirection.OUTBOUND, status=CallStatus.COMPLETED)
    db.add(call)
    await db.commit()
    headers = {"Authorization": f"Bearer {create_access_token(str(user.id), str(org.id), user.role)}"}
    return agent, call, headers


def _google_on(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "csecret")
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "https://api.quickhowl.test")


async def _agent_post(client, path, payload, *, signed=True):
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if signed:
        headers["X-Webhook-Signature"] = sign_webhook_payload(body)
    return await client.post(path, content=body, headers=headers)


# ── connect / callback / settings ────────────────────────────────────────────

async def test_connect_needs_server_setup(client, db, monkeypatch):
    agent, _, h = await _setup(db, connected=False)
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "")
    assert (await client.get(f"/api/calendar/agents/{agent.id}", headers=h)).json()["available"] is False
    assert (await client.post(f"/api/calendar/agents/{agent.id}/connect", headers=h)).status_code == 422


async def test_connect_then_callback_stores_encrypted_token(client, db, monkeypatch):
    _google_on(monkeypatch)
    agent, _, h = await _setup(db, connected=False)
    url = (await client.post(f"/api/calendar/agents/{agent.id}/connect", headers=h)).json()["url"]
    q = parse_qs(urlparse(url).query)
    assert q["redirect_uri"] == ["https://api.quickhowl.test/api/calendar/google/callback"]
    assert "calendar.events" in q["scope"][0] and q["access_type"] == ["offline"]

    with patch.object(gcal, "exchange_code", AsyncMock(return_value=("refresh-xyz", "sales@acme.in"))):
        r = await client.get("/api/calendar/google/callback", params={"state": q["state"][0], "code": "c"})
    assert r.status_code == 200 and "connected" in r.text
    await db.refresh(agent)
    assert agent.gcal_email == "sales@acme.in" and decrypt_value(agent.gcal_refresh_token) == "refresh-xyz"

    status = (await client.get(f"/api/calendar/agents/{agent.id}", headers=h)).json()
    assert status["connected"] is True and status["settings"]["duration_minutes"] == 30


async def test_callback_rejects_forged_or_access_token_state(client, db, monkeypatch):
    _google_on(monkeypatch)
    agent, _, h = await _setup(db, connected=False)
    access = h["Authorization"].split()[1]
    for state in ("garbage", access):
        r = await client.get("/api/calendar/google/callback", params={"state": state, "code": "c"})
        assert "expired" in r.text
    await db.refresh(agent)
    assert agent.gcal_refresh_token is None


async def test_settings_validated_and_disconnect_revokes(client, db):
    agent, _, h = await _setup(db)
    bad = {"duration_minutes": 30, "day_start": "19:00", "day_end": "10:00", "days": [0], "timezone": "Asia/Kolkata"}
    assert (await client.put(f"/api/calendar/agents/{agent.id}", json=bad, headers=h)).status_code == 422
    good = {**bad, "day_start": "09:30", "day_end": "18:00", "duration_minutes": 45}
    assert (await client.put(f"/api/calendar/agents/{agent.id}", json=good, headers=h)).json()["settings"]["day_start"] == "09:30"
    with patch.object(gcal, "revoke", AsyncMock()) as revoke:
        r = await client.delete(f"/api/calendar/agents/{agent.id}", headers=h)
    revoke.assert_awaited_once_with("refresh-1")
    assert r.json()["connected"] is False


# ── mid-call ─────────────────────────────────────────────────────────────────

async def test_agent_endpoints_need_the_signature(client, db):
    _, call, _ = await _setup(db)
    r = await _agent_post(client, f"/api/calendar/calls/{call.id}/slots", {"date": ""}, signed=False)
    assert r.status_code == 401


async def test_slots_moves_to_next_free_day(client, db):
    _, call, _ = await _setup(db)
    # Thursday is fully booked → Friday's times come back, with a note.
    busy = [(_at(THU, 0), _at(THU, 23, 59))]
    with patch.object(gcal, "busy_times", AsyncMock(return_value=busy)), patch.object(gcal, "utcnow", return_value=NOW):
        r = (await _agent_post(client, f"/api/calendar/calls/{call.id}/slots", {"date": THU.isoformat()})).json()
    assert r["status"] == "ok" and r["date"] == "2026-10-30" and r["note"]
    assert 1 <= len(r["free_times"]) <= 6 and r["free_times"][0] == "10:00"


async def test_slots_without_calendar_tells_agent_to_note_time(client, db):
    _, call, _ = await _setup(db, connected=False)
    r = (await _agent_post(client, f"/api/calendar/calls/{call.id}/slots", {})).json()
    assert r["status"] == "unavailable"


async def test_book_busy_slot_offers_alternatives(client, db):
    _, call, _ = await _setup(db)
    busy = [(_at(THU, 15), _at(THU, 16))]
    create = AsyncMock()
    with patch.object(gcal, "busy_times", AsyncMock(return_value=busy)), patch.object(gcal, "utcnow", return_value=NOW), \
            patch.object(gcal, "create_or_move_event", create):
        r = (await _agent_post(client, f"/api/calendar/calls/{call.id}/book",
                               {"date_time": "2026-10-29 15:00", "prospect_name": "Ravi"})).json()
    assert r["status"] == "unavailable" and "15:00" not in r["free_times"]
    create.assert_not_awaited()


async def test_book_creates_event_and_invites_contact_email(client, db):
    _, call, _ = await _setup(db)
    booked = gcal.Booked(event_id="abcdef123", html_link="https://cal/e", meet_link="https://meet.google.com/x")
    create = AsyncMock(return_value=booked)
    with patch.object(gcal, "busy_times", AsyncMock(return_value=[])), patch.object(gcal, "utcnow", return_value=NOW), \
            patch.object(gcal, "create_or_move_event", create):
        r = (await _agent_post(client, f"/api/calendar/calls/{call.id}/book", {
            "date_time": "2026-10-29 15:00", "prospect_name": "Ravi", "company": "Acme", "next_step_type": "demo",
        })).json()
    assert r["status"] == "confirmed" and r["meet_link"] == "https://meet.google.com/x"
    assert r["reference"] == "NS-ABCDEF" and r["invite_sent_to"] == "ravi@acme.in"
    kw = create.await_args.kwargs
    assert kw["start"] == _at(THU, 15) and kw["minutes"] == 30 and kw["attendee_email"] == "ravi@acme.in"
    assert kw["summary"] == "Demo with Ravi" and kw["event_id"] == ""


async def test_book_spoken_email_wins_and_bad_format_is_rejected(client, db):
    _, call, _ = await _setup(db, contact_email=None)
    create = AsyncMock(return_value=gcal.Booked("e1", "", ""))
    with patch.object(gcal, "busy_times", AsyncMock(return_value=[])), patch.object(gcal, "utcnow", return_value=NOW), \
            patch.object(gcal, "create_or_move_event", create):
        bad = (await _agent_post(client, f"/api/calendar/calls/{call.id}/book", {"date_time": "Thursday 3pm"})).json()
        assert bad["status"] == "invalid"
        r = (await _agent_post(client, f"/api/calendar/calls/{call.id}/book",
                               {"date_time": "2026-10-29 15:00", "email": "Ravi.K @ Gmail.com"})).json()
    assert r["invite_sent_to"] == "ravi.k@gmail.com"


async def test_test_call_without_campaign_uses_the_agent_it_names(client, db):
    agent, call, _ = await _setup(db)
    call.campaign_id = None
    other_agent, _, _ = await _setup(db)  # another org's agent must not be usable
    await db.commit()
    with patch.object(gcal, "busy_times", AsyncMock(return_value=[])), patch.object(gcal, "utcnow", return_value=NOW):
        mine = (await _agent_post(client, f"/api/calendar/calls/{call.id}/slots", {"agent_id": str(agent.id)})).json()
        theirs = (await _agent_post(client, f"/api/calendar/calls/{call.id}/slots", {"agent_id": str(other_agent.id)})).json()
        bogus = (await _agent_post(client, f"/api/calendar/calls/{call.id}/slots", {"agent_id": "not-a-uuid"})).json()
    assert mine["status"] == "ok"
    assert theirs["status"] == "unavailable" and bogus["status"] == "unavailable"


def test_misheard_email_falls_back_to_the_one_on_file():
    from app.services.brochure import pick_email
    on_file = "chinmaypol8483@gmail.com"
    assert pick_email("chinmaypo8483@gmail.com", None, on_file) == on_file  # real case: STT dropped the "l"
    assert pick_email("rahul.k@outlook.com", on_file) == "rahul.k@outlook.com"  # really a different address
    assert pick_email("", on_file) == on_file
    assert pick_email("not an email", None) == ""


async def test_book_uses_file_email_when_spoken_one_is_a_near_miss(client, db):
    _, call, _ = await _setup(db, contact_email="chinmaypol8483@gmail.com")
    create = AsyncMock(return_value=gcal.Booked("e1", "", ""))
    with patch.object(gcal, "busy_times", AsyncMock(return_value=[])), patch.object(gcal, "utcnow", return_value=NOW), \
            patch.object(gcal, "create_or_move_event", create):
        r = (await _agent_post(client, f"/api/calendar/calls/{call.id}/book",
                               {"date_time": "2026-10-29 15:00", "email": "chinmaypo8483@gmail.com"})).json()
    assert r["invite_sent_to"] == "chinmaypol8483@gmail.com"


def test_disabled_calendar_api_gets_a_plain_reason():
    import httpx
    resp = httpx.Response(403, json={"error": {"code": 403, "message": "Google Calendar API has not been used in project 123 before or it is disabled.",
                                               "errors": [{"reason": "accessNotConfigured"}]}})
    assert "not enabled" in gcal._google_reason(resp)
    other = httpx.Response(403, json={"error": {"message": "Insufficient Permission", "errors": [{"reason": "insufficientPermissions"}]}})
    assert "insufficientPermissions" in gcal._google_reason(other)


async def test_google_failure_is_a_soft_error(client, db):
    _, call, _ = await _setup(db)
    with patch.object(gcal, "busy_times", AsyncMock(side_effect=gcal.CalendarError("revoked"))):
        r = await _agent_post(client, f"/api/calendar/calls/{call.id}/book", {"date_time": "2026-10-29 15:00"})
    assert r.status_code == 200 and r.json()["status"] == "error"


# ── Google responses → busy times ────────────────────────────────────────────

async def test_busy_times_skips_free_declined_and_ignored_events(monkeypatch):
    items = [
        {"id": "a", "start": {"dateTime": "2026-10-29T11:00:00+05:30"}, "end": {"dateTime": "2026-10-29T12:00:00+05:30"}},
        {"id": "b", "transparency": "transparent", "start": {"dateTime": "2026-10-29T13:00:00+05:30"},
         "end": {"dateTime": "2026-10-29T14:00:00+05:30"}},
        {"id": "c", "attendees": [{"self": True, "responseStatus": "declined"}],
         "start": {"dateTime": "2026-10-29T15:00:00+05:30"}, "end": {"dateTime": "2026-10-29T16:00:00+05:30"}},
        {"id": "d", "start": {"date": "2026-10-30"}, "end": {"date": "2026-10-31"}},
        {"id": "mine", "start": {"dateTime": "2026-10-29T17:00:00+05:30"}, "end": {"dateTime": "2026-10-29T17:30:00+05:30"}},
    ]
    import httpx
    real = httpx.AsyncClient
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"items": items}))
    monkeypatch.setattr(gcal.httpx, "AsyncClient", lambda **kw: real(transport=transport, **kw))
    monkeypatch.setattr(gcal, "_access_token", AsyncMock(return_value="at"))
    start = _at(THU, 0)
    busy = await gcal.busy_times("r", start, start + timedelta(days=3), "Asia/Kolkata", ignore_event_id="mine")
    assert busy == [
        (datetime(2026, 10, 29, 11, 0, tzinfo=timezone(timedelta(hours=5, minutes=30))),
         datetime(2026, 10, 29, 12, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))),
        (_at(date(2026, 10, 30), 0), _at(date(2026, 10, 31), 0)),
    ]
