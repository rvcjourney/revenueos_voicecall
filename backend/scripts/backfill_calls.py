#!/usr/bin/env python3
"""
backfill_calls.py — Backfill recording, transcript, summary and recount campaign stats.

Run once inside the api container on the VPS:
    docker compose exec api python scripts/backfill_calls.py

What it does:
  1. Finds completed calls missing recording_url → fetches from Vobiz
  2. Finds completed calls with outcome=pending → transcribes audio → classifies outcome
  3. Recounts interested_count for every campaign from actual Call records
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
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

VOBIZ_BASE = "https://api.vobiz.ai/api/v1"


def _vobiz_hdrs() -> dict:
    return {
        "X-Auth-ID": settings.VOBIZ_AUTH_ID,
        "X-Auth-Token": settings.VOBIZ_AUTH_TOKEN,
        "Content-Type": "application/json",
    }


async def _find_recording(http: aiohttp.ClientSession, phone: str, call_date) -> str | None:
    norm = phone.lstrip("+")

    # Strategy 1: direct Recording API by to_number
    try:
        offset = 0
        while True:
            async with http.get(
                f"{VOBIZ_BASE}/Account/{settings.VOBIZ_AUTH_ID}/Recording/",
                headers=_vobiz_hdrs(),
                params={"limit": "100", "offset": str(offset)},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    break
                data = await resp.json(content_type=None)

            records = data.get("objects") or []
            if not records:
                break

            for r in records:
                to_num = (r.get("to_number") or "").lstrip("+")
                if norm[-10:] == to_num[-10:]:
                    url = r.get("recording_url") or ""
                    if url:
                        return url

            last_time = records[-1].get("add_time") or ""
            if last_time:
                try:
                    rec_day = datetime.fromisoformat(last_time[:10]).date()
                    if rec_day < call_date - timedelta(days=2):
                        break
                except Exception:
                    pass

            if len(records) < 100:
                break
            offset += 100
    except Exception as exc:
        print(f"    ! Recording search error: {exc}")

    # Strategy 2: CDR → sip_call_id → Recording API
    date_str = call_date.strftime("%Y-%m-%d")
    next_str = (call_date + timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        async with http.get(
            f"{VOBIZ_BASE}/Account/{settings.VOBIZ_AUTH_ID}/cdr",
            headers=_vobiz_hdrs(),
            params={"start_date": date_str, "end_date": next_str, "call_direction": "outbound", "per_page": "100"},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status == 200:
                data = await resp.json(content_type=None)
                records = data.get("data") or data.get("objects") or []
                for rec in records:
                    to_num = (rec.get("destination_number") or rec.get("to_number") or "").lstrip("+")
                    if norm[-10:] != to_num[-10:]:
                        continue
                    call_uuid = rec.get("sip_call_id") or rec.get("call_uuid") or ""
                    if not call_uuid:
                        continue
                    async with http.get(
                        f"{VOBIZ_BASE}/Account/{settings.VOBIZ_AUTH_ID}/Recording/",
                        headers=_vobiz_hdrs(),
                        params={"call_uuid": call_uuid},
                        timeout=aiohttp.ClientTimeout(total=15),
                    ) as r2:
                        if r2.status == 200:
                            rdata = await r2.json(content_type=None)
                            recs = rdata.get("objects") or []
                            for r in recs:
                                url = r.get("recording_url") or r.get("record_url") or ""
                                if url:
                                    return url
    except Exception as exc:
        print(f"    ! CDR error: {exc}")

    return None


async def _download_audio(http: aiohttp.ClientSession, recording_url: str) -> bytes | None:
    try:
        async with http.get(
            recording_url,
            headers={"X-Auth-ID": settings.VOBIZ_AUTH_ID, "X-Auth-Token": settings.VOBIZ_AUTH_TOKEN},
            timeout=aiohttp.ClientTimeout(total=120),
        ) as resp:
            if resp.status != 200:
                print(f"    ! Audio download {resp.status}")
                return None
            return await resp.read()
    except Exception as exc:
        print(f"    ! Audio download: {exc}")
        return None


async def _transcribe(http: aiohttp.ClientSession, audio_bytes: bytes) -> list[dict]:
    try:
        form = aiohttp.FormData()
        form.add_field("file", audio_bytes, filename="recording.wav", content_type="audio/wav")
        form.add_field("model", "whisper-large-v3-turbo")
        form.add_field("language", "hi")
        form.add_field("response_format", "json")
        async with http.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
            data=form,
            timeout=aiohttp.ClientTimeout(total=180),
        ) as resp:
            if resp.status != 200:
                print(f"    ! Whisper {resp.status}: {await resp.text()}")
                return []
            data = await resp.json()
        text = (data.get("text") or "").strip()
        return [{"speaker": "unknown", "text": text}] if text else []
    except Exception as exc:
        print(f"    ! Transcribe: {exc}")
        return []


_VALID_OUTCOMES = {"interested", "not_interested", "callback_requested", "wrong_number", "do_not_call"}


async def _classify(http: aiohttp.ClientSession, segments: list[dict]) -> tuple[str, str]:
    if not segments:
        return "not_interested", ""

    transcript_text = "\n".join(
        f"{'CUSTOMER' if s['speaker'] == 'user' else 'AGENT'}: {s['text']}"
        for s in segments
    )
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
                            "Reply ONLY with valid JSON — no explanation, no markdown.\n"
                            'Format: {"outcome": "...", "summary": "..."}\n'
                            "outcome must be exactly one of:\n"
                            "  interested         - ANY positive signal: asked for WhatsApp/email/catalogue/price,\n"
                            "                       mentioned boss/team/decision-maker, said 'will think about it'\n"
                            "                       or 'send details', asked any question about the product.\n"
                            "                       WHEN IN DOUBT, choose interested.\n"
                            "  callback_requested - customer explicitly asked to be called at a specific later time\n"
                            "  not_interested     - FIRM, CLEAR rejection with zero curiosity\n"
                            "  wrong_number       - wrong person or wrong business\n"
                            "  do_not_call        - customer demanded to never be called again\n"
                            "summary: 2-3 clear English sentences describing what happened."
                        ),
                    },
                    {"role": "user", "content": f"Call transcript:\n{transcript_text}"},
                ],
            },
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.status != 200:
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
        print(f"    ! Groq: {exc}")
        return "not_interested", ""


async def _recount_campaign_stats() -> None:
    """Recount interested_count for all campaigns from actual Call records."""
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


async def backfill() -> None:
    print("=" * 62)
    print("  MOTMVoice — Past Call Backfill")
    print("=" * 62)

    # Find calls needing work: missing recording OR pending outcome
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Call)
            .where(
                Call.status == CallStatus.COMPLETED,
                (Call.recording_url.is_(None)) | (Call.outcome == CallOutcome.PENDING),
            )
            .order_by(Call.started_at.desc())
            .limit(500)
        )
        calls = result.scalars().all()

    total = len(calls)
    if total == 0:
        print("\n✓ No calls need backfilling.\n")
        await _recount_campaign_stats()
        return

    print(f"\nFound {total} calls to process.\n")
    ok = failed = 0

    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=connector) as http:
        for idx, call in enumerate(calls, 1):
            phone = call.phone_number
            start = call.started_at
            date = start.date() if start else datetime.now(timezone.utc).date()
            needs_recording = not call.recording_url
            needs_outcome = call.outcome == CallOutcome.PENDING

            print(f"[{idx:>3}/{total}] {phone}  {start or 'unknown'}  recording={'✗' if needs_recording else '✓'}  outcome={'pending' if needs_outcome else call.outcome}")

            recording_url = call.recording_url

            # Step 1: Recording
            if needs_recording and settings.VOBIZ_AUTH_ID:
                print("         Recording  →", end=" ", flush=True)
                recording_url = await _find_recording(http, phone, date)
                print("✓ found" if recording_url else "✗ not found")

            # Steps 2-4: transcript + outcome (only if outcome is still pending)
            segments: list[dict] = []
            outcome = str(call.outcome)
            summary = call.summary or ""

            if needs_outcome and recording_url and settings.GROQ_API_KEY:
                print("         Download   →", end=" ", flush=True)
                audio = await _download_audio(http, recording_url)
                if audio:
                    print(f"✓ {len(audio)//1024} KB")
                    print("         Transcript →", end=" ", flush=True)
                    segments = await _transcribe(http, audio)
                    print(f"✓ {len(segments[0]['text'])} chars" if segments else "✗ empty")

                    if segments:
                        print("         Summary    →", end=" ", flush=True)
                        outcome, summary = await _classify(http, segments)
                        print(f"✓ {outcome}")
                else:
                    print("✗ failed")

            # Step 5: Save
            try:
                async with AsyncSessionLocal() as session:
                    async with session.begin():
                        updates: dict = {}
                        if recording_url and needs_recording:
                            updates["recording_url"] = recording_url
                        if outcome and outcome != "pending":
                            updates["outcome"] = outcome
                        if summary:
                            updates["summary"] = summary

                        if updates:
                            await session.execute(update(Call).where(Call.id == call.id).values(**updates))

                        if segments:
                            full_text = "\n".join(
                                f"{'CUSTOMER' if s['speaker'] == 'user' else 'AGENT'}: {s['text']}"
                                for s in segments
                            )
                            existing = (await session.execute(
                                select(CallTranscript).where(CallTranscript.call_id == call.id)
                            )).scalar_one_or_none()
                            if existing:
                                existing.segments = segments
                                existing.full_text = full_text
                            else:
                                session.add(CallTranscript(call_id=call.id, segments=segments, full_text=full_text))

                print("         Saved      → ✓\n")
                ok += 1
            except Exception as exc:
                print(f"         Save error → ✗ {exc}\n")
                failed += 1

            await asyncio.sleep(0.5)

    print("=" * 62)
    print(f"  Backfill done: ✓ {ok} processed  |  ✗ {failed} errors")
    print("=" * 62)

    # Always recount campaign interested_count from actual data
    await _recount_campaign_stats()


if __name__ == "__main__":
    asyncio.run(backfill())
