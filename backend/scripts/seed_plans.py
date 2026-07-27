#!/usr/bin/env python3
"""
seed_plans.py — Upsert the Free/Pro/Premium plan catalog.

Idempotent: re-running updates existing plans (matched by name) in place
rather than creating duplicates. Run inside the api container (or locally
with the backend venv active):
    python scripts/seed_plans.py
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
from app.models.agent import VoiceProvider
from app.models.plan import Plan

# name -> plan definition. features["allowed_voice_providers"] gates which
# VoiceProvider values app/core/plan_features.py permits on an AgentTemplate;
# features["voice_cloning"] gates POST /api/voice-cloning.
PLAN_DEFINITIONS = [
    dict(
        name="Free",
        price_minor=0,
        currency="INR",
        monthly_call_quota=200,
        max_concurrent_calls=1,
        credits_per_month=100,
        credit_price_cents=15,
        features={
            "allowed_voice_providers": [VoiceProvider.SARVAM.value],
            "voice_cloning": False,
        },
        is_active=True,
    ),
    dict(
        name="Pro",
        price_minor=299900,
        currency="INR",
        monthly_call_quota=5000,
        max_concurrent_calls=5,
        credits_per_month=2000,
        credit_price_cents=10,
        features={
            "allowed_voice_providers": [
                VoiceProvider.SARVAM.value,
                VoiceProvider.CARTESIA.value,
                VoiceProvider.DEEPGRAM.value,
                VoiceProvider.CHATTERBOX.value,
            ],
            "voice_cloning": False,
        },
        is_active=True,
    ),
    dict(
        name="Premium",
        price_minor=999900,
        currency="INR",
        monthly_call_quota=20000,
        max_concurrent_calls=20,
        credits_per_month=10000,
        credit_price_cents=8,
        features={
            "allowed_voice_providers": [
                VoiceProvider.SARVAM.value,
                VoiceProvider.CARTESIA.value,
                VoiceProvider.DEEPGRAM.value,
                VoiceProvider.CHATTERBOX.value,
                VoiceProvider.ELEVENLABS.value,
            ],
            "voice_cloning": True,
        },
        is_active=True,
    ),
]


async def main() -> None:
    async with AsyncSessionLocal() as session:
        for definition in PLAN_DEFINITIONS:
            existing = await session.scalar(select(Plan).where(Plan.name == definition["name"]))
            if existing:
                for field, value in definition.items():
                    setattr(existing, field, value)
                print(f"Updated plan {definition['name']!r} (id={existing.id}).")
            else:
                plan = Plan(**definition)
                session.add(plan)
                await session.flush()
                print(f"Created plan {definition['name']!r} (id={plan.id}).")
        await session.commit()


if __name__ == "__main__":
    asyncio.run(main())
