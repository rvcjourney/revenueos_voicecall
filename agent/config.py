"""
config.py — Central configuration for the AI Voice Call Agent.
"""

import os
from dotenv import load_dotenv
load_dotenv()

# ── LiveKit ───────────────────────────────────────────────────────────────────
LIVEKIT_URL        = os.getenv("LIVEKIT_URL", "")
LIVEKIT_API_KEY    = os.getenv("LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "")
# Must match the backend's own LIVEKIT_AGENT_NAME (app/config.py) -- set to a distinct
# value (e.g. "voice-call-agent-dev") in a local .env so this process only ever
# receives dispatches meant for it, never ones meant for another worker (e.g. the
# production VPS agent) registered against the same LiveKit Cloud project under the
# default name. Both would otherwise register as "voice-call-agent" and LiveKit would
# round-robin dispatches across them unpredictably.
LIVEKIT_AGENT_NAME = os.getenv("LIVEKIT_AGENT_NAME", "voice-call-agent")

# ── ElevenLabs TTS ────────────────────────────────────────────────────────────
ELEVENLABS_API_KEY  = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "6h2Hja4LgQR8wIIv3XXW")
ELEVENLABS_MODEL_ID = os.getenv("ELEVENLABS_MODEL_ID", "eleven_flash_v2_5")

# ── Cartesia TTS ───────────────────────────────────────────────────────────────
CARTESIA_API_KEY   = os.getenv("CARTESIA_API_KEY", "")
CARTESIA_VOICE_ID  = os.getenv("CARTESIA_VOICE_ID", "910fb75e-1d20-4840-ac63-ac6b26a71bdc")
CARTESIA_MODEL_ID  = os.getenv("CARTESIA_MODEL_ID", "sonic-3")

# ── Chatterbox TTS (self-hosted, e.g. on a RunPod GPU) ──────────────────────────
CHATTERBOX_BASE_URL   = os.getenv("CHATTERBOX_BASE_URL", "")   # e.g. https://xxxxx-8004.proxy.runpod.net
CHATTERBOX_VOICE_ID   = os.getenv("CHATTERBOX_VOICE_ID", "Emily.wav")
CHATTERBOX_LANGUAGE   = os.getenv("CHATTERBOX_LANGUAGE", "hi")
CHATTERBOX_SAMPLE_RATE = int(os.getenv("CHATTERBOX_SAMPLE_RATE", "24000"))
# "predefined" = CHATTERBOX_VOICE_ID is a filename in the server's ./voices (built-in demo voices, all Western accents)
# "clone"      = CHATTERBOX_VOICE_ID is a filename in the server's ./reference_audio (your own uploaded sample)
CHATTERBOX_VOICE_MODE = os.getenv("CHATTERBOX_VOICE_MODE", "predefined")

# ── Sarvam AI TTS (Bulbul v3 — hosted API, native Indian-language voices) ───────
SARVAM_API_KEY      = os.getenv("SARVAM_API_KEY", "")
SARVAM_MODEL        = os.getenv("SARVAM_MODEL", "bulbul:v3")
SARVAM_VOICE_ID     = os.getenv("SARVAM_VOICE_ID", "shubh")  # male default; see agent.py voices list for options
SARVAM_SAMPLE_RATE  = int(os.getenv("SARVAM_SAMPLE_RATE", "24000"))

# ── Sarvam AI STT (Saaras v3 — WebSocket streaming, replaces Deepgram) ──────────
# "codemix" mode is built for exactly the Hindi/English code-switching seen in
# real call transcripts (e.g. "Spice के लिए use करता हूं basically हम") —
# plain "transcribe" mode isn't tuned for that.
SARVAM_STT_MODEL    = os.getenv("SARVAM_STT_MODEL", "saaras:v3")
SARVAM_STT_MODE     = os.getenv("SARVAM_STT_MODE", "codemix")
SARVAM_STT_LANGUAGE = os.getenv("SARVAM_STT_LANGUAGE", "hi-IN")

# ── Groq LLM ──────────────────────────────────────────────────────────────────
GROQ_API_KEY         = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL           = os.getenv("GROQ_MODEL", "qwen/qwen3.6-27b")
GROQ_LLM_TEMPERATURE = float(os.getenv("GROQ_LLM_TEMPERATURE", "0.7"))

# ── Agent behaviour ───────────────────────────────────────────────────────────
# Default fallback — system prompt and welcome message are set via the UI (agent template).
# These defaults are only used if no value is provided by the campaign/agent config.
AGENT_WELCOME_MESSAGE = os.getenv("AGENT_WELCOME_MESSAGE", "Hello! How can I help you today?")
AGENT_SYSTEM_PROMPT   = os.getenv("AGENT_SYSTEM_PROMPT",   "You are a helpful voice assistant.")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ── Observability ─────────────────────────────────────────────────────────────
# "development" renders logs as colored console text; anything else renders JSON.
ENVIRONMENT = os.getenv("ENVIRONMENT", "production")
# Optional — Sentry init is a no-op (see logging_config.init_sentry) when unset.
SENTRY_DSN = os.getenv("SENTRY_DSN", "")
SENTRY_TRACES_SAMPLE_RATE = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1"))

# ── Internal reporting ────────────────────────────────────────────────────────
BACKEND_INTERNAL_URL = os.getenv("BACKEND_INTERNAL_URL", "http://localhost:8000")
AGENT_WEBHOOK_SECRET = os.getenv("AGENT_WEBHOOK_SECRET", "")
# Durable fallback for agent-report POSTs that fail after all retries are exhausted —
# without this, a call's outcome/summary/transcript/extracted_data is lost forever
# the moment the process exits (it only ever existed in memory). See
# replay_failed_reports.py to resend everything logged here.
FAILED_REPORTS_PATH = os.getenv("FAILED_REPORTS_PATH", "failed_reports.jsonl")

# ── Startup validation ────────────────────────────────────────────────────────
_REQUIRED = {
    "LIVEKIT_URL":        LIVEKIT_URL,
    "LIVEKIT_API_KEY":    LIVEKIT_API_KEY,
    "LIVEKIT_API_SECRET": LIVEKIT_API_SECRET,
    "SARVAM_API_KEY":     SARVAM_API_KEY,  # now used for STT on every call, not just Sarvam-TTS agents
    "GROQ_API_KEY":       GROQ_API_KEY,
    "ELEVENLABS_API_KEY": ELEVENLABS_API_KEY,
}

def validate_config() -> None:
    missing = [k for k, v in _REQUIRED.items() if not v]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}\n"
            "Check your .env file."
        )