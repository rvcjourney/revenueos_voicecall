"""
agent.py — Hinglish Voice Sales Agent (Baba Valve India)
Pipeline: Deepgram STT → Groq LLM → ElevenLabs TTS (via livekit-plugins-elevenlabs)
Target latency: 300–600ms (STT final → first TTS audio byte)
"""

import os
import asyncio
import json
import logging
import re
import certifi

os.environ["SSL_CERT_FILE"]      = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

from livekit import agents
from livekit.agents import AgentSession, Agent, JobProcess, TurnHandlingOptions
from livekit.agents.beta.tools import EndCallTool
from livekit.agents.llm import ChatContext
from livekit.agents.voice.room_io import RoomOptions
from livekit.plugins import deepgram, groq, silero, elevenlabs

from config import (
    AGENT_SYSTEM_PROMPT,
    AGENT_WELCOME_MESSAGE,
    GROQ_MODEL,
    ELEVENLABS_API_KEY,
    ELEVENLABS_VOICE_ID,
    ELEVENLABS_MODEL_ID,
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
_LLM_MAX_TOKENS = 80  # ~2 short Hinglish sentences; lower = faster first TTS byte

# Characters buffered before ElevenLabs starts generating audio.
# 30 = aggressive low-latency; ElevenLabs default is [120, 160, 250, 290].
_CHUNK_LENGTH_SCHEDULE = [10, 80, 150, 250]


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
    r"bye|goodbye|alvida"
    r"|ok\s*bye|chalo\s*bye|theek\s*hai\s*bye"
    r"|phir\s+milenge|phir\s+baat\s+karte"
    r"|phone\s+rakhna|phone\s+rakh|band\s+karo"
    r"|call\s+khatam|khatam\s+karte|khatam\s+karte\s+hain"
    r"|rakhta\s+hoon|rakhti\s+hoon|rakh\s+rahi\s+hoon"
    r"|dhanyavaad|shukriya|take\s+care|have\s+a\s+good\s+day"
    r"|disconnect|hang\s*up|call\s+end"
    r")\b",
    re.IGNORECASE | re.UNICODE,
)
_FAREWELL = "Shukriya sir, take care!"

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
def _build_prompt(raw: str) -> str:
    p = raw.strip()
    guardrails = (
        "[ABSOLUTE RULES — never break these]\n"
        "1. MAX 2 SHORT SENTENCES per reply. Never more.\n"
        "2. Never invent product grades, prices, or specs not in this prompt.\n"
        "3. Never reveal you are an AI, chatbot, or language model.\n"
        "4. Never use bullet points, lists, or markdown — this is spoken audio.\n"
        "5. If unsure about anything: say \"Main confirm karke batata hoon sir\" only.\n"
        "6. Never ask more than ONE question per reply.\n"
        "7. Stay in character as Aniket at ALL times.\n"
        "8. Respond ONLY in natural spoken Hinglish.\n"
        "9. ONLY discuss Baba Valve India products and this sales call. "
        "Off-topic: \"Sir main sirf Baba Valve India ke products ke baare mein baat kar sakta hoon.\"\n"
        "10. If asked for info not in this prompt: "
        "\"Iske liye aap hamare website par ja sakte hain: www dot babavalveindia dot com\"\n"
        "11. NEVER say the words 'end_call' or 'end call' out loud — the system ends the call automatically.\n"
        "12. When the conversation is naturally over (customer not interested, info collected, or they said goodbye), "
        "call the end_call tool immediately after your final sentence. Do NOT keep talking.\n"
    )
    return guardrails + "\n" + p

# =============================================================================
# LLM WARMUP
# =============================================================================
async def _warmup_llm(llm: _CappedGroqLLM) -> None:
    try:
        ctx = ChatContext()
        ctx.add_message(role="user", content="Namaste")
        async with llm.chat(chat_ctx=ctx, extra_kwargs={"max_tokens": 5}) as stream:
            async for _ in stream:
                break
        logger.info("LLM pre-warmed ✓")
    except Exception as e:
        logger.debug("LLM warmup skipped: %s", e)


# =============================================================================
# PREWARM — runs once per worker process on startup
# =============================================================================
def prewarm(proc: JobProcess) -> None:
    proc.userdata["vad"] = silero.VAD.load(
        min_silence_duration   = 0.22,
        activation_threshold   = 0.75,
        deactivation_threshold = 0.40,
        sample_rate            = 16000,
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

        end_call_tool = EndCallTool(
            delete_room=True,
            end_instructions="Say ONE short goodbye in Hindi/Hinglish, then the call will end.",
            on_tool_called=self._on_end_call_tool_called,
        )
        super().__init__(
            instructions=instructions,
            tools=[end_call_tool],
        )

    async def _on_end_call_tool_called(self, ev) -> None:
        logger.info("EndCallTool triggered by LLM — disconnecting")
        self._ending = True
        await asyncio.sleep(5.0)  # wait for farewell TTS to finish generating + playing
        await self._post_call_report()
        await self._disconnect()

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
        if self._ending:
            return
        logger.info("TTS filter: end_call detected — hanging up")
        self._ending = True
        _safe_task(self._do_hangup(), "hangup-from-end-call-filter")

    async def on_enter(self) -> None:
        logger.info("Agent entered room — pipeline ready")
        await asyncio.sleep(0.2)  # let TTS output track attach
        try:
            logger.info("Speaking welcome message...")
            await self.session.say(self._welcome_message)
            logger.info("Welcome message sent ✓")
        except Exception as e:
            logger.error("session.say failed: %s", e)
        _safe_task(self._max_duration_guard(max_seconds=600), "max-duration-guard")

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
        logger.info("Turn: %r", text[:80])

        if text:
            self._user_messages.append(text)

        if _HANGUP_RE.search(text):
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
                            "You analyze sales call transcripts. Reply ONLY with valid JSON, no extra text.\n"
                            'Format: {"outcome": "...", "summary": "..."}\n'
                            "outcome must be exactly one of:\n"
                            "  interested          - customer asked for catalogue/pricing or showed clear interest\n"
                            "  not_interested      - customer declined, showed no interest, or barely spoke\n"
                            "  callback_requested  - customer asked to be called back later\n"
                            "  wrong_number        - wrong person or wrong business\n"
                            "  do_not_call         - customer explicitly said do not call again\n"
                            "summary: 1-2 English sentences describing what happened."
                        ),
                    },
                    {"role": "user", "content": f"Call transcript:\n{transcript_text}"},
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
            await asyncio.wait_for(
                self.session.say(_FAREWELL, allow_interruptions=False),
                timeout=2.5,
            )
        except asyncio.TimeoutError:
            logger.warning("Farewell TTS timed out — disconnecting anyway")
        except Exception as e:
            logger.warning("Farewell TTS failed: %s", e)
        await asyncio.sleep(0.3)
        await self._post_call_report()
        await self._disconnect()


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

    raw_prompt      = meta.get("system_prompt") or AGENT_SYSTEM_PROMPT
    welcome_message = meta.get("welcome_message") or AGENT_WELCOME_MESSAGE
    voice_id        = meta.get("voice_id") or ELEVENLABS_VOICE_ID
    llm_model       = meta.get("llm_model") or GROQ_MODEL
    call_id         = meta.get("call_id", "")

    system_prompt = _build_prompt(raw_prompt)
    logger.info("template | voice=%s llm=%s", voice_id, llm_model)

    llm = _CappedGroqLLM(model=llm_model)
    warmup_task = _safe_task(_warmup_llm(llm), "llm-warmup")

    try:
        participant = await asyncio.wait_for(ctx.wait_for_participant(), timeout=30.0)
        logger.info("Participant joined: %s", getattr(participant, "identity", "unknown"))
    except asyncio.TimeoutError:
        logger.error("No participant joined in 30s — exiting")
        warmup_task.cancel()
        return

    tts = elevenlabs.TTS(
        api_key               = ELEVENLABS_API_KEY,
        voice_id              = voice_id,
        model                 = ELEVENLABS_MODEL_ID,
        encoding              = "pcm_24000",
        chunk_length_schedule = _CHUNK_LENGTH_SCHEDULE,
    )
    logger.info("ElevenLabs TTS ready ✓")

    voice_agent = VoiceAgent(
        ctx.room,
        instructions=system_prompt,
        welcome_message=welcome_message,
        call_id=call_id,
        backend_url=BACKEND_INTERNAL_URL,
        webhook_secret=AGENT_WEBHOOK_SECRET,
    )
    end_call_transform = _end_call_filter_transform(voice_agent._trigger_hangup)

    session = AgentSession(
        stt=deepgram.STT(
            model          = "nova-3",
            language       = "hi",
            interim_results= True,
            endpointing_ms = 50,
            smart_format   = False,
            keyterms       = ["Baba Valve", "butterfly", "ball valve", "globe valve"],
        ),
        llm=llm,
        tts=tts,
        vad=ctx.proc.userdata["vad"],
        turn_handling=TurnHandlingOptions(
            allow_interruptions   = True,
            min_endpointing_delay = 0.0,
            min_interruption_words= 5,
        ),
        tts_text_transforms=["filter_markdown", "filter_emoji", end_call_transform],
    )

    try:
        await session.start(
            agent       = voice_agent,
            room        = ctx.room,
            room_options= RoomOptions(
                close_on_disconnect  = True,
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
            entrypoint_fnc = entrypoint,
            prewarm_fnc    = prewarm,
            agent_name     = "voice-call-agent",
            worker_type    = agents.WorkerType.ROOM,
        )
    )
