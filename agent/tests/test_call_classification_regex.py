"""tests/test_call_classification_regex.py — agent._VOICEMAIL_RE, _BOT_IVR_RE,
_FORWARDING_RE.

These decide whether a connected call actually reached a voicemail box, an
IVR/hold queue, or a carrier call-forwarding announcement instead of a real
person -- misclassifying any of these burns a billed minute AND produces a
nonsense "conversation" outcome. Each must fire on real-world phrasing and
must not fire on genuine human speech that merely shares a word with one.
"""
from __future__ import annotations

import pytest

from agent import _BOT_IVR_RE, _FORWARDING_RE, _VOICEMAIL_RE


@pytest.mark.parametrize("text", [
    "Please leave a message after the tone",
    "The person you are trying to reach is not available",
    "This mailbox has not been set up yet",
    "record your message after the beep",
    "You have reached my voicemail",
    "Your call has been forwarded to voicemail",
    "please hang up when you are finished recording",
])
def test_voicemail_re_matches_real_greetings(text):
    assert _VOICEMAIL_RE.search(text), f"expected a voicemail match in {text!r}"


@pytest.mark.parametrize("text", [
    "Hi, yes, who's calling please?",
    "I'm a bit busy right now, can you call back later",
    "leave it with me, I'll think about it",  # "leave" present but not the voicemail phrase
])
def test_voicemail_re_does_not_match_real_conversation(text):
    assert not _VOICEMAIL_RE.search(text)


@pytest.mark.parametrize("text", [
    "For English press 1",
    "Press 2 to speak with sales",
    "All our agents are currently busy, please hold",
    "Your call is important to us",
    "you have been placed in a queue",
    "This is an automated message",
])
def test_bot_ivr_re_matches_real_ivr_phrasing(text):
    assert _BOT_IVR_RE.search(text)


@pytest.mark.parametrize("text", [
    "Hello, this is Priya speaking",
    "hold on a second let me check",  # "hold" without "please hold (while|for)"
])
def test_bot_ivr_re_does_not_match_real_conversation(text):
    assert not _BOT_IVR_RE.search(text)


@pytest.mark.parametrize("text", [
    "Your call is being forwarded",
    "please wait while we connect your call",
    "the number you dialed has been diverted",
    "call forward ki ja rahi hai",
    "aapki call forward ho rahi hai",
])
def test_forwarding_re_matches_carrier_announcements(text):
    assert _FORWARDING_RE.search(text)


def test_forwarding_re_does_not_match_real_conversation():
    assert not _FORWARDING_RE.search("I'll forward you the brochure by email")
