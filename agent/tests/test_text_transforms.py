"""tests/test_text_transforms.py — agent's streaming TTS text-transform
generators: _honorific_greeting_filter_transform, _digit_spellout_transform,
_end_call_filter_transform.

These rewrite the LLM's streamed output chunk-by-chunk before it reaches
TTS. Each is fed as an async generator (mirroring how the real TTS pipeline
calls them) built from a list of arbitrarily-sized chunks, since the whole
point of their "confirmed match" buffering logic is to behave correctly
regardless of where chunk boundaries happen to fall.
"""
from __future__ import annotations

import pytest

from agent import (
    _digit_spellout_transform,
    _end_call_filter_transform,
    _honorific_greeting_filter_transform,
)


async def _achunks(chunks):
    for c in chunks:
        yield c


async def _run_filter(filter_fn, chunks):
    out = []
    async for piece in filter_fn(_achunks(chunks)):
        out.append(piece)
    return "".join(out)


# ── Honorific / greeting filter ─────────────────────────────────────────────

async def test_honorific_sir_becomes_ji():
    filt = _honorific_greeting_filter_transform()
    result = await _run_filter(filt, ["Yes ", "sir", ", of course."])
    assert "sir" not in result.lower()
    assert "ji" in result.lower()


async def test_honorific_maam_becomes_ji():
    filt = _honorific_greeting_filter_transform()
    result = await _run_filter(filt, ["Sure ma'am, ", "no problem."])
    assert "ma'am" not in result.lower()


async def test_honorific_does_not_mangle_word_containing_sir_prefix():
    """The whole point of the 'confirmed match' tail-buffering: a chunk
    boundary landing right after 'Sir' (before 'f' of 'Sirf' arrives) must
    not treat 'Sir' as a standalone word and mangle it into 'jif'."""
    filt = _honorific_greeting_filter_transform()
    result = await _run_filter(filt, ["Sir", "f ek minute lagega"])
    assert "jif" not in result.lower()
    assert "sirf" in result.lower()


async def test_honorific_replaces_wrong_greeting_with_time_of_day_greeting():
    """Whatever "good X" the LLM said gets rewritten to match the REAL
    current time of day -- not asserting a fixed string here since the
    correct answer depends on when the test happens to run; instead confirm
    the filter's output always matches _time_of_day_greeting()'s own answer,
    using an input greeting deliberately different from it."""
    from agent import _time_of_day_greeting

    correct_greeting = _time_of_day_greeting("Asia/Kolkata")
    # Pick an input greeting guaranteed to differ from the correct one.
    wrong_input = "Good night" if correct_greeting != "Good night" else "Good morning"

    filt = _honorific_greeting_filter_transform(tz_name="Asia/Kolkata")
    result = await _run_filter(filt, [wrong_input.split()[0] + " ", wrong_input.split()[1], " to you!"])

    assert wrong_input.lower() not in result.lower()
    assert correct_greeting.lower() in result.lower()


async def test_honorific_filter_is_a_noop_on_plain_text():
    filt = _honorific_greeting_filter_transform()
    result = await _run_filter(filt, ["Sure, ", "let me check ", "that for you."])
    assert result == "Sure, let me check that for you."


# ── Digit spellout ───────────────────────────────────────────────────────────

async def test_digit_run_of_seven_plus_is_spelled_out():
    filt = _digit_spellout_transform()
    result = await _run_filter(filt, ["Your OTP is ", "7881708", ", please confirm."])
    assert "seven eight eight one seven zero eight" in result
    assert "7881708" not in result


async def test_short_digit_run_under_seven_is_left_alone():
    filt = _digit_spellout_transform()
    result = await _run_filter(filt, ["That will be ", "500", " rupees."])
    assert "500" in result
    assert "five zero zero" not in result


async def test_digit_run_split_across_chunk_boundary_is_still_spelled_out():
    """A short prefix ('788') touching the end of one chunk must be held back
    -- not flushed as bare digits -- until the rest of the number ('1708')
    arrives in a later chunk."""
    filt = _digit_spellout_transform()
    result = await _run_filter(filt, ["OTP: ", "788", "1708", " confirm please"])
    assert "7881708" not in result
    assert "seven eight eight one seven zero eight" in result


async def test_digit_spellout_is_a_noop_on_plain_text():
    filt = _digit_spellout_transform()
    result = await _run_filter(filt, ["Sure, ", "let me check ", "that for you."])
    assert result == "Sure, let me check that for you."


# ── End-call filter ──────────────────────────────────────────────────────────

async def test_end_call_marker_is_stripped_and_triggers_hangup():
    fired = []

    async def _hangup():
        fired.append(True)

    filt = _end_call_filter_transform(_hangup)
    result = await _run_filter(filt, ["Thank you, goodbye! ", "[end_call]"])

    assert "end_call" not in result.lower()
    assert "thank you" in result.lower()
    # _safe_task schedules the hangup coroutine -- let the event loop run it.
    import asyncio
    await asyncio.sleep(0)
    assert fired == [True]


async def test_end_call_marker_split_across_chunks_still_detected():
    fired = []

    async def _hangup():
        fired.append(True)

    filt = _end_call_filter_transform(_hangup)
    result = await _run_filter(filt, ["Bye now! [end", "_call]"])

    import asyncio
    await asyncio.sleep(0)
    assert fired == [True]
    assert "end_call" not in result.lower() and "[end" not in result


async def test_normal_speech_never_triggers_hangup():
    fired = []

    async def _hangup():
        fired.append(True)

    filt = _end_call_filter_transform(_hangup)
    result = await _run_filter(filt, ["Sure, ", "let me check ", "that for you."])

    assert result == "Sure, let me check that for you."
    assert fired == []
