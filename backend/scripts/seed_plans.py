#!/usr/bin/env python3
"""
seed_plans.py — Upsert the Talkryn Plans catalog (Starter/Professional/
Enterprise/Business), deactivating any previously-seeded plan not in this
set (e.g. the old Free/Pro/Premium catalog) rather than deleting it, so any
org still assigned to an old plan keeps working untouched.

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
# features["voice_cloning"] gates POST /api/voice-cloning. discount_price_minor,
# is_custom_pricing, is_highlighted, and marketing_bullets drive the public
# pricing card (see app/api/plans.py) and are freely editable afterward from
# the SuperAdmin Plans page -- these are just the initial values.
BUSINESS_BULLETS = [
    "24/7 inbound call handling",
    "AI training & knowledge base",
    "Call recordings & transcripts",
    "AI summaries & sentiment analysis",
    "AI-powered outbound calls",
    "CSV & contact import",
    "AI script builder",
    "Auto-retry on unanswered calls",
    "Campaign analytics",
    "Schedule & launch campaigns anytime",
]

PLAN_DEFINITIONS = [
    dict(
        name="Starter",
        price_minor=499_900,
        currency="INR",
        monthly_call_quota=500,
        max_concurrent_calls=3,
        credits_per_month=500,
        credit_price_cents=15,
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
        discount_price_minor=None,
        is_custom_pricing=False,
        is_highlighted=False,
        marketing_bullets=[],
    ),
    dict(
        name="Professional",
        price_minor=1_499_900,
        currency="INR",
        monthly_call_quota=1600,
        max_concurrent_calls=10,
        credits_per_month=1600,
        credit_price_cents=10,
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
        discount_price_minor=None,
        is_custom_pricing=False,
        is_highlighted=True,
        marketing_bullets=[],
    ),
    dict(
        name="Enterprise",
        price_minor=2_899_900,
        currency="INR",
        monthly_call_quota=3200,
        max_concurrent_calls=25,
        credits_per_month=3200,
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
        discount_price_minor=None,
        is_custom_pricing=False,
        is_highlighted=False,
        marketing_bullets=[],
    ),
    dict(
        name="Business",
        # Sentinel only -- never shown, since is_custom_pricing=True makes
        # the pricing card render "Custom" instead. Kept large so this row
        # naturally sorts last in ORDER BY price_minor.
        price_minor=999_999_900,
        currency="INR",
        monthly_call_quota=0,
        max_concurrent_calls=50,
        credits_per_month=0,
        credit_price_cents=8,
        features={},  # unrestricted -- fail-open per app/core/plan_features.py
        is_active=True,
        discount_price_minor=None,
        is_custom_pricing=True,
        is_highlighted=False,
        marketing_bullets=BUSINESS_BULLETS,
    ),
]

_NEW_NAMES = {d["name"] for d in PLAN_DEFINITIONS}


async def main() -> None:
    async with AsyncSessionLocal() as session:
        existing_plans = (await session.scalars(select(Plan))).all()
        for plan in existing_plans:
            if plan.name not in _NEW_NAMES and plan.is_active:
                plan.is_active = False
                print(f"Deactivated old plan {plan.name!r} (id={plan.id}) -- superseded by Talkryn Plans.")

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
