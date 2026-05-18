#!/usr/bin/env python3
"""
db_check.py — Quick database diagnostic for calls and transcripts.

Run inside the api container:
    docker compose exec api python scripts/db_check.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

_backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(_backend_dir))
os.chdir(_backend_dir)

from dotenv import load_dotenv
load_dotenv(_backend_dir / ".env")

from sqlalchemy import func, select, text
from app.database import AsyncSessionLocal
from app.models.call import Call, CallOutcome, CallStatus, CallTranscript
from app.models.campaign import Campaign


async def main() -> None:
    async with AsyncSessionLocal() as session:

        # ── 1. Overall call counts ────────────────────────────────────────────
        print("\n━━━ CALLS BY STATUS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        rows = (await session.execute(
            select(Call.status, func.count(Call.id))
            .group_by(Call.status)
            .order_by(func.count(Call.id).desc())
        )).all()
        for status, count in rows:
            print(f"  {status:<20} {count}")

        # ── 2. Outcome breakdown (completed calls only) ───────────────────────
        print("\n━━━ OUTCOMES (completed calls) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        rows = (await session.execute(
            select(Call.outcome, func.count(Call.id))
            .where(Call.status == CallStatus.COMPLETED)
            .group_by(Call.outcome)
            .order_by(func.count(Call.id).desc())
        )).all()
        for outcome, count in rows:
            print(f"  {outcome:<25} {count}")

        # ── 3. Transcript coverage ────────────────────────────────────────────
        print("\n━━━ TRANSCRIPT COVERAGE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        total_completed = await session.scalar(
            select(func.count(Call.id)).where(Call.status == CallStatus.COMPLETED)
        )
        with_transcript = await session.scalar(
            select(func.count(Call.id))
            .join(CallTranscript, CallTranscript.call_id == Call.id)
            .where(Call.status == CallStatus.COMPLETED)
        )
        with_fulltext = await session.scalar(
            select(func.count(Call.id))
            .join(CallTranscript, CallTranscript.call_id == Call.id)
            .where(
                Call.status == CallStatus.COMPLETED,
                CallTranscript.full_text.isnot(None),
                CallTranscript.full_text != "",
            )
        )
        with_segments = await session.scalar(
            select(func.count(Call.id))
            .join(CallTranscript, CallTranscript.call_id == Call.id)
            .where(
                Call.status == CallStatus.COMPLETED,
                CallTranscript.segments != text("'[]'::jsonb"),
            )
        )
        print(f"  Total completed calls  : {total_completed}")
        print(f"  Have any transcript    : {with_transcript}")
        print(f"  Have full_text         : {with_fulltext}")
        print(f"  Have segments (JSON)   : {with_segments}")
        print(f"  No transcript at all   : {(total_completed or 0) - (with_transcript or 0)}")

        # ── 4. Last 10 calls with transcript status ───────────────────────────
        print("\n━━━ LAST 10 COMPLETED CALLS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"  {'phone':<16} {'outcome':<20} {'summary?':<10} {'transcript?':<12} {'full_text?'}")
        calls = (await session.execute(
            select(Call)
            .where(Call.status == CallStatus.COMPLETED)
            .order_by(Call.started_at.desc())
            .limit(10)
        )).scalars().all()

        for call in calls:
            t = (await session.execute(
                select(CallTranscript).where(CallTranscript.call_id == call.id)
            )).scalar_one_or_none()
            has_transcript = "yes" if t else "no"
            has_fulltext = "yes" if (t and t.full_text) else "no"
            has_summary = "yes" if call.summary else "no"
            print(f"  {call.phone_number:<16} {str(call.outcome):<20} {has_summary:<10} {has_transcript:<12} {has_fulltext}")

        # ── 5. Campaign stats ─────────────────────────────────────────────────
        print("\n━━━ CAMPAIGN STATS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"  {'name':<30} {'status':<12} {'interested_count'}")
        camps = (await session.execute(select(Campaign))).scalars().all()
        for c in camps:
            actual = await session.scalar(
                select(func.count(Call.id)).where(
                    Call.campaign_id == c.id,
                    Call.outcome == CallOutcome.INTERESTED,
                )
            )
            mismatch = " ← MISMATCH" if (actual or 0) != (c.interested_count or 0) else ""
            print(f"  {c.name:<30} {c.status:<12} stored={c.interested_count}  actual={actual}{mismatch}")

        print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")


if __name__ == "__main__":
    asyncio.run(main())
