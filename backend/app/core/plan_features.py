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

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import PermissionDeniedError
from app.models.cloned_voice import ClonedVoice
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.voice_clone_request import VoiceCloneRequest

# Flat platform-wide cap, not plan-based -- cloned voices are a
# limited/costly resource per org regardless of plan tier. An org that wants
# a different voice once at the cap must delete an existing one first
# (DELETE /api/voice-cloning/{id}) to free a slot before submitting a new one.
MAX_CLONED_VOICES_PER_ORG = 2


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


async def is_voice_cloning_allowed(db: AsyncSession, org_id: UUID) -> bool:
    plan = await _active_plan(db, org_id)
    if plan is None:
        return True
    if "voice_cloning" not in plan.features:
        return True
    return bool(plan.features["voice_cloning"])


async def count_org_voice_clone_slots_used(db: AsyncSession, org_id: UUID) -> int:
    """
    Active ClonedVoice rows + still-pending VoiceCloneRequest rows. A pending
    request will become a ClonedVoice if approved, so it must count against
    the cap too -- otherwise an org could queue up unlimited pending requests
    and have them all approved at once. Rejected requests never count (they
    never became, and never will become, a real voice).
    """
    # Only Sarvam voices count: older ElevenLabs clones are unusable and hidden.
    active = await db.scalar(
        select(func.count(ClonedVoice.id)).where(
            ClonedVoice.org_id == org_id, ClonedVoice.provider == "sarvam", ClonedVoice.deleted_at.is_(None)
        )
    )
    pending = await db.scalar(
        select(func.count(VoiceCloneRequest.id)).where(
            VoiceCloneRequest.org_id == org_id, VoiceCloneRequest.provider == "sarvam",
            VoiceCloneRequest.status == "pending",
        )
    )
    return (active or 0) + (pending or 0)


async def has_voice_clone_capacity(db: AsyncSession, org_id: UUID) -> bool:
    return await count_org_voice_clone_slots_used(db, org_id) < MAX_CLONED_VOICES_PER_ORG


async def check_voice_choice(db: AsyncSession, org_id: UUID, *, language: str, voice_id: str | None) -> None:
    """Validate an agent's or campaign's language + voice: a cloned voice must be
    this org's own (and the plan must allow cloning); a stock voice must exist in
    that language. Messages are customer-safe (no vendor/model names)."""
    from app.core import pipelines
    from app.core.exceptions import ValidationError as AppValidationError

    cloned = None
    if voice_id:
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
        if cloned is not None and cloned.provider != pipelines.SARVAM:
            raise AppValidationError("This cloned voice is no longer supported. Pick another voice.", errors=[])

    settings = await pipelines.get_owner_settings(db)
    try:
        pipelines.validate(language, voice_id, settings, cloned=cloned is not None)
    except pipelines.PipelineValidationError as exc:
        raise AppValidationError(str(exc), errors=[]) from exc
