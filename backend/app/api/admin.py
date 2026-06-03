"""
app/api/admin.py — Admin-only endpoints.

All routes require role=admin.  Admins manage users within their own org.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import TokenPayload, require_admin
from app.core.exceptions import ConflictError, NotFoundError, ValidationError as AppValidationError
from app.core.security import hash_password
from app.database import get_db
from app.models.agent import AgentTemplate
from app.models.agent_access import AgentAccessRequest
from app.models.user import Organization, User, UserRole
from app.schemas.agent import AgentAccessRequestOut
from app.schemas.auth import AdminCreateUserRequest, AdminUpdateUserRequest, AdminUserOut

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
