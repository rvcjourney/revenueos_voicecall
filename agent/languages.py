"""
languages.py — the one place that knows which languages the agent can speak.

Each entry maps a platform language (AgentLanguage in the backend, the
"language" field on an agent template) to the codes its providers need:

  sarvam_tts — Bulbul target_language_code; Bulbul is native to Indian
               languages, so every regional language speaks through Sarvam
               even when the agent's configured voice provider is ElevenLabs
               (whose Indian-language voices are Hindi/Indian-English only).
  sarvam_stt — Saaras streaming language code for speech recognition.

Hindi, Hinglish and English keep whatever voice provider the agent is
configured with — those voices are already tuned for this platform's calls.

Used by agent.py (TTS/STT setup and mid-call language switching). The
backend keeps its own copy of the list in app/models/agent.py's
AgentLanguage enum; the two must stay in sync.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Language:
    key: str          # platform name, e.g. "tamil"
    display: str      # how we say it in a prompt, e.g. "Tamil"
    sarvam_tts: str   # Bulbul target_language_code
    sarvam_stt: str   # Saaras streaming language code
    native_script: bool = True   # False = spoken/written in Roman script (Hinglish, English)
    # Respectful address term the agent appends to the customer's name / uses
    # standalone ("Ravi ji", "haan ji"). "ji" is a Hindi-origin word, naturally
    # used across most Indo-Aryan languages (Hindi, Marathi, Punjabi) but NOT a
    # real part of Dravidian languages (Tamil, Telugu, Kannada) or Bengali — on
    # those calls it was the one Hindi word leaking into every reply (reported
    # as "speaking Hindi + Gujarati" / "Hindi + Telugu"). "" = no honorific
    # particle; the agent uses the customer's name on its own instead.
    honorific: str = "ji"


LANGUAGES: dict[str, Language] = {
    "hinglish": Language("hinglish", "Hinglish (Hindi-English mix)", "hi-IN", "hi-IN", native_script=False, honorific="ji"),
    "hindi":    Language("hindi", "Hindi", "hi-IN", "hi-IN", honorific="ji"),
    "english":  Language("english", "English", "en-IN", "en-IN", native_script=False, honorific=""),
    "marathi":  Language("marathi", "Marathi", "mr-IN", "mr-IN", honorific="ji"),
    "tamil":    Language("tamil", "Tamil", "ta-IN", "ta-IN", honorific=""),
    "telugu":   Language("telugu", "Telugu", "te-IN", "te-IN", honorific=""),
    "bengali":  Language("bengali", "Bengali", "bn-IN", "bn-IN", honorific=""),
    "gujarati": Language("gujarati", "Gujarati", "gu-IN", "gu-IN", honorific=""),
    "kannada":  Language("kannada", "Kannada", "kn-IN", "kn-IN", honorific=""),
    "punjabi":  Language("punjabi", "Punjabi", "pa-IN", "pa-IN", honorific="ji"),
}

DEFAULT_LANGUAGE = "hinglish"

# These keep the agent's own configured voice (ElevenLabs by default); every
# other language is spoken by Sarvam Bulbul regardless of provider.
ELEVENLABS_CAPABLE = frozenset({"hinglish", "hindi", "english"})

# What the customer might call a language, mapped to our key — used to resolve
# the [lang:...] marker the LLM emits when asked to switch mid-call.
ALIASES: dict[str, str] = {
    "hinglish": "hinglish", "hindi": "hindi", "हिंदी": "hindi", "hindustani": "hindi",
    "english": "english", "angrezi": "english", "अंग्रेज़ी": "english",
    "marathi": "marathi", "मराठी": "marathi",
    "tamil": "tamil", "தமிழ்": "tamil",
    "telugu": "telugu", "తెలుగు": "telugu",
    "bengali": "bengali", "bangla": "bengali", "বাংলা": "bengali",
    "gujarati": "gujarati", "ગુજરાતી": "gujarati",
    "kannada": "kannada", "ಕನ್ನಡ": "kannada",
    "punjabi": "punjabi", "panjabi": "punjabi", "ਪੰਜਾਬੀ": "punjabi",
}


def get(language: str | None) -> Language:
    """Resolve a platform language name, falling back to Hinglish."""
    return LANGUAGES.get((language or "").strip().lower(), LANGUAGES[DEFAULT_LANGUAGE])


def resolve(spoken_name: str | None) -> Language | None:
    """Resolve what the customer asked for ("tamil", "bangla") — None if we can't speak it."""
    name = (spoken_name or "").strip().lower().strip(".!?,:;\"'")
    key = ALIASES.get(name)
    if key is None and name:
        key = next((k for alias, k in ALIASES.items() if alias in name), None)
    return LANGUAGES.get(key) if key else None


def uses_sarvam_voice(language: str) -> bool:
    """True when this language must be spoken by Sarvam, whatever the agent's provider."""
    return get(language).key not in ELEVENLABS_CAPABLE


def spoken_list() -> str:
    """Human-readable list for the system prompt."""
    return ", ".join(lang.display for lang in LANGUAGES.values())
