"""tests/test_transfer_tool.py — the transfer_call tool (agent.py).

Offered only when the agent has a transfer number and the call's trunk is known
(metadata "transfer": {"number", "trunk_id", "caller_id"}). It rings the number into
the same room; once answered the agent goes quiet and stops its own timers.
"""
from __future__ import annotations

import asyncio

from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import agent
import sarvam_pipeline as sp

_HINDI = {"hindi": {"stt": "hi-IN", "tts": "hi-IN", "clone": "hi-IN", "tts_model": "bulbul:v4-flash", "display": "Hindi",
                    "voices": [{"id": "ritu_hi_conversation", "gender": "female"}],
                    "repeat_line": "repeat", "failure_line": "failure"}}
_TRANSFER = {"number": "+919876543210", "trunk_id": "ST_abc", "caller_id": "+911234567890"}


def _make_agent(transfer=None, max_duration=600):
    room = MagicMock()
    room.name = "camp-1"
    return agent.VoiceAgent(
        room, instructions="test", welcome_message="hi",
        sarvam_state=sp.SarvamCallState("hindi", "ritu_hi_conversation", False, _HINDI),
        call_id="call-123", backend_url="http://backend.test", webhook_secret="s3cr3t",
        transfer=transfer, max_duration=max_duration,
    )


def _tool(va):
    return next((t for t in va.tools if getattr(t, "info", None) and t.info.name == "transfer_call"), None)


def test_no_number_or_trunk_no_tool():
    assert _tool(_make_agent()) is None
    assert _tool(_make_agent({"number": ""})) is None
    assert _tool(_make_agent({"number": "+919876543210"})) is None  # trunk unknown
    assert _tool(_make_agent(_TRANSFER)) is not None


async def _run(va, sip_side_effect=None):
    lk = MagicMock()
    lk.api.sip.create_sip_participant = AsyncMock(side_effect=sip_side_effect)
    session = MagicMock()
    ctx = MagicMock()
    ctx.wait_for_playout = AsyncMock()
    with patch("agent.get_job_context", return_value=lk), \
         patch.object(agent.VoiceAgent, "session", new_callable=PropertyMock, return_value=session):
        result = await _tool(va)(ctx, hold_message="Please hold")
    return result, lk.api.sip.create_sip_participant, session


async def test_answered_bridges_and_goes_quiet():
    va = _make_agent(_TRANSFER)
    va._background = MagicMock(aclose=AsyncMock())
    result, dial, session = await _run(va)
    assert result is None and va._transfer_state == "connected"
    req = dial.call_args.args[0]
    assert (req.sip_call_to, req.sip_trunk_id, req.sip_number, req.room_name) == (
        "+919876543210", "ST_abc", "+911234567890", "camp-1")
    assert req.wait_until_answered
    session.say.assert_called_once()  # hold line, since the model hadn't spoken
    session.input.set_audio_enabled.assert_called_with(False)
    session.output.set_audio_enabled.assert_called_with(False)


async def test_no_answer_stays_with_agent():
    va = _make_agent(_TRANSFER)
    result, _, session = await _run(va, sip_side_effect=RuntimeError("486 busy"))
    assert va._transfer_state == "failed"
    assert "call them back" in result
    session.input.set_audio_enabled.assert_not_called()


async def test_report_carries_transfer_and_max_duration_spares_a_bridged_call():
    va = _make_agent(_TRANSFER, max_duration=0)
    va._transfer_state = "connected"
    with patch.object(va, "_silent_hangup", new=AsyncMock()) as hangup:
        await va._max_duration_guard()
    hangup.assert_not_called()
    va._user_messages = ["mujhe manager se baat karni hai"]
    with patch.object(va, "_post_agent_report", new=AsyncMock()) as post, \
         patch.object(va, "_transcript", return_value=[{"role": "user", "text": "manager please"}]), \
         patch.object(va, "_classify", new=AsyncMock(return_value=("interested", "s", {}))):
        va._booking = {"x": 1}  # past the short-call gate so extracted_data is sent
        await va._send_report()
    assert post.call_args.args[0]["extracted_data"]["transfer"] == {"to": "+919876543210", "status": "connected"}


def _leaver(identity):
    return MagicMock(identity=identity, attributes={"sip.callStatus": "hangup"}, disconnect_reason=None)


async def test_busy_colleague_leaving_does_not_end_the_customer_call():
    """LiveKit puts the transfer leg in the room while it rings; busy/no-answer makes it leave."""
    va = _make_agent(_TRANSFER)
    va._transfer_state = "dialing"
    with patch.object(va, "_silent_hangup", new=AsyncMock()) as hangup:
        va.on_participant_left(_leaver("transfer-919876543210"))
        await asyncio.sleep(0)
    hangup.assert_not_called()
    assert not va._ending


async def test_colleague_hanging_up_after_answering_ends_the_call():
    va = _make_agent(_TRANSFER)
    va._transfer_state = "connected"
    with patch.object(va, "_silent_hangup", new=AsyncMock()) as hangup:
        va.on_participant_left(_leaver("transfer-919876543210"))
        await asyncio.sleep(0)
    hangup.assert_called_once_with(abrupt_disconnect=False)


async def test_customer_hanging_up_still_ends_the_call():
    va = _make_agent(_TRANSFER)
    va._transfer_state = "dialing"
    with patch.object(va, "_silent_hangup", new=AsyncMock()) as hangup:
        va.on_participant_left(_leaver("phone-919999999999"))
        await asyncio.sleep(0)
    hangup.assert_called_once_with(abrupt_disconnect=True)
