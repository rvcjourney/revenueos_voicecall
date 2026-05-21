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

# ── Deepgram STT ──────────────────────────────────────────────────────────────
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")

# ── ElevenLabs TTS ────────────────────────────────────────────────────────────
ELEVENLABS_API_KEY  = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "C8R8ahkE5XosZ8qPpSPy")
ELEVENLABS_MODEL_ID = os.getenv("ELEVENLABS_MODEL_ID", "eleven_flash_v2_5")

# ── Groq LLM ──────────────────────────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL   = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

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