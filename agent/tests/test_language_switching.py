"""tests/test_language_switching.py — mid-call language switching.

The LLM emits a silent [lang:tamil] marker when the customer asks it to speak
another language. _language_switch_filter_transform must strip that marker
before it reaches TTS (it must never be spoken) and hand the requested
language to the switch callback, which re-points TTS and STT.

Also covers languages.py, the single registry mapping a platform language to
its Sarvam TTS/STT codes.
"""
from __future__ import annotations

import languages
import pytest

from agent import _language_switch_filter_transform


async def _achunks(chunks):
    for c in chunks:
        yield c


async def _run(chunks):
    switched: list[str] = []

    async def _switch(name):
        switched.append(name)

    out = []
    async for piece in _language_switch_filter_transform(_switch)(_achunks(chunks)):
        out.append(piece)
    # the switch task is spawned, not awaited — let it run
    import asyncio
    await asyncio.sleep(0)
    return "".join(out), switched


# ── the marker is stripped, never spoken ────────────────────────────────────

async def test_marker_is_stripped_and_switch_requested():
    spoken, switched = await _run(["[lang:tamil] ", "Vanakkam ji, ", "sollunga."])
    assert "lang" not in spoken.lower() and "[" not in spoken
    assert spoken.strip().startswith("Vanakkam")
    assert switched == ["tamil"]


async def test_marker_split_across_chunks_is_still_caught():
    spoken, switched = await _run(["Theek hai ji. [la", "ng:mar", "athi] Namaskar!"])
    assert "lang" not in spoken.lower() and "marathi]" not in spoken
    assert "Namaskar!" in spoken and "Theek hai ji." in spoken
    assert switched == ["marathi"]


async def test_plain_reply_passes_through_untouched():
    spoken, switched = await _run(["Haan ji, ", "bilkul sahi hai."])
    assert spoken == "Haan ji, bilkul sahi hai."
    assert switched == []


async def test_marker_at_end_of_stream_is_handled():
    spoken, switched = await _run(["Zaroor ji. ", "(lang=bengali)"])
    assert "bengali" not in spoken.lower()
    assert switched == ["bengali"]


# ── the language registry ───────────────────────────────────────────────────

@pytest.mark.parametrize("key,tts_code,stt_code", [
    ("hinglish", "hi-IN", "hi-IN"),
    ("hindi", "hi-IN", "hi-IN"),
    ("english", "en-IN", "en-IN"),
    ("marathi", "mr-IN", "mr-IN"),
    ("tamil", "ta-IN", "ta-IN"),
    ("telugu", "te-IN", "te-IN"),
    ("bengali", "bn-IN", "bn-IN"),
    ("gujarati", "gu-IN", "gu-IN"),
    ("kannada", "kn-IN", "kn-IN"),
    ("punjabi", "pa-IN", "pa-IN"),
])
def test_every_language_maps_to_real_sarvam_codes(key, tts_code, stt_code):
    lang = languages.get(key)
    assert (lang.sarvam_tts, lang.sarvam_stt) == (tts_code, stt_code)


def test_unknown_language_falls_back_to_hinglish():
    assert languages.get("klingon").key == "hinglish"
    assert languages.get(None).key == "hinglish"


@pytest.mark.parametrize("spoken,expected", [
    ("tamil", "tamil"),
    ("Tamil.", "tamil"),
    ("bangla", "bengali"),
    ("தமிழ்", "tamil"),
    ("मराठी", "marathi"),
    ("panjabi", "punjabi"),
])
def test_resolve_what_the_customer_called_it(spoken, expected):
    assert languages.resolve(spoken).key == expected


@pytest.mark.parametrize("spoken", ["french", "assamese", "", None])
def test_unsupported_languages_are_not_resolved(spoken):
    assert languages.resolve(spoken) is None


def test_regional_languages_use_sarvam_voice_but_hindi_keeps_its_own():
    assert languages.uses_sarvam_voice("tamil")
    assert languages.uses_sarvam_voice("bengali")
    assert not languages.uses_sarvam_voice("hinglish")
    assert not languages.uses_sarvam_voice("hindi")
    assert not languages.uses_sarvam_voice("english")
