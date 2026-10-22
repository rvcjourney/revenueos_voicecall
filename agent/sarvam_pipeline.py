"""
sarvam_pipeline.py — the "sarvam" calling engine ("Indic Native" to customers):
Sarvam realtime STT + sarvam-105b-conversations + Bulbul, for one call.

Only provider construction, turn-handling values, the spoken-style prompt
block and the mid-call language switch live here. Everything else about a
call (hang-up logic, silence/voicemail/IVR handling, report, billing, Prime
scripts) is shared with the standard engine in agent.py and untouched.

The backend resolves everything per call and sends it as meta["sarvam"]
(see backend/app/core/pipelines.py sarvam_call_config): the call's language,
voice, whether it is a cloned voice, and every enabled language's codes,
TTS model and voices — so a mid-call switch needs no lookup.

Settings follow Sarvam's "LiveKit in Production" telephony guidance
(docs.sarvam.ai/api/integration/livekit-production-best-practices, read
2026-10-22). Every value is a named constant, overridable by env in config.py.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from livekit.agents import TurnHandlingOptions
from livekit.plugins import sarvam

from config import (
    SARVAM_API_KEY,
    SARVAM_PIPELINE_LLM_MAX_TOKENS,
    SARVAM_PIPELINE_LLM_MODEL,
    SARVAM_PIPELINE_TTS_CODEC,
    SARVAM_PIPELINE_TTS_SAMPLE_RATE,
)

logger = logging.getLogger("voice-agent")

PIPELINE = "sarvam"

# ── STT (realtime, server-side VAD) — telephony starting points ──────────────
STT_STREAM_TYPE = "fast"          # 500 ms chunks; "balanced" adds up to 1 s per turn
STT_ENDPOINTING = "vad"
STT_SAMPLE_RATE = 16000           # 8000 or 16000 only
STT_VAD_MIN_SILENCE_MS = 500
STT_VAD_MIN_SPEECH_MS = 200
STT_VAD_SOT_THRESHOLD = 0.7
STT_PROMPT_MAX_CHARS = 200        # sent as a URL query param; long prompts can fail the handshake
STT_CODEMIX_LANG = "hi-IN"        # codemix for Hindi-English calls, transcribe elsewhere

# ── LLM ───────────────────────────────────────────────────────────────────────
# Agent "creativity" (0..1+, Qwen default 0.7) is mapped into this safe band.
LLM_TEMPERATURE_MIN = 0.2
LLM_TEMPERATURE_MAX = 0.6
CONTEXT_TOKEN_BUDGET = 24000      # model window is 32K; leave room for the reply
CHARS_PER_TOKEN = 3.0             # rough: Indic scripts tokenise denser than English

# ── TTS ───────────────────────────────────────────────────────────────────────
TTS_PACE = 1.0
TTS_V3_TEMPERATURE = 0.6          # bulbul:v3 only (v4-flash ignores temperature)
TTS_MIN_BUFFER = 30
TTS_MAX_CHUNK = 150


def clamp_temperature(creativity: float) -> float:
    """Map the agent's creativity slider (Qwen scale, 0.7 default) to Sarvam's safe band."""
    return round(min(LLM_TEMPERATURE_MAX, max(LLM_TEMPERATURE_MIN, creativity * 0.5)), 2)


def stt_mode(stt_code: str) -> str:
    return "codemix" if stt_code == STT_CODEMIX_LANG else "transcribe"


def turn_handling() -> TurnHandlingOptions:
    return TurnHandlingOptions(
        turn_detection="stt",
        endpointing={"mode": "fixed", "min_delay": 0.3, "max_delay": 2.5},
        interruption={
            "enabled": True,
            "mode": "vad",
            "min_words": 1,
            "false_interruption_timeout": 1.4,
            "resume_false_interruption": True,
        },
        # Sarvam advises leaving preemptive TTS off (wasted synthesis on wrong guesses).
        preemptive_generation={"enabled": True, "preemptive_tts": False},
        user_turn_limit={"max_duration": 45.0},
    )


# AgentSession kwargs specific to this engine: Sarvam's server-side VAD replaces
# LiveKit's Silero VAD; no echo-cancel warmup on a phone line; our own silence
# watchdog (agent.py) handles away/idle callers.
SESSION_KWARGS = {"vad": None, "aec_warmup_duration": None, "user_away_timeout": None}


@dataclass
class SarvamCallState:
    language: str
    voice_id: str
    cloned: bool
    languages: dict
    empty_replies: int = 0
    romanised_replies: int = 0
    extra: dict = field(default_factory=dict)

    @property
    def lang(self) -> dict:
        return self.languages[self.language]


def parse_meta(meta: dict) -> SarvamCallState:
    cfg = meta.get("sarvam") or {}
    langs = cfg.get("languages") or {}
    language = cfg.get("language")
    if language not in langs:
        raise ValueError(f"sarvam call config has no enabled language {language!r}")
    return SarvamCallState(language=language, voice_id=cfg["voice_id"], cloned=bool(cfg.get("cloned")), languages=langs)


def build_stt(state: SarvamCallState, prompt: str | None = None) -> sarvam.STTRealtime:
    return sarvam.STTRealtime(
        api_key=SARVAM_API_KEY,
        language=state.lang["stt"],
        stream_type=STT_STREAM_TYPE,
        mode=stt_mode(state.lang["stt"]),
        endpointing=STT_ENDPOINTING,
        sample_rate=STT_SAMPLE_RATE,
        prompt=(prompt or "")[:STT_PROMPT_MAX_CHARS] or None,
        vad_min_silence_ms=STT_VAD_MIN_SILENCE_MS,
        vad_min_speech_ms=STT_VAD_MIN_SPEECH_MS,
        vad_sot_threshold=STT_VAD_SOT_THRESHOLD,
    )


def build_llm(creativity: float) -> sarvam.LLM:
    # reasoning_effort=None turns thinking off (on by default): first-word
    # latency 0.11 s vs 0.42 s measured 2026-10-22, and a small max_tokens can
    # no longer be eaten by reasoning (finish_reason "length", empty content).
    return sarvam.LLM(
        model=SARVAM_PIPELINE_LLM_MODEL,
        api_key=SARVAM_API_KEY,
        reasoning_effort=None,
        max_tokens=SARVAM_PIPELINE_LLM_MAX_TOKENS,
        temperature=clamp_temperature(creativity),
    )


def _tts_kwargs(model: str, speaker: str, language_code: str) -> dict:
    kw = dict(
        model=model,  # always explicit: omitting it routes to v3
        speaker=speaker,
        target_language_code=language_code,
        speech_sample_rate=SARVAM_PIPELINE_TTS_SAMPLE_RATE,
        output_audio_codec=SARVAM_PIPELINE_TTS_CODEC,
        pace=TTS_PACE,
        enable_preprocessing=True,
        min_buffer_size=TTS_MIN_BUFFER,
        max_chunk_length=TTS_MAX_CHUNK,
        send_completion_event=True,
    )
    if model == "bulbul:v3":
        kw["temperature"] = TTS_V3_TEMPERATURE
    return kw


def build_tts(state: SarvamCallState) -> sarvam.TTS:
    lang = state.lang
    return sarvam.TTS(api_key=SARVAM_API_KEY, **_tts_kwargs(lang["tts_model"], state.voice_id, lang["tts"]))


def voice_for_language(state: SarvamCallState, target: dict) -> str:
    """Same persona family in the new language if it exists (ritu_hi_* -> ritu_mr_*,
    or the same v3 name), else that language's first voice of the same gender."""
    family = state.voice_id.split("_", 1)[0]
    voices = target["voices"]
    for v in voices:
        if v["id"] == family or v["id"].split("_", 1)[0] == family:
            return v["id"]
    current = next((v for lang in state.languages.values() for v in lang["voices"] if v["id"] == state.voice_id), None)
    gender = current["gender"] if current else None
    return next((v["id"] for v in voices if v["gender"] == gender), voices[0]["id"])


def switch_language(state: SarvamCallState, target_key: str, tts, stt_engine) -> bool:
    """Retarget STT, TTS (and voice) to target_key in place — no reconnect.
    Returns False when the language isn't enabled on this engine (the prompt
    tells the LLM to apologise and carry on, so nothing else to do)."""
    target = state.languages.get(target_key)
    if target is None:
        logger.warning("Language switch requested for %r — not enabled on this engine, ignored", target_key)
        return False
    stt_engine.update_options(language=target["stt"], mode=stt_mode(target["stt"]))
    if state.cloned:
        # Cross-lingual cloning: same voice_id, new target language.
        tts.update_options(target_language_code=target["clone"])
    else:
        voice = voice_for_language(state, target)
        kw = _tts_kwargs(target["tts_model"], voice, target["tts"])
        tts.update_options(**{k: kw[k] for k in ("model", "speaker", "target_language_code")},
                           **({"temperature": kw["temperature"]} if "temperature" in kw else {}))
        state.voice_id = voice
    state.language = target_key
    logger.info("Language switched mid-call → %s (engine=sarvam voice=%s)", target_key, state.voice_id)
    return True


def prompt_adapter(system_prompt: str, state: SarvamCallState) -> str:
    """Spoken-style block for this engine, appended AFTER the shared prompt
    (including any Prime Calling script and its fixed closing) — never edits it."""
    display = state.lang["display"]
    if state.language in ("hinglish", "hindi"):
        script = ("Write Hindi words in Devanagari script and English words in Latin letters, the way "
                  "bilingual Indians text — e.g. \"आपका order कब तक चाहिए?\". Never write Hindi in Roman letters.")
    elif state.language == "english":
        script = "Write plain Indian English."
    else:
        script = (f"Write {display} in its own native script, keeping English words (names, business terms) "
                  "in Latin letters. Never write it in Roman letters.")
    no_ji = [v["display"] for v in state.languages.values() if v.get("honorific", "ji") == ""]
    no_ji_rule = (
        f"- In {', '.join(no_ji)} never use the Hindi word 'ji' — including after switching into one of "
        "them mid-call; use the customer's name or address them plainly.\n"
    ) if no_ji else ""
    return (
        system_prompt
        + "\n\n[SPOKEN STYLE — your words are read aloud by a voice engine]\n"
        "- One or two short sentences per reply. No markdown, bullet points, lists or emoji.\n"
        f"- {script} If the call switches language, apply the same rule to the new language.\n"
        "- Write amounts and dates as they are spoken. Phone numbers and OTPs: digit by digit as rule 14 says.\n"
        "- Never address the customer as Sir or Ma'am.\n"
        + no_ji_rule
    )


_JI = re.compile(r"\s*(?<![\wऀ-෿])(?:ji|Ji|जी)(?![\wऀ-෿])")


def no_ji_transform(state: SarvamCallState):
    """TTS text transform: drop the Hindi honorific 'ji' while the call's CURRENT
    language must avoid it (honorific == ""). Prompt rules alone let it leak
    after a mid-call switch (seen live: "சரி ji," after Hinglish -> Tamil).
    Holds back the trailing partial word so 'ji' split across chunks is caught."""
    async def _filter(text_stream):
        buf = ""
        async for chunk in text_stream:
            buf += chunk
            cut = max(buf.rfind(" "), buf.rfind(","), buf.rfind("।"))
            if cut <= 0:
                continue
            out, buf = buf[:cut], buf[cut:]
            yield _JI.sub("", out) if state.lang.get("honorific", "ji") == "" else out
        if buf:
            yield _JI.sub("", buf) if state.lang.get("honorific", "ji") == "" else buf
    return _filter


_LATIN_WORD = re.compile(r"[A-Za-z]{2,}")
_INDIC = re.compile(r"[ऀ-෿]")


def looks_romanised(text: str, language: str) -> bool:
    """Cheap check for Indic text written in Roman letters (degrades TTS)."""
    if language == "english":
        return False
    return len(_LATIN_WORD.findall(text)) >= 4 and not _INDIC.search(text)


def estimate_tokens(chat_ctx) -> int:
    chars = 0
    for item in chat_ctx.items:
        content = getattr(item, "content", None)
        if isinstance(content, list):
            chars += sum(len(c) for c in content if isinstance(c, str))
        elif isinstance(content, str):
            chars += len(content)
    return int(chars / CHARS_PER_TOKEN)


def trim_to_budget(chat_ctx, budget: int = CONTEXT_TOKEN_BUDGET):
    """Copy of chat_ctx with the oldest user/assistant turns dropped until it
    fits. The system script is never trimmed."""
    ctx = chat_ctx.copy()
    while estimate_tokens(ctx) > budget:
        idx = next((i for i, it in enumerate(ctx.items) if getattr(it, "role", None) in ("user", "assistant")), None)
        if idx is None:
            break
        del ctx.items[idx]
    return ctx


def validate_components() -> None:
    """Construct every component once at worker start so a bad model name or
    voice fails loudly in the logs then, not on a live call."""
    sarvam.STTRealtime(api_key=SARVAM_API_KEY or "x", language="hi-IN", stream_type=STT_STREAM_TYPE)
    sarvam.LLM(model=SARVAM_PIPELINE_LLM_MODEL, api_key=SARVAM_API_KEY or "x")
    sarvam.TTS(api_key=SARVAM_API_KEY or "x", **_tts_kwargs("bulbul:v4-flash", "ritu_hi_conversation", "hi-IN"))
    sarvam.TTS(api_key=SARVAM_API_KEY or "x", **_tts_kwargs("bulbul:v3", "ritu", "hi-IN"))
