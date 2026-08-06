#!/usr/bin/env python3
"""
find_voice_id.py — Locate which org/agent/cloned-voice row references a given
ElevenLabs voice_id. One-off diagnostic for chasing "voice_id_does_not_exist"
TTS errors back to the DB row that's pointing at a stale/deleted voice.

Run:
    python scripts/find_voice_id.py <voice_id>
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
from app.database import AsyncSessionLocal
from app.models.agent import AgentTemplate
from app.models.cloned_voice import ClonedVoice
from app.models.user import Organization


async def main(voice_id: str) -> None:
    async with AsyncSessionLocal() as session:
        print(f"\n━━━ AgentTemplate rows with voice_id={voice_id} ━━━")
        rows = (await session.execute(
            select(AgentTemplate).where(AgentTemplate.voice_id == voice_id)
        )).scalars().all()
        if not rows:
            print("  none")
        for a in rows:
            org = await session.get(Organization, a.org_id)
            print(f"  agent_id={a.id} name={a.name!r} org={org.name if org else a.org_id} provider={a.voice_provider} deleted_at={a.deleted_at}")

        print(f"\n━━━ ClonedVoice rows with elevenlabs_voice_id={voice_id} ━━━")
        rows = (await session.execute(
            select(ClonedVoice).where(ClonedVoice.elevenlabs_voice_id == voice_id)
        )).scalars().all()
        if not rows:
            print("  none")
        for c in rows:
            org = await session.get(Organization, c.org_id)
            print(f"  cloned_voice_id={c.id} org={org.name if org else c.org_id} status={c.status} created_at={c.created_at}")
        print()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python scripts/find_voice_id.py <voice_id>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
