"""
app/services/leads.py — keep the lead CRM in sync with calls.

upsert_from_call() runs inside agent_report (app/api/calls.py) in the same
transaction as the report itself, once per call (already_reported guard), and
is reused by scripts/backfill_leads.py for calls made before the CRM existed.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.call import Call
from app.models.campaign import CampaignContact
from app.models.lead import Lead, LeadActivity, LeadActivityType, LeadEmailStatus, LeadMeetingStatus, LeadStatus

# Auto-advance only moves forward along this ladder; anything the team set by
# hand outside it (qualified/won/lost) is never touched by a call.
_RANK = {LeadStatus.NEW: 0, LeadStatus.CONTACTED: 1, LeadStatus.INTERESTED: 2, LeadStatus.MEETING_SCHEDULED: 3}


def fill_lead_placeholders(text: str, lead: Lead) -> str:
    """{name} / {company} in email subjects and bodies."""
    return text.replace("{name}", lead.name or "").replace("{company}", lead.company or "")


def _target_status(outcome: str, booked: bool) -> str:
    if outcome == "do_not_call":
        return LeadStatus.DO_NOT_CALL
    if booked:
        return LeadStatus.MEETING_SCHEDULED
    if outcome == "interested":
        return LeadStatus.INTERESTED
    return LeadStatus.CONTACTED


def _next_status(current: str, target: str) -> str:
    if target == LeadStatus.DO_NOT_CALL:
        return current if current == LeadStatus.WON else target  # a customer's "never call" is respected
    if current not in _RANK:
        return current
    return target if _RANK[target] > _RANK[current] else current


async def upsert_from_call(
    db: AsyncSession, call: Call, outcome: str, summary: str | None, extracted_data: dict | None,
) -> Lead | None:
    # Only campaign calls: test calls and website demo calls would fill the CRM
    # with the team's own numbers and anonymous visitors.
    if call.campaign_id is None:
        return None
    extracted = extracted_data or {}
    contact = await db.get(CampaignContact, call.contact_id) if call.contact_id else None

    # Insert-if-missing first so two calls to the same number can't race into two leads.
    await db.execute(
        pg_insert(Lead).values(org_id=call.org_id, phone=call.phone_number)
        .on_conflict_do_nothing(index_elements=["org_id", "phone"])
    )
    lead = (await db.execute(
        select(Lead).where(Lead.org_id == call.org_id, Lead.phone == call.phone_number).with_for_update()
    )).scalar_one()
    lead.deleted_at = None  # a deleted lead that gets called again comes back

    # Fill contact details only where empty -- never overwrite what the team typed.
    contact_name = contact.name if contact and contact.name != "Contact" else None  # "Contact" = CSV had no name
    lead.name = lead.name or contact_name or extracted.get("caller_name") or None
    lead.email = lead.email or (contact.email if contact else None) or extracted.get("caller_email") or None
    lead.company = lead.company or (contact.company if contact else None) or None
    if contact and contact.custom_fields:
        lead.custom_fields = {**contact.custom_fields, **(lead.custom_fields or {})}
    if extracted.get("caller_email") and lead.email_status == LeadEmailStatus.NONE:
        lead.email_status = LeadEmailStatus.CAPTURED

    lead.last_call_id = call.id
    lead.last_outcome = outcome
    lead.last_summary = summary or None
    # Timeline entries carry the call's own time, so backfilled old calls sort where they happened.
    when = call.started_at or datetime.now(timezone.utc)
    lead.last_called_at = when
    db.add(LeadActivity(
        org_id=call.org_id, lead_id=lead.id, type=LeadActivityType.CALL, created_at=when,
        payload={"call_id": str(call.id), "outcome": outcome, "summary": summary or ""},
    ))

    booking = extracted.get("next_step_booking") if isinstance(extracted.get("next_step_booking"), dict) else None
    if booking:
        lead.meeting_status = LeadMeetingStatus.SCHEDULED
        lead.meeting_at_text = str(booking.get("date_time") or "")[:255] or None
        lead.meeting_ref = str(booking.get("reference") or "")[:64] or None
        db.add(LeadActivity(org_id=call.org_id, lead_id=lead.id, type=LeadActivityType.MEETING, created_at=when, payload=booking))

    new_status = _next_status(lead.status, _target_status(outcome, bool(booking)))
    if new_status != lead.status:
        db.add(LeadActivity(
            org_id=call.org_id, lead_id=lead.id, type=LeadActivityType.STATUS_CHANGE, created_at=when,
            payload={"from": lead.status, "to": new_status, "by": "ai"},
        ))
        lead.status = new_status
    return lead
