"""
app/services/agent_builder.py — "Customise with AI" in the agent editor: an OpenAI
model rewrites an agent's Greeting and Instructions from a plain-language request.
Nothing is saved here; the editor shows the result and the user decides.
"""
from __future__ import annotations

import re

import httpx

from app.config import settings

_URL = "https://api.openai.com/v1/responses"

_SYSTEM = """You edit the script of an AI phone agent that makes outbound calls in India.
You get the agent's current GREETING (spoken word for word when the call connects), its
INSTRUCTIONS (markdown) and a CHANGE REQUEST. Apply the request and return the full,
updated script.

Rules:
- Change only what the request asks for; keep everything else exactly as it is.
- Keep the markdown structure: "## " section headings, "### " sub-headings, "- " bullets.
- Placeholders look like {camelCaseName} and are filled per call from the contact's CSV
  columns or the agent's default values. Keep existing placeholders unless the request
  removes them. Add a new {placeholder} only for a value that changes per contact or per
  campaign. {current_date} (today's date) and {time_greeting} ("Good morning"/"Good afternoon"/"Good evening" for
  the contact's local time) are always available.
- The agent has three tools; refer to them by these exact names: end_interaction (ends the
  call), book_next_step (books a demo/meeting/follow-up), switch_language (changes the
  spoken language).
- If the instructions are empty, write a complete script from the request.

Reply in exactly this format and nothing else:
<summary>One or two sentences on what you changed.</summary>
<greeting>the full greeting</greeting>
<instructions>the full instructions</instructions>"""

_TAG = {tag: re.compile(rf"<{tag}>\s*(.*?)\s*</{tag}>", re.S) for tag in ("summary", "greeting", "instructions")}


class AgentBuilderError(Exception):
    """Customer-safe message."""


def parse(text: str) -> tuple[str, str, str]:
    """(summary, greeting, instructions) from the model's tagged reply."""
    found = {tag: rx.search(text or "") for tag, rx in _TAG.items()}
    if not found["greeting"] or not found["instructions"]:
        raise AgentBuilderError("The AI didn't return a complete script. Try rephrasing your request.")
    return (found["summary"].group(1) if found["summary"] else "",
            found["greeting"].group(1), found["instructions"].group(1))


async def customize(*, greeting: str, instructions: str, request: str) -> tuple[str, str, str]:
    if not settings.OPENAI_API_KEY:
        raise AgentBuilderError("AI customisation isn't configured yet.")
    user = f"GREETING:\n{greeting}\n\nINSTRUCTIONS:\n{instructions}\n\nCHANGE REQUEST:\n{request}"
    try:
        async with httpx.AsyncClient(timeout=180.0) as http:
            resp = await http.post(
                _URL,
                headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                json={
                    "model": settings.OPENAI_BUILDER_MODEL,
                    "instructions": _SYSTEM,
                    "input": user,
                    "reasoning": {"effort": "low"},
                    "max_output_tokens": 32000,
                    "store": False,
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        raise AgentBuilderError("The AI service didn't respond. Please try again.") from exc
    if data.get("status") == "incomplete":
        raise AgentBuilderError("The script is too long for the AI to rewrite in one go. Try a smaller change.")
    text = "".join(part.get("text") or "" for item in data.get("output") or [] if item.get("type") == "message"
                   for part in item.get("content") or [] if part.get("type") == "output_text")
    return parse(text)

# Self-check: the tagged reply parses; a reply missing a section is refused.
assert parse("<summary>s</summary>\n<greeting>Hi {userName}</greeting><instructions>## A\n- b</instructions>") == (
    "s", "Hi {userName}", "## A\n- b")
try:
    parse("<greeting>only</greeting>")
    raise AssertionError("incomplete reply accepted")
except AgentBuilderError:
    pass
