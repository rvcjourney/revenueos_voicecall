"""
app/services/prompt_library.py — helpers shared by the prompt library API.

derive_tags_from_text() gives a first-pass set of use-case tags for a prompt
that was just imported from an AgentTemplate (e.g. "Paint Sales Agent" ->
["paint"]) so search/grouping works immediately without an admin having to
tag every agent by hand. Admins can always edit tags afterwards via PATCH.
"""
from __future__ import annotations

import re

_STOPWORDS = {
    "a", "an", "the", "and", "or", "for", "of", "to", "in", "on", "with",
    "your", "our", "is", "are", "new", "demo", "help", "helps", "using",
    "agent", "agents", "ai", "assistant", "bot", "template", "voice",
    "call", "calls", "calling", "caller",
    "customer", "customers", "lead", "leads", "service", "services",
    "team", "company", "sales", "rep", "representative", "support",
}


def derive_tags_from_text(*texts: str | None, limit: int = 4) -> list[str]:
    """Extract a handful of lowercase, deduped keyword tags from agent name/description."""
    tags: list[str] = []
    seen: set[str] = set()
    for text in texts:
        if not text:
            continue
        for word in re.findall(r"[A-Za-z]+", text.lower()):
            if len(word) < 3 or word in _STOPWORDS or word in seen:
                continue
            seen.add(word)
            tags.append(word)
            if len(tags) >= limit:
                return tags
    return tags
