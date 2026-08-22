#!/usr/bin/env python3
"""
reclassify_calls.py — Re-run outcome + summary for all calls that have a transcript.

Run inside the api container on VPS:
    docker compose exec api python scripts/reclassify_calls.py          # all calls
    docker compose exec api python scripts/reclassify_calls.py 100      # only the 100 most recent

What it does:
  1. Finds COMPLETED calls that have a CallTranscript (with non-empty text),
     most recent first -- optionally capped to the N most recent via an
     integer command-line argument
  2. Re-classifies each one with the updated generous Groq prompt
  3. Writes new outcome + summary back to the Call row
  4. Recounts interested_count for every campaign from actual Call records
     (across ALL calls regardless of the limit above, so counts stay correct)

Use this after updating the classification prompt to fix past mis-classifications.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

_backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(_backend_dir))
os.chdir(_backend_dir)

from dotenv import load_dotenv
load_dotenv(_backend_dir / ".env")

import aiohttp
from sqlalchemy import func, select, update

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.call import Call, CallOutcome, CallStatus, CallTranscript
from app.models.campaign import Campaign


_VALID_OUTCOMES = {"interested", "not_interested", "callback_requested", "wrong_number", "do_not_call"}


async def _classify(http: aiohttp.ClientSession, full_text: str) -> tuple[str, str]:
    """Re-classify a call from its existing transcript text."""
    if not full_text or not full_text.strip():
        return "not_interested", ""

    try:
        async with http.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                # llama-3.3-70b-versatile was deprecated by Groq in 2026 --
                # same wave that broke agent.py's live classifier (404
                # model_not_found). This script runs offline, so no latency
                # cost to using Groq's larger recommended replacement.
                "model": "openai/gpt-oss-120b",
                "max_tokens": 300,
                "temperature": 0.0,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You analyze Indian sales call transcripts (Hinglish/Hindi/English). "
                            "Transcripts may have speech-to-text errors — read the intent, not exact words. "
                            "Reply ONLY with valid JSON — no explanation, no markdown.\n"
                            'Format: {"outcome": "...", "summary": "..."}\n'
                            "outcome must be exactly one of:\n"
                            "  interested         - Use this ONLY when the customer showed CLEAR, ACTIVE interest. "
                            "Requires at least ONE of:\n"
                            "                       • Asked a specific question about price, availability, delivery, or specs\n"
                            "                       • Shared or agreed to share contact info (WhatsApp, phone, email)\n"
                            "                       • Agreed to receive catalogue, sample, demo, or quote\n"
                            "                       • Confirmed they currently buy or use this type of product\n"
                            "                       • Explicitly said they want to place an order or inquire\n"
                            "                       IMPORTANT: Passive replies only ('haan', 'hmm', 'theek hai', 'okay', 'bol') "
                            "do NOT count as interest — the customer must have asked something or agreed to something. "
                            "A long conversation with no rejection is NOT by itself evidence of interest.\n"
                            "  callback_requested - Customer asked to be called back AND gave a SPECIFIC later time "
                            "(a day, date, or time of day). A vague 'call me later'/'baad mein call karo' with NO "
                            "specific time is NOT enough — that phrasing is a common brush-off, not a real booking.\n"
                            "  not_interested     - DEFAULT for all other cases, including:\n"
                            "                       • Customer only gave short/vague replies without engaging\n"
                            "                       • Customer never asked a question or agreed to anything\n"
                            "                       • Firm rejection: 'nahi chahiye', 'busy hoon', 'mat karo call', hung up\n"
                            "                       • 'Call me later' with no specific time, especially right before hanging up\n"
                            "                       WHEN IN DOUBT → use not_interested\n"
                            "  wrong_number       - Wrong person or wrong business\n"
                            "  do_not_call        - Customer demanded to never be called again\n"
                            "RED FLAG - fake contact info: if the phone/WhatsApp number in the transcript is implausible "
                            "(wrong digit count, all one repeated digit, or an obvious sequence like '123456789'), that's "
                            "a strong signal of a brush-off, not real contact info — do NOT classify as 'interested' or "
                            "'callback_requested' on the strength of that number alone; fall back to 'not_interested' "
                            "unless something else in the transcript shows genuine engagement.\n"
                            "summary: 2-3 sentences. Mention what products customer needs and what was agreed."
                        ),
                    },
                    {"role": "user", "content": f"Call transcript:\n{full_text}"},
                ],
            },
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.status != 200:
                print(f"    ! Groq {resp.status}: {await resp.text()}")
                return "not_interested", ""
            data = await resp.json()

        raw = (data["choices"][0]["message"]["content"] or "").strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw.strip())
        outcome = result.get("outcome", "not_interested")
        summary = result.get("summary", "")
        return (outcome if outcome in _VALID_OUTCOMES else "not_interested"), summary

    except Exception as exc:
        print(f"    ! Groq error: {exc}")
        return "not_interested", ""


async def _recount_campaign_stats() -> None:
    print("\n── Recounting campaign interested_count ─────────────────────")
    async with AsyncSessionLocal() as session:
        campaigns = (await session.execute(select(Campaign))).scalars().all()
        for camp in campaigns:
            count = await session.scalar(
                select(func.count(Call.id)).where(
                    Call.campaign_id == camp.id,
                    Call.outcome == CallOutcome.INTERESTED,
                )
            )
            await session.execute(
                update(Campaign).where(Campaign.id == camp.id).values(interested_count=count or 0)
            )
            print(f"  {camp.name}: interested_count = {count or 0}")
        await session.commit()
    print("  Done.\n")


async def reclassify(limit: int | None = None) -> None:
    print("=" * 62)
    label = f"Reclassify Last {limit} Calls" if limit else "Reclassify All Calls with Transcripts"
    print(f"  MOTMVoice — {label}")
    print("=" * 62)

    # Load completed calls that have a transcript (full_text OR segments).
    # Calls still stuck at outcome=PENDING go first regardless of how old
    # they are -- unsticking those is the actual point of this script, and
    # a plain most-recent-first order can silently push an entire campaign's
    # pending calls outside a limited run if other calls (other campaigns,
    # test calls, inbound) happened more recently. Already-classified calls
    # fill any remaining room, most recent first, for prompt re-verification.
    async with AsyncSessionLocal() as session:
        query = (
            select(Call, CallTranscript)
            .join(CallTranscript, CallTranscript.call_id == Call.id)
            .where(Call.status == CallStatus.COMPLETED)
            .order_by((Call.outcome == CallOutcome.PENDING).desc(), Call.started_at.desc())
        )
        if limit is not None:
            query = query.limit(limit)
        rows = (await session.execute(query)).all()

    total = len(rows)
    if total == 0:
        print("\n✓ No calls with transcripts found.\n")
        await _recount_campaign_stats()
        return

    print(f"\nFound {total} calls to reclassify.\n")
    ok = failed = changed = 0

    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=connector) as http:
        for idx, (call, transcript) in enumerate(rows, 1):
            old_outcome = str(call.outcome)
            print(f"[{idx:>3}/{total}] {call.phone_number}  {call.started_at or 'unknown'}  old={old_outcome}", end="  ")

            # Use full_text if available; otherwise rebuild from segments JSON
            text = transcript.full_text or ""
            if not text and transcript.segments:
                try:
                    segs = transcript.segments if isinstance(transcript.segments, list) else []
                    text = "\n".join(
                        f"{'CUSTOMER' if s.get('speaker') in ('user', 'customer') else 'AGENT'}: {s.get('text', '')}"
                        for s in segs if s.get('text')
                    )
                except Exception:
                    pass

            if not text.strip():
                print("→ skip (no text)")
                continue

            new_outcome, new_summary = await _classify(http, text)

            if new_outcome != old_outcome:
                print(f"→ {new_outcome}  CHANGED")
                changed += 1
            else:
                print(f"→ {new_outcome}  (same)")

            try:
                async with AsyncSessionLocal() as session:
                    async with session.begin():
                        await session.execute(
                            update(Call)
                            .where(Call.id == call.id)
                            .values(outcome=new_outcome, summary=new_summary or None)
                        )
                ok += 1
            except Exception as exc:
                print(f"    ! Save error: {exc}")
                failed += 1

            # Rate limit: ~2 req/s to stay within Groq free tier
            await asyncio.sleep(0.5)

    print("\n" + "=" * 62)
    print(f"  Done: ✓ {ok} reclassified  |  {changed} outcomes changed  |  ✗ {failed} errors")
    print("=" * 62)

    await _recount_campaign_stats()


if __name__ == "__main__":
    _limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    asyncio.run(reclassify(_limit))
