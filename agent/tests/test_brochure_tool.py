"""tests/test_brochure_tool.py — the send_brochure tool (agent.py).

Offered only when the backend says a brochure can really be emailed
(metadata "brochure": {"available": true}); the request rides on the post-call
report as extracted_data.brochure_request, even when the customer said little.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import agent
import sarvam_pipeline as sp

_HINDI = {"hindi": {"stt": "hi-IN", "tts": "hi-IN", "clone": "hi-IN", "tts_model": "bulbul:v4-flash", "display": "Hindi",
                    "voices": [{"id": "ritu_hi_conversation", "gender": "female"}],
                    "repeat_line": "repeat", "failure_line": "failure"}}


def _make_agent(brochure=None):
    return agent.VoiceAgent(
        MagicMock(), instructions="test", welcome_message="hi",
        sarvam_state=sp.SarvamCallState("hindi", "ritu_hi_conversation", False, _HINDI),
        call_id="call-123", backend_url="http://backend.test", webhook_secret="s3cr3t", brochure=brochure,
    )


def _tool(va, name):
    return next((t for t in va.tools if getattr(t, "info", None) and t.info.name == name), None)


def test_no_brochure_no_tool():
    assert _tool(_make_agent(), "send_brochure") is None
    assert _tool(_make_agent({"available": False}), "send_brochure") is None


def test_tool_offered_and_description_depends_on_email_on_file():
    with_email = _tool(_make_agent({"available": True, "email_on_file": True}), "send_brochure")
    without = _tool(_make_agent({"available": True, "email_on_file": False}), "send_brochure")
    assert with_email is not None and without is not None
    assert "Don't ask for it" in with_email.info.description
    assert "ask for it" in without.info.description and "letter by letter" in without.info.description


async def _call_tool(va, **kwargs):
    tool = _tool(va, "send_brochure")
    return await tool(MagicMock(), **kwargs)


async def test_tool_records_spoken_email_normalised():
    va = _make_agent({"available": True, "email_on_file": False})
    reply = await _call_tool(va, email="Rahul.K @ Gmail.com")
    assert va._brochure_request == {"email": "rahul.k@gmail.com"}
    assert "emailed right after this call" in reply


async def test_tool_without_usable_email_leaves_it_to_the_backend():
    va = _make_agent({"available": True, "email_on_file": True})
    await _call_tool(va, email="")
    assert va._brochure_request == {"email": ""}
    await _call_tool(va, email="rahul at gmail")  # no "@": not an address, use the one on file
    assert va._brochure_request == {"email": ""}


async def test_short_yes_still_reports_the_brochure_request():
    """'haan, bhej do' is under the 8-word gate but is a real request: it must
    reach the classifier path and ride on extracted_data."""
    va = _make_agent({"available": True, "email_on_file": True})
    va._user_messages = ["haan", "bhej do"]
    await _call_tool(va)
    chat = AsyncMock(return_value=(json.dumps({"outcome": "interested", "summary": "Wants brochure", "extracted_data": {}}), "stop"))
    with patch("agent._sarvam_chat", new=chat), patch.object(va, "_post_agent_report", new=AsyncMock()) as post:
        await va._send_report()
    report = post.call_args.args[0]
    assert report["outcome"] == "interested"
    assert report["extracted_data"]["brochure_request"] == {"email": ""}
    system_prompt = chat.call_args.args[0][0]["content"] if chat.call_args.args else json.dumps(chat.call_args.kwargs)
    assert "brochure" in system_prompt
