"""
sarvam_pipeline.py — the calling engine: Sarvam realtime STT +
sarvam-105b-conversations + Bulbul, for one call.

Provider construction, turn-handling values, cloned voices and the mid-call
language switch live here; call logic (tools, hang-up, silence/voicemail/IVR
handling, report) lives in agent.py.

The backend resolves everything per call and sends it as meta["sarvam"]
(see backend/app/core/pipelines.py sarvam_call_config): the call's language,
voice, whether it is a cloned voice, and every enabled language's codes,
TTS model and voices — so a mid-call switch needs no lookup.

Settings follow Sarvam's "LiveKit in Production" telephony guidance
(docs.sarvam.ai/api/integration/livekit-production-best-practices, read
2026-10-22). Every value is a named constant, overridable by env in config.py.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field

import aiohttp
from livekit.agents import APIConnectOptions, TurnHandlingOptions, tts as lk_tts, utils
from livekit.plugins import elevenlabs, sarvam

from config import (
    ELEVENLABS_API_KEY,
    SARVAM_API_KEY,
    SARVAM_PIPELINE_LLM_MAX_TOKENS,
    SARVAM_PIPELINE_LLM_MODEL,
    SARVAM_PIPELINE_TTS_CODEC,
    SARVAM_PIPELINE_TTS_SAMPLE_RATE,
)

logger = logging.getLogger("voice-agent")

PIPELINE = "sarvam"  # reported per call; the backend tracks calls by engine

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


# AgentSession kwargs: Sarvam's server-side VAD replaces a local VAD; no echo-cancel warmup on a phone line; our own silence
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
    state = SarvamCallState(language=language, voice_id=cfg["voice_id"], cloned=bool(cfg.get("cloned")), languages=langs)
    if not ELEVENLABS_API_KEY or state.cloned:
        # No ElevenLabs key (or a Sarvam cloned voice): everything is spoken by Sarvam.
        if state.lang.get("engine") == "elevenlabs":
            logger.warning("elevenlabs_unavailable | language=%s — using the Sarvam voice", language)
            state.voice_id = state.lang["sarvam_voice"]
        for lang in langs.values():
            lang["engine"] = "sarvam"
    return state


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


def build_tts(state: SarvamCallState):
    lang = state.lang
    if not state.cloned:
        voice = lang["sarvam_voice"] if lang.get("engine") == "elevenlabs" else state.voice_id
        return sarvam.TTS(api_key=SARVAM_API_KEY, **_tts_kwargs(lang["tts_model"], voice, lang["tts"]))
    # Cloned voice first; if it fails to start or dies mid-call the adapter
    # moves the rest of the call to a stock Sarvam voice in the same language
    # (still Sarvam — not a cross-vendor fallback). Never silent.
    fallback_voice = state.extra.setdefault("fallback_voice", lang["voices"][0]["id"])
    clone = SarvamCloneTTS(voice_id=state.voice_id, target_language_code=lang["clone"])
    stock = sarvam.TTS(api_key=SARVAM_API_KEY, **_tts_kwargs(lang["tts_model"], fallback_voice, lang["tts"]))
    adapter = lk_tts.FallbackAdapter([clone, stock], max_retry_per_tts=1)

    def _on_availability(ev) -> None:
        if ev.tts is clone and not ev.available and not state.extra.get("clone_fallback"):
            state.extra["clone_fallback"] = True
            logger.warning("clone_fallback | voice=%s fallback_voice=%s request_id=%s",
                           state.voice_id, fallback_voice, clone.last_request_id or "-")

    adapter.on("tts_availability_changed", _on_availability)
    return adapter


def build_eleven(state: SarvamCallState):
    """ElevenLabs speech for the regional languages the owner assigned it to, plus a Sarvam
    voice to fall back on. None when no language needs it. The call's session TTS stays
    Sarvam; VoiceAgent.tts_node routes by the current language through speak_regional()."""
    langs = {k: v for k, v in state.languages.items() if v.get("engine") == "elevenlabs"}
    if not langs:
        return None
    start = state.lang if state.lang.get("engine") == "elevenlabs" else next(iter(langs.values()))
    voice = state.voice_id if state.lang is start else start["voices"][0]["id"]
    eleven = elevenlabs.TTS(
        voice_id=voice, model=start["eleven_model"], language=start["eleven_code"],
        api_key=ELEVENLABS_API_KEY, encoding=f"pcm_{SARVAM_PIPELINE_TTS_SAMPLE_RATE}",
    )
    stock = sarvam.TTS(api_key=SARVAM_API_KEY, **_tts_kwargs(start["tts_model"], start["sarvam_voice"], start["tts"]))

    def _on_error(ev) -> None:
        # The plugin wraps the real reason ("Could not synthesize"); its cause says what happened.
        err = getattr(ev, "error", None)
        cause = getattr(err, "__cause__", None) or getattr(err, "body", None)
        logger.warning("eleven_error | voice=%s error=%s cause=%r", state.voice_id, err, cause)

    eleven.on("error", _on_error)
    state.extra.update(eleven=eleven, eleven_stock=stock, eleven_failures=0)
    return eleven


# A silent ElevenLabs request is given up on after this long and the Sarvam voice takes over.
ELEVEN_FIRST_AUDIO_TIMEOUT = 4.0
# Consecutive failed utterances after which the rest of the call stays on the Sarvam voice.
ELEVEN_MAX_FAILURES = 2


class _TextTee:
    """Lets two TTS engines read the same text stream, so a failed ElevenLabs request can be
    re-spoken whole by Sarvam without losing what the LLM already produced."""

    def __init__(self, source) -> None:
        self.chunks: list[str] = []
        self.done = False
        self.error: BaseException | None = None
        self._wake = asyncio.Event()
        self._task = asyncio.create_task(self._pump(source))

    async def _pump(self, source) -> None:
        try:
            async for chunk in source:
                self.chunks.append(chunk)
                self._notify()
        except Exception as exc:  # re-raised to whoever is reading
            self.error = exc
        finally:
            self.done = True
            self._notify()

    def _notify(self) -> None:
        old, self._wake = self._wake, asyncio.Event()
        old.set()

    async def reader(self):
        i = 0
        while True:
            wake = self._wake
            while i < len(self.chunks):
                yield self.chunks[i]
                i += 1
            if self.done:
                if self.error:
                    raise self.error
                return
            await wake.wait()

    async def close(self) -> None:
        await utils.aio.cancel_and_wait(self._task)


async def _stream_frames(engine, text, conn_options, first_audio_timeout: float | None = None):
    """Audio frames from one TTS engine for a text stream; raises if it fails or stays silent."""
    stream = engine.stream(conn_options=conn_options)

    async def _feed() -> None:
        async for chunk in text:
            stream.push_text(chunk)
        stream.end_input()

    feed = asyncio.create_task(_feed())
    try:
        async with stream:
            frames = stream.__aiter__()
            try:
                first = await asyncio.wait_for(frames.__anext__(), first_audio_timeout)
            except StopAsyncIteration:
                return
            yield first.frame
            async for ev in frames:
                yield ev.frame
    finally:
        await utils.aio.cancel_and_wait(feed)


async def speak_regional(state: SarvamCallState, text, conn_options):
    """Speak `text` in an ElevenLabs voice. One voice per utterance, always: if ElevenLabs fails
    before any audio, Sarvam speaks the whole utterance; if it fails midway, the utterance just
    ends (replaying it in a second voice made callers ask who else was talking)."""
    eleven, stock = state.extra["eleven"], state.extra["eleven_stock"]
    tee = _TextTee(text)
    try:
        if state.extra.get("eleven_failures", 0) < ELEVEN_MAX_FAILURES:
            spoke = False
            try:
                # one attempt only: the plugin's own retry would re-speak what was already played
                once = APIConnectOptions(max_retry=0, timeout=conn_options.timeout)
                async for frame in _stream_frames(eleven, tee.reader(), once, ELEVEN_FIRST_AUDIO_TIMEOUT):
                    spoke = True
                    yield frame
                state.extra["eleven_failures"] = 0
                return
            except Exception as exc:
                state.extra["eleven_failures"] = state.extra.get("eleven_failures", 0) + 1
                logger.warning("eleven_%s | voice=%s failures=%d error=%r",
                               "cut_off" if spoke else "fallback", state.voice_id, state.extra["eleven_failures"], exc)
                if spoke:
                    return
        async for frame in _stream_frames(stock, tee.reader(), conn_options):
            yield frame
    finally:
        await tee.close()


def eleven_voice_for(state: SarvamCallState, target: dict) -> str:
    """Same-gender ElevenLabs voice in the target language (keeps the current one if it's offered there)."""
    voices = target["voices"]
    if any(v["id"] == state.voice_id for v in voices):
        return state.voice_id
    current = next((v for lang in state.languages.values() for v in lang["voices"] if v["id"] == state.voice_id), None)
    gender = current["gender"] if current else None
    return next((v["id"] for v in voices if v["gender"] == gender), voices[0]["id"])


# ── Cloned voices (Sarvam Instant Voice Cloning, beta) ────────────────────────
# Same config/text/flush/ping WebSocket protocol as stock Bulbul (confirmed in
# the sarvamai 0.1.37 SDK: VoiceCloningConfigureConnection etc.), on a different
# endpoint and with voice_id instead of speaker/model — so the stock plugin's
# streaming, interruption, pooling, keep-alive and metrics are reused and only
# the outgoing config message is rewritten.
SARVAM_CLONE_WS_URL = "wss://api.sarvam.ai/voices/clone/ws"
_CLONE_CONFIG_FIELDS = (
    "target_language_code", "pace", "speech_sample_rate", "output_audio_codec",
    "output_audio_bitrate", "min_buffer_size", "max_chunk_length",
)


def _clone_config(data: str, voice_id: str) -> str:
    """Rewrite the plugin's stock-voice config message into the cloned-voice one;
    every other message passes through unchanged."""
    if '"type": "config"' not in data[:40]:
        return data
    stock = json.loads(data)["data"]
    cfg = {k: stock[k] for k in _CLONE_CONFIG_FIELDS if k in stock}
    # Must be target_language_code (a wrong field name is silently ignored);
    # enable_pretts is the cloning API's name for number/date normalisation.
    cfg.update(voice_id=voice_id, enable_pretts=True)
    return json.dumps({"type": "config", "data": cfg})


def _hook_socket(ws, owner: "SarvamCloneTTS"):
    """Patch THIS socket instance (not a proxy: the plugin tracks sockets by
    identity for its keep-alive task, so the object it gets must be the real one)."""
    send_str, receive = ws.send_str, ws.receive

    async def _send_str(data, *args, **kwargs):
        return await send_str(_clone_config(data, owner.voice_id), *args, **kwargs)

    async def _receive(*args, **kwargs):
        msg = await receive(*args, **kwargs)
        if msg.type == aiohttp.WSMsgType.TEXT and '"request_id"' in msg.data:
            try:
                rid = (json.loads(msg.data).get("data") or {}).get("request_id")
                if rid:
                    owner.last_request_id = rid
            except ValueError:
                pass
        return msg

    ws.send_str, ws.receive = _send_str, _receive
    return ws


class SarvamCloneTTS(sarvam.TTS):
    def __init__(self, *, voice_id: str, target_language_code: str, ws_url: str = SARVAM_CLONE_WS_URL,
                 api_key: str | None = None, http_session=None) -> None:
        # model/speaker only satisfy the parent's local checks; they're never sent.
        kw = _tts_kwargs("bulbul:v3", "ritu", target_language_code)
        kw.pop("model"), kw.pop("speaker"), kw.pop("target_language_code")
        super().__init__(api_key=api_key or SARVAM_API_KEY, model="bulbul:v3", speaker="ritu",
                         target_language_code=target_language_code, ws_url=ws_url,
                         http_session=http_session, **kw)
        self.voice_id = voice_id
        self.last_request_id = ""

    async def _connect_ws(self, timeout: float):
        return _hook_socket(await super()._connect_ws(timeout), self)


def voice_for_language(state: SarvamCallState, target: dict, voice_id: str | None = None) -> str:
    """Same persona family in the new language if it exists (ritu_hi_* -> ritu_mr_*,
    or the same v3 name), else that language's first voice of the same gender."""
    voice_id = voice_id or state.voice_id
    family = voice_id.split("_", 1)[0]
    voices = target["voices"]
    for v in voices:
        if v["id"] == family or v["id"].split("_", 1)[0] == family:
            return v["id"]
    current = next((v for lang in state.languages.values() for v in lang["voices"] if v["id"] == voice_id), None)
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
    stock_tts = tts
    if state.cloned:
        # Cross-lingual cloning: same voice_id, new target language. The stock
        # fallback voice behind it follows the language too.
        clone, stock_tts = tts._tts_instances
        clone.update_options(target_language_code=target["clone"])
    eleven = state.extra.get("eleven")
    if eleven is not None and target.get("engine") == "elevenlabs":
        voice = eleven_voice_for(state, target)
        eleven.update_options(voice_id=voice, model=target["eleven_model"], language=target["eleven_code"])
        sarvam_voice = target["sarvam_voice"]
    else:
        current = state.extra["fallback_voice"] if state.cloned else state.voice_id
        voice = voice_for_language(state, target, current)
        sarvam_voice = voice
    kw = _tts_kwargs(target["tts_model"], sarvam_voice, target["tts"])
    # The Sarvam engines (the call's TTS, and the fallback behind ElevenLabs) follow the language too.
    for engine in (stock_tts, state.extra.get("eleven_stock")):
        if engine is not None:
            engine.update_options(**{k: kw[k] for k in ("model", "speaker", "target_language_code")},
                                  **({"temperature": kw["temperature"]} if "temperature" in kw else {}))
    if state.cloned:
        state.extra["fallback_voice"] = voice
    else:
        state.voice_id = voice
    state.language = target_key
    logger.info("Language switched mid-call → %s (engine=%s voice=%s)", target_key, target.get("engine", "sarvam"), state.voice_id)
    return True


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
