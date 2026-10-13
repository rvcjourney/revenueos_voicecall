"""tests/test_prompt_language_purity.py — regression test for the bug report:
regional-language calls "speaking mix like Hindi+Gujarati" / "Hindi+Telugu".

_build_prompt's guardrails text used to hardcode Hindi/Hinglish example
phrases (closing line, WhatsApp ask, "ji" honorific) unconditionally for
every language, and the honorific transform forced "ji" into every reply
regardless of the agent's configured language. Both leaked Hindi words into
Gujarati/Telugu/Tamil/Kannada/Bengali calls. Covers that the fix holds for
every language the platform offers.
"""
from __future__ import annotations

import pytest

import languages
from agent import _build_prompt

# These must never appear as literal positive examples in the built prompt for
# a non-Hindi/Hinglish language -- they were the hardcoded output templates.
_HARDCODED_HINDI_EXAMPLES = (
    "Bahut shukriya ji, koi zaroorat",
    "Ek kaam karo ji, aapka WhatsApp",
    "Ji ye number thoda sahi se nahi aaya",
    "Maaf kijiye ji, main us bhasha",
)

_NON_HONORIFIC_LANGUAGES = ("tamil", "telugu", "kannada", "bengali", "gujarati", "english")
_HONORIFIC_LANGUAGES = ("hindi", "hinglish", "marathi", "punjabi")


@pytest.mark.parametrize("language", list(languages.LANGUAGES))
def test_no_hardcoded_hindi_example_leaks_for_any_language(language):
    prompt = _build_prompt("You are Priya.", "Namaste", language)
    for example in _HARDCODED_HINDI_EXAMPLES:
        assert example not in prompt


@pytest.mark.parametrize("language", _NON_HONORIFIC_LANGUAGES)
def test_languages_without_ji_never_told_to_use_it(language):
    prompt = _build_prompt("You are Priya.", "Namaste", language)
    rule_1a = prompt[prompt.index("1a."):prompt.index("2. Keep")]
    assert "use the warm, gender-neutral honorific" not in rule_1a
    assert "no 'ji'-style honorific" in rule_1a


@pytest.mark.parametrize("language", _HONORIFIC_LANGUAGES)
def test_languages_with_ji_are_told_to_use_it(language):
    prompt = _build_prompt("You are Priya.", "Namaste", language)
    rule_1a = prompt[prompt.index("1a."):prompt.index("2. Keep")]
    assert "use the warm, gender-neutral honorific 'ji'" in rule_1a


@pytest.mark.parametrize("language", _NON_HONORIFIC_LANGUAGES + ("marathi", "punjabi"))
def test_non_hindi_languages_get_the_anti_mixing_rule(language):
    prompt = _build_prompt("You are Priya.", "Namaste", language)
    assert "9c. LANGUAGE PURITY" in prompt
    assert languages.get(language).display.upper() in prompt


@pytest.mark.parametrize("language", ("hindi", "hinglish"))
def test_hindi_and_hinglish_skip_the_anti_mixing_rule(language):
    """It would be a no-op there (the examples already ARE the target language)."""
    prompt = _build_prompt("You are Priya.", "Namaste", language)
    assert "9c. LANGUAGE PURITY" not in prompt


@pytest.mark.parametrize("language", ("tamil", "telugu", "kannada", "bengali", "gujarati"))
def test_native_script_languages_are_told_not_to_romanise(language):
    prompt = _build_prompt("You are Priya.", "Namaste", language)
    assert "own native script" in prompt
    assert "mispronounces Romanised" in prompt


@pytest.mark.parametrize("language", ("hinglish", "english"))
def test_roman_script_languages_get_no_script_instruction(language):
    prompt = _build_prompt("You are Priya.", "Namaste", language)
    assert "own native script" not in prompt


def test_every_language_in_the_registry_builds_a_valid_prompt():
    """Catches a KeyError/AttributeError in _build_prompt for any language the
    UI's dropdown can actually select (frontend/src/lib/languages.ts)."""
    for key in languages.LANGUAGES:
        prompt = _build_prompt("You are Priya, a sales agent.", "Namaste", key)
        assert "[ABSOLUTE RULES" in prompt and "[end_call]" in prompt
