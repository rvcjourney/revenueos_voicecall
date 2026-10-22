"""
agent.py — the voice call agent. Every call runs on Sarvam: realtime STT,
sarvam-105b-conversations and Bulbul TTS (built in sarvam_pipeline.py).

The agent speaks the Greeting, then follows the agent's Instructions — the
backend has already filled every {variable}. Hanging up, switching language and
booking a next step are tools the LLM calls; no rules are hidden in the prompt.
"""

import os
import asyncio
import hashlib
import hmac
import json
import re
import time
import uuid
from typing import Literal

import certifi
import structlog
from datetime import datetime
from zoneinfo import ZoneInfo

os.environ["SSL_CERT_FILE"]      = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

from livekit import agents
from livekit.agents import AgentSession, Agent, JobProcess, RunContext, StopResponse, function_tool, stt, tts
from livekit.agents.llm import ChatContext
from livekit.agents.voice.room_io import AudioInputOptions, RoomOptions

import sarvam_pipeline
try:
    # Separate package (livekit-plugins-noise-cancellation) -- the livekit-agents
    # "[noise-cancellation]" extra no longer exists in 1.x and pip skips it
    # silently, which crash-looped the agent on the server (2026-09-29). Optional
    # so a missing install degrades to no noise removal instead of no calls.
    from livekit.plugins import noise_cancellation
except ImportError:
    noise_cancellation = None

from config import (
    AGENT_SYSTEM_PROMPT,
    LIVEKIT_AGENT_NAME,
    SARVAM_API_KEY,
    SARVAM_CHAT_URL,
    SARVAM_CLASSIFY_MODEL,
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


def _safe_task(coro, name: str = "") -> asyncio.Task:
    """create_task wrapper that logs instead of raising 'Future exception was never retrieved'."""
    task = asyncio.create_task(coro)
    def _on_done(t: asyncio.Task) -> None:
        if not t.cancelled() and (exc := t.exception()) is not None:
            # Was logger.debug — background tasks include the report-posting paths
            # (voicemail/bot hangups, disconnect handler), so a debug-level log here
            # meant a lost call report never showed up anywhere anyone would look.
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


async def _sarvam_chat(messages: list[dict], *, max_tokens: int) -> tuple[str, str | None]:
    """One non-streaming Sarvam chat completion (post-call classification).
    Returns (content, finish_reason)."""
    import httpx

    async with httpx.AsyncClient(timeout=30.0) as http:
        resp = await http.post(
            SARVAM_CHAT_URL,
            headers={"api-subscription-key": SARVAM_API_KEY},
            json={
                "model": SARVAM_CLASSIFY_MODEL,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": 0,
                "reasoning_effort": "low",
            },
        )
        resp.raise_for_status()
        choice = resp.json()["choices"][0]
        return (choice["message"].get("content") or "").strip(), choice.get("finish_reason")


# ── Silence handling ──────────────────────────────────────────────────────────
_SILENCE_INITIAL_SLEEP  = 15.0   # initial wait (covers greeting playback + response window)
_SILENCE_FIRST_TIMEOUT  = 18.0   # seconds of no user speech before first probe
_SILENCE_PROBE_INTERVAL = 10.0   # seconds between subsequent probes
_SILENCE_PROBE_COUNT    = 2      # probes before hanging up; each speaks the language's repeat_line

# Listening sounds ("backchannels") a caller makes WHILE the agent is talking —
# "haan", "hmm", "achha", "theek hai", "yes" — which mean "go on", not "stop".
# A transcript made up ONLY of these words (Roman + Devanagari, since Sarvam
# codemix outputs either) is dropped in VoiceAgent.stt_node while the agent is
# mid-sentence. Deliberately excludes anything that changes direction: "nahi",
# "no", "ruko", "wait", "kya", "lekin"/"but" — one such word anywhere in the
# utterance ("haan lekin...") and it's a real interruption.
_BACKCHANNEL_WORDS = frozenset({
    # English
    "hm", "hmm", "hmmm", "mm", "mmm", "mhm", "uh", "huh", "ok", "okay", "okey",
    "yes", "yeah", "yep", "yup", "ya", "right", "sure", "correct", "alright",
    "got", "it", "go", "ahead",
    # Hindi, Roman script
    "haan", "han", "haa", "ha", "haanji", "hanji", "ji", "jee", "achha", "acha",
    "accha", "achchha", "theek", "thik", "hai", "sahi", "bilkul", "boliye", "bolo",
    "bataiye",
    # Hindi, Devanagari
    "हाँ", "हां", "हा", "हाँजी", "हांजी", "हम्म", "हम", "जी", "अच्छा", "अच्छा", "ठीक",
    "है", "सही", "बिल्कुल", "बिलकुल", "बोलिए", "बोलो", "बताइए", "ओके", "यस", "राइट", "श्योर",
})
_BACKCHANNEL_MAX_WORDS = 6
# Splits on anything but letters/digits/Devanagari. The explicit Devanagari
# range is needed because Python's \w doesn't match vowel signs (ा ं ्), but it
# skips U+0964/U+0965 so the danda "।" / "॥" still counts as punctuation.
_BACKCHANNEL_SPLIT_RE = re.compile(r"[^\wऀ-ॣ०-ॿ]+")


def _is_backchannel(text: str) -> bool:
    """True if `text` is only listening sounds (see _BACKCHANNEL_WORDS)."""
    words = [w for w in _BACKCHANNEL_SPLIT_RE.split(text.lower()) if w]
    return 0 < len(words) <= _BACKCHANNEL_MAX_WORDS and all(w in _BACKCHANNEL_WORDS for w in words)

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


def build_instructions(instructions: str, state: "sarvam_pipeline.SarvamCallState") -> str:
    """The agent's own Instructions plus the call's language — a campaign setting
    the LLM can't otherwise know. Nothing else is added."""
    return f"{instructions.strip()}\n\n# Call language\nThis call is in {state.lang['display']}."


# =============================================================================
# LLM WARMUP
# =============================================================================
async def _warmup_llm(llm, system_prompt: str = "") -> None:
    """Send a real warmup request with the actual system prompt so the first
    real turn isn't slowed by a cold, large prompt."""
    try:
        ctx = ChatContext()
        if system_prompt:
            ctx.add_message(role="system", content=system_prompt)
        ctx.add_message(role="user", content="Namaste")
        t0 = time.monotonic()
        async with llm.chat(chat_ctx=ctx, extra_kwargs={"max_tokens": 8}) as stream:
            async for _ in stream:
                break
        logger.info("LLM pre-warmed with system prompt ✓ (%.1fs to first token)", time.monotonic() - t0)
    except Exception as e:
        # warning, not debug: a silent failed warmup = slow first reply with no trace in logs
        logger.warning("LLM warmup FAILED (first reply will be cold): %s", e)


# =============================================================================
# PREWARM — runs once per worker process on startup
# =============================================================================
def prewarm(proc: JobProcess) -> None:
    try:
        sarvam_pipeline.validate_components()
        proc.userdata["sarvam_ok"] = True
    except Exception as exc:  # calls refuse cleanly instead of failing mid-call
        proc.userdata["sarvam_ok"] = False
        logger.error("sarvam_engine_invalid_config | %s", exc)
    if noise_cancellation is None:
        logger.warning("livekit-plugins-noise-cancellation not installed — calls run WITHOUT noise removal")


# =============================================================================
# AGENT
# =============================================================================
class VoiceAgent(Agent):
    """One phone call: greeting, the agent's instructions, three tools
    (end_interaction, switch_language, book_next_step), voicemail/IVR/silence
    handling, an empty-reply guard, history trimmed to the model's window, and a
    signed post-call report."""

    # Per-turn numbers LiveKit attaches to each ChatMessage (llm.MetricsReport).
    _LATENCY_KEYS = ("e2e_latency", "transcription_delay", "end_of_turn_delay", "llm_node_ttft", "tts_node_ttfb")

    def __init__(
        self, room, *,
        instructions: str,
        welcome_message: str,
        sarvam_state: "sarvam_pipeline.SarvamCallState",
        call_id: str = "",
        backend_url: str = "",
        webhook_secret: str = "",
        max_duration: int = 600,
    ) -> None:
        self._room            = room
        self._ending          = False
        self._reported        = False
        self._welcome_message = welcome_message
        self._sarvam          = sarvam_state
        self._call_id         = call_id
        self._backend_url     = backend_url
        self._webhook_secret  = webhook_secret
        self._max_duration    = max_duration
        self._user_messages: list[str] = []
        self._turn_count      = 0
        self._last_user_activity = 0.0  # time.monotonic() — updated on user speech
        self._probing = False  # True while _silence_watchdog's own say() is in flight
        self._speaking_done = asyncio.Event()
        self._speaking_done.set()  # not speaking initially
        self._booking: dict | None = None
        self._last_reply_text = ""  # words the LLM spoke in its latest step (end_interaction checks it)
        self._false_interruptions = 0
        self._recoverable_errors = 0
        self._tts_engine = None  # set by entrypoint(); switch_language retargets them
        self._stt_engine = None

        super().__init__(instructions=instructions, tools=[self._switch_language_tool()])

    # ── Tools ─────────────────────────────────────────────────────────────────
    @function_tool
    async def end_interaction(self, ctx: RunContext) -> str | None:
        """End the phone call, once the conversation is over and you have said goodbye. Never call it mid-conversation."""
        if self._ending:
            return None
        self._ending = True
        said_goodbye = bool(self._last_reply_text.strip())
        logger.info("end_interaction called at turn %d (goodbye spoken: %s)", self._turn_count, said_goodbye)
        # The tool reply (if any) plays on this same speech handle, so hang up once
        # it's done. A callback, not an await: awaiting the handle from inside its
        # own tool would wait on itself.
        ctx.speech_handle.add_done_callback(lambda _: _safe_task(self._hangup_after_goodbye(), "end-interaction"))
        # Sarvam's model often calls this with no words first (checked live
        # 2026-10-22) — then ask for the goodbye as the tool reply.
        return None if said_goodbye else "Say a brief, warm goodbye now, in the call's language. Do not call any tool."

    async def _hangup_after_goodbye(self) -> None:
        await asyncio.sleep(0.5)  # let the last audio frames flush through the SIP path
        await self._post_call_report()
        await self._disconnect()

    @function_tool
    async def book_next_step(
        self,
        ctx: RunContext,
        prospect_name: str,
        company: str,
        next_step_type: str,
        date_time: str,
        attendees: str = "",
    ) -> dict:
        """Book the next step (demo, meeting or follow-up) the prospect just agreed to.

        Args:
            prospect_name: The prospect's name.
            company: The prospect's company.
            next_step_type: What was agreed, e.g. "demo" or "discovery follow-up".
            date_time: The confirmed date and time, in natural language.
            attendees: Anyone else the prospect named to join, comma-separated.
        """
        reference = f"NS-{uuid.uuid4().hex[:6].upper()}"
        self._booking = {
            "prospect_name": prospect_name, "company": company, "next_step_type": next_step_type,
            "date_time": date_time, "attendees": attendees, "reference": reference,
        }
        logger.info("book_next_step | call=%s reference=%s when=%s", self._call_id, reference, date_time)
        return {"status": "confirmed", "reference": reference, "date_time": date_time}

    def _switch_language_tool(self):
        keys = tuple(self._sarvam.languages)
        names = ", ".join(f"{k} ({v['display']})" for k, v in self._sarvam.languages.items())
        language_type = Literal[keys]  # type: ignore[valid-type]

        async def switch_language(ctx: RunContext, language: language_type) -> str:  # type: ignore[valid-type]
            """Switch the call's spoken language (speech recognition and voice).

            Args:
                language: The language to switch to.
            """
            if self._tts_engine is None or not sarvam_pipeline.switch_language(
                self._sarvam, language, self._tts_engine, self._stt_engine,
            ):
                return f"{language} is not available on this call; continue in {self._sarvam.lang['display']}."
            return f"Switched. Continue the conversation in {self._sarvam.lang['display']}."

        return function_tool(
            switch_language,
            name="switch_language",
            description=f"Switch the spoken language when the caller asks to talk in another language. Available: {names}.",
        )

    def attach_engines(self, tts_engine, stt_engine) -> None:
        self._tts_engine, self._stt_engine = tts_engine, stt_engine

    # ── Call lifecycle ────────────────────────────────────────────────────────
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

    async def on_enter(self) -> None:
        logger.info("Agent entered room — pipeline ready")
        await asyncio.sleep(0.1)  # let TTS output track attach
        if self._ending:
            return  # participant left before on_enter ran (rejected call)
        self.session.on("agent_state_changed", self._on_agent_state_changed)
        try:
            if self._welcome_message.strip():
                await self.session.say(self._welcome_message)
            else:
                await self.session.generate_reply()
            logger.info("Greeting spoken ✓")
        except Exception as e:
            msg = str(e).lower()
            if "closing" in msg or "closed" in msg or "shutdown" in msg:
                logger.debug("Session closed before greeting (call rejected early)")
                return
            # The voice pipeline itself is broken (bad voice, provider auth failure):
            # the call is connected but the agent can never speak. End it now and
            # flag it as a real system failure instead of a quiet conversation.
            logger.error("Greeting failed — ending call: %s", e)
            self._ending = True
            await self._report_system_failure(f"Greeting failed: {e}")
            await self._disconnect()
            return
        self._last_user_activity = time.monotonic()
        _safe_task(self._max_duration_guard(), "max-duration-guard")
        _safe_task(self._silence_watchdog(), "silence-watchdog")

    def _on_agent_state_changed(self, ev) -> None:
        if ev.new_state == "speaking":
            self._speaking_done.clear()
        if ev.old_state == "speaking" and ev.new_state != "speaking":
            self._speaking_done.set()
            # The silence clock counts from when the AGENT stops talking, not from the
            # last user turn — skipped during the watchdog's own probe, otherwise the
            # probe resets the clock and the watchdog never reaches its hang-up path.
            if not self._probing:
                self._last_user_activity = time.monotonic()

    async def _max_duration_guard(self) -> None:
        await asyncio.sleep(self._max_duration)
        if not self._ending:
            logger.warning("Max call duration reached — auto-hangup")
            self._ending = True
            await self._silent_hangup()

    async def stt_node(self, audio, model_settings):
        # Drops pure listening sounds ("haan", "hmm", "yes"...) said while the agent
        # is mid-sentence, so they never reach the SDK as a transcript — otherwise a
        # "haan" both cuts the agent's sentence for good and becomes a user turn the
        # LLM replies to. "haan" after the agent finished (answering its question)
        # is untouched: current_speech is done by then.
        logged = False
        async for ev in Agent.default.stt_node(self, audio, model_settings):
            rid = getattr(ev, "request_id", None)
            if rid and not logged:
                logged = True
                logger.info("sarvam_stt_session | request_id=%s language=%s", rid, self._sarvam.language)
            if (
                isinstance(ev, stt.SpeechEvent)
                and ev.type in (
                    stt.SpeechEventType.FINAL_TRANSCRIPT,
                    stt.SpeechEventType.INTERIM_TRANSCRIPT,
                    stt.SpeechEventType.PREFLIGHT_TRANSCRIPT,
                )
                and ev.alternatives
                and self._agent_mid_speech()
                and _is_backchannel(ev.alternatives[0].text)
            ):
                logger.info("Backchannel ignored while agent speaking: %r", ev.alternatives[0].text)
                continue
            yield ev

    def _agent_mid_speech(self) -> bool:
        # current_speech stays set (not interrupted, not done) while its audio is
        # merely paused by a possible interruption, which is exactly the window a
        # backchannel's transcript lands in.
        speech = self.session.current_speech
        return speech is not None and not speech.interrupted and not speech.done()

    async def llm_node(self, chat_ctx, tools, model_settings):
        ctx = sarvam_pipeline.trim_to_budget(chat_ctx)
        logger.info("llm_prompt_size | turn=%d est_tokens=%d", self._turn_count, sarvam_pipeline.estimate_tokens(ctx))
        text, called_tool = "", False
        self._last_reply_text = ""
        async for chunk in Agent.default.llm_node(self, ctx, tools, model_settings):
            delta = getattr(chunk, "delta", None)
            if getattr(delta, "tool_calls", None):
                called_tool = True
            text += chunk if isinstance(chunk, str) else (getattr(delta, "content", None) or "")
            self._last_reply_text = text
            yield chunk
        # Only after a real customer turn, and not when the model answered with a tool call.
        if self._turn_count > 0 and not text.strip() and not called_tool and not self._ending:
            self._sarvam.empty_replies += 1
            logger.warning("empty_llm_reply | turn=%d total=%d", self._turn_count, self._sarvam.empty_replies)
            yield self._sarvam.lang.get("repeat_line") or "Sorry, could you say that again?"
        elif text and sarvam_pipeline.looks_romanised(text, self._sarvam.language):
            self._sarvam.romanised_replies += 1
            logger.warning("romanised_llm_reply | turn=%d language=%s", self._turn_count, self._sarvam.language)

    async def on_user_turn_completed(self, turn_ctx, new_message) -> None:
        if self._ending:
            raise StopResponse()

        text = (getattr(new_message, "text_content", "") or "").strip()
        self._turn_count += 1
        logger.info("Turn %d: %r", self._turn_count, text[:80])
        if not text:
            return

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

    async def apology_hangup(self, *, can_speak: bool) -> None:
        if can_speak:
            line = self._sarvam.lang.get("failure_line") or "Sorry, we have a technical problem. Thank you for your time."
            try:
                await asyncio.wait_for(self.session.say(line, allow_interruptions=False), timeout=10.0)
            except Exception as exc:
                logger.warning("Apology TTS failed: %s", exc)
        await self._silent_hangup()

    async def _silent_hangup(self, *, outcome_override: str | None = None, abrupt_disconnect: bool = False) -> None:
        """Hang up without a goodbye (voicemail, bot, silence, max duration)."""
        await self._post_call_report(outcome_override=outcome_override, abrupt_disconnect=abrupt_disconnect)
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
            if probe_idx < _SILENCE_PROBE_COUNT:
                probe_idx += 1
                logger.info("Silence probe #%d (%.1fs silent)", probe_idx, silence_sec)
                self._probing = True
                try:
                    line = self._sarvam.lang.get("repeat_line") or "Hello, can you hear me?"
                    await self.session.say(line, allow_interruptions=True)
                except Exception as e:
                    logger.warning("Silence probe TTS failed: %s", e)
                finally:
                    self._probing = False
                await asyncio.sleep(_SILENCE_PROBE_INTERVAL)
            else:
                logger.info("Silence hangup — %.1fs no response after %d probes", silence_sec, _SILENCE_PROBE_COUNT)
                if not self._ending:
                    self._ending = True
                    await self._silent_hangup()
                return

    # ── Reporting ─────────────────────────────────────────────────────────────
    async def _report_system_failure(self, error_text: str) -> None:
        """The voice pipeline failed before the agent ever spoke — the call
        connected but is completely silent. Report it as a real system failure
        (CallStatus.FAILED + error_message) instead of a quiet conversation."""
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

    def _latency_report(self) -> dict:
        """Numbers only (never transcript text): per-turn samples, capped, so the
        backend can compute real p50/p95 across calls, plus per-call counts."""
        samples: dict[str, list[float]] = {k: [] for k in self._LATENCY_KEYS}
        ctx = getattr(self.session, "history", None)
        messages_attr = getattr(ctx, "messages", None)
        items = messages_attr() if callable(messages_attr) else getattr(ctx, "items", []) or []
        for msg in items:
            metrics = getattr(msg, "metrics", None) or {}
            for key in self._LATENCY_KEYS:
                value = metrics.get(key)
                if isinstance(value, (int, float)) and value >= 0:
                    samples[key].append(round(float(value), 3))
        counts = {
            "turns": self._turn_count,
            "false_interruptions": self._false_interruptions,
            "recoverable_errors": self._recoverable_errors,
            "empty_replies": self._sarvam.empty_replies,
            "romanised_replies": self._sarvam.romanised_replies,
            "clone_fallback": int(bool(self._sarvam.extra.get("clone_fallback"))),
        }
        return {"samples": {k: v[:100] for k, v in samples.items() if v}, "counts": counts}

    async def _post_agent_report(self, payload: dict, *, attempts: int = 3) -> None:
        """POST the call report to the backend, retrying transient failures.

        The transcript/summary only ever exist in this in-memory report, so a
        dropped connection or backend restart must not lose it.
        """
        import httpx

        url = f"{self._backend_url}/api/calls/{self._call_id}/agent-report"
        try:
            payload = {**payload, "pipeline": sarvam_pipeline.PIPELINE, "latency_metrics": self._latency_report()}
        except Exception as exc:  # metrics must never cost us the report itself
            logger.warning("latency_report_failed | %s", exc)
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
                    # Without a status check a 500 during a backend restart looked
                    # like success and the report was silently dropped.
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

    async def _post_call_report(self, *, outcome_override: str | None = None, abrupt_disconnect: bool = False) -> None:
        """Classify the outcome and POST it to the backend. Called once after every call.

        outcome_override: the outcome is already known for certain (e.g. voicemail
        phrase detection) — skip the classifier and report this value directly.
        abrupt_disconnect: the customer's line dropped before the agent closed the
        call, so "barely anything said" means call_dropped, not not_interested.
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
            await asyncio.wait_for(
                self._send_report(outcome_override=outcome_override, abrupt_disconnect=abrupt_disconnect),
                timeout=40.0,
            )
        except asyncio.TimeoutError:
            logger.error("post_call_report timed out — backend may be unreachable at %s", self._backend_url)
        except Exception as exc:
            logger.error("post_call_report failed: %s", exc)

    def _transcript(self) -> list[dict]:
        full_transcript: list[dict] = []
        try:
            ctx = getattr(self.session, "history", None) or getattr(self.session, "_chat_ctx", None)
            if ctx:
                # ChatContext.messages is a METHOD (not a property) — must be called.
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
        return full_transcript or [{"role": "user", "text": t} for t in self._user_messages]

    async def _send_report(self, *, outcome_override: str | None = None, abrupt_disconnect: bool = False) -> None:
        full_transcript = self._transcript()
        extra = {"next_step_booking": self._booking} if self._booking else {}

        if not full_transcript and not outcome_override:
            if abrupt_disconnect:
                # A call that never really started: the line dropped before anyone
                # spoke. Report it, or the outcome sits at "pending" forever.
                await self._post_agent_report({
                    "outcome": "call_dropped",
                    "summary": "Call disconnected before any conversation happened.",
                    "transcript": [],
                })
                logger.info("post_call_report_sent | call=%s outcome=call_dropped (no transcript)", self._call_id)
                return
            logger.info("post_call_report_skipped | call=%s reason=no_conversation_captured", self._call_id)
            return  # nothing was said by either side; leave outcome as PENDING

        # A deterministic detector (voicemail phrasing) already knows the outcome.
        if outcome_override:
            summary = f"Call ended automatically: {outcome_override.replace('_', ' ')} detected."
            await self._post_agent_report({
                "outcome": outcome_override, "summary": summary, "transcript": full_transcript,
            })
            logger.info("post_call_report_sent | call=%s outcome=%s (override)", self._call_id, outcome_override)
            return

        transcript_text = "\n".join(
            f"{'CUSTOMER' if m['role'] == 'user' else 'AGENT'}: {m['text']}"
            for m in full_transcript
        )

        # ── Minimum engagement gate ────────────────────────────────────────────
        # If the customer barely spoke there isn't enough to judge either way —
        # classify deterministically instead of asking the LLM.
        customer_word_count = sum(
            len(m.get("text", "").split()) for m in full_transcript if m.get("role") == "user"
        )
        if customer_word_count < 8 and not self._booking:
            if abrupt_disconnect:
                outcome = "call_dropped"
                summary = "Call disconnected before a real conversation happened."
            else:
                outcome = "not_interested"
                summary = "Customer did not engage meaningfully in the conversation."
            logger.info(
                "classify_skip: customer only spoke %d words (abrupt_disconnect=%s) — marking %s",
                customer_word_count, abrupt_disconnect, outcome,
            )
            await self._post_agent_report({"outcome": outcome, "summary": summary, "transcript": full_transcript})
            logger.info("post_call_report_sent | call=%s outcome=%s words=%d", self._call_id, outcome, customer_word_count)
            return

        outcome, summary, extracted_data = await self._classify(transcript_text, abrupt_disconnect)
        await self._post_agent_report({
            "outcome": outcome,
            "summary": summary,
            "transcript": full_transcript,
            "extracted_data": {**extracted_data, **extra},
        })
        logger.info("post_call_report_sent | call=%s outcome=%s", self._call_id, outcome)

    async def _classify(self, transcript_text: str, abrupt_disconnect: bool) -> tuple[str, str, dict]:
        """Sarvam LLM reads the transcript (and the agent's instructions, to know
        which details it was told to capture). On failure: outcome "pending",
        which the backend's flag_stale_pending_calls task already watches."""
        call_dropped_rule = (
            "  call_dropped        — The customer's line disconnected abruptly before the "
            "conversation reached any real conclusion. Use this ONLY when the transcript was cut "
            "short before any clear signal; classify a clear signal normally even if the call "
            "ended abruptly.\n\n"
        ) if abrupt_disconnect else ""
        booked_rule = (
            "A next step was booked on this call (see NEXT STEP BOOKED below) — that is clear interest.\n\n"
            if self._booking else ""
        )
        system = (
            "You classify sales call outcomes strictly from the CUSTOMER's words in the transcript. "
            "Ignore speech-recognition errors — judge intent, not exact wording. "
            "Reply ONLY with valid JSON: {\"outcome\": \"...\", \"summary\": \"...\", \"extracted_data\": {...}}\n\n"
            "extracted_data — every detail the AGENT INSTRUCTIONS below say to capture, using the exact "
            "snake_case names they mention (e.g. pain_points_mentioned, timeline_to_decide), plus "
            "caller_name, caller_email and caller_phone if the customer gave them. Fill ONLY what the "
            "customer actually said; use null for anything not mentioned. Never guess.\n\n"
            "OUTCOME RULES:\n\n"
            "  interested         — Customer showed CLEAR, ACTIVE interest: asked a specific question about "
            "price/availability/specs, shared or agreed to share contact info, agreed to a demo, meeting, "
            "catalogue or quote, or said they want to buy. Passive replies only ('haan', 'hmm', 'theek "
            "hai', 'okay') do NOT count.\n\n"
            "  callback_requested — Customer asked to be called back AND gave a SPECIFIC later time (a day, "
            "date or time of day). A vague 'call me later' with no time is a brush-off, not a callback.\n\n"
            "  not_interested     — DEFAULT for everything else, including rejections and vague replies. "
            "WHEN IN DOUBT → not_interested.\n\n"
            f"{call_dropped_rule}"
            "  wrong_number       — Wrong person or wrong business.\n\n"
            "  do_not_call        — Customer demanded never to be called again.\n\n"
            f"{booked_rule}"
            "summary: 1–2 sentences. State what the customer actually said and what (if anything) was agreed."
        )
        user = f"AGENT INSTRUCTIONS:\n{self.instructions}\n\nTRANSCRIPT:\n{transcript_text}"
        if self._booking:
            user += f"\n\nNEXT STEP BOOKED: {json.dumps(self._booking)}"

        raw, finish_reason = None, None
        try:
            raw, finish_reason = await _sarvam_chat(
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
                max_tokens=1500,
            )
            text = raw
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            result = json.loads(text.strip())
            outcome = result.get("outcome", "not_interested")
            summary = result.get("summary", "")
            extracted = {k: v for k, v in (result.get("extracted_data") or {}).items() if v is not None}
            valid = {"interested", "not_interested", "callback_requested", "wrong_number", "do_not_call"}
            if abrupt_disconnect:
                valid.add("call_dropped")
            if outcome not in valid:
                outcome = "not_interested"
            logger.info("classify_llm: call=%s outcome=%s finish_reason=%s", self._call_id, outcome, finish_reason)
            return outcome, summary, extracted
        except Exception as exc:
            logger.warning(
                "classify_error | call=%s error_type=%s error=%s stage=%s finish_reason=%s raw_preview=%r",
                self._call_id, type(exc).__name__, exc,
                "api_call" if raw is None else "parse", finish_reason, raw[:500] if raw else None,
            )
            return "pending", "", {}


def _sentry_message(message: str, level: str) -> None:
    try:
        import sentry_sdk
        sentry_sdk.capture_message(message, level=level)
    except Exception:
        pass


def handle_session_error(voice_agent: "VoiceAgent", ev) -> None:
    """session.on("error"). A non-recoverable LLM/TTS error ends the call cleanly:
    one fixed apology (when the voice still works), then the normal report +
    hang-up."""
    source = type(ev.source).__name__
    status = getattr(ev.error, "status_code", None) or getattr(getattr(ev.error, "error", None), "status_code", None)
    if getattr(ev.error, "recoverable", True):
        voice_agent._recoverable_errors += 1
        if voice_agent._recoverable_errors == 3:  # sustained, non-fatal: alert once per call
            _sentry_message(f"sarvam engine: repeated recoverable errors ({source}, status={status})", "warning")
        return
    if voice_agent._ending:
        return
    voice_agent._ending = True
    # Close code 1003 = auth/quota/rate limit, 1008 = session timeout; a 4xx such
    # as "model not found" means Sarvam retired or renamed something.
    logger.error("sarvam_engine_failed | source=%s status=%s error=%s", source, status, ev.error)
    _sentry_message(f"sarvam engine failure ({source}, status={status})", "error")
    _safe_task(voice_agent.apology_hangup(can_speak=not isinstance(ev.source, tts.TTS)), "sarvam-apology-hangup")


def handle_session_close(voice_agent: "VoiceAgent", ev) -> None:
    """Registered on session.on("close", ...) in entrypoint() below.

    Covers the SDK force-closing the session after repeated LLM/TTS failures —
    without this the caller sat on a dead line until the max-duration guard.
    Also fires on every teardown we initiated ourselves; harmless, since the
    report is idempotent (voice_agent._reported) and _disconnect() is safe to
    call twice. A standalone function so it's unit-testable without a real
    session — see tests/test_session_close_handler.py.
    """
    if ev.error is not None:
        logger.error("AgentSession closed due to an unrecoverable error | reason=%s error=%s",
                     ev.reason, ev.error)
    if voice_agent._ending:
        return
    voice_agent._ending = True
    _safe_task(voice_agent._silent_hangup(), "post-call-on-session-close")


# =============================================================================
# ENTRYPOINT
# =============================================================================
async def entrypoint(ctx: agents.JobContext) -> None:
    logger.info("Job received | room=%s", ctx.room.name)
    await ctx.connect()

    # Dispatch metadata arrives with the job itself; room metadata (same payload,
    # set by the backend's _place_call) can race ctx.connect() and read back empty.
    raw_meta = ctx.job.metadata or ctx.room.metadata
    logger.info(
        "job_metadata_raw | room=%s job_present=%s room_present=%s len=%s",
        ctx.room.name, bool(ctx.job.metadata), bool(ctx.room.metadata), len(raw_meta) if raw_meta else 0,
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

    call_id     = meta.get("call_id", "")
    campaign_id = meta.get("campaign_id", "")
    set_log_context(call_id=call_id, room=ctx.room.name, campaign_id=campaign_id, pipeline=sarvam_pipeline.PIPELINE)
    if not ctx.proc.userdata.get("sarvam_ok", True):
        logger.error("sarvam_engine_unavailable | worker failed its startup check — refusing this call")
        return
    try:
        sarvam_state = sarvam_pipeline.parse_meta(meta)
    except Exception as exc:
        logger.error("call_config_invalid | %s meta_keys=%s", exc, list(meta.keys()))
        return

    if not meta.get("system_prompt"):
        logger.warning("system_prompt | source=CONFIG_FALLBACK — metadata had no system_prompt! campaign=%s", campaign_id)
    system_prompt   = build_instructions(meta.get("system_prompt") or AGENT_SYSTEM_PROMPT, sarvam_state)
    welcome_message = meta.get("welcome_message") or ""
    sarvam_cfg      = meta.get("sarvam") or {}

    llm = sarvam_pipeline.build_llm(float(meta.get("llm_temperature") or 0.7))
    # Warm up while we wait for the SIP participant to connect (usually 3-8s).
    warmup_task = _safe_task(_warmup_llm(llm, system_prompt), "llm-warmup")

    try:
        participant = await asyncio.wait_for(ctx.wait_for_participant(), timeout=30.0)
        logger.info("Participant joined: %s", getattr(participant, "identity", "unknown"))
    except asyncio.TimeoutError:
        logger.error("No participant joined in 30s — exiting")
        warmup_task.cancel()
        return

    try:
        await asyncio.wait_for(asyncio.shield(warmup_task), timeout=6.0)
        logger.info("LLM warmup confirmed complete ✓")
    except (asyncio.TimeoutError, Exception) as e:
        logger.debug("LLM warmup await skipped: %s", e)  # proceed anyway

    tts_engine = sarvam_pipeline.build_tts(sarvam_state)
    logger.info("Sarvam TTS ready ✓ (model=%s speaker=%s lang=%s)",
                sarvam_state.lang["tts_model"], sarvam_state.voice_id, sarvam_state.lang["tts"])
    # Pre-open the TTS WebSocket now rather than on the agent's first spoken turn.
    tts_engine.prewarm()
    stt_engine = sarvam_pipeline.build_stt(sarvam_state, sarvam_cfg.get("stt_prompt"))

    voice_agent = VoiceAgent(
        ctx.room,
        instructions=system_prompt,
        welcome_message=welcome_message,
        sarvam_state=sarvam_state,
        call_id=call_id,
        backend_url=BACKEND_INTERNAL_URL,
        webhook_secret=AGENT_WEBHOOK_SECRET,
        max_duration=int(meta.get("max_duration") or 600),
    )
    voice_agent.attach_engines(tts_engine, stt_engine)

    def _log_tts_ttfb(metrics) -> None:
        # ttfb = "synthesis requested" -> "first audio byte back": whether the
        # caller heard a real pause before the agent started speaking.
        if getattr(metrics, "type", None) != "tts_metrics":
            return
        logger.info("TTS time-to-first-audio-byte: %.3fs (turn %d)", metrics.ttfb, voice_agent._turn_count)

    tts_engine.on("metrics_collected", _log_tts_ttfb)

    session = AgentSession(
        stt=stt_engine,
        llm=llm,
        tts=tts_engine,
        **sarvam_pipeline.SESSION_KWARGS,
        turn_handling=sarvam_pipeline.turn_handling(),
        tts_text_transforms=["filter_markdown", "filter_emoji"],
    )

    def _on_user_state_changed(ev) -> None:
        # Fires the instant the customer stopped talking, i.e. BEFORE the
        # endpointing wait — diff against "Turn N" / TTS ttfb logs for real gaps.
        if ev.new_state == "listening":
            logger.info("User stopped speaking (endpointing wait starts now) | turn %d", voice_agent._turn_count)

    session.on("user_state_changed", _on_user_state_changed)

    def _on_speech_created(ev) -> None:
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
    session.on("close", lambda ev: handle_session_close(voice_agent, ev))
    session.on("error", lambda ev: handle_session_error(voice_agent, ev))

    def _on_false_interruption(_ev) -> None:
        voice_agent._false_interruptions += 1

    session.on("agent_false_interruption", _on_false_interruption)

    @ctx.room.on("participant_disconnected")
    def _on_participant_left(participant):
        # Customer hung up — classify + POST the outcome BEFORE tearing the room
        # down ourselves (close_on_disconnect is off below): with it on, the room
        # teardown won the race against the report and every customer-hangup call
        # landed on outcome=pending.
        if not voice_agent._ending:
            voice_agent._ending = True
            logger.info("Participant disconnected — reporting outcome before disconnect")
            _safe_task(voice_agent._silent_hangup(abrupt_disconnect=True), "post-call-on-disconnect")

    try:
        await session.start(
            agent       = voice_agent,
            room        = ctx.room,
            room_options= RoomOptions(
                close_on_disconnect  = False,
                delete_room_on_close = True,
                # Strips traffic/TV/background voices from the caller's audio before
                # the interruption check hears it. BVCTelephony is tuned for
                # narrowband SIP phone audio. Requires LiveKit Cloud.
                audio_input          = AudioInputOptions(
                    noise_cancellation=noise_cancellation.BVCTelephony() if noise_cancellation else None,
                ),
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
