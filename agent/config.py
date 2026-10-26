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

# ── Sarvam (STT, LLM, TTS — the only AI provider) ──────────────────────────────
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "")
SARVAM_PIPELINE_LLM_MODEL      = os.getenv("SARVAM_PIPELINE_LLM_MODEL", "sarvam-105b-conversations")
SARVAM_PIPELINE_LLM_MAX_TOKENS = int(os.getenv("SARVAM_PIPELINE_LLM_MAX_TOKENS", "200"))
# 16 kHz linear16 to start; Sarvam's telephony example uses 8000 + "mulaw" — benchmark on a real call.
SARVAM_PIPELINE_TTS_SAMPLE_RATE = int(os.getenv("SARVAM_PIPELINE_TTS_SAMPLE_RATE", "16000"))
SARVAM_PIPELINE_TTS_CODEC       = os.getenv("SARVAM_PIPELINE_TTS_CODEC", "linear16")
# Post-call outcome classification/summary (agent.py _classify), off the live
# conversation path. sarvam-105b with low reasoning answers in ~2-3 s.
SARVAM_CLASSIFY_MODEL = os.getenv("SARVAM_CLASSIFY_MODEL", "sarvam-105b")
SARVAM_CHAT_URL       = os.getenv("SARVAM_CHAT_URL", "https://api.sarvam.ai/v2/chat/completions")
# Tried first: the conversation model with reasoning off answers in ~0.5 s. sarvam-105b can't turn
# reasoning off and spent 1500 tokens thinking before any JSON (2026-10-26), so it is the slow fallback.
SARVAM_CLASSIFY_FAST_MODEL = os.getenv("SARVAM_CLASSIFY_FAST_MODEL", "sarvam-105b-conversations")
SARVAM_CHAT_FAST_URL       = os.getenv("SARVAM_CHAT_FAST_URL", "https://api.sarvam.ai/v1/chat/completions")

# ── ElevenLabs (TTS only, regional languages; STT and the LLM stay on Sarvam) ──
# Unset -> those languages fall back to Sarvam voices.
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")

# ── Agent behaviour ───────────────────────────────────────────────────────────
# Fallback only — the real instructions come from the agent template in each call's metadata.
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
    "SARVAM_API_KEY":     SARVAM_API_KEY,
}

def validate_config() -> None:
    missing = [k for k, v in _REQUIRED.items() if not v]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}\n"
            "Check your .env file."
        )