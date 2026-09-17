from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from uuid import UUID

import pandas as pd
from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.concurrency import get_current_usage
from app.core.deps import TokenPayload, get_current_user
from app.core.exceptions import (
    NotFoundError,
    PermissionDeniedError,
    ValidationError as AppValidationError,
    CampaignStateError,
    QuotaExceededError,
)
from app.database import get_db
from app.models.campaign import Campaign, CampaignContact, CampaignStatus, ContactStatus
from app.models.call import Call, CallOutcome
from app.models.sip import SipTrunk, UserSipTrunk
from app.models.user import Organization, User
from app.schemas.campaign import (
    CampaignCreate,
    CampaignListResponse,
    CampaignOut,
    CampaignUpdate,
)
from app.workers.tasks.campaign import run_campaign

router = APIRouter()


def _to_out(c: Campaign, created_by_name: str | None = None) -> CampaignOut:
    return CampaignOut(
        id=str(c.id),
        name=c.name,
        description=c.description,
        notes=c.notes,
        status=c.status,
        goal=c.goal,
        folder_id=str(c.folder_id) if c.folder_id else None,
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
        start_time=c.start_time,
        end_time=c.end_time,
        started_at=c.started_at,
        completed_at=c.completed_at,
        created_at=c.created_at,
        created_by_name=created_by_name,
        is_prime=c.is_prime,
    )


@router.get("", response_model=CampaignListResponse)
async def list_campaigns(
    status: str | None = Query(None),
    folder_id: str | None = Query(None),
    is_prime: bool | None = Query(None),
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(Campaign).where(
        Campaign.org_id == token.org_id,
        Campaign.deleted_at.is_(None),
    )
    # Members see only their own campaigns; admins see all
    if token.role != "admin":
        q = q.where(Campaign.created_by_id == token.user_id)
    if status:
        q = q.where(Campaign.status == status)
    if is_prime is not None:
        q = q.where(Campaign.is_prime.is_(is_prime))
    if folder_id == "none":
        q = q.where(Campaign.folder_id.is_(None))
    elif folder_id:
        q = q.where(Campaign.folder_id == UUID(folder_id))

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (await db.execute(q.order_by(Campaign.created_at.desc()))).scalars().all()

    # Batch-load creator names in one query
    user_ids = {c.created_by_id for c in rows if c.created_by_id}
    name_map: dict[str, str] = {}
    if user_ids:
        users = (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()
        name_map = {str(u.id): u.full_name for u in users}

    return CampaignListResponse(
        items=[_to_out(r, name_map.get(str(r.created_by_id))) for r in rows],
        total=total,
    )


@router.post("", response_model=CampaignOut, status_code=201)
async def create_campaign(
    body: CampaignCreate,
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Members must have approved access to the selected AI Agent
    if token.role != "admin":
        from app.models.agent_access import AgentAccessRequest
        access = await db.scalar(
            select(AgentAccessRequest).where(
                AgentAccessRequest.agent_id == body.agent_template_id,
                AgentAccessRequest.user_id == token.user_id,
                AgentAccessRequest.status == "approved",
            )
        )
        if not access:
            raise AppValidationError(
                "You don't have access to this AI Agent. "
                "Request access from the AI Agents page and wait for admin approval.",
                errors=[],
            )

    # Validate the chosen phone number is assigned to this user (non-admin)
    if body.sip_trunk_id and token.role != "admin":
        trunk = await db.get(SipTrunk, body.sip_trunk_id)
        if not trunk or trunk.org_id != token.org_id or trunk.deleted_at or not trunk.is_active:
            raise AppValidationError("Selected phone number not found or inactive", errors=[])
        assignment = await db.scalar(
            select(UserSipTrunk).where(
                UserSipTrunk.user_id == token.user_id,
                UserSipTrunk.trunk_id == body.sip_trunk_id,
            )
        )
        if not assignment:
            raise AppValidationError(
                "This phone number is not assigned to you. Ask your admin to assign it.",
                errors=[],
            )

    campaign = Campaign(
        org_id=token.org_id,
        created_by_id=token.user_id,
        **body.model_dump(),
    )
    # Auto-schedule if start_time is in the future
    if campaign.start_time and campaign.start_time > datetime.now(timezone.utc):
        campaign.status = CampaignStatus.SCHEDULED
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)
    return _to_out(campaign)


def _check_campaign_access(campaign: Campaign, token: TokenPayload) -> None:
    """Raise NotFoundError if this user cannot access the campaign."""
    if not campaign or campaign.org_id != token.org_id or campaign.deleted_at:
        raise NotFoundError("Campaign not found")
    if token.role != "admin" and str(campaign.created_by_id) != str(token.user_id):
        raise NotFoundError("Campaign not found")


@router.get("/{campaign_id}", response_model=CampaignOut)
async def get_campaign(
    campaign_id: UUID,
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    campaign = await db.get(Campaign, campaign_id)
    _check_campaign_access(campaign, token)
    creator = await db.get(User, campaign.created_by_id) if campaign.created_by_id else None
    return _to_out(campaign, creator.full_name if creator else None)


@router.patch("/{campaign_id}", response_model=CampaignOut)
async def update_campaign(
    campaign_id: UUID,
    body: CampaignUpdate,
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    campaign = await db.get(Campaign, campaign_id)
    _check_campaign_access(campaign, token)

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
    _check_campaign_access(campaign, token)

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
                "custom_fields": c.custom_fields or {},
                "generated_system_prompt": c.generated_system_prompt,
                "generated_welcome_message": c.generated_welcome_message,
                "prompt_generated_at": c.prompt_generated_at.isoformat() if c.prompt_generated_at else None,
                "prompt_error": c.prompt_error,
            }
            for c in rows
        ],
        "total": total,
    }


# Header names (after lowercase + spaces→"_") recognised as the contact's name
_NAME_COLUMNS = ("name", "full_name", "contact_name", "first_name", "customer_name", "client_name")
# Recognised as the phone column only when no header contains "phone"
_PHONE_FALLBACK_COLUMNS = (
    "contact", "contact_no", "contact_number", "mobile", "mobile_no", "mobile_number",
    "number", "cell", "whatsapp", "whatsapp_number",
)


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
    except Exception:
        raise AppValidationError(
            "Could not parse the uploaded file — ensure it is a valid CSV or Excel (.xlsx) file",
            errors=[],
        )

    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]

    name_col = next((c for c in df.columns if c in _NAME_COLUMNS), None)
    phone_col = next((c for c in df.columns if "phone" in c), None) or next(
        (c for c in df.columns if c in _PHONE_FALLBACK_COLUMNS and c != name_col), None
    )
    if not phone_col:
        raise AppValidationError(
            "File must have a phone column (e.g. 'phone', 'mobile' or 'contact')", errors=[]
        )

    email_col = next((c for c in df.columns if "email" in c), None)
    company_col = next((c for c in df.columns if "company" in c), None)

    skip_cols = {phone_col, name_col or "", email_col or "", company_col or ""}

    contacts = []
    for _, row in df.iterrows():
        phone_val = row[phone_col]
        if pd.isna(phone_val) if isinstance(phone_val, float) else phone_val is None:
            continue
        # Pandas reads numeric columns as float — convert to int to strip ".0"
        if isinstance(phone_val, float):
            raw_phone = str(int(phone_val))
        else:
            raw_phone = str(phone_val).strip()
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
    _check_campaign_access(campaign, token)

    org = await db.get(Organization, token.org_id)
    if org and not org.is_active:
        raise PermissionDeniedError(
            "Your organization's subscription is inactive — visit Billing to reactivate before launching campaigns."
        )

    from app.core.credits import has_credits_remaining

    if not await has_credits_remaining(db, token.org_id):
        raise QuotaExceededError(
            "Your organization has used all its available call credits. Visit Billing to add more before launching this campaign."
        )

    if campaign.status == CampaignStatus.RUNNING:
        # Campaign is already RUNNING but its dispatcher may have died — in
        # that case the lock is gone (its live dispatcher refreshes it every
        # loop; a dead one lets it expire within 5 min) and re-queuing is the
        # right recovery. But if the dispatcher IS still alive and holding
        # the lock, unconditionally deleting it (the old behavior) yanks the
        # lock out from under it and starts a *second* dispatcher running
        # alongside the first — doubling trunk/CPS/org-slot contention for no
        # reason. Same "lock present = alive" check resume_stalled_campaigns
        # already relies on, so only requeue when it's actually absent.
        lock_key = f"motm:dispatcher:lock:{campaign_id}"
        try:
            from app.core.redis import get_redis
            r = await get_redis()
            if await r.exists(lock_key):
                await db.refresh(campaign)
                return _to_out(campaign)  # dispatcher already running — nothing to do
        except Exception:
            pass  # Redis unreachable — fail open to the old always-requeue behavior
        run_campaign.apply_async(args=[str(campaign_id)], queue="campaigns")
        await db.refresh(campaign)
        return _to_out(campaign)

    if campaign.status not in (CampaignStatus.DRAFT, CampaignStatus.PAUSED):
        raise CampaignStateError(f"Campaign is '{campaign.status}', cannot be launched")

    if campaign.is_prime:
        from app.api.company_profile import get_org_profile
        profile = await get_org_profile(db, token.org_id)
        if not profile or not profile.is_complete:
            raise AppValidationError(
                "Prime Calling needs your Company Profile first — add at least your company name "
                "and what you offer under Prime Calling → Company Profile.",
                errors=[],
            )

    contact_count = await db.scalar(
        select(func.count()).where(
            CampaignContact.campaign_id == campaign_id,
            CampaignContact.status.in_([
                ContactStatus.PENDING,
                ContactStatus.DIALING,
                ContactStatus.NO_ANSWER,  # awaiting retry
            ]),
        )
    )
    if not contact_count:
        raise AppValidationError("Campaign has no pending contacts to call", errors=[])

    # Non-admin users may run up to 5 campaigns simultaneously
    if token.role != "admin":
        running_count = await db.scalar(
            select(func.count()).where(
                Campaign.created_by_id == token.user_id,
                Campaign.status == CampaignStatus.RUNNING,
                Campaign.deleted_at.is_(None),
            )
        )
        if running_count >= 5:
            raise CampaignStateError("You have reached the limit of 5 running campaigns. Pause one before launching another.")

    # Org-wide concurrency gate: reject the launch outright if the org is
    # already at its concurrent-call cap (from other already-running
    # campaigns), rather than starting this one and letting its calls queue
    # silently behind the others.
    usage = await get_current_usage(db, token.org_id)
    if usage["in_use"] >= usage["max"]:
        raise CampaignStateError(
            f"{usage['max']} calls are already running for your organisation. Try again in some time."
        )

    campaign.status = CampaignStatus.RUNNING
    campaign.started_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(campaign)

    # Clear any stale Redis lock left by a crashed or restarted worker so the
    # new dispatcher task can acquire it immediately.
    try:
        from app.core.redis import get_redis
        await (await get_redis()).delete(f"motm:dispatcher:lock:{campaign_id}")
    except Exception:
        pass  # Redis unavailable — task will use in-memory fallback

    # Dispatch to Celery worker (campaigns queue)
    run_campaign.apply_async(args=[str(campaign_id)], queue="campaigns")

    return _to_out(campaign)


def _collect_custom_keys(rows: list) -> list[str]:
    """Return ordered list of custom_field keys found across all contact rows."""
    keys: list[str] = []
    seen: set[str] = set()
    for _, contact in rows:
        if contact and contact.custom_fields:
            for k in contact.custom_fields:
                if k not in seen:
                    seen.add(k)
                    keys.append(k)
    return keys


def _custom_header(key: str) -> str:
    return key.replace("_", " ").title()


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

    from sqlalchemy.orm import aliased
    contact_alias = aliased(CampaignContact)
    rows = (await db.execute(
        select(Call, contact_alias)
        .outerjoin(contact_alias, Call.contact_id == contact_alias.id)
        .where(
            Call.campaign_id == campaign_id,
            Call.outcome == CallOutcome.INTERESTED,
        )
        .order_by(Call.started_at.desc())
    )).all()

    custom_keys = _collect_custom_keys(rows)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Phone Number", "Contact Name", "Email", "Company",
        *[_custom_header(k) for k in custom_keys],
        "Call Date", "Duration (min)", "Summary",
    ])
    for call, contact in rows:
        date_str = call.started_at.strftime("%Y-%m-%d %H:%M") if call.started_at else ""
        duration = f"{round(call.duration_seconds / 60, 1)}" if call.duration_seconds else ""
        cf = (contact.custom_fields or {}) if contact else {}
        writer.writerow([
            call.phone_number,
            contact.name if contact else "",
            contact.email if contact else "",
            contact.company if contact else "",
            *[cf.get(k, "") for k in custom_keys],
            date_str,
            duration,
            call.summary or "",
        ])

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

    from sqlalchemy.orm import aliased
    contact_alias = aliased(CampaignContact)
    rows = (await db.execute(
        select(Call, contact_alias)
        .outerjoin(contact_alias, Call.contact_id == contact_alias.id)
        .where(
            Call.campaign_id == campaign_id,
            Call.outcome.in_([CallOutcome.NO_ANSWER, CallOutcome.VOICEMAIL]),
        )
        .order_by(Call.started_at.desc())
    )).all()

    custom_keys = _collect_custom_keys(rows)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Phone Number", "Contact Name", "Email", "Company",
        *[_custom_header(k) for k in custom_keys],
        "Call Date", "Outcome",
    ])
    for call, contact in rows:
        date_str = call.started_at.strftime("%Y-%m-%d %H:%M") if call.started_at else ""
        cf = (contact.custom_fields or {}) if contact else {}
        writer.writerow([
            call.phone_number,
            contact.name if contact else "",
            contact.email if contact else "",
            contact.company if contact else "",
            *[cf.get(k, "") for k in custom_keys],
            date_str,
            str(call.outcome).replace("_", " ").title(),
        ])

    buf.seek(0)
    filename = f"{campaign.name.replace(' ', '_')}_no_answer.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{campaign_id}/export/callback_requested")
async def export_callback_leads(
    campaign_id: UUID,
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download a CSV of all calls where the customer requested a callback."""
    campaign = await db.get(Campaign, campaign_id)
    if not campaign or campaign.org_id != token.org_id or campaign.deleted_at:
        raise NotFoundError("Campaign not found")

    from sqlalchemy.orm import aliased
    contact_alias = aliased(CampaignContact)
    rows = (await db.execute(
        select(Call, contact_alias)
        .outerjoin(contact_alias, Call.contact_id == contact_alias.id)
        .where(
            Call.campaign_id == campaign_id,
            Call.outcome == CallOutcome.CALLBACK_REQUESTED,
        )
        .order_by(Call.started_at.desc())
    )).all()

    custom_keys = _collect_custom_keys(rows)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Phone Number", "Contact Name", "Email", "Company",
        *[_custom_header(k) for k in custom_keys],
        "Call Date", "Duration (min)", "Summary",
    ])
    for call, contact in rows:
        date_str = call.started_at.strftime("%Y-%m-%d %H:%M") if call.started_at else ""
        duration = f"{round(call.duration_seconds / 60, 1)}" if call.duration_seconds else ""
        cf = (contact.custom_fields or {}) if contact else {}
        writer.writerow([
            call.phone_number,
            contact.name if contact else "",
            contact.email if contact else "",
            contact.company if contact else "",
            *[cf.get(k, "") for k in custom_keys],
            date_str,
            duration,
            call.summary or "",
        ])

    buf.seek(0)
    filename = f"{campaign.name.replace(' ', '_')}_callback_leads.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{campaign_id}/export/all")
async def export_all_results(
    campaign_id: UUID,
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download a full CSV of every call made in this campaign."""
    campaign = await db.get(Campaign, campaign_id)
    if not campaign or campaign.org_id != token.org_id or campaign.deleted_at:
        raise NotFoundError("Campaign not found")

    from sqlalchemy.orm import aliased
    contact_alias = aliased(CampaignContact)
    rows = (await db.execute(
        select(Call, contact_alias)
        .outerjoin(contact_alias, Call.contact_id == contact_alias.id)
        .where(Call.campaign_id == campaign_id)
        .order_by(Call.started_at.asc())
    )).all()

    custom_keys = _collect_custom_keys(rows)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Phone Number", "Contact Name", "Email", "Company",
        *[_custom_header(k) for k in custom_keys],
        "Call Date", "Duration (min)", "Status", "Outcome",
        "Sentiment", "Summary", "Cost (INR)", "Recording URL",
    ])
    for call, contact in rows:
        date_str = call.started_at.strftime("%Y-%m-%d %H:%M") if call.started_at else ""
        duration = f"{round(call.duration_seconds / 60, 2)}" if call.duration_seconds else ""
        cf = (contact.custom_fields or {}) if contact else {}
        writer.writerow([
            call.phone_number,
            contact.name if contact else "",
            contact.email if contact else "",
            contact.company if contact else "",
            *[cf.get(k, "") for k in custom_keys],
            date_str,
            duration,
            str(call.status),
            str(call.outcome),
            str(call.sentiment) if call.sentiment else "",
            call.summary or "",
            str(call.cost_inr) if call.cost_inr is not None else "",
            call.recording_url or "",
        ])

    buf.seek(0)
    filename = f"{campaign.name.replace(' ', '_')}_full_results.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{campaign_id}/duplicate", response_model=CampaignOut, status_code=201)
async def duplicate_campaign(
    campaign_id: UUID,
    copy_contacts: bool = Query(True),
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Clone a campaign's settings into a new draft.

    copy_contacts=False skips copying the original's contact list, leaving
    the new campaign with 0 contacts -- for the "duplicate with fresh data"
    flow, where the frontend uploads a new CSV onto this draft right after
    (POST /{id}/contacts, which appends rather than replaces, so skipping
    the copy here is what keeps the two contact lists from ending up mixed
    together).
    """
    original = await db.get(Campaign, campaign_id)
    _check_campaign_access(original, token)

    new_campaign = Campaign(
        org_id=token.org_id,
        created_by_id=token.user_id,
        name=f"{original.name} (Copy)",
        description=original.description,
        notes=original.notes,
        goal=original.goal,
        folder_id=original.folder_id,
        agent_template_id=original.agent_template_id,
        sip_trunk_id=original.sip_trunk_id,
        calling_window_start=original.calling_window_start,
        calling_window_end=original.calling_window_end,
        calling_days=list(original.calling_days),
        timezone=original.timezone,
        calls_per_minute=original.calls_per_minute,
        max_retries=original.max_retries,
        retry_after_minutes=original.retry_after_minutes,
        is_prime=original.is_prime,
        status=CampaignStatus.DRAFT,
    )
    db.add(new_campaign)
    await db.flush()

    original_contacts = (await db.execute(
        select(CampaignContact).where(CampaignContact.campaign_id == campaign_id)
    )).scalars().all() if copy_contacts else []

    if original_contacts:
        new_contacts = [
            CampaignContact(
                org_id=token.org_id,
                campaign_id=new_campaign.id,
                name=c.name,
                phone=c.phone,
                email=c.email,
                company=c.company,
                custom_fields=c.custom_fields,
                status=ContactStatus.PENDING,
            )
            for c in original_contacts
        ]
        db.add_all(new_contacts)
        new_campaign.total_contacts = len(new_contacts)

    await db.commit()
    await db.refresh(new_campaign)
    return _to_out(new_campaign)


@router.post("/{campaign_id}/pause", response_model=CampaignOut)
async def pause_campaign(
    campaign_id: UUID,
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    campaign = await db.get(Campaign, campaign_id)
    _check_campaign_access(campaign, token)

    if campaign.status != CampaignStatus.RUNNING:
        raise CampaignStateError("Only a running campaign can be paused")

    campaign.status = CampaignStatus.PAUSED
    await db.commit()
    await db.refresh(campaign)
    return _to_out(campaign)


@router.post("/{campaign_id}/prime-preview")
async def prime_preview(
    campaign_id: UUID,
    contact_id: UUID | None = Query(None),
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate (without saving or dialing) the personalised prompt one contact
    would get, so the user can sanity-check a Prime campaign before launch.
    Defaults to the first uploaded contact.
    """
    from app.api.company_profile import get_org_profile
    from app.core.rate_limit import enforce_rate_limit
    from app.models.agent import AgentTemplate
    from app.services.prime_prompt import ContactInfo, generate_contact_prompt

    campaign = await db.get(Campaign, campaign_id)
    _check_campaign_access(campaign, token)
    if not campaign.is_prime:
        raise AppValidationError("Preview is only available for Prime Calling campaigns", errors=[])

    profile = await get_org_profile(db, token.org_id)
    if not profile or not profile.is_complete:
        raise AppValidationError(
            "Fill in your Company Profile (company name and what you offer) before previewing.",
            errors=[],
        )

    q = select(CampaignContact).where(CampaignContact.campaign_id == campaign_id)
    if contact_id:
        q = q.where(CampaignContact.id == contact_id)
    contact = await db.scalar(q.order_by(CampaignContact.created_at).limit(1))
    if not contact:
        raise AppValidationError("Upload contacts before previewing", errors=[])

    await enforce_rate_limit("prime-preview", str(token.org_id), limit=30, window_seconds=3600)

    tmpl = await db.get(AgentTemplate, campaign.agent_template_id)
    try:
        result = await generate_contact_prompt(
            profile=profile,
            base_prompt=(tmpl.system_prompt or "") if tmpl else "",
            language=str(tmpl.language) if tmpl else "hinglish",
            contact=ContactInfo(
                name=contact.name, phone=contact.phone, email=contact.email,
                company=contact.company, custom_fields=contact.custom_fields or {},
            ),
        )
    except Exception:
        raise AppValidationError("Could not generate a preview right now — please try again", errors=[])

    return {
        "contact_id": str(contact.id),
        "contact_name": contact.name,
        "system_prompt": result.system_prompt,
        "welcome_message": result.welcome_message,
        "website_used": result.website_used,
    }
