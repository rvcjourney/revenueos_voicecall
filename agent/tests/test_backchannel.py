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
