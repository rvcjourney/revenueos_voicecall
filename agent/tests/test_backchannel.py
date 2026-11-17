"""tests/test_backchannel.py — agent._is_backchannel.

Decides whether a transcript heard while the agent is mid-sentence is only a
listening sound ("haan", "hmm", "yes") that should NOT stop the agent, or a
real interruption that should. Sarvam codemix returns Hindi in either Roman
or Devanagari script, so both are covered.
"""
from __future__ import annotations

import pytest

from agent import _is_backchannel


@pytest.mark.parametrize("text", [
    "hmm",
    "Hm hm.",
    "haan",
    "haan haan",
    "Haan ji",
    "yes",
    "Yeah, right.",
    "okay",
    "achha",
    "theek hai",
    "sahi hai",
    "bilkul",
    "हाँ",
    "हां जी।",
    "हम्म",
    "अच्छा",
    "ठीक है",
    "जी हाँ",
    "ओके",
    "haan boliye",
])
def test_listening_sounds_are_backchannel(text):
    assert _is_backchannel(text), f"expected {text!r} to be ignored as a backchannel"


@pytest.mark.parametrize("text", [
    "",
    "   ",
    "ruko",
    "wait",
    "nahi",
    "no",
    "haan lekin",
    "haan but I am busy",
    "main busy hoon",
    "kya bola aapne",
    "sorry",
    "नहीं",
    "रुको",
    "हाँ लेकिन अभी नहीं",
    "haan haan haan haan haan haan haan",  # over the length cap — someone talking, not nodding
])
def test_real_interruptions_are_not_backchannel(text):
    assert not _is_backchannel(text), f"expected {text!r} to count as a real interruption"


# ── Caller talking over the agent (stt_node barge-in) ──────────────────────────
import asyncio
from types import SimpleNamespace

from livekit.agents import Agent, stt

import agent as agent_mod
from tests.test_sarvam_pipeline import _agent


class _Speech:
    allow_interruptions, interrupted = True, False

    def done(self):
        return False

    def interrupt(self, **kw):
        self.interrupted = True


async def _run_stt(va, monkeypatch, events):
    """Feed fake Sarvam events through stt_node, sleeping where a float is given."""
    async def fake_stt_node(agent, audio, model_settings):
        for ev in events:
            if isinstance(ev, float):
                await asyncio.sleep(ev)
            else:
                yield stt.SpeechEvent(type=ev)
    monkeypatch.setattr(Agent.default, "stt_node", fake_stt_node)
    monkeypatch.setattr(agent_mod, "_BARGE_IN_S", 0.05)
    async for _ in va.stt_node(None, None):
        pass
    await asyncio.sleep(0.1)


@pytest.mark.asyncio
async def test_caller_talking_over_the_agent_stops_it_without_waiting_for_words(monkeypatch):
    va, speech = _agent(), _Speech()
    monkeypatch.setattr(agent_mod.VoiceAgent, "session", property(lambda self: SimpleNamespace(current_speech=speech)))
    await _run_stt(va, monkeypatch, [stt.SpeechEventType.START_OF_SPEECH, 0.1])
    assert speech.interrupted


@pytest.mark.asyncio
async def test_a_short_haan_over_the_agent_does_not_stop_it(monkeypatch):
    va, speech = _agent(), _Speech()
    monkeypatch.setattr(agent_mod.VoiceAgent, "session", property(lambda self: SimpleNamespace(current_speech=speech)))
    await _run_stt(va, monkeypatch, [stt.SpeechEventType.START_OF_SPEECH, 0.01, stt.SpeechEventType.END_OF_SPEECH])
    assert not speech.interrupted


@pytest.mark.asyncio
async def test_a_goodbye_that_must_not_be_interrupted_is_left_alone(monkeypatch):
    va, speech = _agent(), _Speech()
    speech.allow_interruptions = False
    monkeypatch.setattr(agent_mod.VoiceAgent, "session", property(lambda self: SimpleNamespace(current_speech=speech)))
    await _run_stt(va, monkeypatch, [stt.SpeechEventType.START_OF_SPEECH, 0.1])
    assert not speech.interrupted
