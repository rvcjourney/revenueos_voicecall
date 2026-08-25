"""tests/test_call_dropped_outcome.py — agent.VoiceAgent._send_report's
abrupt_disconnect handling (agent.py's "minimum engagement gate" + the LLM
classifier prompt).

A customer's line disconnecting before the agent could close the call
gracefully carries no real interest/rejection signal when little or nothing
was said -- it should land on outcome="call_dropped", not the "not_interested"
default used for every other low-engagement case (silence timeout, the
agent's own farewell hangup, etc.).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import agent


def _make_agent(**overrides):
    kwargs = dict(
        instructions="test", welcome_message="hi",
        call_id="call-123", backend_url="http://backend.test", webhook_secret="s3cr3t",
    )
    kwargs.update(overrides)
    return agent.VoiceAgent(MagicMock(), **kwargs)


def _groq_response(outcome: str, summary: str = "s"):
    """Shapes a fake Groq chat-completion response matching what
    _send_report's LLM path reads: resp.choices[0].{finish_reason,message.content}
    and resp.usage.completion_tokens."""
    import json

    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].finish_reason = "stop"
    resp.choices[0].message.content = json.dumps({
        "outcome": outcome, "summary": summary, "extracted_data": {},
    })
    resp.usage = MagicMock(completion_tokens=10)
    return resp


# ── Deterministic word-count gate (customer said too little to classify) ────

async def test_zero_words_with_abrupt_disconnect_is_call_dropped():
    va = _make_agent()
    # No customer speech captured at all -- the exact scenario a SIP leg that
    # disconnects before/during the welcome message produces.
    va._user_messages = []
    with patch.object(va, "_post_agent_report", new=AsyncMock()) as mock_post:
        await va._send_report(abrupt_disconnect=True)

    outcome = mock_post.call_args.args[0]["outcome"]
    assert outcome == "call_dropped"


async def test_zero_words_without_abrupt_disconnect_reports_nothing():
    """Same near-silence, but the call ended some other way (agent's own
    farewell, silence timeout) -- unchanged pre-existing behavior: with
    literally no transcript at all and no override, nothing gets reported and
    outcome stays at its DB default (pending)."""
    va = _make_agent()
    va._user_messages = []
    with patch.object(va, "_post_agent_report", new=AsyncMock()) as mock_post:
        await va._send_report(abrupt_disconnect=False)

    mock_post.assert_not_awaited()


async def test_few_words_with_abrupt_disconnect_is_call_dropped():
    va = _make_agent()
    va._user_messages = ["haan", "matlab"]  # 2 words total, well under the 8-word gate
    with patch.object(va, "_post_agent_report", new=AsyncMock()) as mock_post:
        await va._send_report(abrupt_disconnect=True)

    outcome = mock_post.call_args.args[0]["outcome"]
    assert outcome == "call_dropped"


async def test_few_words_without_abrupt_disconnect_stays_not_interested():
    va = _make_agent()
    va._user_messages = ["haan", "matlab"]
    with patch.object(va, "_post_agent_report", new=AsyncMock()) as mock_post:
        await va._send_report(abrupt_disconnect=False)

    outcome = mock_post.call_args.args[0]["outcome"]
    assert outcome == "not_interested"


# ── LLM classification path (customer said enough to judge, >= 8 words) ─────

async def test_llm_path_accepts_call_dropped_only_when_abrupt():
    va = _make_agent()
    va._user_messages = ["yeh ek lambi baat hai jo customer ne kahi thi call par"]  # 12 words

    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=_groq_response("call_dropped"))

    with patch("groq.AsyncGroq", return_value=fake_client), \
         patch.object(va, "_post_agent_report", new=AsyncMock()) as mock_post:
        await va._send_report(abrupt_disconnect=True)

    assert mock_post.call_args.args[0]["outcome"] == "call_dropped"


async def test_llm_path_rejects_call_dropped_when_not_abrupt():
    """The model choosing call_dropped anyway (e.g. hallucination) on a call
    that DIDN'T end via an abrupt customer disconnect must fall back to
    not_interested, same as any other value outside the valid set."""
    va = _make_agent()
    va._user_messages = ["yeh ek lambi baat hai jo customer ne kahi thi call par"]

    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=_groq_response("call_dropped"))

    with patch("groq.AsyncGroq", return_value=fake_client), \
         patch.object(va, "_post_agent_report", new=AsyncMock()) as mock_post:
        await va._send_report(abrupt_disconnect=False)

    assert mock_post.call_args.args[0]["outcome"] == "not_interested"


async def test_llm_prompt_only_mentions_call_dropped_when_abrupt():
    va = _make_agent()
    va._user_messages = ["yeh ek lambi baat hai jo customer ne kahi thi call par"]

    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=_groq_response("not_interested"))

    with patch("groq.AsyncGroq", return_value=fake_client), \
         patch.object(va, "_post_agent_report", new=AsyncMock()):
        await va._send_report(abrupt_disconnect=False)
    system_prompt_not_abrupt = fake_client.chat.completions.create.call_args.kwargs["messages"][0]["content"]

    fake_client.chat.completions.create = AsyncMock(return_value=_groq_response("not_interested"))
    with patch("groq.AsyncGroq", return_value=fake_client), \
         patch.object(va, "_post_agent_report", new=AsyncMock()):
        await va._send_report(abrupt_disconnect=True)
    system_prompt_abrupt = fake_client.chat.completions.create.call_args.kwargs["messages"][0]["content"]

    assert "call_dropped" not in system_prompt_not_abrupt
    assert "call_dropped" in system_prompt_abrupt
