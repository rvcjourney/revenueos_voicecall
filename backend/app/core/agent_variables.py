"""
app/core/agent_variables.py — {placeholders} in an agent's Greeting and
Instructions, filled per call. A value comes from (first match wins):
the contact's CSV column of that name, the agent's default value, then the
system values ({current_date}). Matching a CSV column ignores case, spaces and
underscores, so a "User Name" column fills {userName}.
"""
from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

_VAR_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
SYSTEM_VARIABLES = ("current_date", "time_greeting")


def find(*texts: str) -> list[str]:
    """Placeholder names in order of first appearance, without duplicates."""
    return list(dict.fromkeys(m.group(1) for t in texts for m in _VAR_RE.finditer(t or "")))


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def system_values(tz_name: str | None = None) -> dict[str, str]:
    try:
        now = datetime.now(ZoneInfo(tz_name or "Asia/Kolkata"))
    except Exception:
        now = datetime.now()
    part = "morning" if now.hour < 12 else "afternoon" if now.hour < 17 else "evening"
    return {"current_date": now.strftime("%A, %d %B %Y"), "time_greeting": f"Good {part}"}


def resolve(
    names: list[str], *, columns: dict | None = None, defaults: dict | None = None, system: dict | None = None,
) -> tuple[dict[str, str], list[str]]:
    """(values, missing): `missing` lists placeholders with no non-empty value anywhere."""
    by_key = {_key(k): str(v).strip() for k, v in (columns or {}).items() if v is not None and str(v).strip()}
    defaults, system = defaults or {}, system or {}
    values, missing = {}, []
    for name in names:
        value = by_key.get(_key(name)) or str(defaults.get(name) or "").strip() or system.get(name, "")
        values[name] = value
        if not value:
            missing.append(name)
    return values, missing


def fill(text: str, values: dict[str, str]) -> str:
    """Replace every {name} that has a value; unknown placeholders become empty."""
    return _VAR_RE.sub(lambda m: values.get(m.group(1), ""), text or "")


def contact_columns(contact) -> dict:
    """A contact's CSV values for placeholder matching (all columns but phone)."""
    return {**{"name": contact.name, "email": contact.email, "company": contact.company},
            **(contact.custom_fields or {})}


def render(greeting: str, instructions: str, *, columns: dict | None, defaults: dict | None,
           tz_name: str | None = None) -> tuple[str, str, list[str]]:
    """(greeting, instructions, missing) with every placeholder filled."""
    values, missing = resolve(find(greeting, instructions), columns=columns, defaults=defaults,
                              system=system_values(tz_name))
    return fill(greeting, values), fill(instructions, values), missing


# Self-check: time_greeting follows the hour.
assert system_values("Asia/Kolkata")["time_greeting"] in ("Good morning", "Good afternoon", "Good evening")
# Self-check: CSV column wins over the default, matching ignores case/underscores,
# system values fill last, and an unfilled placeholder is reported.
_g, _i, _m = render("Hi {userName} from {partnerName}", "Today is {current_date}. {crmDealStage}",
                    columns={"user_name": "Ravi"}, defaults={"partnerName": "Acme", "userName": "x"})
assert _g == "Hi Ravi from Acme" and _i.startswith("Today is ") and _m == ["crmDealStage"], (_g, _i, _m)
