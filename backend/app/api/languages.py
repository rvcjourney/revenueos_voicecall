"""The languages and voices calls can use (from app/core/pipelines.py), so the
app never hard-codes either list. Customer-safe: no vendor or model names."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import pipelines
from app.core.deps import TokenPayload, get_current_user
from app.database import get_db
from app.models.user import Organization

router = APIRouter()


@router.get("")
async def list_languages(
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    settings = await pipelines.get_owner_settings(db)
    org = await db.get(Organization, token.org_id)
    return {
        "languages": pipelines.languages_for(settings),
        "cloning_allowed": bool(org and org.sarvam_cloning_allowed),
    }
