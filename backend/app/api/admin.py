"""
app/api/admin.py — Admin-only endpoints.

All routes require role=admin.  Admins manage users within their own org.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pydantic import BaseModel

from app.config import settings
from app.core.deps import TokenPayload, require_admin
from app.core.exceptions import ConflictError, NotFoundError, ValidationError as AppValidationError
from app.core.security import hash_password
from app.database import get_db
from app.models.agent import AgentTemplate
from app.models.agent_access import AgentAccessRequest
from app.models.agent_creation_request import AgentCreationRequest
from app.models.campaign import Campaign, CampaignStatus
from app.models.dnc import DoNotCallEntry, DNCReason
from app.models.user import Organization, User, UserRole
from app.schemas.agent import AgentAccessRequestOut, AgentCreationRequestAdminOut
from app.schemas.auth import AdminCreateUserRequest, AdminUpdateUserRequest, AdminUserOut
from app.storage.backend import get_storage

router = APIRouter()


def _to_user_out(u: User) -> AdminUserOut:
    return AdminUserOut(
        id=str(u.id),
        email=u.email,
        full_name=u.full_name,
        role=u.role,
        is_active=u.is_active,
        last_login_at=u.last_login_at.isoformat() if u.last_login_at else None,
        created_at=u.created_at.isoformat(),
    )


@router.get("/org")
async def get_org_info(
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Return org info including the 8-char invite code for member self-registration."""
    org = await db.get(Organization, token.org_id)
    if not org:
        raise NotFoundError("Organization not found")
    org_id_hex = str(org.id).replace("-", "")
    return {
        "id": str(org.id),
        "name": org.name,
        "plan_tier": org.plan_tier,
        "monthly_call_quota": org.monthly_call_quota,
        "calls_used_this_period": org.calls_used_this_period,
        "invite_code": org_id_hex[:8].upper(),  # share this with team members
    }


@router.get("/stats")
async def get_org_stats(
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Return org-wide totals and per-user performance breakdown."""
    users = (await db.execute(
        select(User)
        .where(User.org_id == token.org_id, User.deleted_at.is_(None))
        .order_by(User.created_at)
    )).scalars().all()

    org_totals = dict(total_members=0, total_campaigns=0, total_calls=0,
                      total_interested=0, active_campaigns=0)
    user_stats = []

    for user in users:
        campaigns = (await db.execute(
            select(Campaign).where(
                Campaign.created_by_id == user.id,
                Campaign.deleted_at.is_(None),
            )
        )).scalars().all()

        u_campaigns  = len(campaigns)
        u_active     = sum(1 for c in campaigns if c.status == CampaignStatus.RUNNING)
        u_calls      = sum(c.completed_calls  for c in campaigns)
        u_interested = sum(c.interested_count for c in campaigns)

        if user.role == "member":
            org_totals["total_members"] += 1
        org_totals["total_campaigns"]  += u_campaigns
        org_totals["total_calls"]      += u_calls
        org_totals["total_interested"] += u_interested
        org_totals["active_campaigns"] += u_active

        user_stats.append({
            "user_id":         str(user.id),
            "full_name":       user.full_name,
            "email":           user.email,
            "role":            user.role,
            "is_active":       user.is_active,
            "total_campaigns": u_campaigns,
            "active_campaigns": u_active,
            "total_calls":     u_calls,
            "total_interested": u_interested,
            "last_login_at":   user.last_login_at.isoformat() if user.last_login_at else None,
        })

    return {"totals": org_totals, "users": user_stats}


@router.get("/users", response_model=list[AdminUserOut])
async def list_users(
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(User)
        .where(User.org_id == token.org_id, User.deleted_at.is_(None))
        .order_by(User.created_at)
    )).scalars().all()
    return [_to_user_out(u) for u in rows]


@router.post("/users", response_model=AdminUserOut, status_code=201)
async def create_user(
    body: AdminCreateUserRequest,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin creates a team member account directly (no email invite needed)."""
    if body.role not in ("admin", "member"):
        raise AppValidationError("Role must be 'admin' or 'member'", errors=[])

    existing = await db.scalar(select(User.id).where(User.email == body.email))
    if existing:
        raise ConflictError("Email already registered")

    if len(body.password) < 6:
        raise AppValidationError("Password must be at least 6 characters", errors=[])

    user = User(
        org_id=token.org_id,
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        role=UserRole.ADMIN if body.role == "admin" else UserRole.MEMBER,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return _to_user_out(user)


@router.patch("/users/{user_id}", response_model=AdminUserOut)
async def update_user(
    user_id: UUID,
    body: AdminUpdateUserRequest,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user or user.org_id != token.org_id or user.deleted_at:
        raise NotFoundError("User not found")

    # Prevent admin from removing their own admin role
    if str(user.id) == str(token.user_id) and body.role and body.role != "admin":
        raise AppValidationError("Cannot change your own role", errors=[])

    if body.full_name is not None:
        user.full_name = body.full_name.strip()

    if body.role is not None:
        if body.role not in ("admin", "member"):
            raise AppValidationError("Role must be 'admin' or 'member'", errors=[])
        user.role = UserRole.ADMIN if body.role == "admin" else UserRole.MEMBER

    if body.is_active is not None:
        user.is_active = body.is_active

    await db.commit()
    await db.refresh(user)
    return _to_user_out(user)


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: UUID,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user or user.org_id != token.org_id or user.deleted_at:
        raise NotFoundError("User not found")
    if str(user.id) == str(token.user_id):
        raise AppValidationError("Cannot delete your own account", errors=[])

    user.deleted_at = datetime.now(timezone.utc)
    await db.commit()


# ── Agent access request management ──────────────────────────────────────────

@router.get("/agent-requests", response_model=list[AgentAccessRequestOut])
async def list_agent_requests(
    status: str | None = None,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all agent access requests for this org (default: pending only)."""
    q = select(AgentAccessRequest).where(AgentAccessRequest.org_id == token.org_id)
    if status:
        q = q.where(AgentAccessRequest.status == status)
    else:
        q = q.where(AgentAccessRequest.status == "pending")
    rows = (await db.execute(q.order_by(AgentAccessRequest.created_at))).scalars().all()

    result = []
    for r in rows:
        agent = await db.get(AgentTemplate, r.agent_id)
        user = await db.get(User, r.user_id)
        result.append(AgentAccessRequestOut(
            id=str(r.id),
            agent_id=str(r.agent_id),
            agent_name=agent.name if agent else "Unknown",
            user_id=str(r.user_id),
            user_name=user.full_name if user else "Unknown",
            user_email=user.email if user else "",
            status=r.status,
            created_at=r.created_at,
        ))
    return result


@router.post("/agent-requests/{request_id}/approve", status_code=200)
async def approve_agent_request(
    request_id: UUID,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    req = await db.get(AgentAccessRequest, request_id)
    if not req or req.org_id != token.org_id:
        raise NotFoundError("Access request not found")
    req.status = "approved"
    await db.commit()
    return {"message": "Access approved"}


@router.post("/agent-requests/{request_id}/reject", status_code=200)
async def reject_agent_request(
    request_id: UUID,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    req = await db.get(AgentAccessRequest, request_id)
    if not req or req.org_id != token.org_id:
        raise NotFoundError("Access request not found")
    req.status = "rejected"
    await db.commit()
    return {"message": "Access rejected"}


@router.get("/agent-access")
async def list_approved_access(
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all currently approved agent accesses in this org."""
    rows = (await db.execute(
        select(AgentAccessRequest)
        .where(
            AgentAccessRequest.org_id == token.org_id,
            AgentAccessRequest.status == "approved",
        )
        .order_by(AgentAccessRequest.updated_at.desc())
    )).scalars().all()

    result = []
    for r in rows:
        agent = await db.get(AgentTemplate, r.agent_id)
        user = await db.get(User, r.user_id)
        last_camp = await db.scalar(
            select(Campaign)
            .where(
                Campaign.created_by_id == r.user_id,
                Campaign.agent_template_id == r.agent_id,
                Campaign.deleted_at.is_(None),
            )
            .order_by(Campaign.created_at.desc())
            .limit(1)
        )
        result.append({
            "request_id": str(r.id),
            "user_id": str(r.user_id),
            "user_name": user.full_name if user else "Unknown",
            "user_email": user.email if user else "",
            "agent_id": str(r.agent_id),
            "agent_name": agent.name if agent else "Deleted Agent",
            "granted_at": r.updated_at.isoformat(),
            "last_campaign_name": last_camp.name if last_camp else None,
            "last_used_at": last_camp.created_at.isoformat() if last_camp else None,
            "can_edit": r.can_edit,
        })
    return result


@router.post("/agent-requests/{request_id}/revoke", status_code=200)
async def revoke_agent_access(
    request_id: UUID,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a previously approved agent access."""
    req = await db.get(AgentAccessRequest, request_id)
    if not req or req.org_id != token.org_id:
        raise NotFoundError("Access request not found")
    if req.status != "approved":
        raise AppValidationError("Can only revoke approved access", errors=[])
    req.status = "rejected"
    await db.commit()
    return {"message": "Access revoked"}


class EditPermissionBody(BaseModel):
    can_edit: bool


@router.patch("/agent-access/{request_id}/edit-permission", status_code=200)
async def set_agent_edit_permission(
    request_id: UUID,
    body: EditPermissionBody,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Grant or revoke edit rights for a user on an approved agent access."""
    req = await db.get(AgentAccessRequest, request_id)
    if not req or req.org_id != token.org_id:
        raise NotFoundError("Access request not found")
    if req.status != "approved":
        raise AppValidationError("Can only set edit permission on approved access", errors=[])
    req.can_edit = body.can_edit
    await db.commit()
    action = "granted" if body.can_edit else "revoked"
    return {"message": f"Edit permission {action}"}


@router.get("/activity")
async def get_activity(
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Recent activity feed: campaign lifecycle events + agent access events for this org."""
    activities = []

    # Campaign events: created, launched, completed
    campaign_rows = (await db.execute(
        select(Campaign, User)
        .join(User, Campaign.created_by_id == User.id)
        .where(
            Campaign.org_id == token.org_id,
            Campaign.deleted_at.is_(None),
        )
        .order_by(Campaign.created_at.desc())
        .limit(30)
    )).all()

    for campaign, creator in campaign_rows:
        agent = await db.get(AgentTemplate, campaign.agent_template_id)
        agent_name = agent.name if agent else "Unknown"

        activities.append({
            "type": "campaign_created",
            "user_name": creator.full_name,
            "user_email": creator.email,
            "detail": campaign.name,
            "agent_name": agent_name,
            "campaign_status": str(campaign.status),
            "timestamp": campaign.created_at.isoformat(),
        })
        if campaign.started_at:
            activities.append({
                "type": "campaign_launched",
                "user_name": creator.full_name,
                "user_email": creator.email,
                "detail": campaign.name,
                "agent_name": agent_name,
                "campaign_status": str(campaign.status),
                "timestamp": campaign.started_at.isoformat(),
            })
        if campaign.completed_at:
            activities.append({
                "type": "campaign_completed",
                "user_name": creator.full_name,
                "user_email": creator.email,
                "detail": campaign.name,
                "agent_name": agent_name,
                "campaign_status": str(campaign.status),
                "timestamp": campaign.completed_at.isoformat(),
            })

    # Agent access events
    access_rows = (await db.execute(
        select(AgentAccessRequest, User, AgentTemplate)
        .join(User, AgentAccessRequest.user_id == User.id)
        .join(AgentTemplate, AgentAccessRequest.agent_id == AgentTemplate.id)
        .where(AgentAccessRequest.org_id == token.org_id)
        .order_by(AgentAccessRequest.updated_at.desc())
        .limit(20)
    )).all()

    for req, user, agent in access_rows:
        activities.append({
            "type": f"agent_access_{req.status}",
            "user_name": user.full_name,
            "user_email": user.email,
            "detail": agent.name,
            "agent_name": agent.name,
            "campaign_status": None,
            "timestamp": req.updated_at.isoformat(),
        })

    activities.sort(key=lambda x: x["timestamp"], reverse=True)
    return activities[:60]


# ── DNC list management ───────────────────────────────────────────────────────

class DNCAddBody(BaseModel):
    phone_number: str
    notes: str | None = None


@router.get("/dnc")
async def list_dnc(
    q: str | None = Query(None),
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all org-level DNC entries (up to 200)."""
    query = select(DoNotCallEntry).where(DoNotCallEntry.org_id == token.org_id)
    if q:
        query = query.where(DoNotCallEntry.phone_number.contains(q))
    rows = (await db.execute(
        query.order_by(DoNotCallEntry.created_at.desc()).limit(200)
    )).scalars().all()
    return [
        {
            "id": str(r.id),
            "phone_number": r.phone_number,
            "reason": str(r.reason),
            "notes": r.notes,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.post("/dnc", status_code=201)
async def add_dnc(
    body: DNCAddBody,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Manually add a phone number to the org DNC list."""
    phone = body.phone_number.strip().replace(" ", "").replace("-", "")
    if not phone.startswith("+"):
        phone = "+91" + phone.lstrip("0")

    existing = await db.scalar(
        select(DoNotCallEntry.id).where(
            DoNotCallEntry.org_id == token.org_id,
            DoNotCallEntry.phone_number == phone,
        )
    )
    if existing:
        raise ConflictError("Number already in DNC list")

    entry = DoNotCallEntry(
        org_id=token.org_id,
        phone_number=phone,
        reason=DNCReason.MANUAL_BLOCK,
        added_by_user_id=token.user_id,
        notes=body.notes,
    )
    db.add(entry)
    await db.commit()
    return {"message": "Added to DNC list", "phone_number": phone}


@router.delete("/dnc/{entry_id}", status_code=204)
async def remove_dnc(
    entry_id: UUID,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Remove a number from the org DNC list."""
    entry = await db.get(DoNotCallEntry, entry_id)
    if not entry or entry.org_id != token.org_id:
        raise NotFoundError("DNC entry not found")
    await db.delete(entry)
    await db.commit()


# ── Agent creation request management ────────────────────────────────────────

class ReviewCreationRequestBody(BaseModel):
    admin_notes: str | None = None


@router.get("/agent-creation-requests", response_model=list[AgentCreationRequestAdminOut])
async def list_agent_creation_requests(
    status: str | None = None,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    q = select(AgentCreationRequest).where(AgentCreationRequest.org_id == token.org_id)
    if status:
        q = q.where(AgentCreationRequest.status == status)
    else:
        q = q.where(AgentCreationRequest.status == "pending")
    rows = (await db.execute(q.order_by(AgentCreationRequest.created_at))).scalars().all()

    result = []
    for r in rows:
        user = await db.get(User, r.user_id)

        # Not a presigned MinIO URL: MinIO is internal-only (see docker-compose.yml),
        # unreachable directly from a browser. This is this router's own proxy
        # endpoint below, authenticated the same way as every other admin request.
        file_url = f"/api/admin/agent-creation-requests/{r.id}/file" if r.file_key else None

        result.append(AgentCreationRequestAdminOut(
            id=str(r.id),
            agent_name=r.agent_name,
            company_name=r.company_name,
            status=r.status,
            admin_notes=r.admin_notes,
            has_file=bool(r.file_key),
            file_name=r.file_name,
            file_url=file_url,
            created_at=r.created_at,
            user_id=str(r.user_id),
            user_name=user.full_name if user else "Unknown",
            user_email=user.email if user else "",
            product_service=r.product_service,
            target_customers=r.target_customers,
            key_points=r.key_points,
        ))
    return result


@router.get("/agent-creation-requests/{request_id}/file")
async def download_agent_creation_request_file(
    request_id: UUID,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    req = await db.get(AgentCreationRequest, request_id)
    if not req or req.org_id != token.org_id or not req.file_key:
        raise NotFoundError("File not found")
    data = await get_storage().download(settings.BUCKET_EXPORTS, req.file_key)
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{req.file_name or "attachment"}"'},
    )


@router.patch("/agent-creation-requests/{request_id}/review", status_code=200)
async def review_agent_creation_request(
    request_id: UUID,
    body: ReviewCreationRequestBody,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Mark a creation request as reviewed (after creating the agent)."""
    req = await db.get(AgentCreationRequest, request_id)
    if not req or req.org_id != token.org_id:
        raise NotFoundError("Request not found")
    req.status = "reviewed"
    if body.admin_notes:
        req.admin_notes = body.admin_notes
    await db.commit()
    return {"message": "Marked as reviewed"}
