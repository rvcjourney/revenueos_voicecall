"""
app/api/sip_trunks.py — Phone number (SIP trunk) management.

Admin endpoints  (require role=admin):
  GET    /api/sip-trunks                       — list all trunks in org
  POST   /api/sip-trunks                       — add a new trunk
  PUT    /api/sip-trunks/{trunk_id}            — update trunk details
  DELETE /api/sip-trunks/{trunk_id}            — soft-delete trunk
  POST   /api/sip-trunks/{trunk_id}/assign     — assign trunk to a user
  DELETE /api/sip-trunks/{trunk_id}/assign/{user_id} — remove assignment
  GET    /api/sip-trunks/{trunk_id}/assignments — list users assigned to trunk

User endpoint (any authenticated user):
  GET    /api/sip-trunks/my                    — list trunks assigned to me
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import TokenPayload, get_current_user, require_admin
from app.core.exceptions import ConflictError, NotFoundError, ValidationError as AppValidationError
from app.database import get_db
from app.models.sip import SipTrunk, SipTransport, UserSipTrunk
from app.models.user import User

router = APIRouter()


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class TrunkCreate(BaseModel):
    name: str
    livekit_trunk_id: str
    sip_domain: str
    sip_username: str
    sip_password: str
    caller_id: str          # E.164, e.g. "+918888888888"
    transport: str = "tcp"
    is_default: bool = False


class TrunkUpdate(BaseModel):
    name: str | None = None
    caller_id: str | None = None
    is_default: bool | None = None
    is_active: bool | None = None


class TrunkOut(BaseModel):
    id: str
    name: str
    livekit_trunk_id: str
    sip_domain: str
    sip_username: str
    caller_id: str
    transport: str
    is_default: bool
    is_active: bool
    created_at: datetime


class AssignBody(BaseModel):
    user_id: UUID


# ── Helpers ───────────────────────────────────────────────────────────────────

def _to_out(trunk: SipTrunk) -> TrunkOut:
    return TrunkOut(
        id=str(trunk.id),
        name=trunk.name,
        livekit_trunk_id=trunk.livekit_trunk_id,
        sip_domain=trunk.sip_domain,
        sip_username=trunk.sip_username,
        caller_id=trunk.caller_id,
        transport=str(trunk.transport),
        is_default=trunk.is_default,
        is_active=trunk.is_active,
        created_at=trunk.created_at,
    )


async def _get_trunk(db: AsyncSession, trunk_id: UUID, org_id: UUID) -> SipTrunk:
    trunk = await db.get(SipTrunk, trunk_id)
    if not trunk or trunk.org_id != org_id or trunk.deleted_at:
        raise NotFoundError("Phone number not found")
    return trunk


# ── Admin: list all trunks ────────────────────────────────────────────────────

@router.get("", response_model=list[TrunkOut])
async def list_trunks(
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(SipTrunk)
        .where(SipTrunk.org_id == token.org_id, SipTrunk.deleted_at.is_(None))
        .order_by(SipTrunk.created_at)
    )).scalars().all()
    return [_to_out(r) for r in rows]


# ── Admin: create trunk ───────────────────────────────────────────────────────

@router.post("", response_model=TrunkOut, status_code=201)
async def create_trunk(
    body: TrunkCreate,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if body.transport not in ("tcp", "udp", "tls"):
        raise AppValidationError("transport must be tcp, udp, or tls", errors=[])

    caller_id = body.caller_id.strip().replace(" ", "")
    if not caller_id.startswith("+"):
        caller_id = "+91" + caller_id.lstrip("0")

    # If this trunk is marked default, clear any existing default first
    if body.is_default:
        await db.execute(
            select(SipTrunk)
            .where(SipTrunk.org_id == token.org_id, SipTrunk.is_default.is_(True))
        )
        existing_defaults = (await db.execute(
            select(SipTrunk).where(
                SipTrunk.org_id == token.org_id,
                SipTrunk.is_default.is_(True),
                SipTrunk.deleted_at.is_(None),
            )
        )).scalars().all()
        for t in existing_defaults:
            t.is_default = False

    transport_enum = SipTransport(body.transport)
    trunk = SipTrunk(
        org_id=token.org_id,
        name=body.name.strip(),
        livekit_trunk_id=body.livekit_trunk_id.strip(),
        sip_domain=body.sip_domain.strip(),
        sip_username=body.sip_username.strip(),
        sip_password=body.sip_password,
        caller_id=caller_id,
        transport=transport_enum,
        is_default=body.is_default,
        is_active=True,
    )
    db.add(trunk)
    await db.commit()
    await db.refresh(trunk)
    return _to_out(trunk)


# ── Admin: update trunk ───────────────────────────────────────────────────────

@router.put("/{trunk_id}", response_model=TrunkOut)
async def update_trunk(
    trunk_id: UUID,
    body: TrunkUpdate,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    trunk = await _get_trunk(db, trunk_id, token.org_id)

    if body.name is not None:
        trunk.name = body.name.strip()

    if body.caller_id is not None:
        caller_id = body.caller_id.strip().replace(" ", "")
        if not caller_id.startswith("+"):
            caller_id = "+91" + caller_id.lstrip("0")
        trunk.caller_id = caller_id

    if body.is_active is not None:
        trunk.is_active = body.is_active

    if body.is_default is not None and body.is_default:
        # Clear existing org default before setting new one
        existing_defaults = (await db.execute(
            select(SipTrunk).where(
                SipTrunk.org_id == token.org_id,
                SipTrunk.is_default.is_(True),
                SipTrunk.deleted_at.is_(None),
            )
        )).scalars().all()
        for t in existing_defaults:
            t.is_default = False
        trunk.is_default = True
    elif body.is_default is not None:
        trunk.is_default = False

    await db.commit()
    await db.refresh(trunk)
    return _to_out(trunk)


# ── Admin: delete trunk ───────────────────────────────────────────────────────

@router.delete("/{trunk_id}", status_code=204)
async def delete_trunk(
    trunk_id: UUID,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    trunk = await _get_trunk(db, trunk_id, token.org_id)
    trunk.deleted_at = datetime.now(timezone.utc)
    trunk.is_default = False
    trunk.is_active = False
    await db.commit()


# ── Admin: assign trunk to user ───────────────────────────────────────────────

@router.post("/{trunk_id}/assign", status_code=201)
async def assign_trunk_to_user(
    trunk_id: UUID,
    body: AssignBody,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    trunk = await _get_trunk(db, trunk_id, token.org_id)

    # Verify target user exists in same org
    user = await db.get(User, body.user_id)
    if not user or user.org_id != token.org_id or user.deleted_at:
        raise NotFoundError("User not found")

    # Check not already assigned
    existing = await db.scalar(
        select(UserSipTrunk).where(
            UserSipTrunk.user_id == body.user_id,
            UserSipTrunk.trunk_id == trunk_id,
        )
    )
    if existing:
        raise ConflictError("This phone number is already assigned to that user")

    assignment = UserSipTrunk(
        user_id=body.user_id,
        trunk_id=trunk.id,
        assigned_by_id=token.user_id,
    )
    db.add(assignment)
    await db.commit()
    return {
        "message": f"Phone number '{trunk.name}' assigned to {user.full_name}",
        "trunk_id": str(trunk.id),
        "user_id": str(user.id),
    }


# ── Admin: remove trunk assignment ───────────────────────────────────────────

@router.delete("/{trunk_id}/assign/{user_id}", status_code=204)
async def remove_trunk_assignment(
    trunk_id: UUID,
    user_id: UUID,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    await _get_trunk(db, trunk_id, token.org_id)  # verify trunk belongs to org

    assignment = await db.scalar(
        select(UserSipTrunk).where(
            UserSipTrunk.trunk_id == trunk_id,
            UserSipTrunk.user_id == user_id,
        )
    )
    if not assignment:
        raise NotFoundError("Assignment not found")

    await db.delete(assignment)
    await db.commit()


# ── Admin: list users assigned to a trunk ────────────────────────────────────

@router.get("/{trunk_id}/assignments")
async def list_trunk_assignments(
    trunk_id: UUID,
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    await _get_trunk(db, trunk_id, token.org_id)

    rows = (await db.execute(
        select(UserSipTrunk, User)
        .join(User, UserSipTrunk.user_id == User.id)
        .where(UserSipTrunk.trunk_id == trunk_id)
        .order_by(UserSipTrunk.created_at)
    )).all()

    return [
        {
            "user_id": str(assignment.user_id),
            "full_name": user.full_name,
            "email": user.email,
            "assigned_at": assignment.created_at.isoformat(),
        }
        for assignment, user in rows
    ]


# ── Any user: live call-slot capacity per trunk ───────────────────────────────

@router.get("/capacity")
async def get_trunk_capacity(
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return how many of the 3 available call slots each trunk is currently using."""
    MAX_PER_TRUNK = 3

    if token.role == "admin":
        trunks = (await db.execute(
            select(SipTrunk).where(
                SipTrunk.org_id == token.org_id,
                SipTrunk.is_active.is_(True),
                SipTrunk.deleted_at.is_(None),
            )
        )).scalars().all()
    else:
        trunks = (await db.execute(
            select(SipTrunk)
            .join(UserSipTrunk, UserSipTrunk.trunk_id == SipTrunk.id)
            .where(
                UserSipTrunk.user_id == token.user_id,
                SipTrunk.is_active.is_(True),
                SipTrunk.deleted_at.is_(None),
            )
        )).scalars().all()

    try:
        from app.core.redis import get_redis
        r = await get_redis()
    except Exception:
        r = None

    result = []
    for trunk in trunks:
        active = 0
        if r:
            try:
                val = await r.get(f"motm:trunk:active:{trunk.livekit_trunk_id}")
                active = max(0, int(val or 0))
            except Exception:
                pass
        result.append({
            "trunk_id": str(trunk.id),
            "caller_id": trunk.caller_id,
            "active_calls": active,
            "max_concurrent": MAX_PER_TRUNK,
            "available_slots": max(0, MAX_PER_TRUNK - active),
        })
    return result


# ── Admin: initialize default trunk from env vars ────────────────────────────

@router.post("/init-default", response_model=TrunkOut, status_code=200)
async def init_default_trunk(
    token: TokenPayload = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Seed all configured SIP trunks for this org. Idempotent — skips existing ones."""
    trunks_cfg = [
        (settings.DEFAULT_SIP_TRUNK_ID, settings.DEFAULT_SIP_CALLER_ID, "Vobiz SIP Trunk", True),
    ]
    if settings.DEFAULT_SIP_TRUNK_ID_2 and settings.DEFAULT_SIP_CALLER_ID_2:
        trunks_cfg.append(
            (settings.DEFAULT_SIP_TRUNK_ID_2, settings.DEFAULT_SIP_CALLER_ID_2, "Vobiz SIP Trunk 2", False)
        )

    first_trunk = None
    for livekit_id, caller_id, name, is_default in trunks_cfg:
        existing = await db.scalar(
            select(SipTrunk).where(
                SipTrunk.org_id == token.org_id,
                SipTrunk.livekit_trunk_id == livekit_id,
                SipTrunk.deleted_at.is_(None),
            )
        )
        if existing:
            if first_trunk is None:
                first_trunk = existing
            continue

        trunk = SipTrunk(
            org_id=token.org_id,
            name=name,
            livekit_trunk_id=livekit_id,
            sip_domain=settings.VOBIZ_SIP_DOMAIN,
            sip_username=settings.VOBIZ_USERNAME,
            sip_password=settings.VOBIZ_PASSWORD,
            caller_id=caller_id,
            transport=SipTransport.TCP,
            is_default=is_default,
            is_active=True,
        )
        db.add(trunk)
        await db.flush()
        if first_trunk is None:
            first_trunk = trunk

    await db.commit()
    if first_trunk:
        await db.refresh(first_trunk)
    return _to_out(first_trunk)


# ── User: list my assigned trunks ─────────────────────────────────────────────

@router.get("/my", response_model=list[TrunkOut])
async def list_my_trunks(
    token: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the phone numbers (SIP trunks) assigned to the current user by admin."""
    # Admins see all active trunks in the org
    if token.role == "admin":
        rows = (await db.execute(
            select(SipTrunk).where(
                SipTrunk.org_id == token.org_id,
                SipTrunk.is_active.is_(True),
                SipTrunk.deleted_at.is_(None),
            ).order_by(SipTrunk.is_default.desc(), SipTrunk.created_at)
        )).scalars().all()
        return [_to_out(r) for r in rows]

    rows = (await db.execute(
        select(SipTrunk)
        .join(UserSipTrunk, UserSipTrunk.trunk_id == SipTrunk.id)
        .where(
            UserSipTrunk.user_id == token.user_id,
            SipTrunk.is_active.is_(True),
            SipTrunk.deleted_at.is_(None),
        )
        .order_by(SipTrunk.is_default.desc(), SipTrunk.created_at)
    )).scalars().all()
    return [_to_out(r) for r in rows]
