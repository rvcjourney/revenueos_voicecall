"""
app/integrations/revenueos.py — RevenueOS Brain: run a calling campaign from one request.

Orchestration only. Each step calls the same code the dashboard uses, so the
rules live in one place:
  - phone number   → app/api/sip_trunks.py::connect_vobiz_trunk
  - company profile → app/api/company_profile.py::save_org_profile
  - agent voice    → app/core/plan_features.py::check_agent_voice_settings
  - launch         → app/api/campaigns.py::start_campaign

Two references: client_reference identifies the client (one organization, one
admin user, its numbers, its company profile); reference identifies one
campaign. Bookkeeping is in app/models/revenueos.py. Every read and action
goes through those rows, so the key can only reach organizations it created.

Routes: app/api/revenueos.py. Decisions: docs/revenueos-integration.md.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, time, timezone
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import structlog
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.campaigns import normalize_phone, start_campaign
from app.api.company_profile import CompanyProfileIn, get_org_profile, save_org_profile
from app.api.sip_trunks import ConnectVobizBody, _rebalance_default, connect_vobiz_trunk, normalize_did
from app.config import settings
from app.core.exceptions import (
    AppError,
    ConflictError,
    NotFoundError,
    ValidationError as AppValidationError,
)
from app.core.plan_features import check_agent_voice_settings
from app.core.security import hash_password
from app.models.agent import AgentLanguage, AgentTemplate, VoiceProvider
from app.models.call import Call, CallTranscript
from app.models.campaign import Campaign, CampaignContact, CampaignGoal, CampaignStatus, ContactStatus
from app.models.dnc import DoNotCallEntry, SystemDncEntry
from app.models.revenueos import RevenueOSClient, RevenueOSLaunch
from app.models.sip import SipTrunk
from app.models.user import Organization, User, UserRole
from app.workers.tasks.campaign import _in_calling_window

log = structlog.get_logger(__name__)

_REFERENCE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"
_E164 = re.compile(r"^\+[1-9]\d{7,14}$")
_DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


# ── Request ───────────────────────────────────────────────────────────────────

class _Strict(BaseModel):
    # An unknown field is refused, so a misspelt name is reported instead of ignored.
    model_config = ConfigDict(extra="forbid")


class UserIn(_Strict):
    email: EmailStr
    password: SecretStr = Field(min_length=6, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)
    company_name: str = Field(min_length=1, max_length=255)
    phone: str = Field("", max_length=20)


class PhoneNumberIn(_Strict):
    auth_id: str = Field(min_length=1, max_length=100)
    auth_token: SecretStr = Field(min_length=1, max_length=500)
    did: str = Field(min_length=1, max_length=20)


class AgentIn(_Strict):
    name: str | None = Field(None, max_length=255)
    language: str = "hinglish"
    welcome_message: str = Field("", max_length=5000)
    system_prompt: str = Field("", max_length=50000)
    voice_id: str = Field("9BWtsMINqrJLrRacOk9x", max_length=100)
    voice_provider: str = "elevenlabs"
    max_call_duration_seconds: int = Field(600, ge=30, le=3600)

    @field_validator("language")
    @classmethod
    def _language(cls, v: str) -> str:
        v = v.lower()
        if v not in {e.value for e in AgentLanguage}:
            raise ValueError("language must be one of: " + ", ".join(e.value for e in AgentLanguage))
        return v

    @field_validator("voice_provider")
    @classmethod
    def _provider(cls, v: str) -> str:
        v = v.lower()
        if v not in {e.value for e in VoiceProvider}:
            raise ValueError("voice_provider must be one of: " + ", ".join(e.value for e in VoiceProvider))
        return v


class CampaignIn(_Strict):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(None, max_length=5000)
    goal: str = "lead_generation"

    @field_validator("goal")
    @classmethod
    def _goal(cls, v: str) -> str:
        if v not in {e.value for e in CampaignGoal}:
            raise ValueError("goal must be one of: " + ", ".join(e.value for e in CampaignGoal))
        return v


class ScheduleIn(_Strict):
    calling_window_start: time = time(9, 0)
    calling_window_end: time = time(19, 0)
    calling_days: list[str] = ["mon", "tue", "wed", "thu", "fri", "sat"]
    timezone: str = "Asia/Kolkata"
    calls_per_minute: int = Field(5, ge=1, le=30)

    @field_validator("calling_days")
    @classmethod
    def _days(cls, v: list[str]) -> list[str]:
        v = [d.lower() for d in v]
        if not v or any(d not in _DAYS for d in v):
            raise ValueError("calling_days must be a non-empty list of: " + ", ".join(_DAYS))
        return [d for d in _DAYS if d in v]

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("timezone is not a known timezone name, e.g. Asia/Kolkata") from exc
        return v

    @model_validator(mode="after")
    def _window(self) -> "ScheduleIn":
        if self.calling_window_start.tzinfo or self.calling_window_end.tzinfo:
            raise ValueError("calling window times must be plain HH:MM, the timezone field sets the zone")
        if self.calling_window_start >= self.calling_window_end:
            raise ValueError("calling_window_start must be earlier than calling_window_end")
        return self


class ContactIn(_Strict):
    name: str = Field("Contact", max_length=255)
    phone: str = Field(max_length=40)
    email: str | None = Field(None, max_length=255)
    company: str | None = Field(None, max_length=255)
    # Prime Calling reads this site to personalise the call
    website: str | None = Field(None, max_length=500)
    custom_fields: dict[str, str] = Field(default_factory=dict)


class LaunchIn(_Strict):
    client_reference: str = Field(min_length=1, max_length=120, pattern=_REFERENCE_PATTERN)
    reference: str = Field(min_length=1, max_length=120, pattern=_REFERENCE_PATTERN)
    user: UserIn
    phone_number: PhoneNumberIn | None = None
    company_profile: CompanyProfileIn | None = None
    agent: AgentIn = Field(default_factory=AgentIn)
    campaign: CampaignIn
    schedule: ScheduleIn = Field(default_factory=ScheduleIn)
    contacts: list[ContactIn] = Field(min_length=1)
    # Prime Calling: a personalised script per contact. Needs a company profile.
    prime: bool = True
    auto_start: bool = True


# ── Helpers ───────────────────────────────────────────────────────────────────

def content_hash(body: LaunchIn) -> str:
    """
    What makes two requests "the same campaign": campaign, agent, schedule,
    prime and the contacts. Not included: the user, the phone_number block,
    the company profile (those belong to the client, not the campaign) and
    auto_start.

    Only fields the caller actually sent are hashed (exclude_unset), so adding
    a new optional field with a default later does not change the hash of
    requests that were stored before it existed.
    """
    contacts = []
    for c in body.contacts:
        d = c.model_dump(exclude_unset=True)
        d["phone"] = normalize_phone(c.phone)
        contacts.append(d)
    identity = {
        "campaign": body.campaign.model_dump(exclude_unset=True),
        "agent": body.agent.model_dump(exclude_unset=True),
        "schedule": body.schedule.model_dump(exclude_unset=True, mode="json"),
        "contacts": contacts,
    }
    if "prime" in body.model_fields_set:
        identity["prime"] = body.prime
    raw = json.dumps(identity, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def _check_contacts(contacts: list[ContactIn]) -> tuple[list[tuple[str, ContactIn]], list[dict]]:
    """Split into (normalised phone, contact) to keep and [{phone, reason}] to refuse."""
    accepted: list[tuple[str, ContactIn]] = []
    rejected: list[dict] = []
    seen: set[str] = set()
    for c in contacts:
        phone = normalize_phone(c.phone.strip())
        if not _E164.match(phone):
            rejected.append({"phone": c.phone, "reason": "not a valid phone number"})
        elif phone in seen:
            rejected.append({"phone": phone, "reason": "listed more than once in this request"})
        else:
            seen.add(phone)
            accepted.append((phone, c))
    return accepted, rejected


async def _dnc_phones(db: AsyncSession, org_id: UUID, phones: list[str]) -> set[str]:
    blocked = set((await db.execute(
        select(SystemDncEntry.phone_number).where(SystemDncEntry.phone_number.in_(phones))
    )).scalars().all())
    blocked |= set((await db.execute(
        select(DoNotCallEntry.phone_number).where(
            DoNotCallEntry.org_id == org_id, DoNotCallEntry.phone_number.in_(phones)
        )
    )).scalars().all())
    return blocked


def _utc_z(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _window_text(campaign: Campaign) -> str:
    return (
        f"{campaign.calling_window_start.strftime('%H:%M')}–{campaign.calling_window_end.strftime('%H:%M')} "
        f"{campaign.timezone}, {', '.join(campaign.calling_days)}"
    )


# ── Account ───────────────────────────────────────────────────────────────────

async def _create_client(db: AsyncSession, body: LaunchIn) -> tuple[RevenueOSClient, Organization, User]:
    email = body.user.email.lower()
    if await db.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise ConflictError(
            "user.email already has an account on the voice platform that does not belong to this "
            "client_reference. Use that account's client_reference, or a different email."
        )

    slug = re.sub(r"[^a-z0-9]+", "-", body.user.company_name.lower()).strip("-") or "org"
    if await db.scalar(select(Organization.id).where(Organization.slug == slug)):
        slug = f"{slug}-{uuid4().hex[:6]}"

    org = Organization(
        name=body.user.company_name,
        slug=slug,
        phone=body.user.phone,
        sip_caller_id="",
        is_active=True,
    )
    db.add(org)
    await db.flush()
    user = User(
        org_id=org.id,
        email=email,
        hashed_password=hash_password(body.user.password.get_secret_value()),
        full_name=body.user.full_name,
        role=UserRole.ADMIN,
        is_active=True,
        # Created by MOTM on the client's behalf, so there is no signup code to confirm.
        email_verified_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()
    client = RevenueOSClient(org_id=org.id, client_reference=body.client_reference, user_id=user.id)
    db.add(client)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError(
            "This client_reference or email was created by another request at the same moment. "
            "Send the same request again."
        ) from exc
    return client, org, user


# ── Phone number ──────────────────────────────────────────────────────────────

async def _resolve_number(
    db: AsyncSession, org: Organization, block: PhoneNumberIn | None
) -> tuple[SipTrunk | None, dict]:
    """Return (trunk to dial from, or None) and the phone_number part of the response."""
    if block is None:
        active = (await db.execute(
            select(SipTrunk)
            .where(SipTrunk.org_id == org.id, SipTrunk.is_active.is_(True), SipTrunk.deleted_at.is_(None))
            .order_by(SipTrunk.is_default.desc(), SipTrunk.created_at)
        )).scalars().first()
        if active is None:
            return None, {
                "status": "missing",
                "reason": "This client has no connected phone number. Send a phone_number block "
                          "(auth_id, auth_token, did).",
            }
        return active, {"status": "reused", "number": active.caller_id}

    did = normalize_did(block.did)
    if not _E164.match(did):
        return None, {"status": "failed", "reason": "phone_number.did is not a valid phone number"}

    existing = (await db.execute(
        select(SipTrunk).where(SipTrunk.caller_id == did, SipTrunk.deleted_at.is_(None))
    )).scalars().all()
    mine = next((t for t in existing if t.org_id == org.id), None)
    if mine is not None:
        if not mine.is_active:
            mine.is_active = True
            await db.flush()
            await _rebalance_default(db, org.id)
            await db.commit()
            return mine, {"status": "activated", "number": did}
        return mine, {"status": "reused", "number": did}
    if existing:
        return None, {
            "status": "failed", "number": did,
            "reason": "This number is already connected to a different account on the voice platform.",
        }

    org_id = org.id
    try:
        trunk = await connect_vobiz_trunk(
            db,
            org_id=org_id,
            body=ConnectVobizBody(
                auth_id=block.auth_id, auth_token=block.auth_token.get_secret_value(), did=did
            ),
            # Owner decision: a number Brain sends goes live without the test call.
            activate=True,
        )
    except HTTPException as exc:
        await db.rollback()
        return None, {"status": "failed", "number": did, "reason": str(exc.detail)}
    return trunk, {"status": "connected", "number": did}


# ── Agent ─────────────────────────────────────────────────────────────────────

async def _resolve_agent(db: AsyncSession, org: Organization, user: User, body: LaunchIn) -> tuple[AgentTemplate, str]:
    spec = body.agent
    name = spec.name or body.campaign.name
    existing = await db.scalar(
        select(AgentTemplate).where(
            AgentTemplate.org_id == org.id,
            AgentTemplate.deleted_at.is_(None),
            AgentTemplate.name == name,
            AgentTemplate.language == spec.language,
            AgentTemplate.welcome_message == spec.welcome_message,
            AgentTemplate.system_prompt == spec.system_prompt,
            AgentTemplate.voice_id == spec.voice_id,
            AgentTemplate.voice_provider == spec.voice_provider,
            AgentTemplate.max_call_duration_seconds == spec.max_call_duration_seconds,
        ).order_by(AgentTemplate.created_at).limit(1)
    )
    if existing is not None:
        return existing, "reused"

    await check_agent_voice_settings(db, org.id, voice_provider=spec.voice_provider, voice_id=spec.voice_id)
    agent = AgentTemplate(
        org_id=org.id,
        created_by_id=user.id,
        name=name,
        language=spec.language,
        welcome_message=spec.welcome_message,
        system_prompt=spec.system_prompt,
        voice_id=spec.voice_id,
        voice_provider=spec.voice_provider,
        max_call_duration_seconds=spec.max_call_duration_seconds,
    )
    db.add(agent)
    await db.flush()
    return agent, "created"


# ── Start ─────────────────────────────────────────────────────────────────────

async def _start(db: AsyncSession, campaign: Campaign, user: User, *, auto_start: bool) -> dict:
    """Try to start the campaign; return start_status / start_reason / next_action."""
    if campaign.status == CampaignStatus.COMPLETED:
        return {"start_status": "already_started", "start_reason": "This campaign has finished.",
                "next_action": "Read the results."}
    if campaign.status == CampaignStatus.FAILED:
        return {"start_status": "failed",
                "start_reason": "This campaign stopped with an error (usually: no working phone number).",
                "next_action": "Fix the phone number, then launch a new reference."}
    if not auto_start:
        if campaign.status == CampaignStatus.RUNNING:
            return {"start_status": "already_started", "start_reason": None, "next_action": "Read the results."}
        return {"start_status": "pending",
                "start_reason": "auto_start was false, so the campaign is stored and not started.",
                "next_action": "Send the same request with auto_start true, or press Launch in the dashboard."}

    was_running = campaign.status == CampaignStatus.RUNNING
    org_id, user_id = campaign.org_id, user.id
    try:
        campaign = await start_campaign(db, campaign, org_id=org_id, user_id=user_id, role=UserRole.ADMIN)
    except AppError as exc:
        await db.rollback()
        return {"start_status": "blocked", "start_reason": exc.message,
                "next_action": "Fix the reason above, then send the same request again."}
    except Exception:
        # start_campaign marks the campaign running before it queues the work.
        # If queuing failed, the worker's own once-a-minute check picks it up.
        log.exception("revenueos_start_queue_failed", campaign_id=str(campaign.id))
        return {"start_status": "pending",
                "start_reason": "The campaign is marked running but could not be handed to the worker "
                                "just now; the worker re-checks every minute.",
                "next_action": "Read the campaign status in a few minutes."}

    if was_running:
        return {"start_status": "already_started", "start_reason": None, "next_action": "Read the results."}
    if not _in_calling_window(campaign):
        return {"start_status": "started",
                "start_reason": f"Outside the calling window right now; calls begin when it opens "
                                f"({_window_text(campaign)}).",
                "next_action": "Read the results after the window opens."}
    return {"start_status": "started", "start_reason": None, "next_action": "Read the results."}


def _campaign_out(campaign: Campaign) -> dict:
    return {
        "id": str(campaign.id),
        "name": campaign.name,
        "status": str(campaign.status),
        "prime": bool(campaign.is_prime),
        "contacts_added": campaign.total_contacts,
    }


# ── Launch ────────────────────────────────────────────────────────────────────

async def launch(db: AsyncSession, body: LaunchIn) -> dict:
    accepted, rejected = _check_contacts(body.contacts)
    if not accepted:
        raise AppValidationError("No contact has a usable phone number, so nothing was created.", errors=rejected)
    if len(body.contacts) > settings.REVENUEOS_MAX_CONTACTS:
        raise AppValidationError(
            f"At most {settings.REVENUEOS_MAX_CONTACTS} contacts per request; this one has {len(body.contacts)}.",
            errors=[],
        )
    digest = content_hash(body)

    client = await db.scalar(
        select(RevenueOSClient).where(RevenueOSClient.client_reference == body.client_reference)
    )
    receipt = await db.scalar(select(RevenueOSLaunch).where(RevenueOSLaunch.reference == body.reference))

    result: dict = {
        "reference": body.reference,
        "client_reference": body.client_reference,
        "duplicate": False,
    }

    # ── Repeat of a reference that already made a campaign ────────────────────
    if receipt is not None:
        if client is None or receipt.client_id != client.id:
            raise ConflictError(
                "This reference was already used under a different client_reference. "
                "Each campaign needs its own reference."
            )
        if receipt.content_hash != digest:
            raise ConflictError(
                "This reference already exists with different content (campaign, agent, schedule or "
                "contacts). Send the original content to repeat it, or a new reference for a new campaign."
            )
        user = await db.get(User, client.user_id)
        campaign = await db.get(Campaign, receipt.campaign_id)
        if campaign is None or campaign.deleted_at or user is None:
            raise ConflictError("The campaign for this reference was deleted. Use a new reference.")
        result.update(
            duplicate=True,
            account={"status": "reused", "organization_id": str(client.org_id), "login_email": user.email},
            contacts_rejected=receipt.contacts_rejected,
        )
        start = await _start(db, campaign, user, auto_start=body.auto_start)
        await db.refresh(campaign)
        result.update(campaign=_campaign_out(campaign), **start)
        return result

    # ── Account ───────────────────────────────────────────────────────────────
    if client is None:
        client, org, user = await _create_client(db, body)
        account_status = "created"
    else:
        org = await db.get(Organization, client.org_id)
        user = await db.get(User, client.user_id)
        if org is None or org.deleted_at or user is None or user.deleted_at:
            raise ConflictError("The account for this client_reference was deleted on the voice platform.")
        if user.email.lower() != body.user.email.lower():
            raise ConflictError(
                "This client_reference already belongs to an account with a different user.email. "
                "Send the original email, or a new client_reference for a new client."
            )
        account_status = "reused"
    result["account"] = {"status": account_status, "organization_id": str(org.id), "login_email": user.email}
    result["contacts_rejected"] = rejected
    result["campaign"] = None
    org_id = org.id

    # ── Company profile (Prime Calling) ───────────────────────────────────────
    if body.company_profile is not None:
        profile = await save_org_profile(db, org_id, body.company_profile)
        result["company_profile"] = {"status": "saved"}
    else:
        profile = await get_org_profile(db, org_id)
        result["company_profile"] = {"status": "unchanged" if profile else "missing"}
    if body.prime and (profile is None or not profile.is_complete):
        result.update(
            start_status="blocked",
            start_reason="Prime Calling needs a company_profile with at least company_name and what_we_offer.",
            next_action="Send the same request with a company_profile block (or with prime false).",
        )
        return result

    # ── Phone number ──────────────────────────────────────────────────────────
    trunk, number = await _resolve_number(db, org, body.phone_number)
    result["phone_number"] = number
    if trunk is None:
        result.update(
            start_status="blocked",
            start_reason=f"No usable phone number: {number['reason']}",
            next_action="The account is kept. Fix the phone number and send the same request again.",
        )
        return result
    trunk_id = trunk.id

    # ── Agent, campaign, contacts — one transaction ───────────────────────────
    dnc = await _dnc_phones(db, org_id, [p for p, _ in accepted])
    rejected = rejected + [{"phone": p, "reason": "on the do-not-call list"} for p, _ in accepted if p in dnc]
    keep = [(p, c) for p, c in accepted if p not in dnc]
    result["contacts_rejected"] = rejected
    if not keep:
        raise AppValidationError(
            "Every contact was refused, so no campaign was created (the account is kept).", errors=rejected
        )

    try:
        agent, agent_status = await _resolve_agent(db, org, user, body)
    except AppError as exc:
        await db.rollback()
        result.update(
            start_status="blocked",
            start_reason=f"The agent could not be created: {exc.message}",
            next_action="Change the agent's voice settings and send the request again.",
        )
        return result
    result["agent"] = {"status": agent_status, "id": str(agent.id), "name": agent.name}

    sched = body.schedule
    campaign = Campaign(
        org_id=org_id,
        created_by_id=user.id,
        name=body.campaign.name,
        description=body.campaign.description,
        notes=f"Created by RevenueOS. reference: {body.reference}",
        goal=body.campaign.goal,
        agent_template_id=agent.id,
        # Always the client's own number: never the platform-wide fallback number.
        sip_trunk_id=trunk_id,
        calling_window_start=sched.calling_window_start,
        calling_window_end=sched.calling_window_end,
        calling_days=sched.calling_days,
        timezone=sched.timezone,
        calls_per_minute=sched.calls_per_minute,
        is_prime=body.prime,
        total_contacts=len(keep),
    )
    db.add(campaign)
    await db.flush()
    for phone, c in keep:
        custom = dict(c.custom_fields)
        if c.website:
            custom["website"] = c.website
        db.add(CampaignContact(
            org_id=org_id,
            campaign_id=campaign.id,
            name=c.name.strip() or "Contact",
            phone=phone,
            email=c.email,
            company=c.company,
            custom_fields=custom,
            status=ContactStatus.PENDING,
        ))
    db.add(RevenueOSLaunch(
        org_id=org_id,
        reference=body.reference,
        client_id=client.id,
        campaign_id=campaign.id,
        content_hash=digest,
        contacts_rejected=rejected,
    ))
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError(
            "This reference was created by another request at the same moment. Send the same request again."
        ) from exc
    await db.refresh(campaign)

    # ── Start — after the commit, so a refused start never undoes the campaign ─
    start = await _start(db, campaign, user, auto_start=body.auto_start)
    await db.refresh(campaign)
    result.update(campaign=_campaign_out(campaign), **start)
    log.info(
        "revenueos_launch",
        reference=body.reference,
        client_reference=body.client_reference,
        account=account_status,
        start_status=start["start_status"],
        contacts=len(keep),
        rejected=len(rejected),
    )
    return result


# ── Read side ─────────────────────────────────────────────────────────────────

async def find_campaign(db: AsyncSession, *, client_reference: str, reference: str) -> tuple[RevenueOSClient, Campaign]:
    """
    The only way a RevenueOS route reaches a campaign. Both references must
    match a row this integration wrote; anything else is "not found", whether
    it does not exist or belongs to another client.
    """
    row = (await db.execute(
        select(RevenueOSClient, RevenueOSLaunch)
        .join(RevenueOSLaunch, RevenueOSLaunch.client_id == RevenueOSClient.id)
        .where(
            RevenueOSClient.client_reference == client_reference,
            RevenueOSLaunch.reference == reference,
        )
    )).first()
    if row is None:
        raise NotFoundError("No campaign with this reference for this client_reference.")
    client, receipt = row
    campaign = await db.get(Campaign, receipt.campaign_id)
    if campaign is None or campaign.org_id != client.org_id or campaign.deleted_at:
        raise NotFoundError("No campaign with this reference for this client_reference.")
    return client, campaign


async def campaign_status(db: AsyncSession, *, client_reference: str, reference: str) -> dict:
    _client, campaign = await find_campaign(db, client_reference=client_reference, reference=reference)

    contact_rows = (await db.execute(
        select(CampaignContact.status, func.count())
        .where(CampaignContact.campaign_id == campaign.id)
        .group_by(CampaignContact.status)
    )).all()
    contacts = {str(status): n for status, n in contact_rows}
    outcome_rows = (await db.execute(
        select(Call.outcome, func.count())
        .where(Call.campaign_id == campaign.id, Call.org_id == campaign.org_id)
        .group_by(Call.outcome)
    )).all()
    outcomes = {str(outcome): n for outcome, n in outcome_rows}
    still_to_call = sum(contacts.get(s, 0) for s in ("pending", "dialing", "queue_timeout"))

    return {
        "reference": reference,
        "client_reference": client_reference,
        "campaign": _campaign_out(campaign),
        "status": str(campaign.status),
        "in_calling_window_now": _in_calling_window(campaign),
        "calling_window": _window_text(campaign),
        "started_at": campaign.started_at,
        "completed_at": campaign.completed_at,
        "contacts_total": campaign.total_contacts,
        "contacts_still_to_call": still_to_call,
        "contacts_by_status": contacts,
        "calls_total": sum(outcomes.values()),
        "calls_by_outcome": outcomes,
    }


async def campaign_calls(
    db: AsyncSession,
    *,
    client_reference: str,
    reference: str,
    since: datetime | None,
    limit: int,
    include_transcript: bool,
) -> dict:
    _client, campaign = await find_campaign(db, client_reference=client_reference, reference=reference)

    q = (
        select(Call, CampaignContact, CallTranscript)
        .outerjoin(CampaignContact, Call.contact_id == CampaignContact.id)
        .outerjoin(CallTranscript, CallTranscript.call_id == Call.id)
        .where(Call.campaign_id == campaign.id, Call.org_id == campaign.org_id)
    )
    if since is not None:
        q = q.where(Call.updated_at > since)
    rows = (await db.execute(q.order_by(Call.updated_at, Call.id).limit(limit + 1))).all()
    has_more = len(rows) > limit
    rows = rows[:limit]

    items = []
    for call, contact, transcript in rows:
        item = {
            "call_id": str(call.id),
            "contact": {
                "name": contact.name if contact else None,
                "phone": call.phone_number,
                "email": contact.email if contact else None,
                "company": contact.company if contact else None,
                "custom_fields": (contact.custom_fields or {}) if contact else {},
            },
            "status": str(call.status),
            "outcome": str(call.outcome),
            "finished": call.ended_at is not None,
            "sentiment": str(call.sentiment) if call.sentiment else None,
            "summary": call.summary,
            "duration_seconds": call.duration_seconds,
            "started_at": call.started_at,
            "answered_at": call.answered_at,
            "ended_at": call.ended_at,
            "extracted_data": call.extracted_data or {},
            "error_message": call.error_message,
            "has_recording": bool(call.recording_url),
            # Prime Calling: False means this contact was called on the base script
            "script_personalised": bool(contact and contact.generated_system_prompt),
            "script_error": contact.prompt_error if contact else None,
            "updated_at": call.updated_at,
        }
        if include_transcript:
            item["transcript"] = [
                {"speaker": seg.get("speaker", ""), "text": seg.get("text", "")}
                for seg in (transcript.segments if transcript else [])
            ]
        items.append(item)

    return {
        "reference": reference,
        "client_reference": client_reference,
        "campaign_status": str(campaign.status),
        "items": items,
        "has_more": has_more,
        # Pass this back as `since` to get only calls that changed after this page.
        # Written with a trailing Z (not +00:00) so it survives a URL unescaped.
        "next_since": _utc_z(items[-1]["updated_at"] if items else since),
    }


async def pause(db: AsyncSession, *, client_reference: str, reference: str) -> dict:
    _client, campaign = await find_campaign(db, client_reference=client_reference, reference=reference)
    if campaign.status == CampaignStatus.RUNNING:
        campaign.status = CampaignStatus.PAUSED
        await db.commit()
        await db.refresh(campaign)
        paused, reason = True, "Paused. Calls already in progress finish; no new calls are placed."
    elif campaign.status == CampaignStatus.PAUSED:
        paused, reason = True, "Already paused."
    else:
        paused, reason = False, f"Only a running campaign can be paused; this one is '{campaign.status}'."
    return {
        "reference": reference,
        "client_reference": client_reference,
        "paused": paused,
        "status": str(campaign.status),
        "reason": reason,
        "next_action": "To resume, send the original launch request again with auto_start true."
        if paused else None,
    }
