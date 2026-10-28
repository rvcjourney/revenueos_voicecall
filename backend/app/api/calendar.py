"""
app/api/calendar.py — Google Calendar per agent.

- /agents/{id}…: connect / settings / disconnect (Agent editor → Calendar tab).
- /google/callback: where Google sends the admin back after signing in.
- /calls/{id}/slots and /calls/{id}/book: called by the voice agent mid-call
  (signed like agent-report). They always answer 200 with a "status" the
  agent can read out, so a Google hiccup never breaks the call.
"""
from __future__ import annotations

import html
import re
from datetime import date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import jwt as pyjwt
import structlog
from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agents import _editable_agent
from app.config import settings
from app.core import google_calendar as gcal
from app.core.crypto import decrypt_value, encrypt_value
from app.core.deps import TokenPayload, get_current_user, require_agent_webhook_signature
from app.core.exceptions import NotFoundError, ValidationError as AppValidationError
from app.database import get_db
from app.models.agent import AgentTemplate
from app.models.call import Call
from app.models.campaign import CampaignContact
from app.models.lead import Lead
from app.services.brochure import agent_for_call

log = structlog.get_logger(__name__)
router = APIRouter()

_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", re.IGNORECASE)
_SEARCH_DAYS = 14  # how far ahead the agent looks for a free day


# ── admin side ───────────────────────────────────────────────────────────────

class CalendarSettings(BaseModel):
    duration_minutes: int = Field(30, ge=15, le=240)
    day_start: str = Field("10:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    day_end: str = Field("19:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    days: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4, 5])
    timezone: str = "Asia/Kolkata"

    @field_validator("days")
    @classmethod
    def _days(cls, v: list[int]) -> list[int]:
        if not v or any(d not in range(7) for d in v):
            raise ValueError("Pick at least one working day")
        return sorted(set(v))

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except Exception as exc:
            raise ValueError("Unknown timezone") from exc
        return v


class CalendarOut(BaseModel):
    available: bool  # Google sign-in is set up on this server
    connected: bool
    email: str | None
    settings: CalendarSettings


def _out(agent: AgentTemplate) -> CalendarOut:
    return CalendarOut(
        available=gcal.configured(), connected=bool(agent.gcal_refresh_token),
        email=agent.gcal_email, settings=CalendarSettings(**gcal.merged_settings(agent.gcal_settings)),
    )


@router.get("/agents/{agent_id}", response_model=CalendarOut)
async def get_calendar(agent_id: UUID, token: TokenPayload = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    agent = await db.get(AgentTemplate, agent_id)
    if not agent or agent.org_id != token.org_id or agent.deleted_at:
        raise NotFoundError("Agent template not found")
    return _out(agent)


@router.post("/agents/{agent_id}/connect")
async def connect_calendar(agent_id: UUID, token: TokenPayload = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The Google sign-in URL; the browser opens it in a new tab."""
    agent = await _editable_agent(db, agent_id, token)
    if not gcal.configured():
        raise AppValidationError("Google Calendar isn't set up on this server yet", errors=[])
    state = pyjwt.encode({
        "type": "gcal_state", "agent_id": str(agent.id), "org_id": str(token.org_id),
        "exp": gcal.utcnow() + timedelta(minutes=15),
    }, settings.SECRET_KEY, algorithm="HS256")
    return {"url": gcal.auth_url(state)}


@router.put("/agents/{agent_id}", response_model=CalendarOut)
async def save_calendar_settings(
    agent_id: UUID, body: CalendarSettings,
    token: TokenPayload = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    agent = await _editable_agent(db, agent_id, token)
    if body.day_start >= body.day_end:
        raise AppValidationError("The working day must end after it starts", errors=[])
    agent.gcal_settings = body.model_dump()
    await db.commit()
    return _out(agent)


@router.delete("/agents/{agent_id}", response_model=CalendarOut)
async def disconnect_calendar(agent_id: UUID, token: TokenPayload = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    agent = await _editable_agent(db, agent_id, token)
    if agent.gcal_refresh_token:
        await gcal.revoke(decrypt_value(agent.gcal_refresh_token))
    agent.gcal_refresh_token = agent.gcal_email = None
    await db.commit()
    return _out(agent)


def _page(title: str, text: str) -> HTMLResponse:
    return HTMLResponse(
        f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
        f"<title>{html.escape(title)}</title>"
        f"<body style='font-family:system-ui;max-width:28rem;margin:4rem auto;padding:0 1rem'>"
        f"<h2>{html.escape(title)}</h2><p>{html.escape(text)}</p>"
        f"<p>You can close this tab and go back to the agent.</p></body>"
    )


@router.get("/google/callback", include_in_schema=False)
async def google_callback(
    state: str = "", code: str = "", error: str = "", db: AsyncSession = Depends(get_db),
):
    try:
        claims = pyjwt.decode(state, settings.SECRET_KEY, algorithms=["HS256"])
    except pyjwt.InvalidTokenError:
        return _page("Link expired", "This sign-in link expired. Click “Connect Google Calendar” again.")
    if claims.get("type") != "gcal_state":
        return _page("Link expired", "This sign-in link expired. Click “Connect Google Calendar” again.")
    if error or not code:
        return _page("Not connected", "Google sign-in was cancelled.")
    agent = await db.get(AgentTemplate, UUID(claims["agent_id"]))
    if not agent or str(agent.org_id) != claims["org_id"] or agent.deleted_at:
        return _page("Not connected", "That agent no longer exists.")
    try:
        refresh_token, email = await gcal.exchange_code(code)
    except gcal.CalendarError as exc:
        return _page("Not connected", str(exc))
    agent.gcal_refresh_token, agent.gcal_email = encrypt_value(refresh_token), email or None
    await db.commit()
    log.info("gcal_connected", agent_id=str(agent.id))
    return _page("Google Calendar connected", f"{agent.name} will now book meetings into {email or 'this calendar'}.")


# ── agent side (mid-call) ────────────────────────────────────────────────────

async def _call_agent(db: AsyncSession, call_id: UUID) -> tuple[Call | None, AgentTemplate | None]:
    call = await db.get(Call, call_id)
    agent = await agent_for_call(db, call) if call else None
    return call, (agent if agent and agent.gcal_refresh_token else None)


async def _free_day(refresh_token: str, cfg: dict, wanted: date, now: datetime) -> tuple[date, list[datetime]] | None:
    """The wanted day's free slots, or the first later day that has some."""
    tz = ZoneInfo(cfg["timezone"])
    first = max(wanted, now.astimezone(tz).date())
    window_start = datetime.combine(first, datetime.min.time(), tz)
    busy = await gcal.busy_times(refresh_token, window_start, window_start + timedelta(days=_SEARCH_DAYS), cfg["timezone"])
    for i in range(_SEARCH_DAYS):
        day = first + timedelta(days=i)
        if slots := gcal.free_slots(day, busy, cfg, now):
            return day, slots
    return None


def _offer(day: date, slots: list[datetime], cfg: dict) -> dict:
    # Spread a handful across the day instead of reading out 16 half-hours.
    picks = slots if len(slots) <= 6 else [slots[round(i * (len(slots) - 1) / 5)] for i in range(6)]
    tz = ZoneInfo(cfg["timezone"])
    return {
        "date": day.isoformat(),
        "day": day.strftime("%A %d %B").replace(" 0", " "),
        "free_times": [s.astimezone(tz).strftime("%H:%M") for s in picks],
        "spoken": [gcal.spoken(s, cfg["timezone"]) for s in picks],
        "meeting_minutes": cfg["duration_minutes"],
    }


class SlotsIn(BaseModel):
    date: str = ""  # YYYY-MM-DD; blank = soonest


@router.post("/calls/{call_id}/slots", dependencies=[Depends(require_agent_webhook_signature)])
async def calendar_slots(call_id: UUID, body: SlotsIn, db: AsyncSession = Depends(get_db)):
    call, agent = await _call_agent(db, call_id)
    if agent is None:
        return {"status": "unavailable", "message": "No calendar is connected. Note the time the customer prefers instead."}
    cfg = gcal.merged_settings(agent.gcal_settings)
    now = gcal.utcnow()
    try:
        wanted = date.fromisoformat(body.date) if body.date else now.date()
    except ValueError:
        wanted = now.date()
    try:
        found = await _free_day(decrypt_value(agent.gcal_refresh_token), cfg, wanted, now)
    except gcal.CalendarError as exc:
        log.warning("gcal_slots_failed", call_id=str(call_id), error=str(exc))
        return {"status": "error", "message": "The calendar can't be checked right now. Note the time the customer prefers instead."}
    if found is None:
        return {"status": "none", "message": f"No free slot in the next {_SEARCH_DAYS} days."}
    day, slots = found
    note = "" if day == wanted else f"Nothing free on {wanted.isoformat()}; this is the next free day."
    return {"status": "ok", "note": note, **_offer(day, slots, cfg)}


class BookIn(BaseModel):
    date_time: str  # "YYYY-MM-DD HH:MM", the calendar's local time
    prospect_name: str = ""
    company: str = ""
    next_step_type: str = ""
    attendees: str = ""
    email: str = ""
    event_id: str = ""  # set when moving a meeting already booked on this call


@router.post("/calls/{call_id}/book", dependencies=[Depends(require_agent_webhook_signature)])
async def calendar_book(call_id: UUID, body: BookIn, db: AsyncSession = Depends(get_db)):
    call, agent = await _call_agent(db, call_id)
    if call is None or agent is None:
        return {"status": "unavailable", "message": "No calendar is connected."}
    cfg = gcal.merged_settings(agent.gcal_settings)
    tz = ZoneInfo(cfg["timezone"])
    try:
        start = datetime.strptime(body.date_time.strip()[:16].replace("T", " "), "%Y-%m-%d %H:%M").replace(tzinfo=tz)
    except ValueError:
        return {"status": "invalid", "message": "Pass date_time as YYYY-MM-DD HH:MM (24-hour)."}
    refresh_token = decrypt_value(agent.gcal_refresh_token)
    now = gcal.utcnow()
    minutes = int(cfg["duration_minutes"])
    try:
        # Moving our own meeting: its current slot isn't a clash.
        busy = await gcal.busy_times(refresh_token, start - timedelta(hours=12), start + timedelta(hours=12),
                                     cfg["timezone"], ignore_event_id=body.event_id)
        if not gcal.is_free(start, busy, cfg, now):
            found = await _free_day(refresh_token, cfg, start.date(), now)
            return {
                "status": "unavailable",
                "message": "That time is not free or is outside working hours. Offer these instead.",
                **(_offer(*found, cfg) if found else {}),
            }

        contact = await db.get(CampaignContact, call.contact_id) if call.contact_id else None
        lead = (await db.execute(
            select(Lead).where(Lead.org_id == call.org_id, Lead.phone == call.phone_number)
        )).scalar_one_or_none()
        spoken_email = body.email.strip().lower().replace(" ", "")
        to = next((e for e in (spoken_email, lead.email if lead else "", contact.email if contact else "")
                   if e and _EMAIL_RE.fullmatch(e)), "")
        who = body.prospect_name or (lead.name if lead else "") or (contact.name if contact else "") or call.phone_number
        title = f"{(body.next_step_type or 'Meeting').strip().title()} with {who}"
        description = "\n".join(filter(None, [
            f"Booked by the AI agent “{agent.name}” on a call to {call.phone_number}.",
            f"Company: {body.company}" if body.company else "",
            f"Others to join: {body.attendees}" if body.attendees else "",
        ]))
        booked = await gcal.create_or_move_event(
            refresh_token, start=start, minutes=minutes, summary=title, description=description,
            attendee_email=to, event_id=body.event_id,
        )
    except gcal.CalendarError as exc:
        log.warning("gcal_book_failed", call_id=str(call_id), error=str(exc))
        return {"status": "error", "message": "The calendar can't be reached right now."}
    log.info("gcal_booked", call_id=str(call_id), invited=bool(to), moved=bool(body.event_id))
    return {
        "status": "confirmed",
        "reference": f"NS-{booked.event_id[:6].upper()}",
        "date_time": gcal.spoken(start, cfg["timezone"]),
        "invite_sent_to": to,
        "event_id": booked.event_id,
        "calendar_link": booked.html_link,
        "meet_link": booked.meet_link,
    }
