"""
app/api/usage.py — Read-only usage endpoints for the frontend.

GET /concurrency exposes the org's current plan-based call-slot usage
(app/core/concurrency.py) so the UI can show "in use / max" and how many
contacts are currently queued waiting for capacity.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.concurrency import get_current_usage
from app.core.deps import TokenPayload, get_current_user
from app.database import get_db

router = APIRouter()


@router.get("/concurrency")
async def get_concurrency_usage(
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Current org-level concurrent-call usage: {in_use, max, queued}."""
    return await get_current_usage(db, token.org_id)
