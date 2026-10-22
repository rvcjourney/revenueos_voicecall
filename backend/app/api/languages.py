"""Calling engines and the languages/voices valid on each (from app/core/pipelines.py),
so the app never hard-codes either list. Customer-safe: no vendor or model names."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import pipelines
from app.core.deps import TokenPayload, get_current_user
from app.database import get_db
from app.models.user import Organization

router = APIRouter()


@router.get("")
async def list_languages(
    pipeline: Literal["standard", "sarvam"] = "standard",
    _: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    settings = await pipelines.get_owner_settings(db)
    return {"pipeline": pipeline, "languages": pipelines.languages_for(pipeline, settings)}


@router.get("/engines")
async def list_engines(
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Engines this org may pick. Only "standard" unless the owner enabled the
    second engine for this org (and hasn't switched it off platform-wide)."""
    org = await db.get(Organization, token.org_id)
    settings = await pipelines.get_owner_settings(db)
    sarvam_on = bool(org and org.sarvam_pipeline_enabled and settings.global_enabled)
    engines = [pipelines.STANDARD] + ([pipelines.SARVAM] if sarvam_on else [])
    return {
        "engines": [{"value": e, "label": pipelines.PIPELINE_LABELS[e]} for e in engines],
        "default_pipeline": org.default_pipeline if sarvam_on and org else pipelines.STANDARD,
        "cloning_allowed": bool(sarvam_on and org.sarvam_cloning_allowed),
    }
