"""
agent.py — Hinglish Voice Sales Agent
Pipeline: Sarvam STT → Groq LLM → ElevenLabs/Sarvam/Cartesia/Chatterbox TTS (per-agent voice_provider)
"""

import os
import asyncio
import json
import logging
import re
import time
import certifi
from datetime import datetime
from zoneinfo import ZoneInfo

os.environ["SSL_CERT_FILE"]      = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

from livekit import agents
from livekit.agents import AgentSession, Agent, JobProcess, TurnHandlingOptions
from livekit.agents.llm import ChatContext
from livekit.agents.voice.room_io import RoomOptions
from livekit.plugins import groq, silero, elevenlabs, cartesia, sarvam
import chatterbox_tts

from config import (
    AGENT_SYSTEM_PROMPT,
    AGENT_WELCOME_MESSAGE,
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
    LOG_LEVEL,
    BACKEND_INTERNAL_URL,
    AGENT_WEBHOOK_SECRET,
    validate_config,
)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("voice-agent")

# ── Constants ─────────────────────────────────────────────────────────────────
_LLM_MAX_TOKENS = 400  # must be high enough for tool-call JSON + speech prefix (~120 tokens); 110 caused Groq "Failed to call a function" truncation errors

# Larger first chunk = more context per TTS call = smoother prosody across chunks.
_CHUNK_LENGTH_SCHEDULE = [120, 200, 280, 360]


def _safe_task(coro, name: str = "") -> asyncio.Task:
    """create_task wrapper that logs instead of raising 'Future exception was never retrieved'."""
    task = asyncio.create_task(coro)
    def _on_done(t: asyncio.Task) -> None:
        if not t.cancelled() and (exc := t.exception()) is not None:
            logger.debug("background task %s raised: %s", name or repr(coro), exc)
    task.add_done_callback(_on_done)
    return task


# =============================================================================
# Groq LLM wrapper — caps max_tokens on every call
# =============================================================================
class _CappedGroqLLM(groq.LLM):
    def chat(self, *, chat_ctx, **kwargs):
        ek = dict(kwargs.pop("extra_kwargs", {}) or {})
        ek.setdefault("max_tokens", _LLM_MAX_TOKENS)
        return super().chat(chat_ctx=chat_ctx, extra_kwargs=ek, **kwargs)


# ── Hangup detection ──────────────────────────────────────────────────────────
_HANGUP_RE = re.compile(
    r"\b("
    # Universal — these words are ONLY ever used to end a call
    r"bye|goodbye|alvida"
    # Hinglish bye combos
    r"|ok\s*bye|chalo\s*bye|theek\s*hai\s*bye|ok\s+ji\s+bye|accha\s+bye"
    # "I'm heading off" — very unambiguous phone-enders
    r"|chalta\s+hoon|chalti\s+hoon|nikalta\s+hoon|nikalti\s+hoon"
    r"|chalta\s+hu|chalti\s+hu|nikalta\s+hu|nikalti\s+hu"
    # Putting down the phone — only said when actually ending
    r"|phone\s+rakhna|phone\s+rakh|band\s+karo|rakho\s+phone|rakh\s+do"
    r"|call\s+khatam|khatam\s+karte\s+hain"
    r"|rakhta\s+hoon|rakhti\s+hoon|rakh\s+rahi\s+hoon"
    # System-level
    r"|disconnect|hang\s*up|call\s+end"
    r")\b",
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

_VOICEMAIL_RE = re.compile(
    r"\b("
    r"please leave (a |your )?message"
    r"|leave (a |your )?message after (the )?(beep|tone)"
    r"|not available to take your call"
    r"|(this |the )?(mailbox|inbox) (is full|has not been set up)"
    r"|this mailbox"
    r"|record (your |a )?message (after|at) the (beep|tone)"
    r"|recording will (begin|start)"
    r"|after the (beep|tone)"
    r"|reached (my |the )?(voicemail|voice mail)"
    r"|voicemail (service|box)"
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
        min_silence_duration    = 0.35,
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
        if self._turn_count < 5:
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
            await self.session.generate_reply()
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
                else:
                    logger.error("say() fallback also failed: %s", e2)
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
            self._last_user_activity = time.monotonic()

    async def _max_duration_guard(self, max_seconds: float) -> None:
        await asyncio.sleep(max_seconds)
        if not self._ending:
            logger.warning("Max call duration reached — auto-hangup")
            self._ending = True
            await self._do_hangup()

    async def on_user_turn_completed(self, turn_ctx, new_message) -> None:
        if self._ending:
            return

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
                _safe_task(self._silent_hangup(), "voicemail-hangup")
                return

            # IVR / automated bot detected — hang up silently
            if _BOT_IVR_RE.search(text):
                logger.info("IVR/bot detected at turn %d — silent hangup", self._turn_count)
                self._ending = True
                _safe_task(self._silent_hangup(), "bot-hangup")
                return

        # Only allow hangup-by-keyword after at least 6 customer turns (agent needs time to pitch)
        if self._turn_count >= 6 and _HANGUP_RE.search(text):
            self._ending = True
            _safe_task(self._do_hangup(), "hangup-from-keyword")
            return

    async def _post_call_report(self) -> None:
        """Classify outcome with Groq and POST to backend. Called once after every call."""
        if not self._call_id or not self._backend_url:
            return
        if self._reported:
            return
        self._reported = True
        try:
            await asyncio.wait_for(self._send_report(), timeout=15.0)
        except asyncio.TimeoutError:
            logger.error("post_call_report timed out — backend may be unreachable at %s", self._backend_url)
        except Exception as exc:
            logger.error("post_call_report failed: %s", exc)

    async def _send_report(self) -> None:
        import json as _json
        import httpx

        if not self._user_messages:
            return  # no conversation to classify; leave outcome as PENDING

        # Try to get full conversation (user + agent) from session history
        full_transcript: list[dict] = []
        try:
            ctx = getattr(self.session, "history", None) or getattr(self.session, "_chat_ctx", None)
            if ctx:
                items = getattr(ctx, "messages", None) or getattr(ctx, "items", [])
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
        except Exception:
            pass

        # Fallback: if session history unavailable, use only captured user messages
        if not full_transcript:
            full_transcript = [{"role": "user", "text": t} for t in self._user_messages]

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
            async with httpx.AsyncClient(timeout=10.0) as http:
                await http.post(
                    f"{self._backend_url}/api/calls/{self._call_id}/agent-report",
                    json={"outcome": outcome, "summary": summary, "transcript": full_transcript},
                )
            logger.info("post_call_report_sent | call=%s outcome=%s words=%d", self._call_id, outcome, customer_word_count)
            return

        # ── LLM classification (customer said enough to judge) ─────────────────
        outcome, summary = "not_interested", ""
        try:
            import groq as _groq
            client = _groq.AsyncGroq(api_key=os.environ.get("GROQ_API_KEY", ""))
            resp = await client.chat.completions.create(
                model="llama-3.1-8b-instant",
                max_tokens=200,
                temperature=0.0,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You classify sales call outcomes strictly from the CUSTOMER's words in the transcript. "
                            "Ignore STT errors — judge intent, not exact wording. "
                            "Reply ONLY with valid JSON: {\"outcome\": \"...\", \"summary\": \"...\"}\n\n"
                            "OUTCOME RULES — read carefully:\n\n"
                            "  interested         — Customer showed CLEAR, ACTIVE interest. Requires at least ONE of:\n"
                            "                       • Asked a specific question about price, availability, delivery, or specs\n"
                            "                       • Shared or agreed to share contact info (WhatsApp, phone, email)\n"
                            "                       • Agreed to receive catalogue, sample, demo, or quote\n"
                            "                       • Confirmed they currently buy or use this type of product\n"
                            "                       • Explicitly said they want to place an order or inquire\n"
                            "                       IMPORTANT: Passive replies only ('haan', 'hmm', 'theek hai', 'okay', 'bol') "
                            "do NOT count as interest — the customer must have asked something or agreed to something.\n\n"
                            "  callback_requested — Customer EXPLICITLY asked to be called back at a specific later time.\n\n"
                            "  not_interested     — DEFAULT for all other cases:\n"
                            "                       • Customer only gave short/vague replies without engaging\n"
                            "                       • Customer never asked a question or agreed to anything\n"
                            "                       • Rejection: 'nahi chahiye', 'busy hoon', 'mat karo call', hung up\n"
                            "                       WHEN IN DOUBT → use not_interested\n\n"
                            "  wrong_number       — Wrong person or wrong business.\n\n"
                            "  do_not_call        — Customer demanded never to be called again.\n\n"
                            "summary: 1–2 sentences. State what the customer actually said and what (if anything) was agreed."
                        ),
                    },
                    {"role": "user", "content": f"Transcript:\n{transcript_text}"},
                ],
            )
            raw = resp.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            result = _json.loads(raw.strip())
            outcome = result.get("outcome", "not_interested")
            summary = result.get("summary", "")
            valid = {"interested", "not_interested", "callback_requested", "wrong_number", "do_not_call"}
            if outcome not in valid:
                outcome = "not_interested"
            logger.info(
                "classify_llm: call=%s outcome=%s words=%d",
                self._call_id, outcome, customer_word_count,
            )
        except Exception as exc:
            logger.warning("groq_classify_error: %s", exc)

        async with httpx.AsyncClient(timeout=10.0) as http:
            await http.post(
                f"{self._backend_url}/api/calls/{self._call_id}/agent-report",
                json={
                    "outcome": outcome,
                    "summary": summary,
                    "transcript": full_transcript,
                },
            )
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

    async def _silent_hangup(self) -> None:
        """Hang up without a farewell (voicemail, bot, or prolonged silence)."""
        await self._post_call_report()
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
                try:
                    await self.session.say(_SILENCE_PROBES[probe_idx - 1], allow_interruptions=True)
                except Exception as e:
                    logger.warning("Silence probe TTS failed: %s", e)
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

    # Load template fields from room metadata (injected by campaign dispatcher).
    # Fall back to config.py values when running outside a campaign (e.g. test calls).
    meta: dict = {}
    if ctx.room.metadata:
        try:
            meta = json.loads(ctx.room.metadata)
        except Exception:
            pass

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
    voice_provider  = (meta.get("voice_provider") or "elevenlabs").lower()
    voice_id        = meta.get("voice_id") or (
        CARTESIA_VOICE_ID if voice_provider == "cartesia"
        else CHATTERBOX_VOICE_ID if voice_provider == "chatterbox"
        else SARVAM_VOICE_ID if voice_provider == "sarvam"
        else ELEVENLABS_VOICE_ID
    )
    language        = (meta.get("language") or "hinglish").lower()
    llm_model       = meta.get("llm_model") or GROQ_MODEL
    llm_temperature = float(meta.get("llm_temperature") or GROQ_LLM_TEMPERATURE)
    call_id         = meta.get("call_id", "")
    campaign_id     = meta.get("campaign_id", "")

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

    llm = _CappedGroqLLM(model=llm_model, temperature=llm_temperature)
    # Start warmup immediately with the real system prompt so Groq caches the full context.
    # Runs concurrently while we wait for the SIP participant to connect (usually 3-8s).
    warmup_task = _safe_task(_warmup_llm(llm, system_prompt), "llm-warmup")

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
            pace                = 1.10,   # 1.0 reads sluggish for phone calls; 1.10 is natural conversational pace
            temperature         = 0.6,    # Sarvam's own default — lowest that still sounds natural; higher caused tone drift between turns
        )
        logger.info("Sarvam TTS ready ✓ (model=%s speaker=%s lang=%s pace=1.10 temp=0.6)", SARVAM_MODEL, voice_id, sarvam_language)
    else:
        tts = elevenlabs.TTS(
            api_key               = ELEVENLABS_API_KEY,
            voice_id              = voice_id,
            model                 = ELEVENLABS_MODEL_ID,
            encoding              = "pcm_16000",  # phone SIP path uses ≤16kHz; pcm_24000 was overkill and caused more WS drops
            chunk_length_schedule = _CHUNK_LENGTH_SCHEDULE,
            voice_settings        = elevenlabs.VoiceSettings(
                stability         = 0.85,  # high = consistent tone across all chunks, no high/low shifts
                similarity_boost  = 0.85,
                style             = 0.0,   # zero expressiveness = no tonal variation between chunks
                use_speaker_boost = True,
            ),
        )
        logger.info("ElevenLabs TTS ready ✓ (voice=%s)", voice_id)

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
            interruption={
                "min_duration": 0.6,  # caller must sustain speech for 600ms to count as an interruption
                "min_words":    12,   # customer must say ~12 words to interrupt agent — prevents "haan/achha" and noise-triggered blips from breaking sentences
            },
        ),
        tts_text_transforms=["filter_markdown", "filter_emoji", honorific_greeting_transform, end_call_transform],
    )

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
            agent_name        = "voice-call-agent",
            worker_type       = agents.WorkerType.ROOM,
            num_idle_processes = 3,   # keep 3 processes warm for fast dispatch
            load_threshold    = 0.9,  # allow up to 90% CPU before refusing new jobs
        )
    )
