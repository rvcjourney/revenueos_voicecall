#!/usr/bin/env python3
"""
reclassify_calls.py — Re-run outcome + summary for all calls that have a transcript.

Run inside the api container on VPS:
    docker compose exec api python scripts/reclassify_calls.py

What it does:
  1. Finds all COMPLETED calls that have a CallTranscript (with non-empty text)
  2. Re-classifies each one with the updated generous Groq prompt
  3. Writes new outcome + summary back to the Call row
  4. Recounts interested_count for every campaign from actual Call records

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
                "model": "llama-3.3-70b-versatile",
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
                            "  interested         - Use this when ANY of these are true:\n"
                            "                       • Customer shared or confirmed WhatsApp/phone/email\n"
                            "                       • Customer agreed to receive catalogue, quote, or details\n"
                            "                       • Customer said they will send an inquiry or think about it\n"
                            "                       • Customer asked about price, availability, or product specs\n"
                            "                       • Customer mentioned they purchase similar products\n"
                            "                       • Conversation lasted more than 3 exchanges without rejection\n"
                            "                       WHEN IN DOUBT → use interested\n"
                            "  callback_requested - Customer explicitly asked to be called at a specific later time\n"
                            "  not_interested     - Customer gave FIRM rejection with no engagement at all\n"
                            "  wrong_number       - Wrong person or wrong business\n"
                            "  do_not_call        - Customer demanded to never be called again\n"
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


async def reclassify() -> None:
    print("=" * 62)
    print("  MOTMVoice — Reclassify All Calls with Transcripts")
    print("=" * 62)

    # Load all completed calls that have a transcript (full_text OR segments)
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            select(Call, CallTranscript)
            .join(CallTranscript, CallTranscript.call_id == Call.id)
            .where(Call.status == CallStatus.COMPLETED)
            .order_by(Call.started_at.desc())
        )).all()

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
    asyncio.run(reclassify())
