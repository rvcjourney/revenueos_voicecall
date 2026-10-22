"""
app/core/pipelines.py — the two calling engines ("standard", "sarvam"),
the language registry they share, pipeline resolution, and the validation
matrix that every save/dial/test path runs through.

This is the ONE place that knows which language, TTS model and voice is valid
on which pipeline. The app reads it via GET /api/languages; the agent receives
the slice it needs in each call's job metadata (it never reads this module).
Customer-facing text never names a vendor or model — labels are "Standard" /
"Indic Native" (PIPELINE_LABELS).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

STANDARD = "standard"
SARVAM = "sarvam"
PIPELINES = (STANDARD, SARVAM)
PIPELINE_LABELS = {STANDARD: "Standard", SARVAM: "Indic Native"}

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
    stt_code: str          # Saaras (both pipelines)
    tts_code: str          # Bulbul target_language_code
    clone_code: str        # Sarvam cloned-voice target_language_code
    enabled: dict[str, bool]
    sarvam_tts_model: str  # default; owner can override per language
    v4_voices: tuple[Voice, ...] = field(default_factory=tuple)
    clone_supported: bool = True
    honorific: str = "ji"  # "" = avoid "ji" (Dravidian languages, Bengali, Gujarati)


def _v(*items: tuple[str, str, str]) -> tuple[Voice, ...]:
    return tuple(Voice(i, n, g) for i, n, g in items)


_BOTH = {STANDARD: True, SARVAM: True}
_NONE = {STANDARD: False, SARVAM: False}

# v4-flash persona IDs verified live against Sarvam's API on 2026-10-21.
# Default model rule (section 9 #10): v4-flash only where >= 3 acceptable
# (conversational/customer/narration, not ads/suspense) voices exist; else v3.
# A starting point — decided finally by ear-check, overridable in /ops.
LANGUAGES: dict[str, Language] = {
    "hinglish": Language("hinglish", "Hinglish (Hindi-English mix)", "Hinglish", "hi-IN", "hi-IN", "hi-IN", _BOTH, V4_FLASH, _v(
        ("simran_enhi_customer", "Simran", "female"), ("ishita_enhi_customer", "Ishita", "female"),
        ("shalini_enhi_customer", "Shalini", "female"), ("sunny_enhi_customer", "Sunny", "male"),
        ("shubh_enhi_companion", "Shubh", "male"))),
    "hindi": Language("hindi", "Hindi", "हिंदी", "hi-IN", "hi-IN", "hi-IN", _BOTH, V4_FLASH, _v(
        ("ritu_hi_conversation", "Ritu", "female"), ("rahul_hi_conversational", "Rahul", "male"),
        ("kavya_hi_conversational", "Kavya", "female"), ("aditya_hi_conversational", "Aditya", "male"),
        ("simran_hi_conversation", "Simran", "female"), ("amit_hi_conversational", "Amit", "male"))),
    "english": Language("english", "English (Indian)", "English", "en-IN", "en-IN", "en-IN", _BOTH, V4_FLASH, _v(
        ("simran_en_conversation", "Simran", "female"), ("dev_en_conversational", "Dev", "male"),
        ("neha_en_customer", "Neha", "female"), ("deven_en_conversation", "Deven", "male")), honorific=""),
    "marathi": Language("marathi", "Marathi", "मराठी", "mr-IN", "mr-IN", "mr-IN", _BOTH, V4_FLASH, _v(
        ("ishita_mr_conversational", "Ishita", "female"), ("nilesh_mr_conversation", "Nilesh", "male"),
        ("neha_mr_narration", "Neha", "female"), ("soham_mr_narration", "Soham", "male"))),
    "tamil": Language("tamil", "Tamil", "தமிழ்", "ta-IN", "ta-IN", "ta-IN", _BOTH, V3, _v(
        ("vijay_ta_narration", "Vijay", "male"), ("gokul_ta_narration", "Gokul", "male")), honorific=""),
    "telugu": Language("telugu", "Telugu", "తెలుగు", "te-IN", "te-IN", "te-IN", _BOTH, V4_FLASH, _v(
        ("kavitha_te_conversation", "Kavitha", "female"), ("pooja_te_conversation", "Pooja", "female"),
        ("tarun_te_narration", "Tarun", "male")), honorific=""),
    "bengali": Language("bengali", "Bengali", "বাংলা", "bn-IN", "bn-IN", "bn-IN", _BOTH, V3, _v(
        ("arnab_bn_conversation", "Arnab", "male"), ("roopa_bn_conversational", "Roopa", "female")), honorific=""),
    "gujarati": Language("gujarati", "Gujarati", "ગુજરાતી", "gu-IN", "gu-IN", "gu-IN", _BOTH, V3, _v(
        ("bhavik_gu_conversation", "Bhavik", "male"), ("pooja_gu_conversational", "Pooja", "female")), honorific=""),
    "kannada": Language("kannada", "Kannada", "ಕನ್ನಡ", "kn-IN", "kn-IN", "kn-IN", _BOTH, V4_FLASH, _v(
        ("chaitra_kn_conversation", "Chaitra", "female"), ("chetan_kn_conversation", "Chetan", "male"),
        ("suchitra_kn_narration", "Suchitra", "female")), honorific=""),
    "punjabi": Language("punjabi", "Punjabi", "ਪੰਜਾਬੀ", "pa-IN", "pa-IN", "pa-IN", _BOTH, V4_FLASH, _v(
        ("anand_pa_conversation", "Anand", "male"), ("harpreet_pa_narration", "Harpreet", "female"),
        ("jaspal_pa_banking", "Jaspal", "male"))),
    # Registered, disabled until ear-checked (section 4A rule 7). v4-flash has no
    # personas for these yet, so stock voices are bulbul:v3; cloning supports both.
    # Odia's codes really differ per component (checked live 2026-10-22): realtime
    # STT accepts only "or-IN" (rejects "od-IN"); Bulbul TTS and cloning use "od-IN".
    "malayalam": Language("malayalam", "Malayalam", "മലയാളം", "ml-IN", "ml-IN", "ml-IN", _NONE, V3, honorific=""),
    "odia": Language("odia", "Odia", "ଓଡ଼ିଆ", "or-IN", "od-IN", "od-IN", _NONE, V3, honorific=""),
}

DEFAULT_LANGUAGE = "hinglish"

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


# ── Owner settings (platform_cost_settings row), cached ≤ 60 s ────────────────
@dataclass(frozen=True)
class OwnerSettings:
    global_enabled: bool = True
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
    value = OwnerSettings(
        global_enabled=row.sarvam_pipeline_global_enabled if row else True,
        language_overrides=dict(row.language_overrides or {}) if row else {},
    )
    _cache = (now + _CACHE_TTL, value)
    return value


def invalidate_owner_settings() -> None:
    global _cache
    _cache = None


# ── Registry lookups with owner overrides layered on ──────────────────────────
def _override(settings: OwnerSettings, language: str, pipeline: str) -> dict:
    return (settings.language_overrides.get(language) or {}).get(pipeline) or {}


def language_enabled(language: str, pipeline: str, settings: OwnerSettings) -> bool:
    lang = LANGUAGES.get(language)
    if lang is None:
        return False
    ov = _override(settings, language, pipeline)
    return bool(ov["enabled"]) if "enabled" in ov else lang.enabled.get(pipeline, False)


def sarvam_tts_model(language: str, settings: OwnerSettings) -> str:
    model = _override(settings, language, SARVAM).get("tts_model")
    return model if model in SARVAM_TTS_MODELS else LANGUAGES[language].sarvam_tts_model


def sarvam_voices(language: str, settings: OwnerSettings) -> tuple[Voice, ...]:
    """Stock voices valid on the sarvam pipeline for this language and its TTS model."""
    lang = LANGUAGES[language]
    if sarvam_tts_model(language, settings) == V3:
        voices = tuple(Voice(i, i.capitalize(), g) for i, g in V3_VOICES)
    else:
        voices = lang.v4_voices
    shortlist = _override(settings, language, SARVAM).get("voices")
    if shortlist:
        voices = tuple(v for v in voices if v.id in set(shortlist)) or voices
    return voices


def all_sarvam_stock_voice_ids() -> set[str]:
    return {i for i, _ in V3_VOICES} | {v.id for lang in LANGUAGES.values() for v in lang.v4_voices}


def default_sarvam_voice(language: str, settings: OwnerSettings, gender: str | None = None) -> str:
    voices = sarvam_voices(language, settings)
    for v in voices:
        if gender is None or v.gender == gender:
            return v.id
    return voices[0].id


# ── Resolution ────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Resolved:
    pipeline: str          # what the call runs on
    requested: str         # what the agent/campaign asked for
    off_reason: str | None  # "global" | "organisation" | "language" when sarvam was refused


def requested_pipeline(campaign_pipeline: str | None, agent_pipeline: str | None) -> str:
    p = campaign_pipeline or agent_pipeline or STANDARD
    return p if p in PIPELINES else STANDARD


def sarvam_off_reason(org, language: str, settings: OwnerSettings) -> str | None:
    if not settings.global_enabled:
        return "global"
    if not getattr(org, "sarvam_pipeline_enabled", False):
        return "organisation"
    if not language_enabled(language, SARVAM, settings):
        return "language"
    return None


def resolve(campaign_pipeline, agent_pipeline, org, language: str, settings: OwnerSettings) -> Resolved:
    requested = requested_pipeline(campaign_pipeline, agent_pipeline)
    if requested == SARVAM:
        reason = sarvam_off_reason(org, language, settings)
        if reason:
            return Resolved(STANDARD, requested, reason)
    return Resolved(requested, requested, None)


# ── Validation matrix ─────────────────────────────────────────────────────────
class PipelineValidationError(ValueError):
    """Message is customer-safe: never names a vendor or model."""


def validate(
    pipeline: str,
    language: str,
    voice_id: str | None,
    settings: OwnerSettings,
    *,
    cloned_provider: str | None = None,
    voice_provider: str | None = None,
) -> None:
    """Reject combinations that would fail on a live call.

    cloned_provider: provider ("elevenlabs" | "sarvam") of the org's cloned
    voice when voice_id is one (None = voice_id is a stock voice or empty). voice_provider: the agent's
    stock voice provider on the standard pipeline.
    """
    if pipeline not in PIPELINES:
        raise PipelineValidationError("Unknown calling engine.")
    label = PIPELINE_LABELS[pipeline]
    if language not in LANGUAGES or not language_enabled(language, pipeline, settings):
        raise PipelineValidationError(f"This language isn't available on the {label} engine.")

    if pipeline == STANDARD:
        # Standard behaviour is unchanged; only block the one new way to break it.
        if cloned_provider == SARVAM:
            raise PipelineValidationError(f"This cloned voice only works on the {PIPELINE_LABELS[SARVAM]} engine.")
        return

    # sarvam
    if cloned_provider is not None:
        if cloned_provider != SARVAM:
            raise PipelineValidationError(f"This cloned voice only works on the {PIPELINE_LABELS[STANDARD]} engine.")
        if not LANGUAGES[language].clone_supported:
            raise PipelineValidationError("Cloned voices aren't available in this language yet.")
        return
    if voice_provider and voice_provider != SARVAM:
        raise PipelineValidationError(f"This voice isn't available on the {label} engine.")
    if voice_id and voice_id not in {v.id for v in sarvam_voices(language, settings)}:
        raise PipelineValidationError(f"This voice isn't available in this language on the {label} engine.")


# ── What the agent needs for a sarvam call (goes into job metadata) ───────────
def sarvam_call_config(language: str, voice_id: str | None, settings: OwnerSettings, *, cloned: bool) -> dict:
    """Everything the agent's SarvamPipeline needs, including every enabled
    language's codes/model/default voices so a mid-call switch needs no lookup."""
    langs = {}
    for key, lang in LANGUAGES.items():
        if not language_enabled(key, SARVAM, settings):
            continue
        voices = sarvam_voices(key, settings)
        langs[key] = {
            "display": lang.display,
            "stt": lang.stt_code,
            "tts": lang.tts_code,
            "clone": lang.clone_code,
            "tts_model": sarvam_tts_model(key, settings),
            "honorific": lang.honorific,
            "voices": [{"id": v.id, "gender": v.gender} for v in voices],
            "repeat_line": SPOKEN_LINES[key][0],
            "failure_line": SPOKEN_LINES[key][1],
        }
    return {
        "language": language,
        "voice_id": voice_id or default_sarvam_voice(language, settings),
        "cloned": cloned,
        "languages": langs,
    }


@dataclass(frozen=True)
class CallEngine:
    """What one call runs on, decided at dial time (toggles apply to the next call)."""
    pipeline: str
    fallback: bool       # asked for sarvam, owner had it off -> runs standard
    pause: bool          # asked for sarvam with a Sarvam-only cloned voice and it's off -> don't dial
    voice_id: str        # standard-engine voice fields (unchanged unless falling back)
    voice_provider: str
    meta: dict           # merged into the agent's job metadata


async def resolve_call_engine(
    db, *, org_id, campaign_pipeline: str | None, agent_pipeline: str | None,
    language: str, voice_id: str, voice_provider: str,
) -> CallEngine:
    from sqlalchemy import select
    from app.models.cloned_voice import ClonedVoice
    from app.models.company_profile import OrgCompanyProfile
    from app.models.user import Organization

    org = await db.get(Organization, org_id)
    settings = await get_owner_settings(db)
    res = resolve(campaign_pipeline, agent_pipeline, org, language, settings)
    cloned = None
    if voice_id:
        cloned = await db.scalar(select(ClonedVoice).where(
            ClonedVoice.elevenlabs_voice_id == voice_id,
            ClonedVoice.org_id == org_id,
            ClonedVoice.deleted_at.is_(None),
        ))
    sarvam_clone = cloned is not None and cloned.provider == SARVAM

    if res.pipeline == SARVAM:
        is_clone = sarvam_clone and str(cloned.status) == "ready"
        stock_ok = voice_id in {v.id for v in sarvam_voices(language, settings)}
        cfg = sarvam_call_config(language, voice_id if (is_clone or stock_ok) else None, settings, cloned=is_clone)
        profile = await db.scalar(select(OrgCompanyProfile).where(OrgCompanyProfile.org_id == org_id))
        if profile is not None:
            cfg["stt_prompt"] = ", ".join(t for t in (profile.company_name, profile.industry) if t)[:200]
        return CallEngine(SARVAM, False, False, voice_id, voice_provider, {"pipeline": SARVAM, "sarvam": cfg})
    if res.requested == SARVAM:
        # Owner switched the engine off (globally / for this org / this language).
        # A Sarvam cloned voice exists nowhere else, so that campaign pauses; a
        # stock-voice one runs on standard with the language's default voice.
        if sarvam_clone:
            return CallEngine(STANDARD, True, True, voice_id, voice_provider, {"pipeline": STANDARD})
        return CallEngine(STANDARD, True, False, "", "elevenlabs", {"pipeline": STANDARD})
    return CallEngine(STANDARD, False, False, voice_id, voice_provider, {"pipeline": STANDARD})


PAUSE_REASON_ENGINE_OFF = "indic_native_unavailable"


def languages_for(pipeline: str, settings: OwnerSettings) -> list[dict]:
    """Customer-safe language list for the app (GET /api/languages)."""
    out = []
    for key, lang in LANGUAGES.items():
        if not language_enabled(key, pipeline, settings):
            continue
        item = {"value": key, "label": lang.display, "native": lang.native, "cloned_voices": lang.clone_supported}
        if pipeline == SARVAM:
            item["voices"] = [{"id": v.id, "name": v.name, "gender": v.gender} for v in sarvam_voices(key, settings)]
        out.append(item)
    return out
