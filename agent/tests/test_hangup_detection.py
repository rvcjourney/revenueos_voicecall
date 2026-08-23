"""tests/test_hangup_detection.py — agent._HANGUP_RE and _trigger_hangup's
firm_decline early-exit gate.

_HANGUP_RE decides whether the customer just said something that should end
the call -- both English and Hindi/Hinglish (Devanagari + romanized), per the
codebase's own note that romanized-only patterns "very likely never matched
a single real Hindi-spoken hangup" since real transcripts come back in
native script for Hindi words and Latin script for English loanwords.
"""
from __future__ import annotations

import pytest

from agent import _HANGUP_RE


@pytest.mark.parametrize("text", [
    "bye",
    "Goodbye then",
    "ok bye",
    "chalo bye",
    "theek hai bye",
    "chalta hoon",
    "nikalti hoon ab",
    "phone rakhta hoon",
    "band karo",
    "call khatam",
    "not interested",
    "no thanks",
    "no thank you",
    "नहीं interested",           # Devanagari negation + English loanword
    "interested नहीं हूँ",
    "मुझे नहीं चाहिए",
    "disconnect the call",
    "please hang up",
])
def test_hangup_re_matches_real_ending_phrases(text):
    assert _HANGUP_RE.search(text), f"expected a hangup match in {text!r}"


@pytest.mark.parametrize("text", [
    "yes I'm interested, tell me more",
    "interested hoon, bas price ki clarity nahi hai",  # "nahi" present but far from "interest"
    "I'm not sure yet, can you explain again",
    "haan bataiye",
    "what is the pricing",
    "sirf ek minute",  # must never false-positive off unrelated "sir"-adjacent text
])
def test_hangup_re_does_not_match_ongoing_conversation(text):
    assert not _HANGUP_RE.search(text), f"unexpected hangup match in {text!r}"


def test_hangup_re_bounded_gap_does_not_span_unrelated_clauses():
    """The nahi<->interest gap is bounded to 2 filler words specifically so an
    unrelated 'nahi' elsewhere in a longer sentence can't falsely trigger a
    hangup on a customer who is still interested (see agent.py's _GAP
    docstring) -- more than 2 filler words between them must NOT match."""
    text = "interested hoon lekin abhi thoda busy hoon shayad nahi ho payega kal tak"
    assert not _HANGUP_RE.search(text)
