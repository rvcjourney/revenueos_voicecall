"""
app/services/brochure.py — email the agent's brochure to a lead.

Called automatically after a call where the customer agreed to receive it
(agent tool send_brochure → extracted_data.brochure_request → agent_report →
app/workers/tasks/brochure.py), and by the "Send brochure" button on a lead.
Every attempt, sent or not, lands on the lead's timeline with the reason.
"""
from __future__ import annotations

import difflib
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.email_sender import Attachment, EmailSendError, org_smtp_config, send_email
from app.models.agent import AgentTemplate
from app.models.call import Call
from app.models.campaign import Campaign, CampaignContact
from app.models.lead import Lead, LeadActivity, LeadActivityType, LeadEmailStatus
from app.models.user import Organization
from app.services.leads import fill_lead_placeholders

_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", re.IGNORECASE)
DEFAULT_SUBJECT = "Brochure as discussed"
DEFAULT_BODY = "Hi {name},\n\nThank you for your time on the call. As discussed, please find our brochure attached.\n\nRegards"


def pick_email(spoken: str, *on_file: str | None) -> str:
    """The address to send to. What the customer said on the call wins, unless it's a
    near-miss of one we already have: speech-to-text drops or swaps a letter
    (heard chinmaypo8483@gmail.com for chinmaypol8483@gmail.com), and then the file is right."""
    known = [e for e in on_file if e and _EMAIL_RE.fullmatch(e)]
    heard = spoken if spoken and _EMAIL_RE.fullmatch(spoken) else ""
    if not heard:
        return known[0] if known else ""
    close = next((k for k in known if difflib.SequenceMatcher(None, heard.lower(), k.lower()).ratio() >= 0.85), None)
    return close or heard


async def agent_for_call(db: AsyncSession, call: Call) -> AgentTemplate | None:
    campaign = await db.get(Campaign, call.campaign_id) if call.campaign_id else None
    return await db.get(AgentTemplate, campaign.agent_template_id) if campaign and campaign.agent_template_id else None


async def deliver_brochure(
    db: AsyncSession, lead: Lead, agent: AgentTemplate | None, *,
    call: Call | None = None, spoken_email: str = "", user_id=None,
) -> tuple[bool, str]:
    """Send it, record the attempt on the lead, and return (ok, detail). Commits."""
    org = await db.get(Organization, lead.org_id)
    contact = await db.get(CampaignContact, call.contact_id) if call and call.contact_id else None
    to = pick_email(spoken_email, lead.email, contact.email if contact else None)

    message_id = None
    subject = fill_lead_placeholders((agent.brochure_email_subject if agent else None) or DEFAULT_SUBJECT, lead)
    if agent is None or not agent.brochure_key:
        ok, detail = False, "The agent has no brochure uploaded"
    elif (cfg := org_smtp_config(org)) is None:
        ok, detail = False, "Email isn't set up yet (Settings → Integrations)"
    elif not to:
        ok, detail = False, "No email address for this customer. Add it on the lead and send again."
    else:
        from app.storage.backend import get_storage
        body = fill_lead_placeholders(agent.brochure_email_body or DEFAULT_BODY, lead)
        try:
            data = await get_storage().download(settings.BUCKET_EXPORTS, agent.brochure_key)
            message_id = await send_email(
                cfg, to=to, subject=subject, body=body,
                attachments=[Attachment(agent.brochure_filename or "brochure.pdf", data,
                                        agent.brochure_content_type or "application/pdf")],
            )
            ok, detail = True, "Brochure sent"
        except EmailSendError as exc:
            ok, detail = False, str(exc)
        lead.email = lead.email or to
        lead.email_status = LeadEmailStatus.SENT if ok else LeadEmailStatus.FAILED
        if ok:
            lead.email_sent_at = datetime.now(timezone.utc)

    db.add(LeadActivity(
        org_id=lead.org_id, lead_id=lead.id, type=LeadActivityType.EMAIL, user_id=user_id,
        payload={
            "kind": "brochure", "to": to, "subject": subject, "ok": ok, "detail": detail,
            "message_id": message_id, "call_id": str(call.id) if call else None,
            "file": agent.brochure_filename if agent else None,
        },
    ))
    await db.commit()
    return ok, detail


async def deliver_brochure_for_call(db: AsyncSession, call_id) -> tuple[bool, str] | None:
    """The automatic path: None if the call didn't ask for a brochure."""
    call = await db.get(Call, call_id)
    request = (call.extracted_data or {}).get("brochure_request") if call else None
    if call is None or not isinstance(request, dict) or call.campaign_id is None:
        return None
    lead = (await db.execute(
        select(Lead).where(Lead.org_id == call.org_id, Lead.phone == call.phone_number)
    )).scalar_one_or_none()
    if lead is None:
        return None
    return await deliver_brochure(
        db, lead, await agent_for_call(db, call), call=call, spoken_email=str(request.get("email") or ""),
    )
