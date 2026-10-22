"""tests/test_sarvam_pipeline.py — the "sarvam" calling engine (sarvam_pipeline.py)
and the agent.py hooks that only exist for it. No network: fakes only."""
from __future__ import annotations

import asyncio
import itertools
from types import SimpleNamespace

import pytest
from livekit.agents import Agent, llm as lk_llm, tts as lk_tts

import agent as agent_mod
import sarvam_pipeline as sp

# Shape of meta["sarvam"]["languages"] (backend/app/core/pipelines.py sarvam_call_config).
_V3 = [{"id": "ritu", "gender": "female"}, {"id": "shubh", "gender": "male"}]
LANGS = {
    "hinglish": {"stt": "hi-IN", "tts": "hi-IN", "clone": "hi-IN", "tts_model": "bulbul:v4-flash", "display": "Hinglish",
                 "voices": [{"id": "simran_enhi_customer", "gender": "female"}, {"id": "sunny_enhi_customer", "gender": "male"}]},
    "hindi": {"stt": "hi-IN", "tts": "hi-IN", "clone": "hi-IN", "tts_model": "bulbul:v4-flash", "display": "Hindi",
              "voices": [{"id": "ritu_hi_conversation", "gender": "female"}, {"id": "rahul_hi_conversational", "gender": "male"}]},
    "english": {"stt": "en-IN", "tts": "en-IN", "clone": "en-IN", "tts_model": "bulbul:v4-flash", "display": "English",
                "voices": [{"id": "simran_en_conversation", "gender": "female"}, {"id": "dev_en_conversational", "gender": "male"}]},
    "marathi": {"stt": "mr-IN", "tts": "mr-IN", "clone": "mr-IN", "tts_model": "bulbul:v4-flash", "display": "Marathi",
                "voices": [{"id": "ishita_mr_conversational", "gender": "female"}, {"id": "nilesh_mr_conversation", "gender": "male"}]},
    "tamil": {"stt": "ta-IN", "tts": "ta-IN", "clone": "ta-IN", "tts_model": "bulbul:v3", "display": "Tamil", "voices": _V3},
    "telugu": {"stt": "te-IN", "tts": "te-IN", "clone": "te-IN", "tts_model": "bulbul:v4-flash", "display": "Telugu",
               "voices": [{"id": "kavitha_te_conversation", "gender": "female"}, {"id": "tarun_te_narration", "gender": "male"}]},
    "bengali": {"stt": "bn-IN", "tts": "bn-IN", "clone": "bn-IN", "tts_model": "bulbul:v3", "display": "Bengali", "voices": _V3},
    "gujarati": {"stt": "gu-IN", "tts": "gu-IN", "clone": "gu-IN", "tts_model": "bulbul:v3", "display": "Gujarati", "voices": _V3},
    "kannada": {"stt": "kn-IN", "tts": "kn-IN", "clone": "kn-IN", "tts_model": "bulbul:v4-flash", "display": "Kannada",
                "voices": [{"id": "chaitra_kn_conversation", "gender": "female"}, {"id": "chetan_kn_conversation", "gender": "male"}]},
    "punjabi": {"stt": "pa-IN", "tts": "pa-IN", "clone": "pa-IN", "tts_model": "bulbul:v4-flash", "display": "Punjabi",
                "voices": [{"id": "harpreet_pa_narration", "gender": "female"}, {"id": "anand_pa_conversation", "gender": "male"}]},
}
for _k in LANGS:
    LANGS[_k]["repeat_line"] = f"repeat-{_k}"
    LANGS[_k]["failure_line"] = f"failure-{_k}"


def _state(language="hindi", voice="ritu_hi_conversation", cloned=False):
    return sp.SarvamCallState(language, voice, cloned, LANGS)


class _Fake:
    def __init__(self):
        self.calls = []

    def update_options(self, **kw):
        self.calls.append(kw)


def test_parse_meta_rejects_disabled_language():
    with pytest.raises(ValueError):
        sp.parse_meta({"sarvam": {"language": "malayalam", "voice_id": "x", "languages": LANGS}})
    s = sp.parse_meta({"sarvam": {"language": "tamil", "voice_id": "ritu", "languages": LANGS}})
    assert s.lang["tts_model"] == "bulbul:v3"


@pytest.mark.parametrize("creativity, expected", [(0.7, 0.35), (0.0, 0.2), (2.0, 0.6), (1.0, 0.5)])
def test_creativity_maps_into_safe_band(creativity, expected):
    assert sp.clamp_temperature(creativity) == expected


def test_codemix_only_for_hindi():
    assert sp.stt_mode("hi-IN") == "codemix"
    assert sp.stt_mode("ta-IN") == "transcribe"


def test_turn_handling_values():
    th = sp.turn_handling()
    assert th["turn_detection"] == "stt"
    assert th["endpointing"]["min_delay"] == 0.3
    assert th["interruption"]["mode"] == "vad" and th["interruption"]["min_words"] == 1
    assert th["preemptive_generation"]["preemptive_tts"] is False
    assert sp.SESSION_KWARGS == {"vad": None, "aec_warmup_duration": None, "user_away_timeout": None}


def test_tts_kwargs_temperature_only_on_v3():
    assert "temperature" not in sp._tts_kwargs("bulbul:v4-flash", "ritu_hi_conversation", "hi-IN")
    assert sp._tts_kwargs("bulbul:v3", "ritu", "ta-IN")["temperature"] == sp.TTS_V3_TEMPERATURE
    assert sp._tts_kwargs("bulbul:v4-flash", "x", "hi-IN")["model"] == "bulbul:v4-flash"  # never omitted


def test_build_components_construct_without_network():
    sp.validate_components()
    sp.build_tts(_state("tamil", "ritu"))
    sp.build_stt(_state(), prompt="x" * 500)  # long prompt is cut, not rejected


def test_prompt_adapter_appends_and_never_edits_script():
    script = "PRIME SCRIPT\n7. Close with: Take care, namaste! [end_call]"
    out = sp.prompt_adapter(script, _state("hinglish", "simran_enhi_customer"))
    assert out.startswith(script)
    assert "Devanagari" in out and "Never address the customer as Sir" in out
    assert "native script" in sp.prompt_adapter(script, _state("tamil", "ritu"))


def test_romanised_check():
    assert sp.looks_romanised("Sir humare yahan naya steel aaya hai", "hindi")
    assert not sp.looks_romanised("आपका order कब तक चाहिए?", "hindi")
    assert not sp.looks_romanised("We have new steel stock today", "english")


def test_trim_keeps_system_script_and_drops_oldest_turns():
    ctx = lk_llm.ChatContext()
    ctx.add_message(role="system", content="S" * 300)
    for i in range(10):
        ctx.add_message(role="user", content=f"u{i} " + "x" * 300)
        ctx.add_message(role="assistant", content=f"a{i} " + "y" * 300)
    trimmed = sp.trim_to_budget(ctx, budget=1200)
    roles = [it.role for it in trimmed.items]
    assert roles[0] == "system"
    assert sp.estimate_tokens(trimmed) <= 1200
    assert trimmed.items[-1].content == ctx.items[-1].content  # newest kept
    assert len(ctx.items) == 21  # original untouched


def test_voice_keeps_persona_family_then_gender():
    s = _state("hindi", "ritu_hi_conversation")
    assert sp.voice_for_language(s, LANGS["tamil"]) == "ritu"                    # v3 has "ritu"
    assert sp.voice_for_language(s, LANGS["marathi"]) == "ishita_mr_conversational"  # no ritu_mr_* -> female
    s = _state("hindi", "rahul_hi_conversational")
    assert sp.voice_for_language(s, LANGS["kannada"]) == "chetan_kn_conversation"   # male


@pytest.mark.parametrize("src, dst", list(itertools.permutations(LANGS, 2)))
def test_switch_every_language_pair(src, dst):
    state = _state(src, LANGS[src]["voices"][0]["id"])
    tts, stt = _Fake(), _Fake()
    assert sp.switch_language(state, dst, tts, stt)
    assert state.language == dst
    assert stt.calls[-1] == {"language": LANGS[dst]["stt"], "mode": sp.stt_mode(LANGS[dst]["stt"])}
    call = tts.calls[-1]
    assert call["model"] == LANGS[dst]["tts_model"] and call["target_language_code"] == LANGS[dst]["tts"]
    assert call["speaker"] in {v["id"] for v in LANGS[dst]["voices"]}
    assert ("temperature" in call) == (LANGS[dst]["tts_model"] == "bulbul:v3")


def test_switch_cloned_voice_keeps_voice_and_retargets_language():
    state = _state("hindi", "svc-abc", cloned=True)
    tts, stt = _Fake(), _Fake()
    sp.switch_language(state, "tamil", tts, stt)
    assert tts.calls == [{"target_language_code": "ta-IN"}]
    assert state.voice_id == "svc-abc"


def test_switch_to_disabled_language_is_ignored():
    tts, stt = _Fake(), _Fake()
    assert not sp.switch_language(_state(), "malayalam", tts, stt)
    assert tts.calls == [] and stt.calls == []


# ── agent.py hooks ────────────────────────────────────────────────────────────
def _agent(turns=1):
    va = agent_mod.SarvamVoiceAgent(SimpleNamespace(), instructions="x", welcome_message="w", sarvam_state=_state())
    va._turn_count = turns
    return va


async def _collect(va, chunks, monkeypatch):
    async def fake_llm_node(agent, chat_ctx, tools, model_settings):
        for c in chunks:
            yield c
    monkeypatch.setattr(Agent.default, "llm_node", fake_llm_node)
    return [c async for c in va.llm_node(lk_llm.ChatContext(), [], None)]


async def test_empty_reply_after_customer_turn_speaks_repeat_line(monkeypatch):
    va = _agent(turns=2)
    assert await _collect(va, [], monkeypatch) == ["repeat-hindi"]
    assert va._sarvam.empty_replies == 1


async def test_empty_welcome_is_left_to_its_own_fallback(monkeypatch):
    va = _agent(turns=0)
    assert await _collect(va, [], monkeypatch) == []


async def test_real_reply_passes_through(monkeypatch):
    va = _agent(turns=1)
    assert await _collect(va, ["नमस्ते", " जी"], monkeypatch) == ["नमस्ते", " जी"]
    assert va._sarvam.empty_replies == 0


class _FakeSarvamAgent:
    def __init__(self, ending=False):
        self._ending = ending
        self.calls = []

    async def apology_hangup(self, *, can_speak):
        self.calls.append(can_speak)


async def _drain():
    await asyncio.sleep(0)
    await asyncio.sleep(0)


async def test_unrecoverable_llm_error_apologises_then_hangs_up():
    va = _FakeSarvamAgent()
    agent_mod.handle_sarvam_error(va, SimpleNamespace(error=SimpleNamespace(recoverable=False), source=object()))
    await _drain()
    assert va._ending and va.calls == [True]


async def test_unrecoverable_tts_error_hangs_up_without_speaking():
    va = _FakeSarvamAgent()
    real_tts = sp.build_tts(_state("tamil", "ritu"))  # constructs offline
    assert isinstance(real_tts, lk_tts.TTS)
    agent_mod.handle_sarvam_error(va, SimpleNamespace(error=SimpleNamespace(recoverable=False), source=real_tts))
    await _drain()
    assert va.calls == [False]


async def test_recoverable_error_or_ending_call_is_ignored():
    va = _FakeSarvamAgent()
    agent_mod.handle_sarvam_error(va, SimpleNamespace(error=SimpleNamespace(recoverable=True), source=object()))
    done = _FakeSarvamAgent(ending=True)
    agent_mod.handle_sarvam_error(done, SimpleNamespace(error=SimpleNamespace(recoverable=False), source=object()))
    await _drain()
    assert va.calls == [] and done.calls == []


async def _run_transform(transform, chunks):
    async def gen():
        for c in chunks:
            yield c
    return "".join([c async for c in transform(gen())])


async def test_no_ji_filter_follows_current_language():
    langs = {k: dict(v) for k, v in LANGS.items()}
    langs["tamil"]["honorific"] = ""
    langs["hinglish"]["honorific"] = "ji"
    state = sp.SarvamCallState("tamil", "ritu", False, langs)
    t = sp.no_ji_transform(state)
    assert await _run_transform(t, ["சரி j", "i, நான் Ji இப்போ"]) == "சரி, நான் இப்போ"
    state.language = "hinglish"
    assert await _run_transform(sp.no_ji_transform(state), ["हाँ ji, बोलिए"]) == "हाँ ji, बोलिए"
    assert await _run_transform(sp.no_ji_transform(sp.SarvamCallState("tamil", "ritu", False, langs)), ["Rajiv sir"]) == "Rajiv sir"
