"""
app/core/plan_features.py — Plan-based feature gating for premium voice features.

Only enforces a restriction when the org has BOTH:
  1. an active Subscription pointing at a Plan, AND
  2. that Plan's `features` JSON explicitly sets the relevant key.

Orgs with no subscription, or plans whose `features` don't mention a given key
at all, are treated as unrestricted. This mirrors how app/core/concurrency.py
already treats orgs without plan data (falls back to a generous default
rather than blocking) — seeding the new Free/Pro/Premium plans must not
retroactively lock out any existing org/plan that predates this gating scheme.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import PermissionDeniedError
from app.models.agent import VoiceProvider
from app.models.cloned_voice import ClonedVoice
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import Organization


async def _active_plan(db: AsyncSession, org_id: UUID) -> Plan | None:
    sub = await db.scalar(
        select(Subscription).where(
            Subscription.org_id == org_id,
            Subscription.deleted_at.is_(None),
        )
    )
    if not sub:
        return None
    return await db.get(Plan, sub.plan_id)


async def is_voice_provider_allowed(db: AsyncSession, org_id: UUID, voice_provider: str) -> bool:
    """ElevenLabs additionally requires Organization.elevenlabs_enabled (a
    platform-level kill switch independent of the plan — see app/models/user.py)."""
    if voice_provider == VoiceProvider.ELEVENLABS:
        org = await db.get(Organization, org_id)
        if org is not None and not org.elevenlabs_enabled:
            return False

    plan = await _active_plan(db, org_id)
    if plan is None:
        return True
    allowed = plan.features.get("allowed_voice_providers")
    if allowed is None:
        return True
    return voice_provider in allowed


async def is_voice_cloning_allowed(db: AsyncSession, org_id: UUID) -> bool:
    plan = await _active_plan(db, org_id)
    if plan is None:
        return True
    if "voice_cloning" not in plan.features:
        return True
    return bool(plan.features["voice_cloning"])


async def check_agent_voice_settings(
    db: AsyncSession, org_id: UUID, *, voice_provider: str, voice_id: str
) -> None:
    """
    Raise PermissionDeniedError if this org's plan doesn't allow the given
    voice_provider, or if voice_id references another org's cloned voice, or
    if it references a cloned voice while the org's plan doesn't allow cloning.
    Called from app/api/agents.py on agent template create/update.
    """
    if not await is_voice_provider_allowed(db, org_id, voice_provider):
        raise PermissionDeniedError(
            f"Your plan does not include the '{voice_provider}' voice provider. Upgrade to use it."
        )

    if voice_provider == VoiceProvider.ELEVENLABS and voice_id:
        cloned = await db.scalar(
            select(ClonedVoice).where(
                ClonedVoice.elevenlabs_voice_id == voice_id,
                ClonedVoice.deleted_at.is_(None),
            )
        )
        if cloned is not None and cloned.org_id != org_id:
            raise PermissionDeniedError("This cloned voice belongs to a different organization")
        if cloned is not None and not await is_voice_cloning_allowed(db, org_id):
            raise PermissionDeniedError(
                "Your plan does not include voice cloning. Upgrade to Premium to use this voice."
            )
