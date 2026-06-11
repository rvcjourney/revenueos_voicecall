"""
agent.py — Hinglish Voice Sales Agent
Pipeline: Deepgram STT → Groq LLM → ElevenLabs TTS (via livekit-plugins-elevenlabs)
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
from livekit.agents.llm import ChatContext
from livekit.agents.voice.room_io import RoomOptions
from livekit.plugins import deepgram, groq, silero, elevenlabs, cartesia

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
_FAREWELL = "Bahut shukriya sir, aapka time dene ke liye! Take care, Bye"

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
            "Then stop immediately and wait for the customer to respond.\n\n"
        )

    guardrails = (
        "[ABSOLUTE RULES — never break these]\n"
        "1. Speak like a real Indian salesperson on a phone call — warm, natural, confident. "
        "Replies should feel human and conversational. Usually 1-2 sentences, occasionally 3 if needed. "
        "Never lecture. Never sound robotic or scripted.\n"
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
        "(e.g. 'Bahut shukriya sir, koi zaroorat ho toh zaroor call karein, take care!'), "
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
        "'Ek kaam karo sir, aapka WhatsApp number de do — main catalogue bhej deta hoon.' "
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
        min_silence_duration   = 0.35,
        activation_threshold   = 0.85,
        deactivation_threshold = 0.40,
        sample_rate            = 8000,
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
        # Goodbye text is ~10-15 words. TTS needs ~300ms to generate + ~5s to play.
        # Wait 8s so the customer always hears the complete farewell before the line drops.
        await asyncio.sleep(8.0)
        await self._post_call_report()
        await self._disconnect()

    async def on_enter(self) -> None:
        logger.info("Agent entered room — pipeline ready")
        await asyncio.sleep(0.1)  # let TTS output track attach
        if self._ending:
            return  # participant left before on_enter ran (rejected call)
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
        self._turn_count += 1
        logger.info("Turn %d: %r", self._turn_count, text[:80])

        if text:
            self._user_messages.append(text)

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
            await asyncio.wait_for(
                self.session.say(_FAREWELL, allow_interruptions=False),
                timeout=5.0,
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
    voice_provider  = (meta.get("voice_provider") or "elevenlabs").lower()
    voice_id        = meta.get("voice_id") or (CARTESIA_VOICE_ID if voice_provider == "cartesia" else ELEVENLABS_VOICE_ID)
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
            speed       = 0.85,        # default is 1.0 — 0.85 is natural phone-call pace
            encoding    = "pcm_s16le",
            sample_rate = 24000,
        )
        logger.info("Cartesia TTS ready ✓ (model=%s voice=%s lang=%s speed=0.85)", CARTESIA_MODEL_ID, voice_id, cartesia_language)
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
            model          = "nova-2",
            language       = "hi",   # Hindi model handles English words naturally (Hinglish)
            interim_results= True,
            endpointing_ms = 150,    # 150ms — fast finalization, safe against single-word false triggers
            smart_format   = False,
        ),
        llm=llm,
        tts=tts,
        vad=ctx.proc.userdata["vad"],
        turn_handling=TurnHandlingOptions(
            allow_interruptions   = True,
            min_endpointing_delay = 0.15,  # 150ms after STT finalises — fast but stable
            min_interruption_words= 12,    # customer must say ~12 words to interrupt agent — prevents "haan/achha" breaking sentences
        ),
        tts_text_transforms=["filter_markdown", "filter_emoji", end_call_transform],
    )

    @ctx.room.on("participant_disconnected")
    def _on_participant_left(participant):
        # Customer hung up — ensure post-call report is always sent
        if not voice_agent._reported:
            logger.info("Participant disconnected — triggering post-call report")
            _safe_task(voice_agent._post_call_report(), "post-call-on-disconnect")

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
