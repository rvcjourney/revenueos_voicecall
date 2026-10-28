"""
app/core/google_calendar.py — an agent's own Google Calendar (OAuth + REST, via httpx).

Each agent can be linked to one Google account (Agent editor → Calendar tab).
During a call the agent asks the backend for free slots and books one
(app/api/calendar.py); the event gets a Google Meet link and Google emails
the invite to the customer. Only the refresh token is stored, Fernet-encrypted.
"""
from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx

from app.config import settings

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
# calendar.events covers both reading busy times and creating events: one scope to approve.
SCOPES = "openid email https://www.googleapis.com/auth/calendar.events"

DEFAULT_SETTINGS = {
    "duration_minutes": 30,
    "day_start": "10:00",
    "day_end": "19:00",
    "days": [0, 1, 2, 3, 4, 5],  # Monday=0 … Saturday=5
    "timezone": "Asia/Kolkata",
}
MIN_NOTICE = timedelta(hours=1)  # never offer a slot starting sooner than this


class CalendarError(Exception):
    """A Google call failed; the message is safe to show the user."""


def configured() -> bool:
    return bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET and settings.PUBLIC_BASE_URL)


def redirect_uri() -> str:
    return f"{settings.PUBLIC_BASE_URL.rstrip('/')}/api/calendar/google/callback"


def merged_settings(saved: dict | None) -> dict:
    return {**DEFAULT_SETTINGS, **(saved or {})}


def auth_url(state: str) -> str:
    return AUTH_URL + "?" + urlencode({
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "prompt": "consent",  # always hand back a refresh token, even on a reconnect
        "include_granted_scopes": "true",
        "state": state,
    })


async def _post_token(data: dict) -> dict:
    async with httpx.AsyncClient(timeout=15.0) as http:
        resp = await http.post(TOKEN_URL, data={
            "client_id": settings.GOOGLE_CLIENT_ID, "client_secret": settings.GOOGLE_CLIENT_SECRET, **data,
        })
    if resp.status_code != 200:
        if resp.status_code == 400 and "invalid_grant" in resp.text:
            raise CalendarError("Google access was revoked or expired. Reconnect the calendar on the agent.")
        raise CalendarError(f"Google sign-in failed ({resp.status_code})")
    return resp.json()


async def exchange_code(code: str) -> tuple[str, str]:
    """OAuth callback code → (refresh_token, google_email)."""
    tok = await _post_token({"code": code, "grant_type": "authorization_code", "redirect_uri": redirect_uri()})
    if "calendar.events" not in tok.get("scope", "") or not tok.get("refresh_token"):
        raise CalendarError("Calendar permission wasn't granted. Connect again and tick the calendar box.")
    # The id_token came straight from Google over TLS; we only read the email out of it.
    claims_b64 = tok.get("id_token", "..").split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(claims_b64 + "=" * (-len(claims_b64) % 4)) or b"{}")
    return tok["refresh_token"], str(claims.get("email") or "")


async def _access_token(refresh_token: str) -> str:
    return (await _post_token({"refresh_token": refresh_token, "grant_type": "refresh_token"}))["access_token"]


async def revoke(refresh_token: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as http:
            await http.post(REVOKE_URL, data={"token": refresh_token})
    except httpx.HTTPError:
        pass  # disconnecting locally still stops us using it


def _google_reason(resp: httpx.Response) -> str:
    """Google's own explanation, e.g. 'Calendar API has not been used in project … or it is disabled'."""
    try:
        err = resp.json().get("error", {})
        reason = (err.get("errors") or [{}])[0].get("reason", "")
        if reason == "accessNotConfigured" or "has not been used" in err.get("message", ""):
            return "the Google Calendar API is not enabled in the Google Cloud project (APIs & Services → Library)"
        return f"{resp.status_code} {reason} {err.get('message', '')}".strip()[:300]
    except ValueError:
        return str(resp.status_code)


# ── availability ──────────────────────────────────────────────────────────────

Busy = list[tuple[datetime, datetime]]


def _bounds(day: date, cfg: dict) -> tuple[datetime, datetime]:
    tz = ZoneInfo(cfg["timezone"])
    start, end = (time.fromisoformat(cfg[k]) for k in ("day_start", "day_end"))
    return datetime.combine(day, start, tz), datetime.combine(day, end, tz)


def is_free(start: datetime, busy: Busy, cfg: dict, now: datetime) -> bool:
    """Inside working hours on a working day, far enough ahead, and clashing with nothing."""
    end = start + timedelta(minutes=int(cfg["duration_minutes"]))
    local = start.astimezone(ZoneInfo(cfg["timezone"]))
    open_, close = _bounds(local.date(), cfg)
    return (
        local.weekday() in cfg["days"]
        and open_ <= start and end <= close
        and start >= now + MIN_NOTICE
        and not any(b_start < end and start < b_end for b_start, b_end in busy)
    )


def free_slots(day: date, busy: Busy, cfg: dict, now: datetime) -> list[datetime]:
    """Every free start time that day, on a half-hour grid."""
    open_, close = _bounds(day, cfg)
    slots, t = [], open_
    while t < close:
        if is_free(t, busy, cfg, now):
            slots.append(t)
        t += timedelta(minutes=30)
    return slots


def _parse_event_time(t: dict, tz: ZoneInfo) -> datetime | None:
    if "dateTime" in t:
        return datetime.fromisoformat(t["dateTime"].replace("Z", "+00:00"))
    if "date" in t:  # all-day event: the end date is already exclusive
        return datetime.combine(date.fromisoformat(t["date"]), time(0), tz)
    return None


async def busy_times(refresh_token: str, start: datetime, end: datetime, tz_name: str, ignore_event_id: str = "") -> Busy:
    token = await _access_token(refresh_token)
    async with httpx.AsyncClient(timeout=15.0) as http:
        resp = await http.get(EVENTS_URL, headers={"Authorization": f"Bearer {token}"}, params={
            "timeMin": start.isoformat(), "timeMax": end.isoformat(),
            "singleEvents": "true", "orderBy": "startTime", "maxResults": 250,
        })
    if resp.status_code != 200:
        raise CalendarError(f"Couldn't read the calendar: {_google_reason(resp)}")
    tz = ZoneInfo(tz_name)
    busy: Busy = []
    for ev in resp.json().get("items", []):
        if ev.get("status") == "cancelled" or ev.get("transparency") == "transparent" or ev.get("id") == ignore_event_id:
            continue  # "Show as: Free" events don't block a slot
        if any(a.get("self") and a.get("responseStatus") == "declined" for a in ev.get("attendees", [])):
            continue
        s, e = _parse_event_time(ev.get("start", {}), tz), _parse_event_time(ev.get("end", {}), tz)
        if s and e:
            busy.append((s, e))
    return busy


# ── booking ───────────────────────────────────────────────────────────────────

@dataclass
class Booked:
    event_id: str
    html_link: str
    meet_link: str


async def create_or_move_event(
    refresh_token: str, *, start: datetime, minutes: int, summary: str, description: str,
    attendee_email: str = "", event_id: str = "",
) -> Booked:
    """New event with a Meet link and an invite to the customer; with event_id, move that one instead."""
    token = await _access_token(refresh_token)
    body: dict = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": (start + timedelta(minutes=minutes)).isoformat()},
    }
    if attendee_email:
        body["attendees"] = [{"email": attendee_email}]
    if not event_id:
        body["conferenceData"] = {"createRequest": {
            "requestId": uuid.uuid4().hex, "conferenceSolutionKey": {"type": "hangoutsMeet"},
        }}
    params = {"conferenceDataVersion": 1, "sendUpdates": "all" if attendee_email else "none"}
    async with httpx.AsyncClient(timeout=20.0) as http:
        if event_id:
            resp = await http.patch(f"{EVENTS_URL}/{event_id}", params=params, json=body,
                                    headers={"Authorization": f"Bearer {token}"})
        else:
            resp = await http.post(EVENTS_URL, params=params, json=body, headers={"Authorization": f"Bearer {token}"})
    if resp.status_code not in (200, 201):
        raise CalendarError(f"Google Calendar refused the booking: {_google_reason(resp)}")
    ev = resp.json()
    return Booked(event_id=ev["id"], html_link=ev.get("htmlLink", ""), meet_link=ev.get("hangoutLink", ""))


def spoken(dt: datetime, tz_name: str) -> str:
    """'Thursday 30 October, 11:00 AM' — what the agent reads out."""
    local = dt.astimezone(ZoneInfo(tz_name))
    return local.strftime("%A %d %B, %I:%M %p").replace(" 0", " ")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
