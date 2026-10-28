"""tests/test_calendar_tool.py — Google Calendar tools (agent.py).

With metadata "calendar": {"available": true} the agent gets check_calendar and a
book_next_step that books through the backend (app/api/calendar.py); without it,
book_next_step only notes the agreed time, as before.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import httpx

import agent
import sarvam_pipeline as sp

_HINDI = {"hindi": {"stt": "hi-IN", "tts": "hi-IN", "clone": "hi-IN", "tts_model": "bulbul:v4-flash", "display": "Hindi",
                    "voices": [{"id": "ritu_hi_conversation", "gender": "female"}],
                    "repeat_line": "repeat", "failure_line": "failure"}}


def _make_agent(calendar=None):
    return agent.VoiceAgent(
        MagicMock(), instructions="test", welcome_message="hi",
        sarvam_state=sp.SarvamCallState("hindi", "ritu_hi_conversation", False, _HINDI),
        call_id="call-123", backend_url="http://backend.test", webhook_secret="s3cr3t", calendar=calendar,
    )


def _tool(va, name):
    return next((t for t in va.tools if getattr(t, "info", None) and t.info.name == name), None)


def _backend(responses: list[dict], seen: list):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, json.loads(request.content), request.headers.get("X-Webhook-Signature")))
        return httpx.Response(200, json=responses.pop(0))
    real = httpx.AsyncClient
    return patch("httpx.AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))


def test_without_calendar_book_next_step_only_notes():
    va = _make_agent()
    assert _tool(va, "check_calendar") is None
    assert _tool(va, "book_next_step") is not None


def test_with_calendar_both_tools_and_one_book_next_step():
    va = _make_agent({"available": True, "email_on_file": False})
    names = [t.info.name for t in va.tools if getattr(t, "info", None)]
    assert names.count("book_next_step") == 1 and "check_calendar" in names
    assert "letter by letter" in _tool(va, "book_next_step").info.description


async def test_booking_confirmed_is_reported_and_a_rebook_moves_the_event():
    va = _make_agent({"available": True, "email_on_file": True})
    seen: list = []
    confirmed = {"status": "confirmed", "reference": "NS-ABC123", "date_time": "Thursday 30 October, 3:00 PM",
                 "event_id": "evt1", "calendar_link": "https://cal/evt1", "meet_link": "https://meet/x",
                 "invite_sent_to": "ravi@acme.in"}
    with _backend([confirmed, {**confirmed, "date_time": "Friday 31 October, 11:00 AM"}], seen):
        book = _tool(va, "book_next_step")
        out = await book(MagicMock(), prospect_name="Ravi", company="Acme", next_step_type="demo",
                         date_time="2026-10-30 15:00", email="Ravi @ Acme.in")
        assert out["status"] == "confirmed"
        await book(MagicMock(), prospect_name="Ravi", company="Acme", next_step_type="demo", date_time="2026-10-31 11:00")
    path, body, sig = seen[0]
    assert path == "/api/calendar/calls/call-123/book" and sig
    assert body["email"] == "ravi@acme.in" and body["event_id"] == ""
    assert seen[1][1]["event_id"] == "evt1"  # second booking moves the first
    assert va._booking["meet_link"] == "https://meet/x" and va._booking["date_time"].startswith("Friday")


async def test_unavailable_slot_is_not_recorded_as_booked():
    va = _make_agent({"available": True, "email_on_file": True})
    with _backend([{"status": "unavailable", "free_times": ["11:00"]}], []):
        out = await _tool(va, "book_next_step")(MagicMock(), prospect_name="R", company="A",
                                                next_step_type="demo", date_time="2026-10-30 15:00")
    assert out["status"] == "unavailable" and va._booking is None


async def test_backend_down_returns_error_instead_of_raising():
    va = _make_agent({"available": True, "email_on_file": True})

    def boom(request):
        raise httpx.ConnectError("down")
    real = httpx.AsyncClient
    with patch("httpx.AsyncClient", lambda **kw: real(transport=httpx.MockTransport(boom), **kw)):
        out = await _tool(va, "check_calendar")(MagicMock(), date="2026-10-30")
    assert out["status"] == "error"
