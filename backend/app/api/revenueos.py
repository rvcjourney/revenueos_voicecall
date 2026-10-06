"""
app/api/revenueos.py — Routes RevenueOS Brain calls. Logic: app/integrations/revenueos.py.

  POST /api/integrations/revenueos/launch
      Account, phone number, company profile, agent, campaign, contacts and
      start, from one payload.
  GET  /api/integrations/revenueos/campaigns/{reference}?client_reference=…
      Where the campaign stands.
  GET  /api/integrations/revenueos/campaigns/{reference}/calls?client_reference=…
      Each call's outcome, summary and transcript; `since` returns only what changed.
  POST /api/integrations/revenueos/campaigns/{reference}/pause?client_reference=…

Authentication is the X-RevenueOS-Key header only — Brain is server code with
no login. Everything is off until settings turn it on:
  REVENUEOS_API_KEY             blank → every route here answers 503
  REVENUEOS_LAUNCH_ENABLED      off   → launch answers 503
  REVENUEOS_AUTO_START_ENABLED  off   → launch with auto_start=true answers 503,
                                        before anything is created
Reading results and pausing need only the key, so a running campaign can
always be stopped.
"""
from __future__ import annotations

import hmac
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import AuthenticationError
from app.database import get_db
from app.integrations import revenueos as service
from app.integrations.revenueos import LaunchIn

router = APIRouter()


async def require_revenueos_key(x_revenueos_key: str | None = Header(None)) -> None:
    if not settings.REVENUEOS_API_KEY:
        raise HTTPException(status_code=503, detail="The RevenueOS integration is not configured on this server.")
    if not x_revenueos_key or not hmac.compare_digest(
        x_revenueos_key.encode(), settings.REVENUEOS_API_KEY.encode()
    ):
        raise AuthenticationError("Missing or wrong X-RevenueOS-Key header.")


@router.post("/launch", dependencies=[Depends(require_revenueos_key)])
async def launch(body: LaunchIn, db: AsyncSession = Depends(get_db)):
    if not settings.REVENUEOS_LAUNCH_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="RevenueOS launch is switched off on this server (REVENUEOS_LAUNCH_ENABLED). Nothing was created.",
        )
    if body.auto_start and not settings.REVENUEOS_AUTO_START_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="Starting calls automatically is switched off on this server "
                   "(REVENUEOS_AUTO_START_ENABLED). Nothing was created. Send auto_start false "
                   "to store the campaign without starting it.",
        )
    return await service.launch(db, body)


@router.get("/campaigns/{reference}", dependencies=[Depends(require_revenueos_key)])
async def campaign_status(
    reference: str,
    client_reference: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    return await service.campaign_status(db, client_reference=client_reference, reference=reference)


@router.get("/campaigns/{reference}/calls", dependencies=[Depends(require_revenueos_key)])
async def campaign_calls(
    reference: str,
    client_reference: str = Query(...),
    since: datetime | None = Query(None),
    limit: int = Query(100, ge=1, le=200),
    include_transcript: bool = Query(True),
    db: AsyncSession = Depends(get_db),
):
    return await service.campaign_calls(
        db,
        client_reference=client_reference,
        reference=reference,
        since=since,
        limit=limit,
        include_transcript=include_transcript,
    )


@router.post("/campaigns/{reference}/pause", dependencies=[Depends(require_revenueos_key)])
async def pause_campaign(
    reference: str,
    client_reference: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    return await service.pause(db, client_reference=client_reference, reference=reference)
