"""
config.py — Central configuration for the AI Voice Call Agent.
Uses ElevenLabs for TTS (replaces Smallest.ai Lightning).
"""

import os
from dotenv import load_dotenv
load_dotenv()

# ── LiveKit ───────────────────────────────────────────────────────────────────
LIVEKIT_URL        = os.getenv("LIVEKIT_URL", "")
LIVEKIT_API_KEY    = os.getenv("LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "")

# ── Deepgram STT ──────────────────────────────────────────────────────────────
DEEPGRAM_API_KEY   = os.getenv("DEEPGRAM_API_KEY", "")
DEEPGRAM_STT_MODEL = os.getenv("DEEPGRAM_STT_MODEL", "nova-2")

# ── ElevenLabs TTS ────────────────────────────────────────────────────────────
# Get API key from: https://elevenlabs.io → Profile → API Key
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")

# Voice ID — find at: https://elevenlabs.io/voice-library
# Recommended voices for Hinglish/Indian accent:
#   - Suyash       : 9BWtsMINqrJLrRacOk9x  (warm & professional)
#   - Rachel       : 21m00Tcm4TlvDq8ikWAM  (neutral US female)
#   - Priya (custom Indian female voice if you clone one)
# For Indian languages, eleven_turbo_v2_5 handles Hinglish well.
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "C8R8ahkE5XosZ8qPpSPy")

# Model — choose based on latency vs quality tradeoff:
#   eleven_flash_v2_5    : ~75–150ms TTFB, fastest, good quality
#   eleven_turbo_v2_5    : ~200–300ms TTFB, better quality (RECOMMENDED for calls)
#   eleven_multilingual_v2 : ~400ms TTFB, highest quality, best for Hinglish
ELEVENLABS_MODEL_ID = os.getenv("ELEVENLABS_MODEL_ID", "eleven_flash_v2_5")

# ── Groq LLM ──────────────────────────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL   = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# ── SIP / Outbound ────────────────────────────────────────────────────────────
SIP_TRUNK_ID     = os.getenv("SIP_TRUNK_ID", "")
SIP_TRUNK_NUMBER = os.getenv("SIP_TRUNK_NUMBER", "")
OUTBOUND_SIP_URI = os.getenv("OUTBOUND_SIP_URI", "")

# ── Agent behaviour ───────────────────────────────────────────────────────────
# Default fallback — system prompt and welcome message are set via the UI (agent template).
# These defaults are only used if no value is provided by the campaign/agent config.
AGENT_WELCOME_MESSAGE = os.getenv("AGENT_WELCOME_MESSAGE", "Hello! How can I help you today?")
AGENT_SYSTEM_PROMPT   = os.getenv("AGENT_SYSTEM_PROMPT",   "You are a helpful voice assistant.")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ── Internal reporting ────────────────────────────────────────────────────────
BACKEND_INTERNAL_URL = os.getenv("BACKEND_INTERNAL_URL", "http://localhost:8000")
AGENT_WEBHOOK_SECRET = os.getenv("AGENT_WEBHOOK_SECRET", "")

# ── Startup validation ────────────────────────────────────────────────────────
_REQUIRED = {
    "LIVEKIT_URL":        LIVEKIT_URL,
    "LIVEKIT_API_KEY":    LIVEKIT_API_KEY,
    "LIVEKIT_API_SECRET": LIVEKIT_API_SECRET,
    "DEEPGRAM_API_KEY":   DEEPGRAM_API_KEY,
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