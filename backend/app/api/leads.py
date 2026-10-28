"""
app/api/leads.py — internal lead CRM (/leads in the app).

Everyone in the org sees and edits every lead; owner_id assigns one teammate.
Leads are created automatically from calls (app/services/leads.py) and by hand
or CSV import here. Every change writes a LeadActivity (the lead's timeline).
"""
from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.contacts_file import normalize_phone, parse_contacts_file
from app.core.deps import TokenPayload, get_current_user
from app.core.email_sender import EmailSendError, org_smtp_config, send_email, smtp_configured
from app.core.exceptions import ConflictError, NotFoundError, ValidationError as AppValidationError
from app.core.rate_limit import enforce_rate_limit
from app.database import get_db
from app.models.call import Call
from app.models.lead import Lead, LeadActivity, LeadActivityType, LeadEmailStatus
from app.models.user import Organization, User
from app.services.brochure import agent_for_call, deliver_brochure
from app.services.leads import fill_lead_placeholders

router = APIRouter()

StatusLit = Literal["new", "contacted", "interested", "meeting_scheduled", "qualified", "won", "lost", "do_not_call"]
EmailStatusLit = Literal["none", "captured", "sent", "failed", "replied"]
MeetingStatusLit = Literal["none", "scheduled", "done", "cancelled"]

_PHONE_RE = re.compile(r"^\+\d{6,15}$")
_MAX_IMPORT_ROWS = 5000


# ── helpers ──────────────────────────────────────────────────────────────────

async def _members(db: AsyncSession, org_id: UUID) -> dict[UUID, str]:
    rows = (await db.execute(
        select(User.id, User.full_name).where(User.org_id == org_id, User.deleted_at.is_(None))
    )).all()
    return {r.id: r.full_name for r in rows}


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _lead_out(lead: Lead, members: dict[UUID, str]) -> dict:
    return {
        "id": str(lead.id), "phone": lead.phone, "name": lead.name, "email": lead.email, "company": lead.company,
        "status": lead.status, "owner_id": str(lead.owner_id) if lead.owner_id else None,
        "owner_name": members.get(lead.owner_id) if lead.owner_id else None,
        "tags": lead.tags or [], "custom_fields": lead.custom_fields or {},
        "last_call_id": str(lead.last_call_id) if lead.last_call_id else None,
        "last_outcome": lead.last_outcome, "last_summary": lead.last_summary,
        "last_called_at": _iso(lead.last_called_at),
        "email_status": lead.email_status, "email_sent_at": _iso(lead.email_sent_at),
        "meeting_status": lead.meeting_status, "meeting_at_text": lead.meeting_at_text,
        "meeting_ref": lead.meeting_ref,
        "created_at": _iso(lead.created_at), "updated_at": _iso(lead.updated_at),
    }


async def _get_lead(db: AsyncSession, lead_id: UUID, org_id: UUID) -> Lead:
    lead = (await db.execute(
        select(Lead).where(Lead.id == lead_id, Lead.org_id == org_id, Lead.deleted_at.is_(None))
    )).scalar_one_or_none()
    if lead is None:
        raise NotFoundError("Lead not found")
    return lead


def _activity(lead: Lead, type_: str, payload: dict, user_id: UUID | None) -> LeadActivity:
    return LeadActivity(org_id=lead.org_id, lead_id=lead.id, type=type_, payload=payload, user_id=user_id)


def _clean_phone(raw: str) -> str:
    phone = normalize_phone(raw)
    if not _PHONE_RE.match(phone):
        raise AppValidationError("Enter a valid phone number, e.g. +919876543210", errors=[])
    return phone


def _check_custom_fields(fields: dict[str, str]) -> None:
    if len(fields) > 100 or any(len(k) > 64 or len(str(v)) > 2000 for k, v in fields.items()):
        raise AppValidationError("Too many custom fields, or a name/value is too long", errors=[])


def _filters(token: TokenPayload, status, owner, q, email_status, meeting_status) -> list:
    f = [Lead.org_id == token.org_id, Lead.deleted_at.is_(None)]
    if status:
        f.append(Lead.status == status)
    if owner == "me":
        f.append(Lead.owner_id == token.user_id)
    elif owner == "none":
        f.append(Lead.owner_id.is_(None))
    elif owner:
        try:
            f.append(Lead.owner_id == UUID(owner))
        except ValueError:
            raise AppValidationError("Invalid owner filter", errors=[])
    if q and q.strip():
        like = f"%{q.strip()}%"
        f.append(or_(Lead.name.ilike(like), Lead.phone.ilike(like), Lead.email.ilike(like), Lead.company.ilike(like)))
    if email_status:
        f.append(Lead.email_status == email_status)
    if meeting_status:
        f.append(Lead.meeting_status == meeting_status)
    return f


def _csv_safe(value) -> str:
    """Stop spreadsheet formula injection from customer-supplied text."""
    s = "" if value is None else str(value)
    return "'" + s if s[:1] in ("=", "+", "-", "@") else s


# ── list / meta / export ─────────────────────────────────────────────────────

@router.get("")
async def list_leads(
    status: StatusLit | None = Query(None),
    owner: str | None = Query(None, description="'me', 'none' or a user id"),
    q: str | None = Query(None),
    email_status: EmailStatusLit | None = Query(None),
    meeting_status: MeetingStatusLit | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    filters = _filters(token, status, owner, q, email_status, meeting_status)
    total = await db.scalar(select(func.count(Lead.id)).where(*filters))
    rows = (await db.execute(
        select(Lead).where(*filters)
        .order_by(Lead.last_called_at.desc().nulls_last(), Lead.created_at.desc())
        .limit(limit).offset(offset)
    )).scalars().all()
    # Pipeline counts ignore the status filter so every status chip keeps its number.
    counts = dict((await db.execute(
        select(Lead.status, func.count(Lead.id))
        .where(*_filters(token, None, owner, q, email_status, meeting_status))
        .group_by(Lead.status)
    )).all())
    members = await _members(db, token.org_id)
    return {"items": [_lead_out(r, members) for r in rows], "total": total, "status_counts": counts}


@router.get("/meta")
async def leads_meta(token: TokenPayload = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Teammates for the owner picker, and whether this org has set up its mail server."""
    members = await _members(db, token.org_id)
    org = await db.get(Organization, token.org_id)
    return {
        "members": [{"id": str(k), "name": v} for k, v in sorted(members.items(), key=lambda kv: kv[1] or "")],
        "email_enabled": smtp_configured(org),
    }


@router.get("/export.csv")
async def export_leads(
    status: StatusLit | None = Query(None),
    owner: str | None = Query(None),
    q: str | None = Query(None),
    email_status: EmailStatusLit | None = Query(None),
    meeting_status: MeetingStatusLit | None = Query(None),
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    filters = _filters(token, status, owner, q, email_status, meeting_status)
    rows = (await db.execute(
        select(Lead).where(*filters).order_by(Lead.last_called_at.desc().nulls_last()).limit(50_000)
    )).scalars().all()
    members = await _members(db, token.org_id)
    custom_keys = sorted({k for r in rows for k in (r.custom_fields or {})})

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Phone", "Name", "Email", "Company", "Status", "Owner", "Last outcome", "Last summary", "Last called",
        "Email status", "Email sent at", "Meeting status", "Meeting when", "Meeting ref", "Tags", *custom_keys,
    ])
    for r in rows:
        cf = r.custom_fields or {}
        writer.writerow([
            r.phone, *[_csv_safe(v) for v in (
                r.name, r.email, r.company, r.status, members.get(r.owner_id, "") if r.owner_id else "",
                r.last_outcome, r.last_summary, _iso(r.last_called_at), r.email_status, _iso(r.email_sent_at),
                r.meeting_status, r.meeting_at_text, r.meeting_ref, ", ".join(r.tags or []),
                *[cf.get(k, "") for k in custom_keys],
            )],
        ])
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="leads.csv"'},
    )


# ── create / import ──────────────────────────────────────────────────────────

class LeadCreate(BaseModel):
    phone: str = Field(min_length=5, max_length=30)
    name: str | None = Field(None, max_length=255)
    email: str | None = Field(None, max_length=255)
    company: str | None = Field(None, max_length=255)
    owner_id: UUID | None = None
    custom_fields: dict[str, str] = {}


@router.post("", status_code=201)
async def create_lead(body: LeadCreate, token: TokenPayload = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    phone = _clean_phone(body.phone)
    _check_custom_fields(body.custom_fields)
    members = await _members(db, token.org_id)
    if body.owner_id and body.owner_id not in members:
        raise AppValidationError("Owner must be someone in your team", errors=[])

    lead = (await db.execute(select(Lead).where(Lead.org_id == token.org_id, Lead.phone == phone))).scalar_one_or_none()
    if lead and lead.deleted_at is None:
        raise ConflictError("A lead with this phone number already exists")
    if lead is None:
        lead = Lead(org_id=token.org_id, phone=phone)
        db.add(lead)
    lead.deleted_at = None
    lead.name, lead.email, lead.company = body.name or None, body.email or None, body.company or None
    lead.owner_id = body.owner_id
    lead.custom_fields = body.custom_fields
    await db.flush()
    db.add(_activity(lead, LeadActivityType.EDIT, {"created": True}, token.user_id))
    await db.commit()
    await db.refresh(lead)
    return _lead_out(lead, members)


@router.post("/import")
async def import_leads(
    file: UploadFile = File(...),
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """CSV/Excel import. Existing phones are updated (file values win, custom
    fields are merged), new phones become new leads."""
    rows = parse_contacts_file(await file.read(), file.filename or "")
    if not rows:
        raise AppValidationError("No valid rows found in file", errors=[])
    if len(rows) > _MAX_IMPORT_ROWS:
        raise AppValidationError(f"Import up to {_MAX_IMPORT_ROWS} rows at a time", errors=[])
    by_phone = {r["phone"]: r for r in rows}  # a phone repeated in the file: last row wins
    existing = {
        lead.phone: lead for lead in (await db.execute(
            select(Lead).where(Lead.org_id == token.org_id, Lead.phone.in_(list(by_phone)))
        )).scalars().all()
    }

    created = updated = 0
    for phone, r in by_phone.items():
        if not _PHONE_RE.match(phone):
            continue
        lead = existing.get(phone)
        is_new = lead is None
        if is_new:
            lead = Lead(org_id=token.org_id, phone=phone, custom_fields={}, tags=[])
            db.add(lead)
        lead.deleted_at = None
        lead.name = r["name"] or lead.name
        lead.email = r["email"] or lead.email
        lead.company = r["company"] or lead.company
        lead.custom_fields = {**(lead.custom_fields or {}), **r["custom_fields"]}
        await db.flush()
        db.add(_activity(lead, LeadActivityType.IMPORT, {"file": (file.filename or "")[:200], "created": is_new}, token.user_id))
        created += is_new
        updated += not is_new
    await db.commit()
    return {"created": created, "updated": updated}


# ── one lead ─────────────────────────────────────────────────────────────────

@router.get("/{lead_id}")
async def get_lead(lead_id: UUID, token: TokenPayload = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    lead = await _get_lead(db, lead_id, token.org_id)
    members = await _members(db, token.org_id)
    activities = (await db.execute(
        select(LeadActivity).where(LeadActivity.lead_id == lead.id, LeadActivity.org_id == token.org_id)
        .order_by(LeadActivity.created_at.desc()).limit(500)
    )).scalars().all()
    calls = (await db.execute(
        select(Call).where(Call.org_id == token.org_id, Call.phone_number == lead.phone)
        .order_by(Call.created_at.desc()).limit(100)
    )).scalars().all()
    return {
        **_lead_out(lead, members),
        "activities": [{
            "id": str(a.id), "type": a.type, "payload": a.payload or {}, "created_at": _iso(a.created_at),
            "user_name": members.get(a.user_id) if a.user_id else None,
        } for a in activities],
        "calls": [{
            "id": str(c.id), "campaign_id": str(c.campaign_id) if c.campaign_id else None,
            "started_at": _iso(c.started_at), "status": c.status, "outcome": c.outcome, "summary": c.summary,
            "duration_seconds": c.duration_seconds, "has_recording": bool(c.recording_url),
        } for c in calls],
    }


class LeadPatch(BaseModel):
    name: str | None = Field(None, max_length=255)
    email: str | None = Field(None, max_length=255)
    company: str | None = Field(None, max_length=255)
    status: StatusLit | None = None
    owner_id: UUID | None = None
    tags: list[str] | None = Field(None, max_length=20)
    custom_fields: dict[str, str] | None = None
    email_status: EmailStatusLit | None = None
    meeting_status: MeetingStatusLit | None = None
    meeting_at_text: str | None = Field(None, max_length=255)
    meeting_ref: str | None = Field(None, max_length=64)


_NOT_NULL = {"status", "tags", "custom_fields", "email_status", "meeting_status"}


@router.patch("/{lead_id}")
async def update_lead(
    lead_id: UUID, body: LeadPatch,
    token: TokenPayload = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    lead = await _get_lead(db, lead_id, token.org_id)
    members = await _members(db, token.org_id)
    changes = {k: v for k, v in body.model_dump(exclude_unset=True).items() if not (k in _NOT_NULL and v is None)}
    if "owner_id" in changes and changes["owner_id"] and changes["owner_id"] not in members:
        raise AppValidationError("Owner must be someone in your team", errors=[])
    if "custom_fields" in changes:
        _check_custom_fields(changes["custom_fields"])
    if "tags" in changes:
        changes["tags"] = [t.strip()[:40] for t in changes["tags"] if t.strip()]
    if changes.get("email") and "@" not in changes["email"]:
        raise AppValidationError("Enter a valid email address", errors=[])

    edited: dict = {}
    for field, new in changes.items():
        if isinstance(new, str):
            new = new.strip() or None
        old = getattr(lead, field)
        if old == new:
            continue
        setattr(lead, field, new)
        if field == "status":
            db.add(_activity(lead, LeadActivityType.STATUS_CHANGE, {"from": old, "to": new, "by": "user"}, token.user_id))
        elif field.startswith("meeting_"):
            db.add(_activity(lead, LeadActivityType.MEETING, {field: new}, token.user_id))
        elif field == "owner_id":
            edited["owner"] = members.get(new) if new else None
        elif field in ("custom_fields", "tags"):
            edited[field] = "updated"
        else:
            edited[field] = new
    if edited:
        db.add(_activity(lead, LeadActivityType.EDIT, edited, token.user_id))
    await db.commit()
    await db.refresh(lead)
    return _lead_out(lead, members)


class NoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


@router.post("/{lead_id}/notes", status_code=201)
async def add_note(
    lead_id: UUID, body: NoteIn,
    token: TokenPayload = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    lead = await _get_lead(db, lead_id, token.org_id)
    lead.updated_at = datetime.now(timezone.utc)
    db.add(_activity(lead, LeadActivityType.NOTE, {"text": body.text.strip()}, token.user_id))
    await db.commit()
    return {"ok": True}


class EmailIn(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=20_000)
    to: str | None = Field(None, max_length=255)


@router.post("/{lead_id}/email")
async def email_lead(
    lead_id: UUID, body: EmailIn,
    token: TokenPayload = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    """Send a real email to the lead through the org's own mail server. A
    failure is recorded on the lead (status failed + timeline entry) and
    returned as ok=false rather than an error, so the failed attempt is saved."""
    cfg = org_smtp_config(await db.get(Organization, token.org_id))
    if cfg is None:
        raise AppValidationError("Ask your admin to set up email in Settings → Integrations first", errors=[])
    lead = await _get_lead(db, lead_id, token.org_id)
    to = (body.to or lead.email or "").strip()
    if "@" not in to:
        raise AppValidationError("This lead has no email address", errors=[])
    await enforce_rate_limit("lead_email", str(token.org_id), limit=300, window_seconds=3600)

    subject, text_body = fill_lead_placeholders(body.subject, lead), fill_lead_placeholders(body.body, lead)
    try:
        message_id = await send_email(cfg, to=to, subject=subject, body=text_body)
        ok, detail = True, "Email sent"
    except EmailSendError as exc:
        message_id, ok, detail = None, False, str(exc)

    lead.email = lead.email or to
    lead.email_status = LeadEmailStatus.SENT if ok else LeadEmailStatus.FAILED
    if ok:
        lead.email_sent_at = datetime.now(timezone.utc)
    db.add(_activity(lead, LeadActivityType.EMAIL, {
        "to": to, "subject": subject, "body": text_body[:2000], "ok": ok, "detail": detail, "message_id": message_id,
    }, token.user_id))
    await db.commit()
    return {"ok": ok, "detail": detail}


@router.post("/{lead_id}/brochure")
async def send_lead_brochure(
    lead_id: UUID,
    token: TokenPayload = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    """Send (or resend) the brochure of the agent that last called this lead."""
    lead = await _get_lead(db, lead_id, token.org_id)
    await enforce_rate_limit("lead_email", str(token.org_id), limit=300, window_seconds=3600)
    calls = (await db.execute(
        select(Call).where(Call.org_id == token.org_id, Call.phone_number == lead.phone, Call.campaign_id.is_not(None))
        .order_by(Call.created_at.desc()).limit(20)
    )).scalars().all()
    for call in calls:
        agent = await agent_for_call(db, call)
        if agent and agent.brochure_key:
            ok, detail = await deliver_brochure(db, lead, agent, call=call, user_id=token.user_id)
            return {"ok": ok, "detail": detail}
    raise AppValidationError("None of the agents that called this lead has a brochure", errors=[])


@router.delete("/{lead_id}", status_code=204)
async def delete_lead(lead_id: UUID, token: TokenPayload = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    lead = await _get_lead(db, lead_id, token.org_id)
    lead.deleted_at = datetime.now(timezone.utc)
    await db.commit()
