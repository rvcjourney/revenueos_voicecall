"""tests/test_session_close_handler.py — agent.handle_session_close.

Covers the fix for readiness-audit blocker 6: nothing previously reacted
when livekit-agents force-closed a session after repeated LLM/TTS errors,
leaving the caller connected to a dead session for up to the max-duration
guard. Extracted from an inline closure in entrypoint() specifically so it's
testable without a real JobContext/AgentSession.
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from agent import handle_session_close


class _FakeCloseEvent:
    def __init__(self, *, error=None, reason="job_shutdown"):
        self.error = error
        self.reason = reason


class _FakeVoiceAgent:
    def __init__(self, *, ending: bool = False):
        self._ending = ending
        self.silent_hangup_calls = 0

    async def _silent_hangup(self):
        self.silent_hangup_calls += 1


async def _drain_pending_tasks():
    # handle_session_close fires the hangup via _safe_task (asyncio.create_task) --
    # let it actually run before asserting on its effects.
    await asyncio.sleep(0)
    await asyncio.sleep(0)


async def test_triggers_hangup_and_report_when_session_force_closed():
    va = _FakeVoiceAgent(ending=False)
    ev = _FakeCloseEvent(error=RuntimeError("provider outage"), reason="error")

    handle_session_close(va, ev)
    await _drain_pending_tasks()

    assert va._ending is True
    assert va.silent_hangup_calls == 1


async def test_noop_when_teardown_already_in_progress():
    """A close event fired by our OWN _disconnect() (called from
    _trigger_hangup/_silent_hangup/on_enter's failure branch) must not spawn
    a second, redundant hangup -- those paths already set _ending=True
    before tearing the session down."""
    va = _FakeVoiceAgent(ending=True)  # already being torn down elsewhere
    ev = _FakeCloseEvent(error=None, reason="job_shutdown")

    handle_session_close(va, ev)
    await _drain_pending_tasks()

    assert va.silent_hangup_calls == 0


async def test_normal_hangup_close_event_does_not_double_fire():
    """A normal call end (no error) still needs the same guard -- confirms
    the error-vs-no-error branch doesn't affect whether the dedup applies."""
    va = _FakeVoiceAgent(ending=False)
    ev = _FakeCloseEvent(error=None, reason="participant_disconnected")

    handle_session_close(va, ev)
    await _drain_pending_tasks()
    assert va.silent_hangup_calls == 1

    # A second close event for the same (now-ending) session must not fire again.
    handle_session_close(va, ev)
    await _drain_pending_tasks()
    assert va.silent_hangup_calls == 1


async def test_logs_error_when_close_reason_is_an_unrecoverable_error(monkeypatch):
    logged = {}

    def _fake_error(msg, *args):
        logged["called"] = True

    monkeypatch.setattr("agent.logger.error", _fake_error)

    va = _FakeVoiceAgent(ending=False)
    ev = _FakeCloseEvent(error=RuntimeError("tts died"), reason="error")

    handle_session_close(va, ev)
    await _drain_pending_tasks()

    assert logged.get("called") is True
