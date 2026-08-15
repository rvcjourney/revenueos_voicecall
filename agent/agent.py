"""
agent.py — Hinglish Voice Sales Agent
Pipeline: Sarvam STT → Groq LLM → ElevenLabs/Sarvam/Cartesia/Chatterbox TTS (per-agent voice_provider)
"""

import os
import asyncio
import hashlib
import hmac
import json
import re
import time
import certifi
import structlog
from datetime import datetime
from zoneinfo import ZoneInfo

os.environ["SSL_CERT_FILE"]      = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

from livekit import agents
from livekit.agents import AgentSession, Agent, JobProcess, StopResponse, TurnHandlingOptions
from livekit.agents.llm import ChatContext
from livekit.agents.voice.room_io import RoomOptions
from livekit.plugins import groq, silero, elevenlabs, cartesia, sarvam
from livekit.plugins.turn_detector.multilingual import MultilingualModel
import chatterbox_tts

from config import (
    AGENT_SYSTEM_PROMPT,
    AGENT_WELCOME_MESSAGE,
    LIVEKIT_AGENT_NAME,
    GROQ_MODEL,
    GROQ_LLM_TEMPERATURE,
    ELEVENLABS_API_KEY,
    ELEVENLABS_VOICE_ID,
    ELEVENLABS_MODEL_ID,
    CARTESIA_API_KEY,
    CARTESIA_VOICE_ID,
    CARTESIA_MODEL_ID,
    CHATTERBOX_BASE_URL,
    CHATTERBOX_VOICE_ID,
    CHATTERBOX_LANGUAGE,
    CHATTERBOX_SAMPLE_RATE,
    CHATTERBOX_VOICE_MODE,
    SARVAM_API_KEY,
    SARVAM_MODEL,
    SARVAM_VOICE_ID,
    SARVAM_SAMPLE_RATE,
    SARVAM_STT_MODEL,
    SARVAM_STT_MODE,
    SARVAM_STT_LANGUAGE,
    BACKEND_INTERNAL_URL,
    AGENT_WEBHOOK_SECRET,
    FAILED_REPORTS_PATH,
    validate_config,
)
from logging_config import configure_logging, init_sentry, set_log_context

# ── Logging ───────────────────────────────────────────────────────────────────
configure_logging()
init_sentry()
logger = structlog.get_logger("voice-agent")

# ── Constants ─────────────────────────────────────────────────────────────────
_LLM_MAX_TOKENS = 400  # must be high enough for tool-call JSON + speech prefix (~120 tokens); 110 caused Groq "Failed to call a function" truncation errors

# Smallest schedule ElevenLabs allows (floor is 50/chunk): once a chunk's audio
# starts playing it can't be recalled, so a caller's interruption can only take
# effect at the next chunk boundary. Large chunks (this was [120, 200, 280, 360])
# meant that boundary could be a full sentence away, so an interruption only cut
# the agent off after it finished speaking — this shrinks that window to a few
# words at most, at the cost of very slightly more segmented prosody between chunks.
_CHUNK_LENGTH_SCHEDULE = [50, 90, 120, 150]


def _safe_task(coro, name: str = "") -> asyncio.Task:
    """create_task wrapper that logs instead of raising 'Future exception was never retrieved'."""
    task = asyncio.create_task(coro)
    def _on_done(t: asyncio.Task) -> None:
        if not t.cancelled() and (exc := t.exception()) is not None:
            # Was logger.debug — background tasks include the report-posting paths
            # (voicemail/bot/keyword hangups, disconnect handler), so a debug-level
            # log here meant a lost call report never showed up anywhere anyone
            # would actually look.
            logger.error("background task %s raised: %s", name or repr(coro), exc)
    task.add_done_callback(_on_done)
    return task


def _persist_failed_report(call_id: str | None, payload: dict, error: Exception) -> None:
    """Last-resort durable fallback when agent-report POSTs exhaust all retries.

    The transcript/summary/extracted_data only ever exist in this process's memory —
    once it exits, an undelivered report is gone for good unless it's written
    somewhere first. Appends one JSON line per failure; replay with
    replay_failed_reports.py once the backend is reachable again.
    """
    try:
        entry = {
            "call_id": call_id,
            "failed_at": datetime.now(ZoneInfo("UTC")).isoformat(),
            "error": str(error),
            "payload": payload,
        }
        with open(FAILED_REPORTS_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as exc:
        logger.error("failed_report_persist_error | call=%s error=%s", call_id, exc)


def _sign_webhook_body(body: bytes) -> str:
    """Mirrors app/core/security.py:sign_webhook_payload() on the backend --
    a separate implementation (this is a different Python process/codebase)
    of the exact same HMAC-SHA256 scheme, so app/api/agent_internal.py's
    verify_webhook_signature() can check it."""
    ts = int(time.time())
    signed = f"{ts}.".encode() + body
    mac = hmac.new(AGENT_WEBHOOK_SECRET.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


async def _resolve_inbound_call(meta: dict, participant, room_name: str) -> dict | None:
    """
    Called once for every inbound call, right after the SIP participant joins.
    Reads which number was dialed off the participant's SIP attributes, asks
    the backend which InboundAgentTemplate answers it (and has it create the
    Call row -- inbound calls have no campaign/test-call flow to do that
    ahead of time the way outbound does), and returns a dict shaped exactly
    like the fields entrypoint() already reads from outbound room metadata.

    Returns None if the call can't be resolved (backend down, number not
    configured for inbound, etc.) -- entrypoint() hangs up in that case.
    """
    import httpx

    sip_trunk_id = meta.get("sip_trunk_id", "")
    attrs = dict(getattr(participant, "attributes", None) or {})
    # NOTE: standard LiveKit SIP attribute keys -- log the full set below so a
    # live inbound test call can confirm/correct these if this project's
    # LiveKit Cloud version names them differently.
    from_number = attrs.get("sip.phoneNumber", "")
    to_number = attrs.get("sip.trunkPhoneNumber", "")
    logger.info(
        "inbound_participant_attributes | sip_trunk_id=%s from=%s to=%s all=%s",
        sip_trunk_id, from_number, to_number, attrs,
    )

    if not sip_trunk_id:
        logger.error("inbound_call_missing_sip_trunk_id | room metadata=%s", meta)
        return None

    payload = {
        "sip_trunk_id": sip_trunk_id,
        "room_name": room_name,
        "from_number": from_number,
        "to_number": to_number,
    }
    body = json.dumps(payload).encode()
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Signature": _sign_webhook_body(body),
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as http:
            resp = await http.post(
                f"{BACKEND_INTERNAL_URL}/api/internal/inbound/start",
                content=body,
                headers=headers,
            )
        if resp.status_code != 200:
            logger.error("inbound_resolve_failed | status=%s body=%s", resp.status_code, resp.text[:500])
            return None
        return resp.json()
    except Exception as exc:
        logger.error("inbound_resolve_error | %s", exc)
        return None


# =============================================================================
# Groq LLM wrapper — caps max_tokens on every call
# =============================================================================
# Reasoning models add real chain-of-thought latency before the visible answer
# even at their lowest setting -- openai/gpt-oss-20b/120b can only go as low as
# "low" (confirmed in the installed livekit-plugins-groq SDK, which auto-sets
# reasoning_effort="low" for those two models and nothing lower is available),
# which measured as an 18s+ welcome-message delay in real testing. qwen/qwen3.6-27b
# is the one model on this list that supports a genuine non-thinking mode via
# reasoning_effort="none" -- explicitly forced here since the installed SDK
# version predates this model and has no built-in default for it (it would
# otherwise fall through to Groq's server-side default, which is "default"/
# thinking-mode-on).
_REASONING_EFFORT_OVERRIDES = {
    "qwen/qwen3.6-27b": "none",
}

# Confirmed via a real 400 from Groq: "failed to template request: ... minijinja:
# rendering failed: raise_exception: No user query found in messages." -- this
# model's chat template hard-rejects a request containing only a system prompt
# and no user turn, which is exactly how the welcome message is generated (no
# customer has spoken yet). Every other model tolerates this; only listing the
# ones confirmed to need the workaround in on_enter() below.
_NEEDS_SYNTHETIC_FIRST_TURN = {"qwen/qwen3.6-27b"}


class _CappedGroqLLM(groq.LLM):
    def chat(self, *, chat_ctx, **kwargs):
        ek = dict(kwargs.pop("extra_kwargs", {}) or {})
        ek.setdefault("max_tokens", _LLM_MAX_TOKENS)
        return super().chat(chat_ctx=chat_ctx, extra_kwargs=ek, **kwargs)


# ── Hangup detection ──────────────────────────────────────────────────────────
# Sarvam's STT transcribes Hindi words in Devanagari script even in codemix mode
# (confirmed against real call transcripts — e.g. "नहीं", not "nahi") while
# English loanwords ("bye", "ok", "interested") stay in Latin script. Every
# Hindi word below is matched in BOTH scripts for exactly this reason — the
# original Latin-only version of this pattern (alvida/chalta hoon/band karo/...)
# was very likely never matching a single real Hindi-spoken hangup, since real
# transcripts never come back romanized.
_alvida  = r"(?:alvida|अलविदा)"
_chalta  = r"(?:chalta|चलता)"
_chalti  = r"(?:chalti|चलती)"
_nikalta = r"(?:nikalta|निकलता)"
_nikalti = r"(?:nikalti|निकलती)"
_hoon    = r"(?:hoon|hu|हूँ|हूं)"
_phone   = r"(?:phone|फोन)"
_rakhna  = r"(?:rakhna|रखना)"
_rakh    = r"(?:rakh|रख)"
_band    = r"(?:band|बंद)"
_karo    = r"(?:karo|करो)"
_rakho   = r"(?:rakho|रखो)"
_do_w    = r"(?:do|दो)"
_call_w  = r"(?:call|कॉल)"
_khatam  = r"(?:khatam|khatm|खतम|ख़त्म)"
_karte   = r"(?:karte|करते)"
_hain    = r"(?:hain|हैं)"
_rakhta  = r"(?:rakhta|रखता)"
_rakhti  = r"(?:rakhti|रखती)"
_rahi    = r"(?:rahi|रही)"
_chalo   = r"(?:chalo|चलो)"
_theek   = r"(?:theek|ठीक)"
_hai_w   = r"(?:hai|है)"
_ji_w    = r"(?:ji|जी)"
_accha   = r"(?:accha|अच्छा)"
_interest = r"interest(?:ed)?"  # "interest" and "interested" both occur in real transcripts
_nahi_w   = r"(?:nahi|नहीं)"
# Up to 2 filler words between the negation and "interest"/"chahiye" -- real
# speech doesn't always put them adjacent (e.g. "interest भी नहीं है" has
# "bhi"/"hai" in between). Bounded rather than unbounded so an unrelated "nahi"
# elsewhere in a longer sentence ("interested hoon, bas price ki clarity nahi
# hai") can't falsely trigger a hangup on a customer who's still interested.
_GAP      = r"(?:\s+\S+){0,2}\s+"

# Devanagari letters are built from a base consonant plus separate combining
# vowel-sign codepoints (matras) -- Python's stdlib `re` module's \b/\w do NOT
# treat those combining marks as word characters, so \b silently splits a word
# like "अलविदा" mid-letter and never matches it with a trailing \b (confirmed:
# \b-wrapped Devanagari alternatives never matched ANY real or synthetic test
# string). These lookarounds define "boundary" as "not touching another
# non-space, non-punctuation character" instead -- script-agnostic, and still
# allows punctuation with no space before it (real transcripts do this, e.g.
# "interested. Thank you").
_LB = r"(?<![^\s.,!?;:\"'()\-])"
_LA = r"(?![^\s.,!?;:\"'()\-])"

_HANGUP_RE = re.compile(
    _LB + r"(" +
    # Universal — these words are ONLY ever used to end a call
    rf"bye|goodbye|{_alvida}"
    # Hinglish bye combos ("bye"/"ok" stay Latin as English loanwords)
    rf"|ok\s*bye|{_chalo}\s*bye|{_theek}\s*{_hai_w}\s*bye|ok\s+{_ji_w}\s+bye|{_accha}\s+bye"
    # "I'm heading off" — very unambiguous phone-enders
    rf"|{_chalta}\s+{_hoon}|{_chalti}\s+{_hoon}|{_nikalta}\s+{_hoon}|{_nikalti}\s+{_hoon}"
    # Putting down the phone — only said when actually ending
    rf"|{_phone}\s+{_rakhna}|{_phone}\s+{_rakh}|{_band}\s+{_karo}|{_rakho}\s+{_phone}|{_rakh}\s+{_do_w}"
    rf"|{_call_w}\s+{_khatam}|{_khatam}\s+{_karte}\s+{_hain}"
    rf"|{_rakhta}\s+{_hoon}|{_rakhti}\s+{_hoon}|{_rakh}\s+{_rahi}\s+{_hoon}"
    # Firm rejection — customer isn't just pausing/thinking, they've said no.
    # A clear decline should end the call at ANY turn count (see _trigger_hangup's
    # firm_decline check below) — nothing to gain by continuing to pitch someone
    # who has already refused.
    r"|not\s+interested|no\s+thanks|no\s+thank\s+you"
    rf"|{_nahi_w}{_GAP}{_interest}|{_interest}{_GAP}{_nahi_w}"
    rf"|{_nahi_w}\s*(?:hai\s*)?चाहिए|चाहिए\s*{_nahi_w}"
    # System-level
    r"|disconnect|hang\s*up|call\s+end"
    r")" + _LA,
    re.IGNORECASE | re.UNICODE,
)
_FAREWELL = "Bahut shukriya ji, aapka time dene ke liye! Take care, Bye"

# ── Silence / voicemail / bot detection ───────────────────────────────────────
_SILENCE_INITIAL_SLEEP  = 15.0   # initial wait (covers welcome TTS playback + response window)
_SILENCE_FIRST_TIMEOUT  = 18.0   # seconds of no user speech before first probe
_SILENCE_PROBE_INTERVAL = 10.0   # seconds between subsequent probes
_SILENCE_PROBES = [
    "Hello ji? Kya aap sun rahe hain mujhe? Am I audible?",
    "Koi awaaz nahi aa rahi aapki taraf se. Are you still there?",
]

# ── Time-of-day greeting + gender-neutral address ─────────────────────────────
# Every campaign in this system already defaults to "Asia/Kolkata" when no
# timezone is configured (see Campaign.timezone / _in_calling_window in
# backend/app/workers/tasks/campaign.py) — reuse the same default here so a
# stored welcome_message's greeting always matches the real time of the call,
# and never assumes the customer's gender via "Sir"/"Ma'am".
_GREETING_RE = re.compile(r"\bgood\s+(morning|afternoon|evening|night)\b", re.IGNORECASE)
_HONORIFIC_RE = re.compile(r"\b(sir|ma'?am|madam)\b", re.IGNORECASE)


def _time_of_day_greeting(tz_name: str = "Asia/Kolkata") -> str:
    try:
        hour = datetime.now(ZoneInfo(tz_name)).hour
    except Exception:
        # Covers ZoneInfoNotFoundError (bad tz name) AND the IANA tzdata
        # package being entirely unavailable (e.g. Windows / slim Docker
        # images without the `tzdata` PyPI package) — never let a timezone
        # lookup failure crash the whole call. Falls back to system local
        # time, which is still correct for the single-region (India) case
        # this deployment runs in.
        hour = datetime.now().hour
    if hour < 12:
        return "Good Morning"
    if hour < 17:
        return "Good Afternoon"
    return "Good Evening"


def _localize_welcome_message(text: str, tz_name: str = "Asia/Kolkata") -> str:
    """Correct a stored welcome_message's time-of-day greeting to match right now,
    and swap gendered honorifics for the neutral Hinglish "ji" — same message,
    spoken at the right time to the right person."""
    if not text:
        return text
    try:
        corrected = _GREETING_RE.sub(_time_of_day_greeting(tz_name), text)
        corrected = _HONORIFIC_RE.sub("ji", corrected)
        return corrected
    except Exception:
        logger.warning("greeting localization failed — using original text unchanged", exc_info=True)
        return text


_HONORIFIC_GREETING_RE = re.compile(
    r"\bgood\s+(?:morning|afternoon|evening|night)\b|\b(?:sir|ma'?am|madam)\b",
    re.IGNORECASE,
)


def _honorific_greeting_filter_transform(tz_name: str = "Asia/Kolkata"):
    """Backstop for the LIVE TTS stream, not just the pre-corrected welcome_message text.
    Guardrail 1a tells the LLM not to say "Sir"/"Ma'am" and to use the right time-of-day
    greeting, but that's a soft instruction — the LLM can still improvise it on the opening
    line ("speak naturally") or later in the call. Rewrite every chunk deterministically so
    a wrong honorific/greeting can never actually reach the caller.

    A match is only substituted once `tail` further characters have arrived after it —
    i.e. once its right word-boundary is confirmed by text actually received, not just
    "nothing else happened to arrive yet". Without that, a chunk boundary landing right
    after "Sir" (before the "f" of "Sirf" arrives) would wrongly treat "Sir" as a whole
    word and mangle it into "jif"."""
    tail = max(len("good afternoon"), len("madam")) - 1
    greeting = _time_of_day_greeting(tz_name)

    def _replace(m: re.Match) -> str:
        return greeting if m.group(0)[0].lower() == "g" else "ji"

    async def _filter(text_stream):
        buf = ""
        async for chunk in text_stream:
            buf += chunk
            confirmed_end = len(buf) - tail
            if confirmed_end > 0:
                # Build output from the matches themselves (using their real position in
                # `buf`, which already has `tail` chars of real lookahead past them) rather
                # than slicing off a prefix and re-running the regex on it in isolation —
                # re-matching an isolated slice loses that lookahead and reintroduces the
                # exact false-positive ("Sirf" split right after "Sir") this is guarding against.
                out_end = confirmed_end
                parts, last = [], 0
                for m in _HONORIFIC_GREETING_RE.finditer(buf):
                    if m.end() > confirmed_end:
                        out_end = min(out_end, m.start())
                        break
                    parts.append(buf[last:m.start()])
                    parts.append(_replace(m))
                    last = m.end()
                if out_end > 0:
                    parts.append(buf[last:out_end])
                    yield "".join(parts)
                    buf = buf[out_end:]
        if buf:
            yield _HONORIFIC_GREETING_RE.sub(_replace, buf)

    return _filter


_DIGIT_RUN_RE = re.compile(r"\b\d(?:[ \-]?\d){6,}\b")
# A digit run still being dictated, touching the end of the buffered text so far —
# either mid-digit or on a dangling separator waiting for the next digit. Used to
# hold back output rather than flush a short prefix (e.g. "788") before the rest
# of the number ("7881708") arrives in a later chunk.
_TRAILING_DIGIT_RUN_RE = re.compile(r"\d(?:[ \-]?\d)*[ \-]?$")
_DIGIT_WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine")


def _digit_spellout_transform():
    """Backstop for phone numbers / OTPs read back to the customer.

    Guardrail 14 asks the LLM to speak digit sequences as English words (never
    Hindi 'ek/do/teen...'), but that's a soft instruction — the LLM can still
    emit a bare numeral string or Hindi words. Rewrite any run of 7+ digits
    deterministically into spelled-out English digit words before it reaches
    TTS, so a hi-IN-configured voice (Sarvam Bulbul, Chatterbox) can't localize
    a bare numeral into Hindi number words.

    Same "confirmed match" buffering as _honorific_greeting_filter_transform,
    plus an extra guard: a short digit run (fewer than 7 digits so far) touching
    the tail of the buffer doesn't match _DIGIT_RUN_RE at all yet, so without
    this it would get flushed as bare digits before the rest of the number
    arrives in the next chunk. _TRAILING_DIGIT_RUN_RE catches that in-progress
    run (of any length) and holds it back too.
    """
    tail = 2

    def _spell(m: re.Match) -> str:
        digits = re.sub(r"\D", "", m.group(0))
        return " ".join(_DIGIT_WORDS[int(d)] for d in digits)

    async def _filter(text_stream):
        buf = ""
        async for chunk in text_stream:
            buf += chunk
            confirmed_end = len(buf) - tail
            if confirmed_end > 0:
                out_end = confirmed_end
                parts, last = [], 0
                for m in _DIGIT_RUN_RE.finditer(buf):
                    if m.end() > confirmed_end:
                        out_end = min(out_end, m.start())
                        break
                    parts.append(buf[last:m.start()])
                    parts.append(_spell(m))
                    last = m.end()
                trailing = _TRAILING_DIGIT_RUN_RE.search(buf, last)
                if trailing:
                    out_end = min(out_end, trailing.start())
                if out_end > last:
                    parts.append(buf[last:out_end])
                if out_end > 0:
                    yield "".join(parts)
                    buf = buf[out_end:]
        if buf:
            yield _DIGIT_RUN_RE.sub(_spell, buf)

    return _filter

_VOICEMAIL_RE = re.compile(
    r"\b("
    r"please leave (a |your )?message"
    r"|leave (a |your )?message after (the )?(beep|tone)"
    r"|not available to take your call"
    r"|(person|number) you (are|were) trying to reach (is|are) not available"
    r"|(this |the )?(mailbox|inbox) (is full|has not been set up)"
    r"|this mailbox"
    r"|record (your |a )?message"  # was ...(after|at) the (beep|tone) -- too narrow,
                                   # missed real greetings where "at the tone" comes
                                   # BEFORE "record your message", not immediately after
    r"|recording will (begin|start)"
    r"|after the (beep|tone)"
    r"|at the (beep|tone)"
    r"|reached (my |the )?(voicemail|voice mail)"
    r"|forwarded to (voice ?mail|voice mail box)"  # distinct from a live-person call
                                   # forward -- _FORWARDING_RE's generic "call...forward"
                                   # pattern would otherwise catch this first and miss
                                   # tagging it as voicemail specifically
    r"|voicemail (service|box)"
    r"|(you may|please) (now )?hang up"  # near-exclusively an automated-message phrase
    r"|when (you have|you're) finished recording"
    r")\b",
    re.IGNORECASE | re.UNICODE,
)

_BOT_IVR_RE = re.compile(
    r"\b("
    r"press \d (for|to)"
    r"|for (english|hindi|option \d) press"
    r"|dial \d"
    r"|to return to (the )?main menu"
    r"|all (our )?(agents|operators|representatives) are (busy|unavailable|currently busy)"
    r"|your call is (important|being (monitored|recorded))"
    r"|please hold (while|for)"
    r"|estimated wait time"
    r"|(you are|you have been) placed in (a )?queue"
    r"|this is an? (automated|recorded) (message|call|system)"
    r")\b",
    re.IGNORECASE | re.UNICODE,
)

# Carrier / network call-forwarding announcements. SIP "answered" (200 OK) fires the
# moment the forward destination's line picks up -- which may be a network announcement
# rather than the actual person, and none of that announcement's phrasing matches
# _VOICEMAIL_RE or _BOT_IVR_RE above. Covers common English carrier wording plus
# transliterated Hinglish, since outbound trunks here are Indian carriers.
_FORWARDING_RE = re.compile(
    r"\b("
    r"call is being forwarded"
    r"|(is |being )?divert(ed|ing) your call"
    r"|forwarding your call"
    r"|call.{0,15}forward"
    r"|number you (have )?(dialed|called) (is|has been) (forwarded|diverted)"
    r"|please wait while we (forward|divert|connect) your call"
    r"|call forward ki ja rahi hai"
    r"|aapki call forward"
    r"|call ko forward kiya ja raha hai"
    r"|call divert kiya ja raha hai"
    r")\b",
    re.IGNORECASE | re.UNICODE,
)

# Strips "end_call" text (and Llama tool-call leakage variants) before TTS.
_END_CALL_STRIP_RE = re.compile(
    r'(?:function\s+)?[\[\(]?\bend[_\s]call\b[\]\)]?(?:\s+function)?'
    r'|\{[^{}]*\bend[_\s]call\b[^{}]*\}',
    re.IGNORECASE,
)


def _end_call_filter_transform(hangup_fn):
    tail = len("end_call") - 1  # rolling buffer so split tokens aren't missed

    async def _filter(text_stream):
        buf = ""
        fired = False
        async for chunk in text_stream:
            buf += chunk
            if not fired and _END_CALL_STRIP_RE.search(buf):
                fired = True
                _safe_task(hangup_fn(), "hangup-from-tts-filter")
                buf = _END_CALL_STRIP_RE.sub("", buf).strip()
            if len(buf) > tail:
                yield buf[:-tail]
                buf = buf[-tail:]
        if buf:
            if not fired:
                buf = _END_CALL_STRIP_RE.sub("", buf).strip()
            if buf:
                yield buf

    return _filter


# ── System prompt guardrails ──────────────────────────────────────────────────
def _build_prompt(raw: str, welcome_message: str = "", language: str = "hinglish") -> str:
    p = raw.strip()

    # Inject the welcome message as a first-turn instruction.
    # This makes the LLM generate the opening through the same streaming
    # LLM→TTS pipeline as every other turn — identical voice tone and prosody.
    # (session.say() sends a static text block to ElevenLabs which produces
    #  a noticeably different prosody from streamed LLM output.)
    opening_block = ""
    if welcome_message and welcome_message.strip():
        opening_block = (
            "[FIRST TURN — no customer input yet]\n"
            f'Open the call with this line, spoken naturally: "{welcome_message.strip()}"\n'
            "This line's time-of-day greeting and address term are already correct for right "
            "now — say it as-is, naturally, like a real person on the phone, not read off a script.\n"
            "Then stop immediately and wait for the customer to respond.\n\n"
        )

    guardrails = (
        "[ABSOLUTE RULES — never break these]\n"
        "1. Speak like a real Indian salesperson on a phone call — warm, natural, confident. "
        "Replies should feel human and conversational. Usually 1-2 sentences, occasionally 3 if needed. "
        "Never lecture. Never sound robotic or scripted.\n"
        "1a. Never assume or state the customer's gender. Do not address them as 'Sir' or 'Ma'am' — "
        "use the warm, gender-neutral Hinglish 'ji', or their name once you know it.\n"
        "2. Keep the SAME tone and energy from the very first word to the last — consistent warmth throughout.\n"
        "3. Never invent product grades, prices, or specs not in your instructions.\n"
        "4. Never reveal you are an AI, chatbot, or language model.\n"
        "5. Never use bullet points, lists, numbers, or markdown — this is a phone call, speak naturally.\n"
        "6. If unsure about anything: politely say you will confirm and get back.\n"
        "7. Never ask more than ONE question per reply.\n"
        "8. Stay in character at ALL times as described in your instructions.\n"
        f"9. LANGUAGE — you MUST speak in {language.upper()} for the ENTIRE call. "
        "Never switch language mid-conversation regardless of what the customer speaks. "
        "If the customer speaks English, Hindi, or anything else — you still respond in "
        f"{language.upper()} only. Consistent language from first word to last.\n"
        "10. ONLY discuss topics related to this sales call. Politely redirect off-topic questions.\n"
        "11. To end the call: first say a complete warm goodbye OUT LOUD "
        "(e.g. 'Bahut shukriya ji, koi zaroorat ho toh zaroor call karein, take care!'), "
        "then immediately output the EXACT text [end_call] on its own. "
        "The system will end the call automatically — never say 'end_call' as a spoken word.\n"
        "12. Only end the call when ALL of these are true:\n"
        "    (A) At least 5 back-and-forth exchanges have happened.\n"
        "    (B) If the customer showed ANY interest, you have already asked for their WhatsApp or email.\n"
        "    (C) The customer has clearly said goodbye OR firmly rejected: "
        "bye / goodbye / alvida / ok bye / chalo bye / theek hai bye / "
        "band karo / call khatam / rakhta hoon / rakhti hoon / nahi chahiye / mat karo call.\n"
        "These are NOT goodbyes — never end for them: "
        "ok / theek hai / accha / haan / hmm / ji / bilkul / shukriya / phir milenge / sochta hoon.\n"
        "If ANY condition is not met — keep the conversation going. "
        "If the customer has not given contact info yet, ask: "
        "'Ek kaam karo ji, aapka WhatsApp number de do — main catalogue bhej deta hoon.' "
        "Never end early.\n"
        "13. TELLING REAL INTEREST FROM POLITENESS — words like 'haan', 'theek hai', 'accha', "
        "'ok', 'hmm', 'ji', 'bilkul' are just the customer being polite or listening — they are "
        "NOT interest. Never treat them as a buying signal, never skip ahead to pitching harder "
        "or asking for contact info just because you heard one of these. To confirm real interest, "
        "ask a direct question about their actual need, current usage, budget, or timeline, and "
        "judge the ANSWER — a specific question back from them, a clear 'yes I want this', or "
        "agreeing to receive info/catalogue/quote are real signals; a one-word acknowledgement is "
        "not. If after 2-3 such questions the customer keeps giving only vague one-word replies "
        "with no real engagement, treat them as not interested and close the call politely and "
        "briefly — do not keep pushing a disinterested person, it wastes the call and sounds dumb.\n"
        "14. VALIDATING PHONE / WHATSAPP NUMBERS — a real Indian mobile number has exactly 10 "
        "digits and starts with 6, 7, 8, or 9. When the customer speaks a number, listen for "
        "this shape. If what you hear has the wrong number of digits, is an obvious non-number "
        "(all the same digit repeated, a plain sequence like 123456789 or 0000000000), or was "
        "unclear/cut off, do NOT accept it silently — say so naturally, e.g. 'Ji ye number thoda "
        "sahi se nahi aaya, ek baar phir se, dheere dheere digit by digit bata dijiye' and ask "
        "again. Once you have a number that looks like a real 10-digit mobile number, always "
        "read it back to the customer digit-by-digit to confirm before moving on or ending the "
        "call. IMPORTANT — when reading digits back (phone numbers, OTPs, any numeric sequence), "
        "always say them as ENGLISH digit words: 'one', 'two', 'three', 'four', 'five', 'six', "
        "'seven', 'eight', 'nine', 'zero' — never as Hindi digit words ('ek', 'do', 'teen', 'saat', "
        "'aath'...). This is the one exception to rule 9's 'speak only in that language' rule — "
        "digits are always English words even mid-Hinglish-sentence. "
        "Do the same for an email address — if it sounds incomplete or malformed (no '@', "
        "no domain), ask them to repeat or spell it. This check still applies even if the customer "
        "says the number in the very same breath as 'bye' or hangs up right after — a goodbye "
        "never excuses skipping the number check. If a customer says goodbye while leaving you an "
        "invalid number, your reply must still ask them to repeat it clearly before you say your "
        "own farewell — never let the word 'bye' from the customer make you accept a bad number "
        "silently.\n"
    )
    return opening_block + guardrails + "\n" + p

# =============================================================================
# LLM WARMUP
# =============================================================================
async def _warmup_llm(llm: _CappedGroqLLM, system_prompt: str = "") -> None:
    """
    Send a real warmup call to Groq using the actual system prompt so Groq
    pre-loads and caches the full context. Without this, the first real turn
    is slow because Groq processes a large system prompt cold.
    """
    try:
        ctx = ChatContext()
        if system_prompt:
            ctx.add_message(role="system", content=system_prompt)
        ctx.add_message(role="user", content="Namaste")
        async with llm.chat(chat_ctx=ctx, extra_kwargs={"max_tokens": 8}) as stream:
            async for _ in stream:
                break
        logger.info("LLM pre-warmed with system prompt ✓")
    except Exception as e:
        logger.debug("LLM warmup skipped: %s", e)


# =============================================================================
# PREWARM — runs once per worker process on startup
# =============================================================================
def prewarm(proc: JobProcess) -> None:
    proc.userdata["vad"] = silero.VAD.load(
        min_speech_duration     = 0.20,  # require ~200ms of sustained speech-like audio before
                                          # VAD confirms onset — rejects short noise transients
                                          # (clicks/coughs/horns) without missing real words
        min_silence_duration    = 0.5,   # was 0.35 — too short for the natural pauses between
                                          # digit groups when a customer dictates a phone number,
                                          # causing premature end-of-turn mid-number
        activation_threshold    = 0.88,
        deactivation_threshold  = 0.40,
        sample_rate             = 8000,
    )
    logger.info("VAD loaded in prewarm ✓")


# =============================================================================
# AGENT
# =============================================================================
class VoiceAgent(Agent):
    def __init__(
        self, room, *,
        instructions: str,
        welcome_message: str,
        call_id: str = "",
        backend_url: str = "",
        webhook_secret: str = "",
    ) -> None:
        self._room            = room
        self._ending          = False
        self._reported        = False
        self._welcome_message = welcome_message
        self._call_id         = call_id
        self._backend_url     = backend_url
        self._webhook_secret  = webhook_secret
        self._user_messages: list[str] = []
        self._turn_count      = 0
        self._last_user_activity = 0.0  # time.monotonic() — updated on user speech
        self._probing = False  # True while _silence_watchdog's own say() is in flight
        self._speaking_done = asyncio.Event()
        self._speaking_done.set()  # not speaking initially

        super().__init__(instructions=instructions)

    async def _disconnect(self) -> None:
        try:
            self.session.shutdown(drain=False)
        except Exception as e:
            logger.debug("session.shutdown: %s", e)
        try:
            await self._room.disconnect()
            logger.info("Room disconnected ✓")
        except Exception as e:
            logger.warning("room.disconnect: %s", e)

    async def _trigger_hangup(self) -> None:
        """Called when agent's own speech contains [end_call] — agent already said goodbye."""
        if self._ending:
            return
        # A customer who just firmly declined ("not interested", "nahi chahiye", "bye"...)
        # should be allowed to end the call at ANY turn count -- the <5 floor below exists
        # to catch the LLM bailing too early with no real signal from the customer yet
        # (e.g. after a single "haan"), not to force it to keep pitching someone who has
        # already said no. Real bug this fixed: customer declined at turn 4, got stuck in
        # silence probes for the rest of the call instead of a clean goodbye.
        last_user_text = self._user_messages[-1] if self._user_messages else ""
        firm_decline = bool(_HANGUP_RE.search(last_user_text))
        if self._turn_count < 5 and not firm_decline:
            # LLM generated [end_call] too early — suppress and let conversation continue
            logger.warning("[end_call] at turn %d (<5) — suppressing early exit", self._turn_count)
            return
        logger.info("TTS filter: [end_call] detected at turn %d — waiting for farewell TTS to finish", self._turn_count)
        self._ending = True

        # Bind directly to the SpeechHandle for the in-flight turn (which contains the
        # farewell text + [end_call]) instead of the call-wide `_speaking_done` Event.
        # That Event is a single shared flag: if this task starts running before
        # agent_state_changed has flipped to "speaking" for THIS farewell, the Event
        # can still be left set() from the end of the PREVIOUS turn, making .wait()
        # return instantly — before the farewell audio has even started.
        # session.current_speech doesn't have this race: AgentActivity assigns it
        # before generation (LLM stream -> TTS text-transforms -> synthesis) begins,
        # and we're reached here from inside that very TTS text-transform stream, so
        # it's already bound to this exact farewell handle by construction.
        speech = self.session.current_speech
        if speech is None:
            # Defensive-only fallback in case a future SDK version changes this ordering.
            for _ in range(20):  # up to ~1s
                await asyncio.sleep(0.05)
                speech = self.session.current_speech
                if speech is not None:
                    break

        try:
            if speech is not None:
                await asyncio.wait_for(speech.wait_for_playout(), timeout=15.0)
            else:
                logger.warning("current_speech unavailable for farewell — falling back to state-change wait")
                await asyncio.wait_for(self._speaking_done.wait(), timeout=15.0)
        except asyncio.TimeoutError:
            logger.warning("Timed out waiting for farewell TTS to finish — hanging up anyway")

        await asyncio.sleep(0.5)  # let the last audio frames flush through the SIP path
        await self._post_call_report()
        await self._disconnect()

    async def on_enter(self) -> None:
        logger.info("Agent entered room — pipeline ready")
        await asyncio.sleep(0.1)  # let TTS output track attach
        if self._ending:
            return  # participant left before on_enter ran (rejected call)
        self.session.on("agent_state_changed", self._on_agent_state_changed)
        try:
            logger.info("Generating welcome via LLM pipeline...")
            reply_kwargs: dict = {}
            model_name = getattr(self.session.llm, "model", "")
            if model_name in _NEEDS_SYNTHETIC_FIRST_TURN:
                # Short bracketed trigger (matches the existing "[FIRST TURN...]"
                # convention already in the system prompt) satisfies this model's
                # template requirement without reading as real customer speech.
                reply_kwargs["user_input"] = (
                    "[SYSTEM: The call has just connected — greet the customer now, "
                    "following your welcome-turn instructions.]"
                )
            handle = await self.session.generate_reply(**reply_kwargs)
            if not handle.chat_items:
                # generate_reply() completed without raising but produced zero
                # output -- e.g. a provider-side API error logged deep inside the
                # SDK's generation pipeline that never propagates up as a Python
                # exception here. Previously this silently logged "Welcome
                # generated" even though nothing was ever spoken, leaving the
                # caller in dead air until they spoke first themselves.
                raise RuntimeError("generate_reply produced no output (empty chat_items)")
            logger.info("Welcome generated ✓")
        except Exception as e:
            msg = str(e).lower()
            if "closing" in msg or "closed" in msg or "shutdown" in msg:
                # Session already closing — call was rejected/dropped before agent spoke
                logger.debug("Session closed before welcome (call rejected early)")
                return
            logger.error("generate_reply failed — falling back to say(): %s", e)
            try:
                await self.session.say(self._welcome_message)
            except Exception as e2:
                if "closing" in str(e2).lower() or "closed" in str(e2).lower():
                    logger.debug("Session closed before fallback say()")
                    return
                # Both the LLM-generated reply and the plain say() fallback failed —
                # the TTS pipeline itself is broken (bad voice_id, provider auth
                # failure, etc). The call is connected but the agent can never speak.
                # Previously this was only logged, leaving the call to run silently
                # for up to _max_duration_guard's 600s and get misreported by the
                # outcome classifier. End it now and flag it as a real system failure.
                logger.error("say() fallback also failed — TTS is broken, ending call: %s", e2)
                self._ending = True
                await self._report_system_failure(f"TTS failed: {e2}")
                await self._disconnect()
                return
        self._last_user_activity = time.monotonic()
        _safe_task(self._max_duration_guard(max_seconds=600), "max-duration-guard")
        _safe_task(self._silence_watchdog(), "silence-watchdog")

    def _on_agent_state_changed(self, ev) -> None:
        if ev.new_state == "speaking":
            self._speaking_done.clear()
        if ev.old_state == "speaking" and ev.new_state != "speaking":
            self._speaking_done.set()
            # The silence clock must start counting from when the AGENT stops talking —
            # not from the last user turn. Otherwise the agent's own thinking+speaking
            # time silently eats into the "silence" budget, and the probe can fire
            # almost immediately after the agent finishes a sentence.
            # Skip this during _silence_watchdog's own probe utterance — otherwise the
            # probe itself resets the clock to "just now", probe_idx keeps getting reset
            # to 0 next loop iteration, and the watchdog can never advance past probe #1
            # or reach its hangup-after-N-probes path (silence just resets indefinitely).
            if not self._probing:
                self._last_user_activity = time.monotonic()

    async def _max_duration_guard(self, max_seconds: float) -> None:
        await asyncio.sleep(max_seconds)
        if not self._ending:
            logger.warning("Max call duration reached — auto-hangup")
            self._ending = True
            await self._do_hangup()

    async def on_user_turn_completed(self, turn_ctx, new_message) -> None:
        if self._ending:
            raise StopResponse()

        text = (getattr(new_message, "text_content", "") or "").strip()
        self._turn_count += 1
        logger.info("Turn %d: %r", self._turn_count, text[:80])

        if text:
            self._user_messages.append(text)
            self._last_user_activity = time.monotonic()

            # Voicemail detected — hang up silently (don't leave a message)
            if _VOICEMAIL_RE.search(text):
                logger.info("Voicemail detected at turn %d — silent hangup", self._turn_count)
                self._ending = True
                _safe_task(self._silent_hangup(outcome_override="voicemail"), "voicemail-hangup")
                raise StopResponse()

            # Call-forwarding announcement detected (not the actual person) — hang up silently
            if _FORWARDING_RE.search(text):
                logger.info("Call forwarding announcement detected at turn %d — silent hangup", self._turn_count)
                self._ending = True
                _safe_task(self._silent_hangup(), "forwarding-hangup")
                raise StopResponse()

            # IVR / automated bot detected — hang up silently
            if _BOT_IVR_RE.search(text):
                logger.info("IVR/bot detected at turn %d — silent hangup", self._turn_count)
                self._ending = True
                _safe_task(self._silent_hangup(), "bot-hangup")
                raise StopResponse()

        # Only allow hangup-by-keyword after at least 6 customer turns (agent needs time to pitch)
        if self._turn_count >= 6 and _HANGUP_RE.search(text):
            self._ending = True
            _safe_task(self._do_hangup(), "hangup-from-keyword")
            raise StopResponse()

    async def _report_system_failure(self, error_text: str) -> None:
        """The TTS pipeline itself failed before the agent ever spoke — the call
        connected but is completely silent. Report it as a real system failure
        (CallStatus.FAILED + error_message) instead of leaving it to be silently
        misclassified as a normal (but quiet) conversation outcome."""
        if not self._call_id or not self._backend_url:
            logger.warning(
                "report_system_failure_skipped | call_id=%r backend_url=%r — nothing to report to",
                self._call_id, self._backend_url,
            )
            return
        if self._reported:
            return
        self._reported = True
        try:
            await self._post_agent_report(
                {"outcome": "pending", "summary": "", "transcript": [], "error_message": error_text}
            )
            logger.info("post_call_report_sent | call=%s status=failed error=%s", self._call_id, error_text)
        except Exception as exc:
            logger.error("report_system_failure failed to reach backend: %s", exc)

    async def _post_agent_report(self, payload: dict, *, attempts: int = 3) -> None:
        """POST the call report to the backend, retrying transient failures.

        A single dropped connection or momentary backend restart used to lose
        the whole report permanently (one-shot POST, no retry) — the call would
        then sit at outcome=pending forever with no way to recover the data,
        since the transcript/summary only ever exist in this in-memory report.
        """
        import httpx

        url = f"{self._backend_url}/api/calls/{self._call_id}/agent-report"
        body = json.dumps(payload).encode()
        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Signature": _sign_webhook_body(body),
        }
        delay = 1.0
        last_exc: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=10.0) as http:
                    resp = await http.post(url, content=body, headers=headers)
                    # A 4xx/5xx from the backend was previously indistinguishable from
                    # success here (no status check) — the loop would return on the
                    # first attempt and silently drop the report on e.g. a 500 during
                    # a backend restart, with no retry and no error anywhere.
                    resp.raise_for_status()
                return
            except Exception as exc:
                last_exc = exc
                if attempt < attempts:
                    logger.warning(
                        "agent_report_post_retry | call=%s attempt=%d/%d error=%s",
                        self._call_id, attempt, attempts, exc,
                    )
                    await asyncio.sleep(delay)
                    delay *= 2
        assert last_exc is not None
        logger.error(
            "agent_report_post_failed | call=%s attempts=%d error=%s — persisting to %s for replay",
            self._call_id, attempts, last_exc, FAILED_REPORTS_PATH,
        )
        _persist_failed_report(self._call_id, payload, last_exc)
        raise last_exc

    async def _post_call_report(self, *, outcome_override: str | None = None) -> None:
        """Classify outcome with Groq and POST to backend. Called once after every call.

        outcome_override: when the caller already KNOWS the outcome with certainty
        (e.g. deterministic voicemail-phrase detection), skip the transcript-based
        classifier entirely and report this value directly — see _send_report.
        """
        if not self._call_id or not self._backend_url:
            logger.warning(
                "post_call_report_skipped | call_id=%r backend_url=%r — nothing to report to "
                "(check BACKEND_INTERNAL_URL / room metadata)",
                self._call_id, self._backend_url,
            )
            return
        if self._reported:
            return
        self._reported = True
        try:
            await asyncio.wait_for(self._send_report(outcome_override=outcome_override), timeout=15.0)
        except asyncio.TimeoutError:
            logger.error("post_call_report timed out — backend may be unreachable at %s", self._backend_url)
        except Exception as exc:
            logger.error("post_call_report failed: %s", exc)

    async def _send_report(self, *, outcome_override: str | None = None) -> None:
        import json as _json

        # Try to get full conversation (user + agent) from session history
        full_transcript: list[dict] = []
        try:
            ctx = getattr(self.session, "history", None) or getattr(self.session, "_chat_ctx", None)
            if ctx:
                # ChatContext.messages is a METHOD (not a property) — must be
                # called. `getattr(ctx, "messages", None)` alone returns a
                # truthy bound method, which previously short-circuited the
                # `or ctx.items` fallback and then raised TypeError when
                # iterated, silently swallowed below and degrading every
                # transcript to customer-only.
                messages_attr = getattr(ctx, "messages", None)
                items = messages_attr() if callable(messages_attr) else getattr(ctx, "items", [])
                for msg in items:
                    role_raw = str(getattr(msg, "role", "")).lower()
                    if "system" in role_raw:
                        continue
                    role_out = "agent" if "assistant" in role_raw else "user"
                    content = getattr(msg, "content", "") or ""
                    if isinstance(content, list):
                        text = " ".join(
                            getattr(c, "text", "") if hasattr(c, "text") else (c.get("text", "") if isinstance(c, dict) else str(c))
                            for c in content
                        ).strip()
                    else:
                        text = str(content).strip()
                    if text:
                        full_transcript.append({"role": role_out, "text": text})
        except Exception as exc:
            logger.warning("transcript_history_read_failed | call=%s error=%s", self._call_id, exc)

        # Fallback: if session history unavailable, use only captured user messages
        if not full_transcript:
            full_transcript = [{"role": "user", "text": t} for t in self._user_messages]

        if not full_transcript and not outcome_override:
            logger.info("post_call_report_skipped | call=%s reason=no_conversation_captured", self._call_id)
            return  # nothing was said by either side; leave outcome as PENDING

        # A deterministic detector (voicemail phrasing, etc.) already knows the real
        # outcome with certainty -- skip the word-count gate and the LLM classifier
        # entirely rather than letting a voicemail greeting get misread as a normal
        # (dis)interested customer response.
        if outcome_override:
            summary = f"Call ended automatically: {outcome_override.replace('_', ' ')} detected."
            await self._post_agent_report({
                "outcome": outcome_override, "summary": summary, "transcript": full_transcript,
            })
            logger.info("post_call_report_sent | call=%s outcome=%s (override)", self._call_id, outcome_override)
            return

        # Build text for Groq — show both sides when available
        transcript_text = "\n".join(
            f"{'CUSTOMER' if m['role'] == 'user' else 'AGENT'}: {m['text']}"
            for m in full_transcript
        ) or "\n".join(f"CUSTOMER: {t}" for t in self._user_messages)

        # ── Minimum engagement gate ────────────────────────────────────────────
        # Count how many words the customer actually said across all turns.
        # If they barely spoke, there is no evidence of interest — skip the LLM
        # entirely and classify as not_interested immediately.
        customer_word_count = sum(
            len(m.get("text", "").split())
            for m in full_transcript
            if m.get("role") == "user"
        )
        if customer_word_count < 8:
            logger.info(
                "classify_skip: customer only spoke %d words — marking not_interested",
                customer_word_count,
            )
            outcome = "not_interested"
            summary = "Customer did not engage meaningfully in the conversation."
            await self._post_agent_report({"outcome": outcome, "summary": summary, "transcript": full_transcript})
            logger.info("post_call_report_sent | call=%s outcome=%s words=%d", self._call_id, outcome, customer_word_count)
            return

        # ── LLM classification (customer said enough to judge) ─────────────────
        outcome, summary = "not_interested", ""
        raw = None          # stays None if the Groq call itself never returned a response
        finish_reason = None
        try:
            import groq as _groq
            client = _groq.AsyncGroq(api_key=os.environ.get("GROQ_API_KEY", ""))
            resp = await client.chat.completions.create(
                model="llama-3.1-8b-instant",
                max_tokens=350,
                temperature=0.0,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You classify sales call outcomes strictly from the CUSTOMER's words in the transcript. "
                            "Ignore STT errors — judge intent, not exact wording. "
                            "Reply ONLY with valid JSON: {\"outcome\": \"...\", \"summary\": \"...\", "
                            "\"extracted_data\": {\"caller_name\": ..., \"caller_email\": ..., "
                            "\"caller_phone\": ..., \"requirements\": ..., \"budget\": ..., "
                            "\"decision_maker\": ...}}\n\n"
                            "extracted_data fields — fill in ONLY what the CUSTOMER actually said in the "
                            "transcript; use null for anything not explicitly mentioned. Never guess or "
                            "invent a value:\n"
                            "  caller_name     — the customer's name, if they gave one\n"
                            "  caller_email    — an email address, if they gave one\n"
                            "  caller_phone    — a callback/contact number, if they gave one\n"
                            "  requirements    — 1 short sentence on what they want/need (product, design, "
                            "service, etc.), if they described anything\n"
                            "  budget          — budget they mentioned, if any\n"
                            "  decision_maker  — true/false only if the transcript makes it clear whether "
                            "they can make the purchase decision themselves, else null\n\n"
                            "OUTCOME RULES — read carefully:\n\n"
                            "  interested         — Customer showed CLEAR, ACTIVE interest. Requires at least ONE of:\n"
                            "                       • Asked a specific question about price, availability, delivery, or specs\n"
                            "                       • Shared or agreed to share contact info (WhatsApp, phone, email)\n"
                            "                       • Agreed to receive catalogue, sample, demo, or quote\n"
                            "                       • Confirmed they currently buy or use this type of product\n"
                            "                       • Explicitly said they want to place an order or inquire\n"
                            "                       IMPORTANT: Passive replies only ('haan', 'hmm', 'theek hai', 'okay', 'bol') "
                            "do NOT count as interest — the customer must have asked something or agreed to something.\n\n"
                            "  callback_requested — Customer asked to be called back AND gave a SPECIFIC later time "
                            "(a day, date, or time of day — e.g. 'kal subah', 'shaam ko', 'Monday', 'next week'). "
                            "A vague 'baad mein call karo' / 'call me later' with NO specific time is NOT enough by "
                            "itself — that phrasing is a common brush-off to end the call politely, not a real booking.\n\n"
                            "  not_interested     — DEFAULT for all other cases:\n"
                            "                       • Customer only gave short/vague replies without engaging\n"
                            "                       • Customer never asked a question or agreed to anything\n"
                            "                       • Rejection: 'nahi chahiye', 'busy hoon', 'mat karo call', hung up\n"
                            "                       • Said 'call me later'/'I'll give you my number' with no specific "
                            "time, especially right before hanging up\n"
                            "                       WHEN IN DOUBT → use not_interested\n\n"
                            "  wrong_number       — Wrong person or wrong business.\n\n"
                            "  do_not_call        — Customer demanded never to be called again.\n\n"
                            "RED FLAG — fake contact info: if the phone/WhatsApp number in the transcript is implausible "
                            "(wrong digit count for a 10-digit Indian mobile, all one repeated digit, or an obvious "
                            "sequence like '123456789' or '0000000000'), that is a strong signal the customer was "
                            "brushing you off, not giving real contact info. In that case do NOT classify as "
                            "'interested' or 'callback_requested' on the strength of that number alone — fall back to "
                            "'not_interested' unless something else in the transcript shows genuine engagement.\n\n"
                            "summary: 1–2 sentences. State what the customer actually said and what (if anything) was agreed."
                        ),
                    },
                    {"role": "user", "content": f"Transcript:\n{transcript_text}"},
                ],
            )
            finish_reason = resp.choices[0].finish_reason
            raw = resp.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            raw = raw.strip()
            result = _json.loads(raw)
            outcome = result.get("outcome", "not_interested")
            summary = result.get("summary", "")
            raw_extracted = result.get("extracted_data") or {}
            extracted_data = {k: v for k, v in raw_extracted.items() if v is not None}
            valid = {"interested", "not_interested", "callback_requested", "wrong_number", "do_not_call"}
            if outcome not in valid:
                outcome = "not_interested"
            # finish_reason == "length" means Groq hit max_tokens and cut the response off —
            # if this ever shows up on a *successful* parse it means we got lucky (the JSON
            # happened to close before the cut), and it's a warning sign max_tokens=350 is
            # running too close to the edge for calls with a lot to extract.
            logger.info(
                "classify_llm: call=%s outcome=%s words=%d finish_reason=%s completion_tokens=%s",
                self._call_id, outcome, customer_word_count, finish_reason,
                getattr(getattr(resp, "usage", None), "completion_tokens", None),
            )
        except Exception as exc:
            # A genuine classification failure used to silently fall back to
            # the pre-try "not_interested" default -- indistinguishable from a
            # confident real classification, so a Groq outage could quietly
            # mislabel every affected call that day with no visible flag
            # anywhere. "pending" is a real, already-monitored value instead:
            # the backend's flag_stale_pending_calls beat task (10 min later)
            # logs any COMPLETED call still sitting at outcome=pending, which
            # this now reaches on purpose instead of by accident.
            outcome = "pending"
            # raw is None  -> failed before/during the Groq API call itself (network,
            #                 auth, rate limit) -- never got a response to parse.
            # raw is set   -> Groq responded but json.loads/field access failed; raw_preview
            #                 + finish_reason show whether max_tokens=350 truncated it
            #                 mid-JSON (finish_reason="length" is the smoking gun).
            logger.warning(
                "groq_classify_error | call=%s error_type=%s error=%s stage=%s finish_reason=%s "
                "raw_len=%s raw_preview=%r",
                self._call_id,
                type(exc).__name__,
                exc,
                "groq_api_call" if raw is None else "parse_or_extract",
                finish_reason,
                len(raw) if raw is not None else None,
                raw[:500] if raw else None,
            )
            extracted_data = {}

        await self._post_agent_report({
            "outcome": outcome,
            "summary": summary,
            "transcript": full_transcript,
            "extracted_data": extracted_data,
        })
        logger.info("post_call_report_sent | call=%s outcome=%s", self._call_id, outcome)

    async def _do_hangup(self) -> None:
        logger.info("Hangup — saying farewell")
        try:
            # session.say() already awaits true end-to-end playback completion
            # (SpeechHandle.wait_for_playout(), driven by the audio sink's real
            # "playback_finished" event). TTS generation alone has been observed
            # to take 8s+ for a single utterance (see _trigger_hangup below), so
            # 20s gives real safety margin above the worst observed case.
            await asyncio.wait_for(
                self.session.say(_FAREWELL, allow_interruptions=False),
                timeout=20.0,
            )
        except asyncio.TimeoutError:
            logger.warning("Farewell TTS timed out — disconnecting anyway")
        except Exception as e:
            logger.warning("Farewell TTS failed: %s", e)
        await asyncio.sleep(0.3)
        await self._post_call_report()
        await self._disconnect()

    async def _silent_hangup(self, *, outcome_override: str | None = None) -> None:
        """Hang up without a farewell (voicemail, bot, or prolonged silence)."""
        await self._post_call_report(outcome_override=outcome_override)
        await self._disconnect()

    async def _silence_watchdog(self) -> None:
        """Probe if customer is silent; hang up after all probes are exhausted."""
        await asyncio.sleep(_SILENCE_INITIAL_SLEEP)
        probe_idx = 0
        while not self._ending:
            silence_sec = time.monotonic() - self._last_user_activity
            if silence_sec < _SILENCE_FIRST_TIMEOUT:
                probe_idx = 0  # user recently spoke — reset probe counter
                await asyncio.sleep(2.0)
                continue
            if probe_idx < len(_SILENCE_PROBES):
                probe_idx += 1
                logger.info("Silence probe #%d (%.1fs silent)", probe_idx, silence_sec)
                self._probing = True
                try:
                    await self.session.say(_SILENCE_PROBES[probe_idx - 1], allow_interruptions=True)
                except Exception as e:
                    logger.warning("Silence probe TTS failed: %s", e)
                finally:
                    self._probing = False
                await asyncio.sleep(_SILENCE_PROBE_INTERVAL)
            else:
                logger.info("Silence hangup — %.1fs no response after %d probes", silence_sec, len(_SILENCE_PROBES))
                if not self._ending:
                    self._ending = True
                    await self._silent_hangup()
                return


# =============================================================================
# ENTRYPOINT
# =============================================================================
async def entrypoint(ctx: agents.JobContext) -> None:
    logger.info("Job received | room=%s", ctx.room.name)
    await ctx.connect()

    # Primary source: dispatch metadata (JobContext.job.metadata) -- delivered as part of
    # the job assignment itself (see _place_call() in campaign.py, which now puts the full
    # payload on CreateAgentDispatchRequest), available the instant the job starts with no
    # dependency on room state sync. ctx.room.metadata is set by the same backend call but
    # over a separate path (room state, synced to this process after ctx.connect()) that can
    # race it -- confirmed in practice: ctx.room.metadata read back empty on some jobs even
    # though create_room() had already completed and returned before dispatch was requested.
    # Falls back to room metadata for inbound calls, which carry only
    # {"call_type":"inbound","sip_trunk_id":...} via a static SIP dispatch rule
    # (app/api/sip_trunks.py setup_inbound()), not per-job dispatch metadata.
    raw_meta = ctx.job.metadata or ctx.room.metadata
    # Logged unconditionally (length/preview only, never the raw system_prompt in full)
    # so an empty-vs-malformed metadata gap is visible instead of silently defaulting
    # every field (voice_provider, call_id, etc.) with no trace of why.
    logger.info(
        "job_metadata_raw | room=%s job_present=%s room_present=%s len=%s preview=%r",
        ctx.room.name,
        bool(ctx.job.metadata),
        bool(ctx.room.metadata),
        len(raw_meta) if raw_meta else 0,
        raw_meta[:300] if raw_meta else None,
    )
    meta: dict = {}
    if raw_meta:
        try:
            meta = json.loads(raw_meta)
        except Exception as exc:
            logger.error(
                "job_metadata_parse_failed | room=%s error_type=%s error=%s raw_preview=%r",
                ctx.room.name, type(exc).__name__, exc, raw_meta[:300],
            )

    # Inbound calls (LiveKit SIP dispatch rule, see app/api/sip_trunks.py
    # setup_inbound()) carry only {"call_type":"inbound","sip_trunk_id":...} --
    # nothing to build a prompt from yet. Resolve the real config from the
    # backend first, merging it into `meta` so every line below reads exactly
    # like it does for outbound. This means the participant wait happens here
    # (before warmup) instead of after, since we need the participant's SIP
    # attributes before we know which agent answers -- warmup can't overlap
    # with the participant wait the way it does for outbound.
    inbound_participant = None
    if meta.get("call_type") == "inbound":
        try:
            inbound_participant = await asyncio.wait_for(ctx.wait_for_participant(), timeout=30.0)
            logger.info("Inbound participant joined: %s", getattr(inbound_participant, "identity", "unknown"))
        except asyncio.TimeoutError:
            logger.error("No inbound participant joined in 30s — exiting")
            return

        inbound_config = await _resolve_inbound_call(meta, inbound_participant, ctx.room.name)
        if inbound_config is None:
            logger.error("Could not resolve inbound call — hanging up")
            return
        meta = {**meta, **inbound_config}

    tz_name         = meta.get("timezone") or "Asia/Kolkata"
    # Correct greeting/honorific wording wherever it lives — either the dedicated
    # welcome_message field, or baked into the system_prompt's own OPENING section
    # (older templates generated before the gender-neutral/time-of-day fix have it
    # hardcoded there, e.g. a literal "Good Morning Sir" line).
    raw_prompt      = _localize_welcome_message(
        meta.get("system_prompt") or AGENT_SYSTEM_PROMPT, tz_name
    )
    welcome_message = _localize_welcome_message(
        meta.get("welcome_message") or AGENT_WELCOME_MESSAGE, tz_name
    )
    # LOCAL_TEST_VOICE_PROVIDER only matters when there's no real call metadata at
    # all (i.e. `agent.py console` locally) -- meta.get() always wins on a real
    # call, so this has no effect in production.
    voice_provider  = (meta.get("voice_provider") or os.getenv("LOCAL_TEST_VOICE_PROVIDER") or "elevenlabs").lower()
    voice_id        = meta.get("voice_id") or (
        CARTESIA_VOICE_ID if voice_provider == "cartesia"
        else CHATTERBOX_VOICE_ID if voice_provider == "chatterbox"
        else SARVAM_VOICE_ID if voice_provider == "sarvam"
        else ELEVENLABS_VOICE_ID
    )
    language        = (meta.get("language") or "hinglish").lower()
    tts_model_id    = meta.get("tts_model_id") or ELEVENLABS_MODEL_ID
    llm_model       = meta.get("llm_model") or GROQ_MODEL
    llm_temperature = float(meta.get("llm_temperature") or GROQ_LLM_TEMPERATURE)
    call_id         = meta.get("call_id", "")
    campaign_id     = meta.get("campaign_id", "")
    set_log_context(call_id=call_id, room=ctx.room.name, campaign_id=campaign_id)

    if meta.get("system_prompt"):
        logger.info("system_prompt | source=room_metadata campaign=%s len=%d", campaign_id, len(raw_prompt))
    else:
        logger.warning(
            "system_prompt | source=CONFIG_FALLBACK — room metadata had no system_prompt! "
            "campaign=%s meta_keys=%s",
            campaign_id, list(meta.keys()),
        )

    system_prompt = _build_prompt(raw_prompt, welcome_message, language)
    logger.info("template | voice=%s llm=%s temperature=%s", voice_id, llm_model, llm_temperature)

    llm_kwargs: dict = {"model": llm_model, "temperature": llm_temperature}
    if llm_model in _REASONING_EFFORT_OVERRIDES:
        llm_kwargs["reasoning_effort"] = _REASONING_EFFORT_OVERRIDES[llm_model]
    llm = _CappedGroqLLM(**llm_kwargs)
    # Start warmup immediately with the real system prompt so Groq caches the full context.
    # Runs concurrently while we wait for the SIP participant to connect (usually 3-8s).
    warmup_task = _safe_task(_warmup_llm(llm, system_prompt), "llm-warmup")

    # ElevenLabs' plugin has no real prewarm() -- tts.prewarm() below is a no-op for it
    # (only Sarvam/Cartesia implement a connection pool it can actually warm), so
    # without this, the very first request pays a full TLS+WebSocket handshake to
    # elevenlabs.io inline with the welcome message: extra silence before the agent
    # speaks, AND a colder/differently-paced opening chunk than every turn after it,
    # which is what read as "a different tone" on the first line. Firing a tiny
    # throwaway synthesis now reuses the same participant-connect window LLM warmup
    # already gets for free, and warms the shared HTTP session (_ensure_session() in
    # the plugin) so the real welcome request reuses an already-open connection.
    if voice_provider == "elevenlabs":
        async def _warm_elevenlabs_tts() -> None:
            warm_tts = elevenlabs.TTS(api_key=ELEVENLABS_API_KEY)
            try:
                async for _ in warm_tts.synthesize("hi"):
                    pass
            finally:
                await warm_tts.aclose()
        _safe_task(_warm_elevenlabs_tts(), "elevenlabs-tts-warmup")

    if inbound_participant is not None:
        participant = inbound_participant  # already awaited above, before this config was known
    else:
        try:
            participant = await asyncio.wait_for(ctx.wait_for_participant(), timeout=30.0)
            logger.info("Participant joined: %s", getattr(participant, "identity", "unknown"))
        except asyncio.TimeoutError:
            logger.error("No participant joined in 30s — exiting")
            warmup_task.cancel()
            return

    # Ensure warmup is complete before the first turn so the first response is fast.
    # Participant just connected — we have a few seconds while TTS/session setup happens.
    try:
        await asyncio.wait_for(asyncio.shield(warmup_task), timeout=6.0)
        logger.info("LLM warmup confirmed complete ✓")
    except (asyncio.TimeoutError, Exception) as e:
        logger.debug("LLM warmup await skipped: %s", e)  # proceed anyway

    if voice_provider == "cartesia":
        # Cartesia sonic models only support: "en", "de", "es", "fr".
        # Hindi ("hi") is NOT supported — passing it causes hallucination.
        # For Hinglish/Hindi use "en"; the model phonetically handles mixed text correctly.
        _cartesia_lang_map = {
            "english":  "en",
            "german":   "de",
            "spanish":  "es",
            "french":   "fr",
        }
        cartesia_language = _cartesia_lang_map.get(language, "en")  # all Indian languages → "en"
        tts = cartesia.TTS(
            api_key     = CARTESIA_API_KEY,
            voice       = voice_id,
            model       = CARTESIA_MODEL_ID,
            language    = cartesia_language,
            speed       = 1,        # default is 1.0 — 0.85 is natural phone-call pace
            encoding    = "pcm_s16le",
            sample_rate = 24000,
        )
        logger.info("Cartesia TTS ready ✓ (model=%s voice=%s lang=%s speed=0.85)", CARTESIA_MODEL_ID, voice_id, cartesia_language)
    elif voice_provider == "chatterbox":
        # Chatterbox's multilingual model genuinely supports Hindi ("hi") — validated
        # separately with good quality. But forcing "hi" on purely English text (e.g. the
        # generic AGENT_WELCOME_MESSAGE fallback when no welcome_message is configured)
        # causes hallucinated/garbled audio. Map English content to "en" explicitly;
        # keep "hi" for hindi/hinglish, which tested fine.
        _chatterbox_lang_map = {
            "english":  "en",
            "hindi":    "hi",
            "hinglish": "hi",
            "marathi":  "hi",  # not natively supported by Chatterbox — closest available
        }
        chatterbox_language = _chatterbox_lang_map.get(language, CHATTERBOX_LANGUAGE)
        tts = chatterbox_tts.TTS(
            base_url    = CHATTERBOX_BASE_URL,
            voice       = voice_id,
            language    = chatterbox_language,
            sample_rate = CHATTERBOX_SAMPLE_RATE,
            voice_mode  = CHATTERBOX_VOICE_MODE,
        )
        logger.info("Chatterbox TTS ready ✓ (base_url=%s voice=%s lang=%s mode=%s)", CHATTERBOX_BASE_URL, voice_id, chatterbox_language, CHATTERBOX_VOICE_MODE)
    elif voice_provider == "sarvam":
        # Sarvam's Bulbul models are native to Indian languages — no English fallback
        # needed the way Cartesia/Chatterbox require, but still map cleanly per language.
        _sarvam_lang_map = {
            "english":  "en-IN",
            "hindi":    "hi-IN",
            "hinglish": "hi-IN",
            "marathi":  "mr-IN",
        }
        sarvam_language = _sarvam_lang_map.get(language, "hi-IN")
        # NOTE: pitch/loudness are silently ignored by Sarvam's API on bulbul:v3 and
        # v3-beta (only bulbul:v2 honors them) — so tuning pitch here would do nothing.
        # temperature controls per-utterance sampling randomness. Every conversational
        # turn opens a brand-new TTS session (see logs: distinct session_id per turn),
        # so higher temperature = each line sampled more independently = audible tone
        # drift turn-to-turn — bad for a sales call, which needs one steady voice
        # (same reasoning ElevenLabs uses stability=0.85/style=0.0 below). Keep it at
        # Sarvam's own default for consistency; pace alone fixes the sluggish pacing.
        tts = sarvam.TTS(
            api_key             = SARVAM_API_KEY,
            target_language_code= sarvam_language,
            model               = SARVAM_MODEL,
            speaker             = voice_id,
            speech_sample_rate  = SARVAM_SAMPLE_RATE,
            pace                = 1.0,   # 1.0 reads sluggish for phone calls; 1.10 is natural conversational pace
            temperature         = 0.6,    # Sarvam's own default — lowest that still sounds natural; higher caused tone drift between turns
        )
        logger.info("Sarvam TTS ready ✓ (model=%s speaker=%s lang=%s pace=1.10 temp=0.6)", SARVAM_MODEL, voice_id, sarvam_language)
    else:
        tts = elevenlabs.TTS(
            api_key               = ELEVENLABS_API_KEY,
            voice_id              = voice_id,
            model                 = tts_model_id,
            encoding              = "pcm_16000",  # phone SIP path uses ≤16kHz; pcm_24000 was overkill and caused more WS drops
            chunk_length_schedule = _CHUNK_LENGTH_SCHEDULE,
            voice_settings        = elevenlabs.VoiceSettings(
                stability         = 0.4,  # high = consistent tone across all chunks, no high/low shifts
                similarity_boost  = 0.8,
                style             = 0.3,   # zero expressiveness = no tonal variation between chunks
                use_speaker_boost = True,
            ),
        )
        logger.info("ElevenLabs TTS ready ✓ (voice=%s model=%s)", voice_id, tts_model_id)

    # Pre-open the TTS connection (WebSocket for Sarvam/Cartesia) in the background now,
    # rather than paying that handshake latency on the agent's very first spoken turn.
    # No-op for providers that don't implement it.
    tts.prewarm()

    voice_agent = VoiceAgent(
        ctx.room,
        instructions=system_prompt,
        welcome_message=welcome_message,
        call_id=call_id,
        backend_url=BACKEND_INTERNAL_URL,
        webhook_secret=AGENT_WEBHOOK_SECRET,
    )
    end_call_transform = _end_call_filter_transform(voice_agent._trigger_hangup)
    honorific_greeting_transform = _honorific_greeting_filter_transform(tz_name)
    digit_spellout_transform = _digit_spellout_transform()

    def _log_tts_ttfb(metrics) -> None:
        # ttfb = seconds from "synthesis requested" to "first audio byte back
        # from the provider" -- the number that actually answers "did the
        # caller hear a real pause", as opposed to the full-utterance
        # synthesis duration already logged by the Sarvam/ElevenLabs plugins
        # ("WebSocket session completed successfully"), which covers the
        # whole reply and isn't when playback actually started.
        if getattr(metrics, "type", None) != "tts_metrics":
            return
        logger.info(
            "TTS time-to-first-audio-byte: %.3fs (turn %d)",
            metrics.ttfb, voice_agent._turn_count,
        )

    tts.on("metrics_collected", _log_tts_ttfb)

    session = AgentSession(
        stt=sarvam.STT(
            api_key  = SARVAM_API_KEY,
            language = SARVAM_STT_LANGUAGE,  # hi-IN — same "Hindi model handles English naturally" reasoning as before
            model    = SARVAM_STT_MODEL,     # saaras:v3 — WebSocket streaming, sub-200ms
            mode     = SARVAM_STT_MODE,      # codemix — tuned for Hindi/English code-switching (heavy in real transcripts)
        ),
        llm=llm,
        tts=tts,
        vad=ctx.proc.userdata["vad"],
        turn_handling=TurnHandlingOptions(
            turn_detection=MultilingualModel(),  # semantic end-of-turn model (Hindi/English) — judges
                                                  # whether an utterance actually sounds finished instead
                                                  # of relying on silence length alone, so a pause mid
                                                  # phone-number no longer gets treated as "done talking"
            endpointing={
                "min_delay": 0.9,  # was dropped to the SDK default 0.5s trusting turn_detection
                                   # (above) alone to catch a mid-sentence pause -- in practice it
                                   # doesn't catch every case, and the agent started replying while
                                   # the customer had only paused briefly, not actually finished.
                                   # Restoring the floor to 0.9s (proven previously for the same
                                   # mid-phone-number case) so every turn gets at least this much
                                   # silence before committing, with turn_detection still handling
                                   # the smarter judgment call on top of that floor.
                "max_delay": 3.0,  # unchanged (SDK default) — ceiling the model can stretch to when unsure
            },
            interruption={
                "min_duration": 0.35,  # was 0.6 -- a single short word ("ruko", "wait", "sorry")
                                      # rarely sustains 600ms of speech, so real short interruptions were
                                      # being silently ignored (this check must pass before min_words is
                                      # even evaluated). 0.35s is still comfortably above VAD's own 0.20s
                                      # onset requirement (prewarm() below), so it still filters clicks/
                                      # breaths shorter than a real word.
                "min_words":    0,    # was 1 -- requiring even one recognized word meant waiting on STT
                                      # to transcribe it (real latency on top of min_duration above),
                                      # which is what made interruptions feel like they only landed after
                                      # the agent finished its sentence. 0 disables the word-recognition
                                      # gate entirely: min_duration's 0.35s of sustained VAD-detected
                                      # speech is now the only bar, so the agent stops on raw voice
                                      # activity alone -- true human-conversation-style barge-in, at the
                                      # cost of occasionally reacting to a loud breath/cough/background
                                      # noise VAD mistakes for speech (no longer filtered by a real word).
                "false_interruption_timeout": None,  # SDK default (2.0) PAUSES the agent's audio on a
                                      # detected interruption and silently RESUMES it from where it left
                                      # off if a full turn doesn't confirm within 2s — audibly identical to
                                      # "the agent just kept talking" even though an interruption fired.
                                      # min_duration + min_words above already require 600ms of sustained,
                                      # transcribed speech before triggering, so a second false-positive
                                      # safety net isn't needed — disabling it (None) makes every detected
                                      # interruption cut the agent off for good, immediately.
            },
        ),
        tts_text_transforms=["filter_markdown", "filter_emoji", honorific_greeting_transform, digit_spellout_transform, end_call_transform],
    )

    def _on_speech_created(ev) -> None:
        # Proves whether turn_handling.interruption (above) is actually cutting
        # the agent off mid-sentence, rather than inferring it indirectly from
        # turn timestamps -- wait_for_playout() resolves whether the speech
        # finished normally or was cut short, and .interrupted tells us which.
        speech_handle = ev.speech_handle

        async def _log_if_interrupted() -> None:
            try:
                await speech_handle.wait_for_playout()
            except Exception:
                pass
            if speech_handle.interrupted:
                logger.info("Agent speech interrupted by caller (turn %d)", voice_agent._turn_count)

        _safe_task(_log_if_interrupted(), "interruption-logger")

    session.on("speech_created", _on_speech_created)

    @ctx.room.on("participant_disconnected")
    def _on_participant_left(participant):
        # Customer hung up — classify + POST the outcome BEFORE tearing the room
        # down ourselves. close_on_disconnect is deliberately off (below): with it
        # on, RoomIO closes the session/room on this same event, and that teardown
        # was consistently winning the race against this handler's fire-and-forget
        # report (an httpx POST plus a Groq LLM call — real network time), because
        # a customer-initiated hangup has no farewell TTS to wait out first. The
        # job process exits once the room disconnects, killing the report
        # mid-flight, which is why every customer-hangup call was landing on
        # outcome=pending regardless of how the call actually went. Routing through
        # _silent_hangup (await report, then disconnect) makes this path match the
        # agent-initiated hangup paths, which already await the report first.
        if not voice_agent._ending:
            voice_agent._ending = True
            logger.info("Participant disconnected — reporting outcome before disconnect")
            _safe_task(voice_agent._silent_hangup(), "post-call-on-disconnect")

    try:
        await session.start(
            agent       = voice_agent,
            room        = ctx.room,
            room_options= RoomOptions(
                close_on_disconnect  = False,
                delete_room_on_close = True,
            ),
        )
        logger.info("Agent session started ✓")
    except Exception:
        logger.exception("Session start failed")
        warmup_task.cancel()
        raise


# =============================================================================
# CLI ENTRY
# =============================================================================
if __name__ == "__main__":
    validate_config()
    agents.cli.run_app(
        agents.WorkerOptions(
            entrypoint_fnc    = entrypoint,
            prewarm_fnc       = prewarm,
            agent_name        = LIVEKIT_AGENT_NAME,
            worker_type       = agents.WorkerType.ROOM,
            num_idle_processes = 3,   # keep 3 processes warm for fast dispatch
            load_threshold    = 0.9,  # allow up to 90% CPU before refusing new jobs
        )
    )
