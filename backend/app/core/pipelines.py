"""
app/core/pipelines.py — the calling engine: every call runs on Sarvam (realtime
STT, sarvam-105b-conversations, Bulbul TTS). This module holds the language
registry, the owner's per-language overrides, voice validation, and the per-call
config the agent receives in its job metadata (it never reads this module).

Customer-facing text never names a vendor or model.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from app.config import settings as app_settings

SARVAM = "sarvam"  # Call.pipeline value for every call; older rows may say "standard"

V4_FLASH = "bulbul:v4-flash"
V3 = "bulbul:v3"
SARVAM_TTS_MODELS = (V4_FLASH, V3)
# Must match agent/config.py SARVAM_PIPELINE_LLM_MODEL (separate deployables).
SARVAM_LLM_MODEL = "sarvam-105b-conversations"
# The live engine uses realtime STT (WebSocket only); the daily probe checks the
# REST model behind the same service as a cheap availability signal.
SARVAM_STT_PROBE_MODEL = "saaras:v3"

# bulbul:v3 speakers (simple names, every language) — same set the standard
# pipeline already uses for regional calls (agent/config.py SARVAM_VOICE_ID etc.).
V3_VOICES: tuple[tuple[str, str], ...] = (
    ("shubh", "male"), ("ritu", "female"), ("rahul", "male"), ("pooja", "female"),
    ("simran", "female"), ("kavya", "female"), ("amit", "male"), ("ratan", "male"),
    ("rohan", "male"), ("dev", "male"), ("ishita", "female"), ("shreya", "female"),
    ("manan", "male"), ("sumit", "male"), ("priya", "female"), ("aditya", "male"),
    ("kabir", "male"), ("neha", "female"), ("varun", "male"), ("roopa", "female"),
)


@dataclass(frozen=True)
class Voice:
    id: str
    name: str
    gender: str  # "male" | "female"


@dataclass(frozen=True)
class Language:
    key: str
    display: str
    native: str
    stt_code: str          # Saaras realtime STT
    tts_code: str          # Bulbul target_language_code
    clone_code: str        # Sarvam cloned-voice target_language_code
    enabled: bool
    sarvam_tts_model: str  # default; owner can override per language
    v4_voices: tuple[Voice, ...] = field(default_factory=tuple)
    clone_supported: bool = True


def _v(*items: tuple[str, str, str]) -> tuple[Voice, ...]:
    return tuple(Voice(i, n, g) for i, n, g in items)


_ON, _OFF = True, False

# v4-flash persona IDs verified live against Sarvam's API on 2026-10-21.
# Default model rule (section 9 #10): v4-flash only where >= 3 acceptable
# (conversational/customer/narration, not ads/suspense) voices exist; else v3.
# A starting point — decided finally by ear-check, overridable in /ops.
LANGUAGES: dict[str, Language] = {
    "hinglish": Language("hinglish", "Hinglish (Hindi-English mix)", "Hinglish", "hi-IN", "hi-IN", "hi-IN", _ON, V4_FLASH, _v(
        ("simran_enhi_customer", "Simran", "female"), ("ishita_enhi_customer", "Ishita", "female"),
        ("shalini_enhi_customer", "Shalini", "female"), ("sunny_enhi_customer", "Sunny", "male"),
        ("shubh_enhi_companion", "Shubh", "male"))),
    "hindi": Language("hindi", "Hindi", "हिंदी", "hi-IN", "hi-IN", "hi-IN", _ON, V4_FLASH, _v(
        ("ritu_hi_conversation", "Ritu", "female"), ("rahul_hi_conversational", "Rahul", "male"),
        ("kavya_hi_conversational", "Kavya", "female"), ("aditya_hi_conversational", "Aditya", "male"),
        ("simran_hi_conversation", "Simran", "female"), ("amit_hi_conversational", "Amit", "male"))),
    "english": Language("english", "English (Indian)", "English", "en-IN", "en-IN", "en-IN", _ON, V4_FLASH, _v(
        ("simran_en_conversation", "Simran", "female"), ("dev_en_conversational", "Dev", "male"),
        ("neha_en_customer", "Neha", "female"), ("deven_en_conversation", "Deven", "male"))),
    "marathi": Language("marathi", "Marathi", "मराठी", "mr-IN", "mr-IN", "mr-IN", _ON, V4_FLASH, _v(
        ("ishita_mr_conversational", "Ishita", "female"), ("nilesh_mr_conversation", "Nilesh", "male"),
        ("neha_mr_narration", "Neha", "female"), ("soham_mr_narration", "Soham", "male"))),
    "tamil": Language("tamil", "Tamil", "தமிழ்", "ta-IN", "ta-IN", "ta-IN", _ON, V3, _v(
        ("vijay_ta_narration", "Vijay", "male"), ("gokul_ta_narration", "Gokul", "male"))),
    "telugu": Language("telugu", "Telugu", "తెలుగు", "te-IN", "te-IN", "te-IN", _ON, V4_FLASH, _v(
        ("kavitha_te_conversation", "Kavitha", "female"), ("pooja_te_conversation", "Pooja", "female"),
        ("tarun_te_narration", "Tarun", "male"))),
    "bengali": Language("bengali", "Bengali", "বাংলা", "bn-IN", "bn-IN", "bn-IN", _ON, V3, _v(
        ("arnab_bn_conversation", "Arnab", "male"), ("roopa_bn_conversational", "Roopa", "female"))),
    "gujarati": Language("gujarati", "Gujarati", "ગુજરાતી", "gu-IN", "gu-IN", "gu-IN", _ON, V3, _v(
        ("bhavik_gu_conversation", "Bhavik", "male"), ("pooja_gu_conversational", "Pooja", "female"))),
    "kannada": Language("kannada", "Kannada", "ಕನ್ನಡ", "kn-IN", "kn-IN", "kn-IN", _ON, V4_FLASH, _v(
        ("chaitra_kn_conversation", "Chaitra", "female"), ("chetan_kn_conversation", "Chetan", "male"),
        ("suchitra_kn_narration", "Suchitra", "female"))),
    "punjabi": Language("punjabi", "Punjabi", "ਪੰਜਾਬੀ", "pa-IN", "pa-IN", "pa-IN", _ON, V4_FLASH, _v(
        ("anand_pa_conversation", "Anand", "male"), ("harpreet_pa_narration", "Harpreet", "female"),
        ("jaspal_pa_banking", "Jaspal", "male"))),
    # Registered, disabled until ear-checked (section 4A rule 7). v4-flash has no
    # personas for these yet, so stock voices are bulbul:v3; cloning supports both.
    # Odia's codes really differ per component (checked live 2026-10-22): realtime
    # STT accepts only "or-IN" (rejects "od-IN"); Bulbul TTS and cloning use "od-IN".
    "malayalam": Language("malayalam", "Malayalam", "മലയാളം", "ml-IN", "ml-IN", "ml-IN", _OFF, V3),
    "odia": Language("odia", "Odia", "ଓଡ଼ିଆ", "or-IN", "od-IN", "od-IN", _OFF, V3),
}

DEFAULT_LANGUAGE = "hinglish"

# Regional languages are voiced by ElevenLabs once the owner has added voices for them
# (platform "Languages & voices"); Sarvam keeps STT and the LLM for every call.
ELEVENLABS = "elevenlabs"
SARVAM_VOICE_ONLY = ("hinglish", "hindi", "english")

# Fixed lines the sarvam engine speaks itself (agent/sarvam_pipeline.py):
# (empty-reply "please repeat", mid-call failure apology). Native script,
# English words in Latin — needs a native-speaker check before customer rollout.
# shortcut: malayalam/odia use English until they are enabled and ear-checked.
_HI = ("माफ़ कीजिए, आवाज़ साफ़ नहीं आई, क्या आप दोबारा बोल सकते हैं?",
       "माफ़ कीजिए, हमारी तरफ़ से थोड़ी technical दिक्कत आ गई है। आपके समय के लिए धन्यवाद।")
_EN = ("Sorry, I didn't catch that. Could you say it again?",
       "Sorry, we've hit a technical problem on our side. Thank you for your time.")
SPOKEN_LINES: dict[str, tuple[str, str]] = {
    "hinglish": _HI,
    "hindi": _HI,
    "english": _EN,
    "marathi": ("माफ करा, नीट ऐकू आलं नाही, पुन्हा सांगाल का?",
                "माफ करा, आमच्याकडे थोडी technical अडचण आली आहे. तुमच्या वेळेबद्दल धन्यवाद."),
    "tamil": ("மன்னிக்கவும், சரியாகக் கேட்கவில்லை, மீண்டும் சொல்ல முடியுமா?",
              "மன்னிக்கவும், எங்கள் பக்கம் ஒரு technical சிக்கல் ஏற்பட்டுள்ளது. உங்கள் நேரத்திற்கு நன்றி."),
    "telugu": ("క్షమించండి, సరిగా వినిపించలేదు, మళ్ళీ చెప్పగలరా?",
               "క్షమించండి, మా వైపు technical సమస్య వచ్చింది. మీ సమయానికి ధన్యవాదాలు."),
    "bengali": ("দুঃখিত, ঠিক শুনতে পাইনি, আবার বলবেন?",
                "দুঃখিত, আমাদের দিকে একটু technical সমস্যা হয়েছে। আপনার সময়ের জন্য ধন্যবাদ।"),
    "gujarati": ("માફ કરશો, બરાબર સંભળાયું નહીં, ફરીથી કહેશો?",
                 "માફ કરશો, અમારી બાજુ થોડી technical તકલીફ આવી છે. તમારા સમય માટે આભાર."),
    "kannada": ("ಕ್ಷಮಿಸಿ, ಸರಿಯಾಗಿ ಕೇಳಿಸಲಿಲ್ಲ, ಮತ್ತೊಮ್ಮೆ ಹೇಳುತ್ತೀರಾ?",
                "ಕ್ಷಮಿಸಿ, ನಮ್ಮ ಕಡೆ technical ತೊಂದರೆ ಆಗಿದೆ. ನಿಮ್ಮ ಸಮಯಕ್ಕೆ ಧನ್ಯವಾದಗಳು."),
    "punjabi": ("ਮਾਫ਼ ਕਰਨਾ, ਠੀਕ ਤਰ੍ਹਾਂ ਸੁਣਿਆ ਨਹੀਂ, ਦੁਬਾਰਾ ਦੱਸ ਸਕਦੇ ਹੋ?",
                "ਮਾਫ਼ ਕਰਨਾ, ਸਾਡੇ ਵੱਲੋਂ ਕੁਝ technical ਦਿੱਕਤ ਆ ਗਈ ਹੈ। ਤੁਹਾਡੇ ਸਮੇਂ ਲਈ ਧੰਨਵਾਦ।"),
    "malayalam": _EN,
    "odia": _EN,
}

# Spoken before the greeting on every call: Vobiz records every call
# (core/vobiz.py), and the person called must be told. Same ear-check caveat.
_EN_NOTICE = "This call is being recorded for quality purposes."
RECORDING_NOTICE: dict[str, str] = {
    "hinglish": "यह कॉल quality के लिए record की जा रही है।",
    "hindi": "यह कॉल गुणवत्ता के लिए रिकॉर्ड की जा रही है।",
    "english": _EN_NOTICE,
    "marathi": "हा कॉल गुणवत्तेसाठी रेकॉर्ड केला जात आहे.",
    "tamil": "இந்த அழைப்பு தரத்திற்காக பதிவு செய்யப்படுகிறது.",
    "telugu": "ఈ కాల్ నాణ్యత కోసం రికార్డ్ చేయబడుతోంది.",
    "bengali": "এই কলটি মান উন্নয়নের জন্য রেকর্ড করা হচ্ছে।",
    "gujarati": "આ કૉલ ગુણવત્તા માટે રેકોર્ડ કરવામાં આવી રહ્યો છે.",
    "kannada": "ಈ ಕರೆಯನ್ನು ಗುಣಮಟ್ಟಕ್ಕಾಗಿ ರೆಕಾರ್ಡ್ ಮಾಡಲಾಗುತ್ತಿದೆ.",
    "punjabi": "ਇਹ ਕਾਲ ਗੁਣਵੱਤਾ ਲਈ ਰਿਕਾਰਡ ਕੀਤੀ ਜਾ ਰਹੀ ਹੈ।",
    "malayalam": _EN_NOTICE,
    "odia": _EN_NOTICE,
}


# ── Owner settings (platform_cost_settings row), cached ≤ 60 s ────────────────
@dataclass(frozen=True)
class OwnerSettings:
    # {language: {"sarvam": {"enabled"?, "tts_model"?, "voices"?}}} — the "sarvam"
    # level is kept so overrides saved before the single-engine change still apply.
    language_overrides: dict = field(default_factory=dict)


_CACHE_TTL = 60.0
_cache: tuple[float, OwnerSettings] | None = None


async def get_owner_settings(db) -> OwnerSettings:
    global _cache
    now = time.monotonic()
    if _cache and _cache[0] > now:
        return _cache[1]
    from app.models.platform_cost_settings import PlatformCostSettings
    row = await db.get(PlatformCostSettings, 1)
    value = OwnerSettings(language_overrides=dict(row.language_overrides or {}) if row else {})
    _cache = (now + _CACHE_TTL, value)
    return value


def invalidate_owner_settings() -> None:
    global _cache
    _cache = None


# ── Registry lookups with owner overrides layered on ──────────────────────────
def _override(settings: OwnerSettings, language: str) -> dict:
    return (settings.language_overrides.get(language) or {}).get(SARVAM) or {}


def language_enabled(language: str, settings: OwnerSettings) -> bool:
    lang = LANGUAGES.get(language)
    if lang is None:
        return False
    ov = _override(settings, language)
    return bool(ov["enabled"]) if "enabled" in ov else lang.enabled


def sarvam_tts_model(language: str, settings: OwnerSettings) -> str:
    model = _override(settings, language).get("tts_model")
    return model if model in SARVAM_TTS_MODELS else LANGUAGES[language].sarvam_tts_model


def sarvam_voices(language: str, settings: OwnerSettings) -> tuple[Voice, ...]:
    """Stock voices valid for this language and its TTS model."""
    lang = LANGUAGES[language]
    if sarvam_tts_model(language, settings) == V3:
        voices = tuple(Voice(i, i.capitalize(), g) for i, g in V3_VOICES)
    else:
        voices = lang.v4_voices
    shortlist = _override(settings, language).get("voices")
    if shortlist:
        voices = tuple(v for v in voices if v.id in set(shortlist)) or voices
    return voices


def _el_override(settings: OwnerSettings, language: str) -> dict:
    return (settings.language_overrides.get(language) or {}).get(ELEVENLABS) or {}


def elevenlabs_voices(language: str, settings: OwnerSettings) -> tuple[Voice, ...]:
    """The owner's ElevenLabs shortlist for a regional language ((), for Hindi/Hinglish/English)."""
    if not app_settings.ELEVENLABS_REGIONAL_ENABLED or language in SARVAM_VOICE_ONLY or language not in LANGUAGES:
        return ()
    return tuple(Voice(str(v["id"]), str(v.get("name") or v["id"]), str(v.get("gender") or "female"))
                 for v in _el_override(settings, language).get("voices") or [] if v.get("id"))


def tts_engine(language: str, settings: OwnerSettings) -> str:
    return ELEVENLABS if elevenlabs_voices(language, settings) else SARVAM


def voices_for(language: str, settings: OwnerSettings) -> tuple[Voice, ...]:
    """Voices a customer can pick for this language: ElevenLabs when it speaks it, else Sarvam stock."""
    return elevenlabs_voices(language, settings) or sarvam_voices(language, settings)


def all_sarvam_stock_voice_ids() -> set[str]:
    return {i for i, _ in V3_VOICES} | {v.id for lang in LANGUAGES.values() for v in lang.v4_voices}


def default_sarvam_voice(language: str, settings: OwnerSettings, gender: str | None = None) -> str:
    """Default for the language's *Sarvam* voice (also the fallback behind an ElevenLabs voice)."""
    voices = sarvam_voices(language, settings)
    for v in voices:
        if gender is None or v.gender == gender:
            return v.id
    return voices[0].id


def default_voice(language: str, settings: OwnerSettings, gender: str | None = None) -> str:
    voices = voices_for(language, settings)
    for v in voices:
        if gender is None or v.gender == gender:
            return v.id
    return voices[0].id


# ── Validation ────────────────────────────────────────────────────────────────
class PipelineValidationError(ValueError):
    """Message is customer-safe: never names a vendor or model."""


def validate(language: str, voice_id: str | None, settings: OwnerSettings, *, cloned: bool = False) -> None:
    """Reject a language/voice combination that would fail on a live call.
    cloned: voice_id is one of the org's (ready) cloned voices."""
    if language not in LANGUAGES or not language_enabled(language, settings):
        raise PipelineValidationError("This language isn't available.")
    if cloned:
        if not LANGUAGES[language].clone_supported:
            raise PipelineValidationError("Cloned voices aren't available in this language yet.")
        return
    if voice_id and voice_id not in {v.id for v in voices_for(language, settings)}:
        raise PipelineValidationError("This voice isn't available in this language.")


# ── What the agent needs for a call (goes into job metadata) ──────────────────
def sarvam_call_config(language: str, voice_id: str | None, settings: OwnerSettings, *, cloned: bool) -> dict:
    """Everything the agent needs, including every enabled language's
    codes/model/default voices so a mid-call switch needs no lookup."""
    langs = {}
    for key, lang in LANGUAGES.items():
        if not language_enabled(key, settings):
            continue
        voices = voices_for(key, settings)
        langs[key] = {
            "display": lang.display,
            "stt": lang.stt_code,
            "tts": lang.tts_code,
            "clone": lang.clone_code,
            "tts_model": sarvam_tts_model(key, settings),
            # "elevenlabs": the agent speaks this language with an ElevenLabs voice from
            # "voices"; the Sarvam voice named here is its fallback.
            "engine": tts_engine(key, settings),
            "eleven_model": app_settings.ELEVENLABS_TTS_MODEL,
            "eleven_code": lang.tts_code.split("-")[0],
            "sarvam_voice": default_sarvam_voice(key, settings),
            "voices": [{"id": v.id, "gender": v.gender} for v in voices],
            "repeat_line": SPOKEN_LINES[key][0],
            "failure_line": SPOKEN_LINES[key][1],
            "recording_notice": RECORDING_NOTICE[key],
        }
    return {
        "language": language,
        "voice_id": voice_id or default_voice(language, settings),
        "cloned": cloned,
        "languages": langs,
    }


async def call_meta(db, *, org_id, language: str, voice_id: str | None) -> dict:
    """{"sarvam": ...} for one call's job metadata. A voice that isn't valid for
    this language (e.g. one saved before the Sarvam-only change) falls back to
    the language's default voice rather than failing the call."""
    from sqlalchemy import select
    from app.models.cloned_voice import ClonedVoice

    settings = await get_owner_settings(db)
    if not language_enabled(language, settings):
        language = DEFAULT_LANGUAGE
    cloned = None
    if voice_id:
        cloned = await db.scalar(select(ClonedVoice).where(
            ClonedVoice.elevenlabs_voice_id == voice_id,
            ClonedVoice.org_id == org_id,
            ClonedVoice.provider == SARVAM,
            ClonedVoice.deleted_at.is_(None),
        ))
    is_clone = cloned is not None and str(cloned.status) == "ready" and LANGUAGES[language].clone_supported
    stock_ok = voice_id in {v.id for v in voices_for(language, settings)}
    return {"sarvam": sarvam_call_config(language, voice_id if (is_clone or stock_ok) else None, settings, cloned=is_clone)}


def languages_for(settings: OwnerSettings) -> list[dict]:
    """Customer-safe language list for the app (GET /api/languages)."""
    return [
        {
            "value": key, "label": lang.display, "native": lang.native, "cloned_voices": lang.clone_supported,
            "voices": [{"id": v.id, "name": v.name, "gender": v.gender} for v in voices_for(key, settings)],
        }
        for key, lang in LANGUAGES.items()
        if language_enabled(key, settings)
    ]
