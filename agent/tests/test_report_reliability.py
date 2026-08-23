"""tests/test_report_reliability.py — agent.VoiceAgent._post_agent_report's
retry/backoff and durable fallback (agent._persist_failed_report), plus the
_reported idempotency guard shared by _post_call_report/_report_system_failure.

A call's outcome/transcript/summary only ever exist in this process's
memory until this POST succeeds -- these are the only things standing
between a real backend hiccup and permanently losing that data.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

import agent


def _make_agent(**overrides):
    kwargs = dict(
        instructions="test", welcome_message="hi",
        call_id="call-123", backend_url="http://backend.test", webhook_secret="s3cr3t",
    )
    kwargs.update(overrides)
    return agent.VoiceAgent(MagicMock(), **kwargs)


def _fake_client(*, responses):
    """responses: list of either an httpx.Response-like MagicMock or an Exception
    to raise, one per successive `async with httpx.AsyncClient(...) as http:` use."""
    calls = {"n": 0}

    class _FakeAsyncClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, content=None, headers=None):
            i = calls["n"]
            calls["n"] += 1
            outcome = responses[i]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

    return _FakeAsyncClient, calls


def _ok_response():
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    return resp


def _http_error_response():
    resp = MagicMock()
    resp.raise_for_status = MagicMock(side_effect=httpx.HTTPStatusError("500", request=MagicMock(), response=MagicMock()))
    return resp


# ── Success / signature ─────────────────────────────────────────────────────

async def test_succeeds_on_first_attempt_with_signed_request():
    va = _make_agent()
    fake_cls, calls = _fake_client(responses=[_ok_response()])

    with patch("httpx.AsyncClient", fake_cls):
        await va._post_agent_report({"outcome": "interested", "summary": "x", "transcript": []})

    assert calls["n"] == 1


async def test_request_carries_a_valid_hmac_signature():
    va = _make_agent()
    captured = {}
    fake_cls, _calls = _fake_client(responses=[_ok_response()])

    class _CapturingClient(fake_cls):
        async def post(self, url, content=None, headers=None):
            captured["headers"] = headers
            captured["body"] = content
            return await super().post(url, content=content, headers=headers)

    with patch("httpx.AsyncClient", _CapturingClient):
        await va._post_agent_report({"outcome": "interested"})

    sig = captured["headers"]["X-Webhook-Signature"]
    assert sig.startswith("t=") and ",v1=" in sig


# ── Retry / backoff ──────────────────────────────────────────────────────────

async def test_retries_transient_failure_then_succeeds():
    va = _make_agent()
    fake_cls, calls = _fake_client(responses=[httpx.ConnectError("boom"), _ok_response()])

    with patch("httpx.AsyncClient", fake_cls), patch("asyncio.sleep", new=AsyncMock()) as mock_sleep:
        await va._post_agent_report({"outcome": "interested"})

    assert calls["n"] == 2
    mock_sleep.assert_awaited_once()


async def test_retries_on_bad_http_status_not_just_connection_errors():
    """A 4xx/5xx response was previously indistinguishable from success here
    (no status check) -- confirms raise_for_status() is actually checked."""
    va = _make_agent()
    fake_cls, calls = _fake_client(responses=[_http_error_response(), _ok_response()])

    with patch("httpx.AsyncClient", fake_cls), patch("asyncio.sleep", new=AsyncMock()):
        await va._post_agent_report({"outcome": "interested"})

    assert calls["n"] == 2


async def test_exhausting_all_retries_persists_and_reraises():
    va = _make_agent()
    fake_cls, calls = _fake_client(responses=[
        httpx.ConnectError("1"), httpx.ConnectError("2"), httpx.ConnectError("3"),
    ])

    with patch("httpx.AsyncClient", fake_cls), \
         patch("asyncio.sleep", new=AsyncMock()), \
         patch("agent._persist_failed_report") as mock_persist:
        with pytest.raises(httpx.ConnectError):
            await va._post_agent_report({"outcome": "interested", "summary": "s"}, attempts=3)

    assert calls["n"] == 3
    mock_persist.assert_called_once()
    persisted_call_id, persisted_payload, persisted_error = mock_persist.call_args.args
    assert persisted_call_id == "call-123"
    assert persisted_payload == {"outcome": "interested", "summary": "s"}


# ── _persist_failed_report durable fallback ─────────────────────────────────

async def test_persist_failed_report_writes_valid_jsonl(tmp_path):
    path = tmp_path / "failed_reports.jsonl"
    with patch("agent.FAILED_REPORTS_PATH", str(path)):
        agent._persist_failed_report("call-abc", {"outcome": "interested"}, RuntimeError("network down"))

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["call_id"] == "call-abc"
    assert entry["payload"] == {"outcome": "interested"}
    assert "network down" in entry["error"]
    assert "failed_at" in entry


async def test_persist_failed_report_appends_not_overwrites(tmp_path):
    path = tmp_path / "failed_reports.jsonl"
    with patch("agent.FAILED_REPORTS_PATH", str(path)):
        agent._persist_failed_report("call-1", {"outcome": "a"}, RuntimeError("e1"))
        agent._persist_failed_report("call-2", {"outcome": "b"}, RuntimeError("e2"))

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2


# ── _reported idempotency guard ──────────────────────────────────────────────

async def test_post_call_report_only_sends_once():
    va = _make_agent()
    with patch.object(va, "_send_report", new=AsyncMock()) as mock_send:
        await va._post_call_report()
        await va._post_call_report()  # simulates a second teardown path also calling in

    mock_send.assert_awaited_once()
    assert va._reported is True


async def test_report_system_failure_only_sends_once():
    va = _make_agent()
    with patch.object(va, "_post_agent_report", new=AsyncMock()) as mock_post:
        await va._report_system_failure("tts broke")
        await va._report_system_failure("tts broke again")

    mock_post.assert_awaited_once()


async def test_report_system_failure_does_not_block_post_call_report_guard():
    """Whichever of the two report paths runs FIRST wins -- confirms they
    share the same _reported flag rather than each having their own."""
    va = _make_agent()
    with patch.object(va, "_post_agent_report", new=AsyncMock()) as mock_post, \
         patch.object(va, "_send_report", new=AsyncMock()) as mock_send:
        await va._report_system_failure("tts broke")
        await va._post_call_report()

    mock_post.assert_awaited_once()
    mock_send.assert_not_awaited()
