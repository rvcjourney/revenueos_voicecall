#!/usr/bin/env python3
"""
backfill_leads.py — build the lead CRM from calls made before it existed.

Run once inside the api container on the VPS (safe to re-run: calls already
on a lead's timeline are skipped):
    docker compose run --rm api python scripts/backfill_leads.py
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

from sqlalchemy import select

from app.database import AsyncSessionLocal, dispose_engine
from app.models.call import Call
from app.models.lead import LeadActivity, LeadActivityType
from app.services.leads import upsert_from_call

BATCH = 200


async def main() -> None:
    async with AsyncSessionLocal() as db:
        done = set((await db.execute(
            select(LeadActivity.payload["call_id"].astext).where(LeadActivity.type == LeadActivityType.CALL)
        )).scalars().all())
        call_ids = (await db.execute(
            select(Call.id).where(Call.reported_at.is_not(None), Call.campaign_id.is_not(None))
            .order_by(Call.created_at)  # oldest first, so the latest call ends up as the lead's "last call"
        )).scalars().all()
        todo = [cid for cid in call_ids if str(cid) not in done]
        print(f"{len(call_ids)} reported campaign calls, {len(todo)} not on a lead yet")

        for i, cid in enumerate(todo, 1):
            call = await db.get(Call, cid)
            await upsert_from_call(db, call, str(call.outcome), call.summary, call.extracted_data)
            if i % BATCH == 0:
                await db.commit()
                print(f"  {i}/{len(todo)}")
        await db.commit()
    await dispose_engine()  # close pooled connections before this event loop ends
    print("done")


if __name__ == "__main__":
    asyncio.run(main())
