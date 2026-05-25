from __future__ import annotations

import asyncio
import csv
import io
from datetime import datetime, timezone
from uuid import UUID

import pandas as pd
from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import TokenPayload, get_current_user
from app.core.exceptions import NotFoundError, ValidationError as AppValidationError, CampaignStateError
from app.database import get_db
from app.models.campaign import Campaign, CampaignContact, CampaignStatus, ContactStatus
from app.models.call import Call, CallOutcome
from app.schemas.campaign import (
    CampaignCreate,
    CampaignListResponse,
    CampaignOut,
    CampaignUpdate,
)
from app.workers.tasks.campaign import _run_campaign_async

router = APIRouter()


def _to_out(c: Campaign) -> CampaignOut:
    return CampaignOut(
        id=str(c.id),
        name=c.name,
        description=c.description,
        status=c.status,
        goal=c.goal,
        agent_template_id=str(c.agent_template_id),
        total_contacts=c.total_contacts,
        completed_calls=c.completed_calls,
        interested_count=c.interested_count,
        failed_count=c.failed_count,
        calling_window_start=str(c.calling_window_start),
        calling_window_end=str(c.calling_window_end),
        calling_days=c.calling_days,
        timezone=c.timezone,
        calls_per_minute=c.calls_per_minute,
        max_retries=c.max_retries,
        started_at=c.started_at,
        completed_at=c.completed_at,
        created_at=c.created_at,
    )


@router.get("", response_model=CampaignListResponse)
async def list_campaigns(
    status: str | None = Query(None),
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(Campaign).where(
        Campaign.org_id == token.org_id,
        Campaign.deleted_at.is_(None),
    )
    if status:
        q = q.where(Campaign.status == status)

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (await db.execute(q.order_by(Campaign.created_at.desc()))).scalars().all()
    return CampaignListResponse(items=[_to_out(r) for r in rows], total=total)


@router.post("", response_model=CampaignOut, status_code=201)
async def create_campaign(
    body: CampaignCreate,
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    campaign = Campaign(
        org_id=token.org_id,
        created_by_id=token.user_id,
        **body.model_dump(),
    )
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)
    return _to_out(campaign)


@router.get("/{campaign_id}", response_model=CampaignOut)
async def get_campaign(
    campaign_id: UUID,
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    campaign = await db.get(Campaign, campaign_id)
    if not campaign or campaign.org_id != token.org_id or campaign.deleted_at:
        raise NotFoundError("Campaign not found")
    return _to_out(campaign)


@router.patch("/{campaign_id}", response_model=CampaignOut)
async def update_campaign(
    campaign_id: UUID,
    body: CampaignUpdate,
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    campaign = await db.get(Campaign, campaign_id)
    if not campaign or campaign.org_id != token.org_id or campaign.deleted_at:
        raise NotFoundError("Campaign not found")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(campaign, field, value)

    await db.commit()
    await db.refresh(campaign)
    return _to_out(campaign)


@router.delete("/{campaign_id}", status_code=204)
async def delete_campaign(
    campaign_id: UUID,
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    campaign = await db.get(Campaign, campaign_id)
    if not campaign or campaign.org_id != token.org_id or campaign.deleted_at:
        raise NotFoundError("Campaign not found")

    campaign.deleted_at = datetime.now(timezone.utc)
    await db.commit()


@router.get("/{campaign_id}/contacts")
async def list_contacts(
    campaign_id: UUID,
    status: str | None = Query(None),
    limit: int = Query(200, le=1000),
    offset: int = Query(0),
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    campaign = await db.get(Campaign, campaign_id)
    if not campaign or campaign.org_id != token.org_id or campaign.deleted_at:
        raise NotFoundError("Campaign not found")

    q = select(CampaignContact).where(CampaignContact.campaign_id == campaign_id)
    if status:
        q = q.where(CampaignContact.status == status)

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (await db.execute(
        q.order_by(CampaignContact.created_at).limit(limit).offset(offset)
    )).scalars().all()

    return {
        "items": [
            {
                "id": str(c.id),
                "name": c.name,
                "phone": c.phone,
                "email": c.email,
                "company": c.company,
                "status": str(c.status),
                "attempt_count": c.attempt_count,
                "last_attempted_at": c.last_attempted_at.isoformat() if c.last_attempted_at else None,
            }
            for c in rows
        ],
        "total": total,
    }


@router.post("/{campaign_id}/contacts", status_code=201)
async def upload_contacts(
    campaign_id: UUID,
    file: UploadFile = File(...),
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    campaign = await db.get(Campaign, campaign_id)
    if not campaign or campaign.org_id != token.org_id or campaign.deleted_at:
        raise NotFoundError("Campaign not found")

    contents = await file.read()
    fname = (file.filename or "").lower()
    try:
        if fname.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(contents))
        else:
            df = pd.read_csv(io.BytesIO(contents))
    except Exception as exc:
        raise AppValidationError(f"Could not parse file: {exc}", errors=[])

    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]

    phone_col = next((c for c in df.columns if "phone" in c), None)
    if not phone_col:
        raise AppValidationError("File must have a column named 'phone' or 'phone_number'", errors=[])

    name_col = next((c for c in df.columns if c in ("name", "full_name", "contact_name")), None)
    email_col = next((c for c in df.columns if "email" in c), None)
    company_col = next((c for c in df.columns if "company" in c), None)

    skip_cols = {phone_col, name_col or "", email_col or "", company_col or ""}

    contacts = []
    for _, row in df.iterrows():
        raw_phone = str(row[phone_col]).strip()
        if not raw_phone or raw_phone in ("nan", "None", ""):
            continue

        # Normalise to E.164: strip spaces/dashes, add +91 if no country code
        phone = raw_phone.replace(" ", "").replace("-", "")
        if not phone.startswith("+"):
            phone = "+91" + phone.lstrip("0")

        name = str(row[name_col]).strip() if name_col and pd.notna(row.get(name_col)) else "Contact"
        email = str(row[email_col]).strip() if email_col and pd.notna(row.get(email_col)) else None
        company = str(row[company_col]).strip() if company_col and pd.notna(row.get(company_col)) else None

        custom = {
            c: str(row[c])
            for c in df.columns
            if c not in skip_cols and pd.notna(row.get(c))
        }

        contacts.append(CampaignContact(
            org_id=campaign.org_id,
            campaign_id=campaign.id,
            name=name,
            phone=phone,
            email=email,
            company=company,
            custom_fields=custom,
            status=ContactStatus.PENDING,
        ))

    if not contacts:
        raise AppValidationError("No valid contacts found in file", errors=[])

    db.add_all(contacts)
    await db.execute(
        update(Campaign)
        .where(Campaign.id == campaign_id)
        .values(total_contacts=len(contacts))
    )
    await db.commit()
    return {"count": len(contacts), "message": f"Uploaded {len(contacts)} contacts"}


@router.post("/{campaign_id}/launch", response_model=CampaignOut)
async def launch_campaign(
    campaign_id: UUID,
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    campaign = await db.get(Campaign, campaign_id)
    if not campaign or campaign.org_id != token.org_id or campaign.deleted_at:
        raise NotFoundError("Campaign not found")

    if campaign.status not in (CampaignStatus.DRAFT, CampaignStatus.PAUSED):
        raise CampaignStateError(f"Campaign is '{campaign.status}', only draft or paused can be launched")

    contact_count = await db.scalar(
        select(func.count()).where(
            CampaignContact.campaign_id == campaign_id,
            CampaignContact.status == ContactStatus.PENDING,
        )
    )
    if not contact_count:
        raise AppValidationError("Campaign has no pending contacts to call", errors=[])

    campaign.status = CampaignStatus.RUNNING
    campaign.started_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(campaign)

    # Run dispatcher as asyncio background task (no Celery needed for single-machine)
    from app.workers.tasks.campaign import _run_campaign_async
    asyncio.create_task(_run_campaign_async(str(campaign_id)))

    return _to_out(campaign)


@router.get("/{campaign_id}/export/interested")
async def export_interested_leads(
    campaign_id: UUID,
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download a CSV of all interested leads with their call summary."""
    campaign = await db.get(Campaign, campaign_id)
    if not campaign or campaign.org_id != token.org_id or campaign.deleted_at:
        raise NotFoundError("Campaign not found")

    rows = (await db.execute(
        select(Call)
        .where(
            Call.campaign_id == campaign_id,
            Call.outcome == CallOutcome.INTERESTED,
        )
        .order_by(Call.started_at.desc())
    )).scalars().all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Phone Number", "Call Date", "Duration (min)", "Summary"])
    for call in rows:
        date_str = call.started_at.strftime("%Y-%m-%d %H:%M") if call.started_at else ""
        duration = f"{round(call.duration_seconds / 60, 1)}" if call.duration_seconds else ""
        writer.writerow([call.phone_number, date_str, duration, call.summary or ""])

    buf.seek(0)
    filename = f"{campaign.name.replace(' ', '_')}_interested_leads.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{campaign_id}/export/no_answer")
async def export_no_answer_calls(
    campaign_id: UUID,
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download a CSV of all calls that were not answered."""
    campaign = await db.get(Campaign, campaign_id)
    if not campaign or campaign.org_id != token.org_id or campaign.deleted_at:
        raise NotFoundError("Campaign not found")

    rows = (await db.execute(
        select(Call)
        .where(
            Call.campaign_id == campaign_id,
            Call.outcome == CallOutcome.NO_ANSWER,
        )
        .order_by(Call.started_at.desc())
    )).scalars().all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Phone Number", "Call Date"])
    for call in rows:
        date_str = call.started_at.strftime("%Y-%m-%d %H:%M") if call.started_at else ""
        writer.writerow([call.phone_number, date_str])

    buf.seek(0)
    filename = f"{campaign.name.replace(' ', '_')}_no_answer.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{campaign_id}/pause", response_model=CampaignOut)
async def pause_campaign(
    campaign_id: UUID,
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    campaign = await db.get(Campaign, campaign_id)
    if not campaign or campaign.org_id != token.org_id or campaign.deleted_at:
        raise NotFoundError("Campaign not found")

    if campaign.status != CampaignStatus.RUNNING:
        raise CampaignStateError("Only a running campaign can be paused")

    campaign.status = CampaignStatus.PAUSED
    await db.commit()
    await db.refresh(campaign)
    return _to_out(campaign)
