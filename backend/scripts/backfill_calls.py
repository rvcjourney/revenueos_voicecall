#!/usr/bin/env python3
"""
backfill_calls.py — Backfill recording, transcript, and summary for all past calls.

Run once from the backend directory:
    cd "C:\\Users\\p\\Desktop\\My AI Voice Call Agent\\backend"
    python scripts/backfill_calls.py

For each completed call that still shows outcome=pending, this script:
  1. Queries Vobiz Recording API  → gets recording URL
  2. Downloads audio from Vobiz   → raw bytes (auth required)
  3. Sends audio to Groq Whisper  → full transcript
  4. Sends transcript to Groq LLM → outcome + summary
  5. Saves all to the database
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── Bootstrap: make app imports work ──────────────────────────────────────────
_backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(_backend_dir))
os.chdir(_backend_dir)

from dotenv import load_dotenv
load_dotenv(_backend_dir / ".env")

import aiohttp
from sqlalchemy import select, update

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.call import Call, CallOutcome, CallStatus, CallTranscript

# ── Vobiz helpers ──────────────────────────────────────────────────────────────

VOBIZ_BASE = "https://api.vobiz.ai/api/v1"


def _vobiz_hdrs() -> dict:
    return {
        "X-Auth-ID": settings.VOBIZ_AUTH_ID,
        "X-Auth-Token": settings.VOBIZ_AUTH_TOKEN,
        "Content-Type": "application/json",
    }


async def _find_recording(
    http: aiohttp.ClientSession,
    phone: str,
    call_date: "datetime.date",
) -> str | None:
    """
    Find the recording URL for an outbound call to `phone` on `call_date`.
    Strategy 1: search Recording API directly by to_number (fastest).
    Strategy 2: CDR (destination_number + sip_call_id) → Recording API.
    """
    norm = phone.lstrip("+")

    # ── Strategy 1: Recording API has to_number — search all pages ────────────
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
                    rec_url = r.get("recording_url") or ""
                    if rec_url:
                        return rec_url

            # Stop paginating if we've gone past the call date by >2 days
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
        print(f"    ! Recording direct search error: {exc}")

    # ── Strategy 2: CDR → sip_call_id → Recording API ─────────────────────────
    date_str = call_date.strftime("%Y-%m-%d")
    next_str = (call_date + timedelta(days=1)).strftime("%Y-%m-%d")

    endpoints = [
        (f"{VOBIZ_BASE}/Account/{settings.VOBIZ_AUTH_ID}/cdr",
         {"start_date": date_str, "end_date": next_str, "call_direction": "outbound", "per_page": "100"}),
        (f"{VOBIZ_BASE}/Account/{settings.VOBIZ_AUTH_ID}/cdr/recent", {}),
    ]

    for url, params in endpoints:
        try:
            async with http.get(url, headers=_vobiz_hdrs(), params=params,
                                timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    continue
                data = await resp.json(content_type=None)

            records = data.get("data") or data.get("objects") or data.get("calls") or []

            for rec in records:
                to_num = (
                    rec.get("destination_number")
                    or rec.get("to_number")
                    or rec.get("to")
                    or ""
                ).lstrip("+")
                if norm[-10:] != to_num[-10:]:
                    continue

                # sip_call_id matches call_uuid in the Recording API
                call_uuid = rec.get("sip_call_id") or rec.get("call_uuid") or rec.get("uuid") or ""
                if not call_uuid:
                    continue

                async with http.get(
                    f"{VOBIZ_BASE}/Account/{settings.VOBIZ_AUTH_ID}/Recording/",
                    headers=_vobiz_hdrs(),
                    params={"call_uuid": call_uuid},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as r2:
                    if r2.status != 200:
                        continue
                    rdata = await r2.json(content_type=None)

                recs = rdata.get("objects") or rdata.get("recordings") or []
                for r in recs:
                    rec_url = r.get("recording_url") or r.get("record_url") or r.get("url") or ""
                    if rec_url:
                        return rec_url

        except Exception as exc:
            print(f"    ! Vobiz CDR error: {exc}")

    return None


async def _download_audio(http: aiohttp.ClientSession, recording_url: str) -> bytes | None:
    """Download Vobiz recording — requires Vobiz auth headers."""
    try:
        async with http.get(
            recording_url,
            headers={
                "X-Auth-ID": settings.VOBIZ_AUTH_ID,
                "X-Auth-Token": settings.VOBIZ_AUTH_TOKEN,
            },
            timeout=aiohttp.ClientTimeout(total=120),
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                print(f"    ! Audio download error {resp.status}: {body[:100]}")
                return None
            return await resp.read()
    except Exception as exc:
        print(f"    ! Audio download exception: {exc}")
        return None


# ── Groq helpers ───────────────────────────────────────────────────────────────

async def _transcribe(http: aiohttp.ClientSession, audio_bytes: bytes) -> list[dict]:
    """
    Transcribe audio bytes with Groq Whisper.
    Returns [{speaker: "unknown", text: str}].
    """
    try:
        form = aiohttp.FormData()
        form.add_field(
            "file",
            audio_bytes,
            filename="recording.wav",
            content_type="audio/wav",
        )
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
                body = await resp.text()
                print(f"    ! Groq Whisper error {resp.status}: {body[:120]}")
                return []
            data = await resp.json()

        text = (data.get("text") or "").strip()
        if not text:
            return []
        return [{"speaker": "unknown", "text": text}]

    except Exception as exc:
        print(f"    ! Transcription exception: {exc}")
        return []


_VALID_OUTCOMES = {"interested", "not_interested", "callback_requested", "wrong_number", "do_not_call"}


async def _classify(http: aiohttp.ClientSession, segments: list[dict]) -> tuple[str, str]:
    """
    Send transcript to Groq llama-3.3-70b and classify the outcome.
    Returns (outcome, summary).
    """
    if not segments:
        return "not_interested", ""

    transcript_text = "\n".join(
        f"{'CUSTOMER' if s['speaker'] == 'user' else 'AGENT'}: {s['text']}"
        for s in segments
    )

    try:
        async with http.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
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
                            "  interested         - customer asked for catalogue, pricing, or showed clear interest\n"
                            "  not_interested     - customer declined or showed no interest\n"
                            "  callback_requested - customer asked to be called back later\n"
                            "  wrong_number       - wrong person or wrong business\n"
                            "  do_not_call        - customer explicitly said do not call again\n"
                            "summary: 2-3 clear English sentences describing what happened in this call."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Call transcript:\n{transcript_text}",
                    },
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
        print(f"    ! Groq error: {exc}")
        return "not_interested", ""


# ── Main backfill ──────────────────────────────────────────────────────────────

async def backfill() -> None:
    print("=" * 62)
    print("  MOTMVoice — Past Call Backfill")
    print("=" * 62)

    if not settings.VOBIZ_AUTH_ID:
        print("\n⚠  VOBIZ_AUTH_ID not set — recording fetch will be skipped.")
    if not settings.GROQ_API_KEY:
        print("\n⚠  GROQ_API_KEY not set — transcription and summary will be skipped.")

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Call)
            .where(
                Call.status == CallStatus.COMPLETED,
                Call.outcome == CallOutcome.PENDING,
            )
            .order_by(Call.started_at.desc())
            .limit(500)
        )
        calls = result.scalars().all()

    total = len(calls)
    if total == 0:
        print("\n✓ Nothing to backfill — all completed calls already have outcomes set.\n")
        return

    print(f"\nFound {total} calls with outcome=pending to process.\n")

    ok = failed = 0

    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=connector) as http:
        for idx, call in enumerate(calls, 1):
            phone = call.phone_number
            start = call.started_at
            date  = start.date() if start else datetime.now(timezone.utc).date()

            print(f"[{idx:>3}/{total}] {phone}  |  {start or 'unknown time'}")

            recording_url = call.recording_url

            # ── Step 1: Recording URL ──────────────────────────────────────
            if not recording_url and settings.VOBIZ_AUTH_ID:
                print("         Recording  → fetching from Vobiz...", end=" ", flush=True)
                recording_url = await _find_recording(http, phone, date)
                print("✓ found" if recording_url else "✗ not found")
            elif recording_url:
                print("         Recording  → already saved")
            else:
                print("         Recording  → skipped (no Vobiz credentials)")

            # ── Step 2: Download audio ─────────────────────────────────────
            audio_bytes: bytes | None = None
            if recording_url and settings.GROQ_API_KEY:
                print("         Download   → downloading audio...", end=" ", flush=True)
                audio_bytes = await _download_audio(http, recording_url)
                if audio_bytes:
                    print(f"✓ {len(audio_bytes) // 1024} KB")
                else:
                    print("✗ failed")

            # ── Step 3: Transcription ──────────────────────────────────────
            segments: list[dict] = []
            if audio_bytes:
                print("         Transcript → transcribing with Groq Whisper...", end=" ", flush=True)
                segments = await _transcribe(http, audio_bytes)
                print(f"✓ {len(segments[0]['text'])} chars" if segments else "✗ empty")
            elif not recording_url:
                print("         Transcript → skipped (no recording)")
            else:
                print("         Transcript → skipped (no audio / no Groq key)")

            # ── Step 4: Classify + Summarize ───────────────────────────────
            outcome = str(call.outcome)
            summary = call.summary or ""

            if segments and settings.GROQ_API_KEY:
                print("         Summary    → classifying with Groq...", end=" ", flush=True)
                outcome, summary = await _classify(http, segments)
                print(f"✓ {outcome}")
                if summary:
                    short = summary[:75] + "…" if len(summary) > 75 else summary
                    print(f"                      \"{short}\"")
            else:
                print("         Summary    → skipped (no transcript)")

            # ── Step 5: Save to database ───────────────────────────────────
            try:
                async with AsyncSessionLocal() as session:
                    async with session.begin():
                        updates: dict = {}
                        if recording_url and not call.recording_url:
                            updates["recording_url"] = recording_url
                        if outcome and outcome != "pending":
                            updates["outcome"] = outcome
                        if summary:
                            updates["summary"] = summary

                        if updates:
                            await session.execute(
                                update(Call).where(Call.id == call.id).values(**updates)
                            )

                        if segments:
                            full_text = "\n".join(
                                f"{'CUSTOMER' if s['speaker'] == 'user' else 'AGENT'}: {s['text']}"
                                for s in segments
                            )
                            existing = (
                                await session.execute(
                                    select(CallTranscript).where(CallTranscript.call_id == call.id)
                                )
                            ).scalar_one_or_none()

                            if existing:
                                existing.segments = segments
                                existing.full_text = full_text
                            else:
                                session.add(
                                    CallTranscript(
                                        call_id=call.id,
                                        segments=segments,
                                        full_text=full_text,
                                    )
                                )
                print("         Saved      → ✓\n")
                ok += 1
            except Exception as exc:
                print(f"         Save error → ✗ {exc}\n")
                failed += 1

            await asyncio.sleep(1.0)

    print("=" * 62)
    print(f"  Done!  ✓ {ok} processed  |  ✗ {failed} errors")
    print("=" * 62)
    print()


if __name__ == "__main__":
    asyncio.run(backfill())
